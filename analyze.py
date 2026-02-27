"""
analyze.py

Reads raw PR data from data/prs.json and computes per-engineer impact metrics,
saving results to data/impact.json for the dashboard.

Key improvements over v1:
  - PR title parsed for conventional-commit type (feat/fix/perf/refactor/etc.)
    Each type carries a different impact multiplier
  - Review quality aware: reviews with substantive bodies score higher than
    empty state-change reviews (has_body signals real feedback)
  - Bot reviewers are excluded from reviewer scoring
  - Self-reviews (author commenting on their own PR) excluded
  - Approval on a PR that already has another approval is de-weighted
    (first approval is the critical unblocking event)
  - Review engagement: human comments with bodies on others' PRs scored
    separately from trivial automated comments

Usage:
    python analyze.py
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
PRS_PATH = DATA_DIR / "prs.json"
META_PATH = DATA_DIR / "meta.json"
IMPACT_PATH = DATA_DIR / "impact.json"


# ---------------------------------------------------------------------------
# Bot accounts — excluded from all reviewer scoring
# Add any bots your repo uses here.
# ---------------------------------------------------------------------------
BOT_LOGINS = {
    "greptile-apps",
    "graphite-app",
    "copilot-pull-request-reviewer",
    "chatgpt-codex-connector",
    "github-actions",
    "dependabot",
    "dependabot[bot]",
    "github-actions[bot]",
    "renovate",
    "renovate[bot]",
    "linear",
    "linear[bot]",
    "sentry-io",
    "codecov",
    "codecov[bot]",
    "snyk-bot",
    "sonarcloud",
    "vercel",
    "netlify",
}


# ---------------------------------------------------------------------------
# Conventional-commit PR type → impact multiplier on the base PR score
#
# Rationale:
#   fix / hotfix / revert  → directly resolves production issues, highest value
#   feat                   → ships user-facing value, high value
#   perf / security        → non-functional improvements, meaningful
#   refactor / test / ci   → internal health, moderate
#   chore / docs / style   → housekeeping, lower but still positive
#   (unknown)              → treat neutrally, weight 1.0
# ---------------------------------------------------------------------------
PR_TYPE_MULTIPLIERS: dict[str, float] = {
    "fix":      2.0,   # bug fixes — critical reliability work
    "hotfix":   2.5,   # emergency fixes — even more critical
    "revert":   1.8,   # reverts imply fixing a broken main — urgent
    "feat":     1.5,   # new features — primary product value
    "security": 2.0,   # security patches
    "perf":     1.4,   # performance improvements
    "refactor": 1.1,   # internal quality improvements
    "test":     1.0,   # test coverage — neutral
    "ci":       0.9,   # CI/CD changes
    "build":    0.9,
    "chore":    0.8,   # maintenance
    "docs":     0.7,   # documentation
    "style":    0.6,   # cosmetic only
    "wip":      0.5,   # work-in-progress, likely not production-ready
}

# Regex: matches  type(optional-scope): ...  or  Type/...  (case-insensitive)
# Examples:
#   feat(experiments): add new card
#   fix: crash on login
#   Feat/hogql cte using key
#   revert: "fix: monaco editor upgrade"
_TITLE_RE = re.compile(
    r"^(?P<type>[a-z]+)"       # type keyword
    r"(?:\([^)]*\))?"          # optional (scope)
    r"\s*[:/]",                # colon or slash separator
    re.IGNORECASE,
)


def parse_pr_type(title: str) -> str:
    """
    Extract the conventional-commit type from a PR title.
    Returns the lowercase type string, or 'unknown' if not matched.
    """
    m = _TITLE_RE.match(title.strip())
    if m:
        return m.group("type").lower()
    return "unknown"


def pr_type_multiplier(title: str) -> float:
    """Return the impact multiplier for a given PR title."""
    pt = parse_pr_type(title)
    return PR_TYPE_MULTIPLIERS.get(pt, 1.0)


# ---------------------------------------------------------------------------
# Base scoring weights
# These are multiplied by pr_type_multiplier for authored PRs.
# ---------------------------------------------------------------------------
WEIGHTS = {
    # --- authored ---
    "pr_merged":            10.0,  # base score per merged PR (× type multiplier)
    "pr_opened":             2.0,  # non-merged opened PR
    "lines_per_1k":          1.0,  # per 1000 net lines touched
    "files_changed":         0.5,  # per file changed (complexity proxy)

    # --- review quality: given to others' PRs ---
    # Approvals
    "first_approval":        8.0,  # first human approval unblocks the PR — high signal
    "subsequent_approval":   3.0,  # still positive but PR was already unblocked
    # Change requests
    "change_request_body":   7.0,  # substantive change request with written feedback
    "change_request_empty":  3.0,  # change request without body (less actionable)
    # Comments
    "comment_body":          3.0,  # substantive inline/review comment with body
    "comment_empty":         0.5,  # empty comment (e.g. automated reaction, +1)
    # Breadth bonus
    "unique_prs_reviewed":   2.0,  # per unique PR reviewed (encourages broad coverage)
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def days_to_merge(pr: dict) -> float | None:
    created = parse_dt(pr["created_at"])
    merged = parse_dt(pr["merged_at"])
    if created and merged:
        return (merged - created).total_seconds() / 86400
    return None


def is_bot(login: str) -> bool:
    return login.lower() in BOT_LOGINS or login.endswith("[bot]")


# ---------------------------------------------------------------------------
# Core impact computation
# ---------------------------------------------------------------------------

def compute_impact(prs: list[dict]) -> list[dict]:
    """
    Build per-engineer stats and a composite impact score from all PRs.
    """
    engineers: dict[str, dict] = {}

    def get(login: str) -> dict:
        if login not in engineers:
            engineers[login] = {
                "login": login,
                "author_name": login,
                "author_avatar": "",
                # authored
                "prs_opened": 0,
                "prs_merged": 0,
                "prs_closed_unmerged": 0,
                "prs_draft": 0,
                "total_additions": 0,
                "total_deletions": 0,
                "total_files_changed": 0,
                "total_commits": 0,
                "total_comments_received": 0,
                "merge_times_days": [],
                "labels_used": defaultdict(int),
                "weekly_prs": defaultdict(int),
                # PR type breakdown (authored)
                "pr_types": defaultdict(int),
                # review quality counters
                "first_approvals": 0,
                "subsequent_approvals": 0,
                "change_requests_with_body": 0,
                "change_requests_empty": 0,
                "comments_with_body": 0,
                "comments_empty": 0,
                "prs_reviewed_set": set(),
                # raw review total (for display)
                "reviews_given": 0,
            }
        return engineers[login]

    for pr in prs:
        author = pr["author"]
        if is_bot(author):
            continue  # skip bot-authored PRs entirely

        e = get(author)

        # Backfill display name / avatar
        if pr.get("author_name") and e["author_name"] == author:
            e["author_name"] = pr["author_name"]
        if pr.get("author_avatar") and not e["author_avatar"]:
            e["author_avatar"] = pr["author_avatar"]

        # PR counts
        e["prs_opened"] += 1
        if pr["is_draft"]:
            e["prs_draft"] += 1

        if pr["state"] == "MERGED":
            e["prs_merged"] += 1
            td = days_to_merge(pr)
            if td is not None:
                e["merge_times_days"].append(td)
        elif pr["state"] == "CLOSED":
            e["prs_closed_unmerged"] += 1

        # Code output
        e["total_additions"] += pr["additions"]
        e["total_deletions"] += pr["deletions"]
        e["total_files_changed"] += pr["changed_files"]
        e["total_commits"] += pr["total_commits"]
        e["total_comments_received"] += pr["total_comments"]

        # Labels
        for lbl in pr.get("labels", []):
            e["labels_used"][lbl["name"]] += 1

        # Weekly activity
        created = parse_dt(pr["created_at"])
        if created:
            week = created.strftime("%Y-W%W")
            e["weekly_prs"][week] += 1

        # PR type from title
        pt = parse_pr_type(pr["title"])
        e["pr_types"][pt] += 1

        # -----------------------------------------------------------------
        # Reviews — process each review on this PR
        # -----------------------------------------------------------------
        # Track how many human approvals this PR has received so far
        # to distinguish first vs subsequent approvals
        approval_count_on_pr = 0

        # Sort reviews by submitted_at so we process chronologically
        reviews_sorted = sorted(
            pr.get("reviews", []),
            key=lambda r: r.get("submitted_at") or "",
        )

        for review in reviews_sorted:
            reviewer = review["reviewer"]

            # Skip bots, skip self-review
            if is_bot(reviewer) or reviewer == author:
                continue

            r = get(reviewer)
            state = review["state"]
            has_body = review.get("has_body", False)

            r["reviews_given"] += 1
            r["prs_reviewed_set"].add(pr["number"])

            if state == "APPROVED":
                if approval_count_on_pr == 0:
                    r["first_approvals"] += 1
                else:
                    r["subsequent_approvals"] += 1
                approval_count_on_pr += 1

            elif state == "CHANGES_REQUESTED":
                if has_body:
                    r["change_requests_with_body"] += 1
                else:
                    r["change_requests_empty"] += 1

            elif state == "COMMENTED":
                if has_body:
                    r["comments_with_body"] += 1
                else:
                    r["comments_empty"] += 1

    # ---------------------------------------------------------------------------
    # Aggregate + score
    # ---------------------------------------------------------------------------
    results = []

    for e in engineers.values():
        net_lines = e["total_additions"] + e["total_deletions"]

        # Merge time stats
        mt = e["merge_times_days"]
        avg_merge_time = round(sum(mt) / len(mt), 1) if mt else None
        median_merge_time = round(sorted(mt)[len(mt) // 2], 1) if mt else None

        unique_prs_reviewed = len(e["prs_reviewed_set"])
        merge_rate = (
            round(e["prs_merged"] / e["prs_opened"] * 100, 1)
            if e["prs_opened"] > 0 else 0
        )

        # -----------------------------------------------------------------
        # Composite impact score — compute every component individually
        # so the dashboard can display an exact, auditable breakdown
        # -----------------------------------------------------------------

        # Per-PR-type authored scores (merged)
        merged_by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "pts": 0.0})
        opened_by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "pts": 0.0})
        for pr in prs:
            if pr["author"] != e["login"] or is_bot(pr["author"]):
                continue
            pt = parse_pr_type(pr["title"])
            mult = PR_TYPE_MULTIPLIERS.get(pt, 1.0)
            if pr["state"] == "MERGED":
                merged_by_type[pt]["count"] += 1
                merged_by_type[pt]["pts"] += round(WEIGHTS["pr_merged"] * mult, 4)
            else:
                opened_by_type[pt]["count"] += 1
                opened_by_type[pt]["pts"] += round(WEIGHTS["pr_opened"] * mult, 4)

        # Round every leaf component to 1dp first, then sum — this ensures
        # sum(score_components[].pts) == authored_score == impact_score exactly.
        authored_merged_pts  = round(sum(v["pts"] for v in merged_by_type.values()), 1)
        authored_opened_pts  = round(sum(v["pts"] for v in opened_by_type.values()), 1)
        lines_pts            = round((net_lines / 1000) * WEIGHTS["lines_per_1k"], 1)
        files_pts            = round(e["total_files_changed"] * WEIGHTS["files_changed"], 1)

        authored_score = round(authored_merged_pts + authored_opened_pts + lines_pts + files_pts, 1)

        # Review score — every component rounded at leaf level
        first_approval_pts      = round(e["first_approvals"]             * WEIGHTS["first_approval"],       1)
        subseq_approval_pts     = round(e["subsequent_approvals"]        * WEIGHTS["subsequent_approval"],  1)
        cr_body_pts             = round(e["change_requests_with_body"]   * WEIGHTS["change_request_body"],  1)
        cr_empty_pts            = round(e["change_requests_empty"]       * WEIGHTS["change_request_empty"], 1)
        comment_body_pts        = round(e["comments_with_body"]          * WEIGHTS["comment_body"],         1)
        comment_empty_pts       = round(e["comments_empty"]              * WEIGHTS["comment_empty"],        1)
        breadth_pts             = round(unique_prs_reviewed              * WEIGHTS["unique_prs_reviewed"],  1)

        review_score = round(
            first_approval_pts + subseq_approval_pts
            + cr_body_pts + cr_empty_pts
            + comment_body_pts + comment_empty_pts
            + breadth_pts, 1
        )

        # Total is exact sum of the two sub-totals — no re-rounding surprises
        total_score = round(authored_score + review_score, 1)

        # Exact breakdown list — every non-zero component, stored on the engineer
        # so the dashboard never needs to re-derive anything
        score_components = []
        for pt, data in sorted(merged_by_type.items(), key=lambda x: x[1]["pts"], reverse=True):
            if data["pts"] > 0:
                mult = PR_TYPE_MULTIPLIERS.get(pt, 1.0)
                score_components.append({
                    "label":  f"{pt} PRs merged",
                    "group":  "authored",
                    "count":  data["count"],
                    "weight": WEIGHTS["pr_merged"],
                    "mult":   mult,
                    "calc":   f"{data['count']} × {WEIGHTS['pr_merged']} × {mult}×",
                    "pts":    round(data["pts"], 1),
                    "color":  "authored",
                })
        for pt, data in sorted(opened_by_type.items(), key=lambda x: x[1]["pts"], reverse=True):
            if data["pts"] > 0:
                mult = PR_TYPE_MULTIPLIERS.get(pt, 1.0)
                score_components.append({
                    "label":  f"{pt} PRs opened (not merged)",
                    "group":  "authored",
                    "count":  data["count"],
                    "weight": WEIGHTS["pr_opened"],
                    "mult":   mult,
                    "calc":   f"{data['count']} × {WEIGHTS['pr_opened']} × {mult}×",
                    "pts":    round(data["pts"], 1),
                    "color":  "authored_dim",
                })
        if lines_pts > 0:
            score_components.append({
                "label":  "Code volume",
                "group":  "authored",
                "count":  net_lines,
                "weight": WEIGHTS["lines_per_1k"],
                "mult":   None,
                "calc":   f"{net_lines:,} lines ÷ 1000 × {WEIGHTS['lines_per_1k']}",
                "pts":    lines_pts,
                "color":  "authored_dim",
            })
        if files_pts > 0:
            score_components.append({
                "label":  "Files changed",
                "group":  "authored",
                "count":  e["total_files_changed"],
                "weight": WEIGHTS["files_changed"],
                "mult":   None,
                "calc":   f"{e['total_files_changed']} files × {WEIGHTS['files_changed']}",
                "pts":    files_pts,
                "color":  "authored_dim",
            })
        if first_approval_pts > 0:
            score_components.append({
                "label":  "First approvals given",
                "group":  "review",
                "count":  e["first_approvals"],
                "weight": WEIGHTS["first_approval"],
                "mult":   None,
                "calc":   f"{e['first_approvals']} × {WEIGHTS['first_approval']}pts",
                "pts":    first_approval_pts,
                "color":  "review",
                "tip":    "First approval unblocks a PR for merge — the highest-value review action.",
            })
        if subseq_approval_pts > 0:
            score_components.append({
                "label":  "Subsequent approvals",
                "group":  "review",
                "count":  e["subsequent_approvals"],
                "weight": WEIGHTS["subsequent_approval"],
                "mult":   None,
                "calc":   f"{e['subsequent_approvals']} × {WEIGHTS['subsequent_approval']}pts",
                "pts":    subseq_approval_pts,
                "color":  "review_dim",
                "tip":    "PR was already approved — still positive, but not the unblocking event.",
            })
        if cr_body_pts > 0:
            score_components.append({
                "label":  "Change requests (with feedback)",
                "group":  "review",
                "count":  e["change_requests_with_body"],
                "weight": WEIGHTS["change_request_body"],
                "mult":   None,
                "calc":   f"{e['change_requests_with_body']} × {WEIGHTS['change_request_body']}pts",
                "pts":    cr_body_pts,
                "color":  "review",
                "tip":    "Written change request — highest signal review, provides actionable guidance.",
            })
        if cr_empty_pts > 0:
            score_components.append({
                "label":  "Change requests (no body)",
                "group":  "review",
                "count":  e["change_requests_empty"],
                "weight": WEIGHTS["change_request_empty"],
                "mult":   None,
                "calc":   f"{e['change_requests_empty']} × {WEIGHTS['change_request_empty']}pts",
                "pts":    cr_empty_pts,
                "color":  "review_dim",
            })
        if comment_body_pts > 0:
            score_components.append({
                "label":  "Review comments (with body)",
                "group":  "review",
                "count":  e["comments_with_body"],
                "weight": WEIGHTS["comment_body"],
                "mult":   None,
                "calc":   f"{e['comments_with_body']} × {WEIGHTS['comment_body']}pts",
                "pts":    comment_body_pts,
                "color":  "review_dim",
                "tip":    "Substantive inline comment — shows engagement with the code.",
            })
        if comment_empty_pts > 0:
            score_components.append({
                "label":  "Review comments (empty)",
                "group":  "review",
                "count":  e["comments_empty"],
                "weight": WEIGHTS["comment_empty"],
                "mult":   None,
                "calc":   f"{e['comments_empty']} × {WEIGHTS['comment_empty']}pts",
                "pts":    comment_empty_pts,
                "color":  "review_dim",
            })
        if breadth_pts > 0:
            score_components.append({
                "label":  "Review breadth (unique PRs)",
                "group":  "review",
                "count":  unique_prs_reviewed,
                "weight": WEIGHTS["unique_prs_reviewed"],
                "mult":   None,
                "calc":   f"{unique_prs_reviewed} PRs × {WEIGHTS['unique_prs_reviewed']}pts",
                "pts":    breadth_pts,
                "color":  "review_dim",
                "tip":    "Bonus for reviewing many different PRs — encourages broad team coverage.",
            })

        # PR type breakdown for display
        pr_type_breakdown = [
            {"type": t, "count": c}
            for t, c in sorted(e["pr_types"].items(), key=lambda x: x[1], reverse=True)
        ]

        # Top labels
        top_labels = [
            {"name": n, "count": c}
            for n, c in sorted(e["labels_used"].items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        # Weekly sparkline
        weekly_activity = [
            {"week": w, "count": c}
            for w, c in sorted(e["weekly_prs"].items())
        ]

        results.append({
            "login": e["login"],
            "author_name": e["author_name"],
            "author_avatar": e["author_avatar"],
            # authored
            "prs_opened": e["prs_opened"],
            "prs_merged": e["prs_merged"],
            "prs_closed_unmerged": e["prs_closed_unmerged"],
            "prs_draft": e["prs_draft"],
            "merge_rate_pct": merge_rate,
            "total_additions": e["total_additions"],
            "total_deletions": e["total_deletions"],
            "net_lines": net_lines,
            "total_files_changed": e["total_files_changed"],
            "total_commits": e["total_commits"],
            "total_comments_received": e["total_comments_received"],
            "avg_merge_time_days": avg_merge_time,
            "median_merge_time_days": median_merge_time,
            "pr_type_breakdown": pr_type_breakdown,
            "top_labels": top_labels,
            "weekly_activity": weekly_activity,
            # reviewed (human only, no bots, no self-reviews)
            "reviews_given": e["reviews_given"],
            "first_approvals": e["first_approvals"],
            "subsequent_approvals": e["subsequent_approvals"],
            "change_requests_with_body": e["change_requests_with_body"],
            "change_requests_empty": e["change_requests_empty"],
            "comments_with_body": e["comments_with_body"],
            "comments_empty": e["comments_empty"],
            "unique_prs_reviewed": unique_prs_reviewed,
            # scores
            "authored_score": round(authored_score, 1),
            "review_score": round(review_score, 1),
            "impact_score": total_score,
            # exact per-component breakdown (used by dashboard)
            "score_components": score_components,
        })

    results.sort(key=lambda x: x["impact_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results


# ---------------------------------------------------------------------------
# Repo-wide stats
# ---------------------------------------------------------------------------

def compute_repo_stats(prs: list[dict], impact: list[dict]) -> dict:
    human_prs = [p for p in prs if not is_bot(p["author"])]
    merged = [p for p in human_prs if p["state"] == "MERGED"]
    open_prs = [p for p in human_prs if p["state"] == "OPEN"]

    merge_times = [
        (parse_dt(p["merged_at"]) - parse_dt(p["created_at"])).total_seconds() / 86400
        for p in merged if p["merged_at"] and p["created_at"]
    ]

    # PR type distribution across whole repo
    type_dist: dict[str, int] = defaultdict(int)
    for p in human_prs:
        type_dist[parse_pr_type(p["title"])] += 1
    type_distribution = [
        {"type": t, "count": c}
        for t, c in sorted(type_dist.items(), key=lambda x: x[1], reverse=True)
    ]

    # Weekly PR trend
    weekly: dict[str, int] = defaultdict(int)
    for p in human_prs:
        created = parse_dt(p["created_at"])
        if created:
            weekly[created.strftime("%Y-W%W")] += 1
    weekly_trend = [{"week": w, "count": c} for w, c in sorted(weekly.items())]

    top_by_merges = sorted(impact, key=lambda x: x["prs_merged"], reverse=True)[:5]
    top_by_reviews = sorted(impact, key=lambda x: x["reviews_given"], reverse=True)[:5]
    top_by_fixes = sorted(
        impact,
        key=lambda x: next((b["count"] for b in x["pr_type_breakdown"] if b["type"] == "fix"), 0),
        reverse=True,
    )[:5]

    return {
        "total_prs": len(human_prs),
        "total_merged": len(merged),
        "total_open": len(open_prs),
        "total_closed_unmerged": len(human_prs) - len(merged) - len(open_prs),
        "total_additions": sum(p["additions"] for p in human_prs),
        "total_deletions": sum(p["deletions"] for p in human_prs),
        "avg_merge_time_days": (
            round(sum(merge_times) / len(merge_times), 1) if merge_times else None
        ),
        "active_contributors": len(impact),
        "type_distribution": type_distribution,
        "weekly_trend": weekly_trend,
        "top_by_merges": [{"login": e["login"], "prs_merged": e["prs_merged"]} for e in top_by_merges],
        "top_by_reviews": [{"login": e["login"], "reviews_given": e["reviews_given"]} for e in top_by_reviews],
        "top_by_fixes": [
            {
                "login": e["login"],
                "fixes": next((b["count"] for b in e["pr_type_breakdown"] if b["type"] == "fix"), 0),
            }
            for e in top_by_fixes
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not PRS_PATH.exists():
        raise SystemExit(f"No data found at {PRS_PATH}. Run fetch_prs.py first.")

    with open(PRS_PATH) as f:
        prs = json.load(f)

    meta = {}
    if META_PATH.exists():
        with open(META_PATH) as f:
            meta = json.load(f)

    log.info("Loaded %d PRs. Computing impact …", len(prs))

    impact = compute_impact(prs)
    repo_stats = compute_repo_stats(prs, impact)

    # Recent PRs — top 10 per engineer (merged, sorted newest first)
    # Stored flat so the dashboard can quickly look them up by author
    top_logins = {e["login"] for e in impact[:10]}  # only store for top 10 to keep JSON small
    recent_prs = [
        {
            "number":    p["number"],
            "title":     p["title"],
            "state":     p["state"],
            "author":    p["author"],
            "merged_at": p["merged_at"],
            "url":       p["url"],
        }
        for p in sorted(
            [p for p in prs if p["author"] in top_logins and not is_bot(p["author"])],
            key=lambda p: p.get("merged_at") or p.get("updated_at") or "",
            reverse=True,
        )
    ]
    # Keep at most 15 per author
    from collections import defaultdict as _dd
    _counts: dict = _dd(int)
    recent_prs_trimmed = []
    for p in recent_prs:
        if _counts[p["author"]] < 15:
            recent_prs_trimmed.append(p)
            _counts[p["author"]] += 1

    output = {
        "meta": meta,
        "repo_stats": repo_stats,
        "engineers": impact,
        "recent_prs": recent_prs_trimmed,
        "weights": WEIGHTS,
        "pr_type_multipliers": PR_TYPE_MULTIPLIERS,
        "bot_logins": sorted(BOT_LOGINS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    DATA_DIR.mkdir(exist_ok=True)
    with open(IMPACT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    log.info("Impact data saved → %s", IMPACT_PATH)

    # Print a readable scoring summary
    log.info("─" * 60)
    log.info("%-20s %8s %8s %8s %8s", "Engineer", "Score", "Authored", "Reviews", "Merges")
    log.info("─" * 60)
    for e in impact[:15]:
        log.info(
            "%-20s %8.0f %8.0f %8.0f %8d",
            e["login"], e["impact_score"], e["authored_score"],
            e["review_score"], e["prs_merged"],
        )
    log.info("─" * 60)
    log.info(
        "Total: %d contributors, %d merged PRs, top: %s",
        len(impact), repo_stats["total_merged"],
        impact[0]["login"] if impact else "—",
    )
    log.info("Done. Run `python app.py` to view the dashboard.")


if __name__ == "__main__":
    main()
