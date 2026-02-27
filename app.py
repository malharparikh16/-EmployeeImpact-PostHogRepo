"""
app.py  —  Engineer Impact Dashboard
Single-page view of the top 5 most impactful engineers, with score breakdowns.

Usage:
    pip install flask
    python app.py   →  http://localhost:5000
"""

import json
from pathlib import Path
from flask import Flask, render_template_string, jsonify, abort

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / "data"
IMPACT_PATH = DATA_DIR / "impact.json"


def load_impact():
    if not IMPACT_PATH.exists():
        return None
    with open(IMPACT_PATH) as f:
        return json.load(f)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Engineer Impact · {{ meta.owner }}/{{ meta.repo }}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --bg:       #080b12;
  --s1:       #0e1320;
  --s2:       #141929;
  --s3:       #1c2235;
  --border:   #1e2640;
  --border2:  #28305a;
  --green:    #22d3a0;
  --blue:     #5b8fff;
  --orange:   #f97316;
  --pink:     #e879a0;
  --yellow:   #eab308;
  --text:     #e8ecf4;
  --muted:    #5a6485;
  --muted2:   #8492b8;
  --sans: 'Space Grotesk', sans-serif;
  --mono: 'JetBrains Mono', monospace;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  overflow: hidden;
}

/* ─── outer shell: header + body ─── */
.shell {
  height: 100vh;
  display: grid;
  grid-template-rows: 48px 1fr;
  overflow: hidden;
}

/* ─── header ─── */
header {
  background: var(--s1);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 16px;
  flex-shrink: 0;
}
.header-repo {
  font-family: var(--mono);
  font-size: 0.75rem;
  color: var(--green);
  letter-spacing: 0.03em;
}
.header-title {
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--text);
}
.header-meta {
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--muted2);
  margin-left: auto;
}
.header-pill {
  background: var(--s3);
  border: 1px solid var(--border2);
  border-radius: 20px;
  padding: 3px 10px;
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--muted2);
}

/* ─── body: left panel + right panel ─── */
.body {
  display: grid;
  grid-template-columns: 280px 1fr;
  overflow: hidden;
  min-height: 0;
}

/* ─── left: ranked list ─── */
.left-panel {
  background: var(--s1);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.left-header {
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.left-header h2 {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted2);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.left-header p {
  font-size: 0.7rem;
  color: var(--muted);
  margin-top: 2px;
  font-family: var(--mono);
}
.rank-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.rank-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: background 0.12s;
  position: relative;
}
.rank-item:hover { background: var(--s2); }
.rank-item.active {
  background: var(--s2);
  border-left-color: var(--green);
}
.rank-num {
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 600;
  width: 18px;
  text-align: center;
  flex-shrink: 0;
}
.rank-num.r1 { color: #f59e0b; }
.rank-num.r2 { color: #94a3b8; }
.rank-num.r3 { color: #cd7c3a; }
.rank-num.rn { color: var(--muted); }
.rank-avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--s3);
  border: 1px solid var(--border2);
  flex-shrink: 0;
  object-fit: cover;
}
.rank-info { flex: 1; min-width: 0; }
.rank-name {
  font-weight: 600;
  font-size: 0.82rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rank-login {
  font-family: var(--mono);
  font-size: 0.66rem;
  color: var(--muted);
}
.rank-score-col { text-align: right; flex-shrink: 0; }
.rank-score {
  font-family: var(--mono);
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--green);
}
.rank-bar-wrap {
  padding: 4px 16px 6px;
  display: flex;
  gap: 2px;
}
.rank-bar-seg {
  height: 3px;
  border-radius: 2px;
  transition: width 0.4s;
}

/* ─── right: detail panel ─── */
.right-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}
.detail-header {
  padding: 14px 20px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  background: var(--s1);
}
.detail-avatar {
  width: 40px; height: 40px;
  border-radius: 50%;
  border: 2px solid var(--border2);
  object-fit: cover;
  background: var(--s3);
}
.detail-name { font-size: 1rem; font-weight: 700; }
.detail-login { font-family: var(--mono); font-size: 0.72rem; color: var(--green); margin-top: 1px; }
.detail-score-group {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.score-badge {
  background: #0d2a1e;
  border: 1px solid var(--green);
  border-radius: 8px;
  padding: 6px 14px;
  font-family: var(--mono);
  font-weight: 600;
  font-size: 1.1rem;
  color: var(--green);
}
.score-formula {
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--muted2);
  text-align: right;
  line-height: 1.6;
}
.score-formula span { font-weight: 600; }
.score-formula .authored { color: var(--blue); }
.score-formula .review { color: var(--orange); }

/* ─── detail body: scrollable ─── */
.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 20px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: auto auto auto;
  gap: 12px;
  align-content: start;
}

/* cards */
.card {
  background: var(--s1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
}
.card-title {
  font-size: 0.67rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title .score-tag {
  font-size: 0.67rem;
  font-family: var(--mono);
  font-weight: 600;
  background: var(--s3);
  border-radius: 4px;
  padding: 1px 6px;
  letter-spacing: 0;
  text-transform: none;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 0.78rem;
  border-bottom: 1px solid var(--border);
}
.row:last-child { border-bottom: none; }
.row-label { color: var(--muted2); }
.row-val { font-family: var(--mono); font-weight: 600; }
.row-val.green  { color: var(--green); }
.row-val.blue   { color: var(--blue); }
.row-val.orange { color: var(--orange); }
.row-val.pink   { color: var(--pink); }
.row-val.muted  { color: var(--muted2); }

/* score breakdown card */
.score-breakdown { grid-column: span 2; }
.breakdown-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.77rem;
}
.breakdown-row:last-child { border-bottom: none; }
.breakdown-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.breakdown-label { flex: 1; color: var(--muted2); }
.breakdown-calc { font-family: var(--mono); font-size: 0.68rem; color: var(--muted); }
.breakdown-pts { font-family: var(--mono); font-weight: 600; font-size: 0.82rem; }
.breakdown-bar-wrap { width: 60px; }
.breakdown-bar-bg { height: 4px; background: var(--s3); border-radius: 2px; overflow: hidden; }
.breakdown-bar-fill { height: 100%; border-radius: 2px; }

/* pr type tags */
.type-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.type-tag {
  font-family: var(--mono);
  font-size: 0.65rem;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid;
  display: flex;
  align-items: center;
  gap: 4px;
}
.type-tag .mult {
  font-size: 0.6rem;
  opacity: 0.7;
}

/* spark card */
.spark-card { grid-column: span 1; }
.spark-wrap { height: 56px; margin-top: 4px; }

/* chart card full width */
.chart-card { grid-column: span 3; }
.chart-wrap { height: 110px; }

/* ─── "why" tooltip ─── */
.why-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--s3);
  border: 1px solid var(--border2);
  font-size: 0.6rem;
  color: var(--muted2);
  cursor: help;
  margin-left: 4px;
  position: relative;
}
.why-icon:hover::after {
  content: attr(data-tip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--s3);
  border: 1px solid var(--border2);
  border-radius: 6px;
  padding: 6px 10px;
  font-family: var(--sans);
  font-size: 0.72rem;
  color: var(--text);
  white-space: pre-line;
  width: 220px;
  line-height: 1.5;
  z-index: 100;
  pointer-events: none;
  text-align: left;
  font-weight: 400;
}

/* ─── empty state ─── */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 0.8rem;
}
</style>
</head>
<body>
<div class="shell">

  <!-- ═══ HEADER ═══ -->
  <header>
    <div>
      <div class="header-repo">{{ meta.owner }}/{{ meta.repo }}</div>
      <div class="header-title">Engineer Impact</div>
    </div>
    <div class="header-pill">past {{ meta.days }}d</div>
    <div class="header-pill">{{ repo_stats.total_prs }} PRs</div>
    <div class="header-pill">{{ repo_stats.total_merged }} merged</div>
    <div class="header-pill">{{ repo_stats.active_contributors }} contributors</div>
    <div class="header-meta">Last updated {{ meta.fetched_at[:10] if meta.fetched_at else '—' }}</div>
  </header>

  <!-- ═══ BODY ═══ -->
  <div class="body">

    <!-- ── LEFT: ranked list ── -->
    <div class="left-panel">
      <div class="left-header">
        <h2>Top 5 Engineers</h2>
        <p>by composite impact score</p>
      </div>
      <div class="rank-list" id="rank-list">
        <!-- filled by JS -->
      </div>
    </div>

    <!-- ── RIGHT: detail ── -->
    <div class="right-panel">
      <div class="detail-header" id="detail-header">
        <div class="empty" style="height:auto;flex-direction:row;color:var(--muted2);font-family:var(--sans);font-size:0.82rem;">
          ← Select an engineer to see their breakdown
        </div>
      </div>
      <div class="detail-body" id="detail-body">
        <!-- filled by JS -->
      </div>
    </div>

  </div>
</div>

<script>
const DATA   = {{ impact_json | safe }};
const TOP5   = DATA.engineers.slice(0, 5);
const WEIGHTS = DATA.weights || {};
const MULTS  = DATA.pr_type_multipliers || {};

const TYPE_COLORS = {
  fix: '#f97316', hotfix: '#ef4444', revert: '#f87171',
  feat: '#22d3a0', perf: '#c084fc', security: '#ef4444',
  refactor: '#5b8fff', test: '#64748b', ci: '#64748b',
  build: '#64748b', chore: '#94a3b8', docs: '#8492b8',
  style: '#6b7280', wip: '#4b5563', unknown: '#374151',
};

function fmtNum(n) {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return (n/1000).toFixed(1) + 'k';
  return n.toLocaleString();
}
function fmtDays(d) { return d != null ? d + 'd' : '—'; }

// ── build rank list ──
function buildRankList() {
  const maxScore = TOP5[0]?.impact_score || 1;
  document.getElementById('rank-list').innerHTML = TOP5.map((e, i) => {
    const numClass = ['r1','r2','r3','rn','rn'][i];
    const authoredW = (e.authored_score / e.impact_score) * 100;
    const reviewW   = (e.review_score   / e.impact_score) * 100;
    return `
      <div class="rank-item" id="ri-${i}" onclick="selectEngineer(${i})">
        <span class="rank-num ${numClass}">${i+1}</span>
        ${e.author_avatar
          ? `<img class="rank-avatar" src="${e.author_avatar}" alt="">`
          : `<div class="rank-avatar"></div>`}
        <div class="rank-info">
          <div class="rank-name">${e.author_name || e.login}</div>
          <div class="rank-login">@${e.login}</div>
        </div>
        <div class="rank-score-col">
          <div class="rank-score">${e.impact_score}</div>
        </div>
      </div>
      <div class="rank-bar-wrap">
        <div class="rank-bar-seg" style="width:${authoredW*2.2}px;background:#5b8fff55;max-width:120px"></div>
        <div class="rank-bar-seg" style="width:${reviewW*2.2}px;background:#f9731655;max-width:80px"></div>
      </div>`;
  }).join('');
  selectEngineer(0);
}

// ── select engineer ──
function selectEngineer(idx) {
  document.querySelectorAll('.rank-item').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });
  renderDetail(TOP5[idx]);
}

// ── render right panel ──
function renderDetail(e) {
  renderHeader(e);
  renderBody(e);
}

function renderHeader(e) {
  document.getElementById('detail-header').innerHTML = `
    ${e.author_avatar ? `<img class="detail-avatar" src="${e.author_avatar}" alt="">` : `<div class="detail-avatar"></div>`}
    <div>
      <div class="detail-name">${e.author_name || e.login}</div>
      <div class="detail-login">@${e.login} &nbsp;·&nbsp; rank #${e.rank} of ${DATA.engineers.length}</div>
    </div>
    <div class="detail-score-group">
      <div class="score-formula">
        <div>authored <span class="authored">${e.authored_score}</span></div>
        <div>reviews &nbsp;<span class="review">${e.review_score}</span></div>
      </div>
      <div class="score-badge">⚡ ${e.impact_score}</div>
    </div>`;
}

function renderBody(e) {
  const sparkId = 'spark_' + e.login.replace(/[^a-z0-9]/gi, '_');
  const scoreMax = e.impact_score || 1;

  // ── score breakdown rows ──
  const fix_count  = (e.pr_type_breakdown||[]).find(t=>t.type==='fix')?.count || 0;
  const feat_count = (e.pr_type_breakdown||[]).find(t=>t.type==='feat')?.count || 0;
  const other_merged = e.prs_merged - fix_count - feat_count;

  const breakdownRows = [
    {
      label: 'Fix PRs merged',
      dot: '#f97316',
      calc: `${fix_count} × ${WEIGHTS.pr_merged||10} × ${MULTS.fix||2.0}× mult`,
      pts: +(fix_count * (WEIGHTS.pr_merged||10) * (MULTS.fix||2.0)).toFixed(1),
      tip: `Each merged fix/ PR earns ${WEIGHTS.pr_merged||10} base points × the fix multiplier (${MULTS.fix||2.0}×)\nbecause bug fixes directly improve reliability.`
    },
    {
      label: 'Feature PRs merged',
      dot: '#22d3a0',
      calc: `${feat_count} × ${WEIGHTS.pr_merged||10} × ${MULTS.feat||1.5}× mult`,
      pts: +(feat_count * (WEIGHTS.pr_merged||10) * (MULTS.feat||1.5)).toFixed(1),
      tip: `feat/ PRs earn ${WEIGHTS.pr_merged||10} base pts × ${MULTS.feat||1.5}× multiplier.\nFeatures ship user value, so they score higher than chores.`
    },
    {
      label: 'Other merged PRs',
      dot: '#5b8fff',
      calc: `${other_merged} × ${WEIGHTS.pr_merged||10} × ~1.0× mult`,
      pts: +(other_merged * (WEIGHTS.pr_merged||10) * 1.0).toFixed(1),
      tip: `Merged PRs with other prefixes (refactor, perf, etc.) earn the base weight × their own multiplier.\nShown here as avg 1.0× for simplicity.`
    },
    {
      label: 'Code volume',
      dot: '#c084fc',
      calc: `${fmtNum(e.net_lines)} lines ÷ 1000 × ${WEIGHTS.lines_per_1k||1}`,
      pts: +((e.net_lines / 1000) * (WEIGHTS.lines_per_1k||1)).toFixed(1),
      tip: `Net lines touched (additions + deletions) ÷ 1000.\nRewarded lightly — 1pt per 1k lines — so big refactors\naren't penalised but raw line count doesn't dominate.`
    },
    {
      label: 'First approvals given',
      dot: '#f97316',
      calc: `${e.first_approvals||0} × ${WEIGHTS.first_approval||8}pts`,
      pts: +((e.first_approvals||0) * (WEIGHTS.first_approval||8)).toFixed(1),
      tip: `The FIRST human approval on a PR is the critical unblocking event.\nIt scores ${WEIGHTS.first_approval||8}pts — higher than subsequent approvals.`
    },
    {
      label: 'Substantive change requests',
      dot: '#e879a0',
      calc: `${e.change_requests_with_body||0} × ${WEIGHTS.change_request_body||7}pts`,
      pts: +((e.change_requests_with_body||0) * (WEIGHTS.change_request_body||7)).toFixed(1),
      tip: `Change requests with written feedback (has_body=true) score ${WEIGHTS.change_request_body||7}pts each.\nThese represent the highest-signal review work — actual written guidance.`
    },
    {
      label: 'Substantive comments',
      dot: '#60a5fa',
      calc: `${e.comments_with_body||0} × ${WEIGHTS.comment_body||3}pts`,
      pts: +((e.comments_with_body||0) * (WEIGHTS.comment_body||3)).toFixed(1),
      tip: `Review comments with a body score ${WEIGHTS.comment_body||3}pts.\nEmpty comments (automated reactions, +1s) score only ${WEIGHTS.comment_empty||0.5}pts.`
    },
    {
      label: 'Breadth of reviewing',
      dot: '#a78bfa',
      calc: `${e.unique_prs_reviewed||0} unique PRs × ${WEIGHTS.unique_prs_reviewed||2}pts`,
      pts: +((e.unique_prs_reviewed||0) * (WEIGHTS.unique_prs_reviewed||2)).toFixed(1),
      tip: `Reviewing many different PRs is rewarded as ${WEIGHTS.unique_prs_reviewed||2}pt per unique PR.\nEncourages broad team coverage over reviewing the same PR repeatedly.`
    },
  ].filter(r => r.pts > 0);

  const breakdownTotal = breakdownRows.reduce((s, r) => s + r.pts, 0) || 1;

  const breakdownHTML = breakdownRows.map(r => {
    const barW = Math.round((r.pts / scoreMax) * 100);
    return `<div class="breakdown-row">
      <div class="breakdown-dot" style="background:${r.dot}"></div>
      <div class="breakdown-label">${r.label}
        <span class="why-icon" data-tip="${r.tip}">?</span>
      </div>
      <div class="breakdown-calc">${r.calc}</div>
      <div class="breakdown-bar-wrap">
        <div class="breakdown-bar-bg">
          <div class="breakdown-bar-fill" style="width:${barW}%;background:${r.dot}88"></div>
        </div>
      </div>
      <div class="breakdown-pts" style="color:${r.dot}">${r.pts}</div>
    </div>`;
  }).join('');

  // ── PR type tags ──
  const typeTags = (e.pr_type_breakdown||[]).map(t => {
    const col = TYPE_COLORS[t.type] || '#64748b';
    const mult = MULTS[t.type] ? MULTS[t.type] + '×' : '1×';
    return `<span class="type-tag" style="color:${col};border-color:${col}44;background:${col}10">
      ${t.type} <strong>${t.count}</strong><span class="mult">${mult}</span>
    </span>`;
  }).join('');

  document.getElementById('detail-body').innerHTML = `

    <!-- row 1: authored stats | review stats | pr types -->
    <div class="card">
      <div class="card-title">
        Authored PRs
        <span class="score-tag" style="color:#5b8fff">${e.authored_score} pts</span>
      </div>
      <div class="row"><span class="row-label">Merged</span><span class="row-val green">${e.prs_merged}</span></div>
      <div class="row"><span class="row-label">Merge rate</span><span class="row-val">${e.merge_rate_pct}%</span></div>
      <div class="row"><span class="row-label">Avg time to merge</span><span class="row-val muted">${fmtDays(e.avg_merge_time_days)}</span></div>
      <div class="row"><span class="row-label">Commits</span><span class="row-val muted">${fmtNum(e.total_commits)}</span></div>
      <div class="row"><span class="row-label">Files changed</span><span class="row-val muted">${fmtNum(e.total_files_changed)}</span></div>
      <div class="row"><span class="row-label">Net lines</span><span class="row-val muted">${fmtNum(e.net_lines)}</span></div>
    </div>

    <div class="card">
      <div class="card-title">
        Reviews Given
        <span class="score-tag" style="color:#f97316">${e.review_score} pts</span>
      </div>
      <div class="row">
        <span class="row-label">First approvals
          <span class="why-icon" data-tip="First approval on a PR unblocks it for merge.\nScores ${WEIGHTS.first_approval||8}pts — more than follow-on approvals.">?</span>
        </span>
        <span class="row-val green">${e.first_approvals||0}</span>
      </div>
      <div class="row">
        <span class="row-label">Change req (detailed)</span>
        <span class="row-val orange">${e.change_requests_with_body||0}</span>
      </div>
      <div class="row">
        <span class="row-label">Change req (empty)</span>
        <span class="row-val muted">${e.change_requests_empty||0}</span>
      </div>
      <div class="row">
        <span class="row-label">Comments (detailed)</span>
        <span class="row-val blue">${e.comments_with_body||0}</span>
      </div>
      <div class="row">
        <span class="row-label">Comments (empty)</span>
        <span class="row-val muted">${e.comments_empty||0}</span>
      </div>
      <div class="row">
        <span class="row-label">Unique PRs reviewed</span>
        <span class="row-val muted">${e.unique_prs_reviewed||0}</span>
      </div>
    </div>

    <div class="card">
      <div class="card-title">PR Type Breakdown</div>
      <div class="type-tags">${typeTags || '<span style="color:var(--muted);font-size:0.72rem">No type data</span>'}</div>
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border)">
        <div class="row"><span class="row-label">+${fmtNum(e.total_additions)}</span><span class="row-val green">additions</span></div>
        <div class="row"><span class="row-label">-${fmtNum(e.total_deletions)}</span><span class="row-val pink">deletions</span></div>
      </div>
    </div>

    <!-- row 2: score breakdown (spans 2) + sparkline -->
    <div class="card score-breakdown">
      <div class="card-title">
        Score Breakdown — how ${e.impact_score} pts were earned
        <span class="why-icon" data-tip="Each bar shows the contribution of one factor to the total impact score.\nHover any ? for the exact formula.">?</span>
      </div>
      ${breakdownHTML}
    </div>

    <div class="card spark-card">
      <div class="card-title">Weekly Activity</div>
      <div class="spark-wrap"><canvas id="${sparkId}"></canvas></div>
    </div>

  `;

  // draw sparkline
  const weekly = e.weekly_activity || [];
  setTimeout(() => {
    const ctx = document.getElementById(sparkId);
    if (!ctx || !weekly.length) return;
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: weekly.map(w => w.week),
        datasets: [{
          data: weekly.map(w => w.count),
          backgroundColor: '#5b8fff44',
          borderColor: '#5b8fff',
          borderWidth: 1,
          borderRadius: 2,
        }]
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: {
          callbacks: { label: c => `${c.raw} PRs` }
        }},
        scales: {
          x: { display: false },
          y: { display: false, beginAtZero: true }
        }
      }
    });
  }, 50);
}

buildRankList();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    data = load_impact()
    if data is None:
        return (
            "<pre style='font:14px monospace;padding:40px;background:#080b12;color:#22d3a0'>"
            "No data found.\n\nRun the pipeline first:\n\n"
            "  1. set GITHUB_TOKEN=your_token\n"
            "  2. python fetch_prs.py\n"
            "  3. python analyze.py\n"
            "  4. python app.py\n"
            "</pre>", 503,
        )
    return render_template_string(
        TEMPLATE,
        meta=data.get("meta", {}),
        repo_stats=data.get("repo_stats", {}),
        impact_json=json.dumps(data),
    )


@app.route("/api/impact")
def api_impact():
    data = load_impact()
    if data is None:
        abort(503, "No impact data. Run fetch_prs.py and analyze.py first.")
    return jsonify(data)


if __name__ == "__main__":
    print("Dashboard → http://localhost:5000")
    app.run(debug=True, port=5000)