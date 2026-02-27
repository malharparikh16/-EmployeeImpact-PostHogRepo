"""
fetch_prs.py

Efficiently fetches all PRs (and reviews) from a GitHub repo via GraphQL.
Resilient against 502/503/timeout errors with:
  - Exponential backoff + jitter on transient failures
  - Checkpoint file so a crashed run resumes from the last successful page
  - Incremental save — data already fetched is never lost

Usage:
    export GITHUB_TOKEN=your_personal_access_token
    python fetch_prs.py
    python fetch_prs.py --owner PostHog --repo posthog --days 90

Re-running after a crash resumes automatically from the last checkpoint.
Pass --reset to ignore any existing checkpoint and start fresh.
"""

import os
import json
import time
import random
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
PRS_PATH = DATA_DIR / "prs.json"
META_PATH = DATA_DIR / "meta.json"
CHECKPOINT_PATH = DATA_DIR / ".checkpoint.json"

# Retry config
MAX_RETRIES = 7
BASE_BACKOFF = 2.0    # seconds, doubles each attempt
MAX_BACKOFF = 120.0   # cap at 2 minutes

# Save progress to disk every N pages (100 PRs/page)
SAVE_EVERY_N_PAGES = 5

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------
PR_QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(
      first: 100
      after: $cursor
      orderBy: {field: UPDATED_AT, direction: DESC}
      states: [OPEN, CLOSED, MERGED]
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        state
        isDraft
        createdAt
        updatedAt
        mergedAt
        closedAt
        additions
        deletions
        changedFiles
        url
        author {
          login
          ... on User {
            name
            avatarUrl
          }
        }
        mergedBy {
          login
        }
        labels(first: 10) {
          nodes { name color }
        }
        reviews(first: 30) {
          nodes {
            author { login }
            state
            submittedAt
            body
          }
        }
        reviewRequests(first: 10) {
          nodes {
            requestedReviewer {
              ... on User { login }
              ... on Team { name }
            }
          }
        }
        comments {
          totalCount
        }
        commits {
          totalCount
        }
      }
    }
  }
  rateLimit {
    remaining
    resetAt
    cost
  }
}
"""

# ---------------------------------------------------------------------------
# HTTP layer — retries with exponential backoff + jitter
# ---------------------------------------------------------------------------

# Transient status codes worth retrying
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _backoff(attempt: int, resp=None, base: float = BASE_BACKOFF) -> float:
    """
    Full-jitter exponential backoff.
    Respects Retry-After header when present.
    """
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after) + 1
            except ValueError:
                pass

    cap = min(MAX_BACKOFF, base * (2 ** attempt))
    return random.uniform(0, cap)  # full jitter avoids thundering herd


def graphql_request(token: str, query: str, variables: dict) -> dict:
    """
    Send a GitHub GraphQL request.

    Retries automatically on:
      - Network errors (Timeout, ConnectionError)
      - Transient HTTP errors (502, 503, 504, 429, 500)
      - GitHub secondary rate limits
      - GitHub point-based rate limit exhaustion (sleeps until reset)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = "https://api.github.com/graphql"
    attempt = 0

    while True:
        try:
            resp = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=60,  # generous — GraphQL can be slow on large repos
            )

            # ---- transient HTTP errors ----
            if resp.status_code in RETRYABLE_STATUSES:
                attempt += 1
                if attempt > MAX_RETRIES:
                    resp.raise_for_status()
                wait = _backoff(attempt, resp)
                log.warning(
                    "HTTP %d on attempt %d/%d — retrying in %.0fs …",
                    resp.status_code, attempt, MAX_RETRIES, wait,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            # ---- GraphQL-level errors ----
            if "errors" in data:
                err_msgs = [e.get("message", "") for e in data["errors"]]
                if any("secondary rate limit" in m.lower() for m in err_msgs):
                    attempt += 1
                    wait = _backoff(attempt, base=30)
                    log.warning(
                        "Secondary rate limit hit — sleeping %.0fs (attempt %d/%d) …",
                        wait, attempt, MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"GraphQL errors: {data['errors']}")

            # ---- GitHub point-based rate limit ----
            rate = data.get("data", {}).get("rateLimit", {})
            remaining = rate.get("remaining", 9999)
            reset_at = rate.get("resetAt")
            log.debug("Rate limit: %d remaining (cost=%s)", remaining, rate.get("cost"))

            if remaining < 5 and reset_at:
                reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
                wait = max(0, (reset_dt - datetime.now(timezone.utc)).total_seconds()) + 3
                log.warning(
                    "Rate limit nearly exhausted (%d left). Sleeping %.0fs until reset …",
                    remaining, wait,
                )
                time.sleep(wait)
                continue  # retry same request

            attempt = 0  # reset counter on clean success
            return data

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,  # "Response ended prematurely"
        ) as exc:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            wait = _backoff(attempt)
            log.warning(
                "%s (attempt %d/%d) — retrying in %.0fs …",
                type(exc).__name__, attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_checkpoint(cursor: str | None, page: int) -> None:
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(
            {
                "cursor": cursor,
                "page": page,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            },
            f,
        )


def clear_checkpoint() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


# ---------------------------------------------------------------------------
# Incremental save helpers
# ---------------------------------------------------------------------------

def load_existing_prs() -> list[dict]:
    """Return PRs already on disk from a previous partial run."""
    if PRS_PATH.exists():
        try:
            with open(PRS_PATH) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def flush_prs(prs: list[dict]) -> None:
    """
    Overwrite prs.json with the current full list.

    Uses a temp file in the system temp dir (outside OneDrive) to avoid
    Windows/OneDrive locking the file mid-sync and blocking the rename.
    Falls back to a direct write if the cross-drive move also fails.
    """
    import tempfile
    import shutil

    # Write to system temp dir — outside any OneDrive-watched folder
    fd, tmp_path_str = tempfile.mkstemp(suffix=".json", prefix="prs_tmp_")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(prs, f, indent=2, default=str)

        # Try atomic move first
        try:
            shutil.move(str(tmp_path), str(PRS_PATH))
        except (PermissionError, OSError):
            # OneDrive or antivirus has prs.json locked — write directly
            log.warning(
                "Could not atomically replace prs.json (file locked by OneDrive/AV). "
                "Writing directly ..."
            )
            tmp_path.unlink(missing_ok=True)
            with open(PRS_PATH, "w") as f:
                json.dump(prs, f, indent=2, default=str)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Normalise raw GraphQL node → clean dict
# ---------------------------------------------------------------------------

def normalize_pr(pr: dict) -> dict:
    author_node = pr.get("author") or {}
    author = author_node.get("login", "ghost")

    reviews = [
        {
            "reviewer": (r.get("author") or {}).get("login", "ghost"),
            "state": r["state"],
            "submitted_at": r["submittedAt"],
            "has_body": bool(r.get("body", "").strip()),
        }
        for r in pr.get("reviews", {}).get("nodes", [])
    ]

    labels = [
        {"name": l["name"], "color": l.get("color", "cccccc")}
        for l in pr.get("labels", {}).get("nodes", [])
    ]

    return {
        "number": pr["number"],
        "title": pr["title"],
        "state": pr["state"],
        "is_draft": pr["isDraft"],
        "author": author,
        "author_name": author_node.get("name") or author,
        "author_avatar": author_node.get("avatarUrl", ""),
        "merged_by": (pr.get("mergedBy") or {}).get("login"),
        "created_at": pr["createdAt"],
        "updated_at": pr["updatedAt"],
        "merged_at": pr["mergedAt"],
        "closed_at": pr["closedAt"],
        "additions": pr["additions"],
        "deletions": pr["deletions"],
        "changed_files": pr["changedFiles"],
        "total_commits": pr["commits"]["totalCount"],
        "total_comments": pr["comments"]["totalCount"],
        "labels": labels,
        "url": pr["url"],
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# Core fetch loop — yields normalized PRs, saves checkpoints
# ---------------------------------------------------------------------------

def fetch_prs(
    token: str,
    owner: str,
    repo: str,
    since: datetime,
    resume_cursor: str | None = None,
    resume_page: int = 0,
) -> Iterator[dict]:
    """
    Yield normalized PR dicts updated after `since`.
    Writes a checkpoint after every page so a crash can be resumed.
    """
    cursor = resume_cursor
    page = resume_page

    while True:
        page += 1
        log.info("Fetching page %d (cursor=%.50s) …", page, cursor or "start")

        data = graphql_request(
            token, PR_QUERY, {"owner": owner, "repo": repo, "cursor": cursor}
        )
        pr_data = data["data"]["repository"]["pullRequests"]
        nodes = pr_data["nodes"]
        page_info = pr_data["pageInfo"]

        if not nodes:
            break

        stop = False
        for pr in nodes:
            updated = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
            if updated < since:
                stop = True
                break
            yield normalize_pr(pr)

        cursor = page_info["endCursor"]

        # Checkpoint after every page (cheap write, guards against any crash)
        save_checkpoint(cursor, page)

        if stop or not page_info["hasNextPage"]:
            break


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch GitHub PRs and save raw data to data/"
    )
    parser.add_argument("--owner", default="PostHog")
    parser.add_argument("--repo", default="posthog")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Ignore any existing checkpoint and start fresh",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "Set the GITHUB_TOKEN environment variable to a GitHub personal access token."
        )

    DATA_DIR.mkdir(exist_ok=True)
    since = datetime.now(timezone.utc) - timedelta(days=args.days)

    # --- decide whether to resume or start fresh ---
    checkpoint = {} if args.reset else load_checkpoint()
    resume_cursor = checkpoint.get("cursor")
    resume_page = checkpoint.get("page", 0)

    if args.reset:
        clear_checkpoint()
        existing_prs: list[dict] = []
        log.info("--reset flag set: starting fresh.")
    elif resume_cursor:
        existing_prs = load_existing_prs()
        log.info(
            "Resuming from page %d with %d PRs already on disk …",
            resume_page, len(existing_prs),
        )
    else:
        existing_prs = []
        log.info(
            "Starting fresh fetch for %s/%s since %s …",
            args.owner, args.repo, since.date(),
        )

    all_prs: list[dict] = existing_prs.copy()
    new_count = 0

    try:
        for pr in fetch_prs(token, args.owner, args.repo, since, resume_cursor, resume_page):
            all_prs.append(pr)
            new_count += 1

            # Flush to disk every SAVE_EVERY_N_PAGES × 100 new PRs
            if new_count % (SAVE_EVERY_N_PAGES * 100) == 0:
                flush_prs(all_prs)
                log.info(
                    "  → incremental save: %d total PRs on disk (%d new this run)",
                    len(all_prs), new_count,
                )

    except Exception as exc:
        # Always save what we have before propagating the error
        if new_count > 0:
            flush_prs(all_prs)
            log.error(
                "Interrupted by error: %s\n"
                "Saved %d PRs (%d new this run). "
                "Re-run without --reset to continue from where we left off.",
                exc, len(all_prs), new_count,
            )
        else:
            log.error("Failed before fetching any new PRs: %s", exc)
        raise

    # --- success ---
    flush_prs(all_prs)
    clear_checkpoint()

    log.info(
        "Fetch complete. %d new PRs fetched. %d total on disk.",
        new_count, len(all_prs),
    )

    with open(META_PATH, "w") as f:
        json.dump(
            {
                "owner": args.owner,
                "repo": args.repo,
                "days": args.days,
                "since": since.isoformat(),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "total_prs": len(all_prs),
            },
            f,
            indent=2,
        )
    log.info("Metadata saved → %s", META_PATH)
    log.info("Done. Run `python analyze.py` next.")


if __name__ == "__main__":
    main()