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
  --bg:     #080b12; --s1: #0e1320; --s2: #141929; --s3: #1c2235;
  --bdr:    #1e2640; --bdr2: #28305a;
  --green:  #22d3a0; --blue: #5b8fff; --orange: #f97316;
  --pink:   #e879a0; --purple: #c084fc;
  --text:   #e8ecf4; --muted: #5a6485; --muted2: #8492b8;
  --sans:   'Space Grotesk', sans-serif;
  --mono:   'JetBrains Mono', monospace;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; font-family: var(--sans); background: var(--bg); color: var(--text); font-size: 13px; overflow: hidden; }

.shell { height: 100vh; display: grid; grid-template-rows: 48px 1fr; overflow: hidden; }

/* header */
header { background: var(--s1); border-bottom: 1px solid var(--bdr); display: flex; align-items: center; padding: 0 20px; gap: 14px; }
.hrepo  { font-family: var(--mono); font-size: .75rem; color: var(--green); }
.htitle { font-weight: 700; font-size: .95rem; }
.hmeta  { font-family: var(--mono); font-size: .68rem; color: var(--muted2); margin-left: auto; }
.pill   { background: var(--s3); border: 1px solid var(--bdr2); border-radius: 20px; padding: 3px 10px; font-family: var(--mono); font-size: .68rem; color: var(--muted2); }

/* layout */
.body { display: grid; grid-template-columns: 280px 1fr; overflow: hidden; min-height: 0; }

/* left */
.left-panel { background: var(--s1); border-right: 1px solid var(--bdr); display: flex; flex-direction: column; overflow: hidden; }
.left-hdr   { padding: 14px 16px 10px; border-bottom: 1px solid var(--bdr); flex-shrink: 0; }
.left-hdr h2 { font-size: .8rem; font-weight: 600; color: var(--muted2); text-transform: uppercase; letter-spacing: .1em; }
.left-hdr p  { font-size: .7rem; color: var(--muted); margin-top: 2px; font-family: var(--mono); }
.rank-list  { flex: 1; overflow-y: auto; padding: 8px 0; }
.rank-item  { display: flex; align-items: center; gap: 10px; padding: 10px 16px; cursor: pointer; border-left: 2px solid transparent; transition: background .12s; }
.rank-item:hover  { background: var(--s2); }
.rank-item.active { background: var(--s2); border-left-color: var(--green); }
.rnum  { font-family: var(--mono); font-size: .72rem; font-weight: 600; width: 18px; text-align: center; flex-shrink: 0; }
.rnum.r1 { color: #f59e0b; } .rnum.r2 { color: #94a3b8; } .rnum.r3 { color: #cd7c3a; } .rnum.rn { color: var(--muted); }
.ravatar { width: 32px; height: 32px; border-radius: 50%; background: var(--s3); border: 1px solid var(--bdr2); flex-shrink: 0; object-fit: cover; }
.rinfo   { flex: 1; min-width: 0; }
.rname   { font-weight: 600; font-size: .82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rlogin  { font-family: var(--mono); font-size: .66rem; color: var(--muted); }
.rscore  { font-family: var(--mono); font-size: .88rem; font-weight: 600; color: var(--green); flex-shrink: 0; }
.rbar-wrap { padding: 2px 16px 6px; display: flex; gap: 2px; }
.rbar-seg  { height: 3px; border-radius: 2px; }

/* right */
.right-panel { display: flex; flex-direction: column; overflow: hidden; background: var(--bg); }
.dhdr { padding: 14px 20px 12px; border-bottom: 1px solid var(--bdr); display: flex; align-items: center; gap: 12px; flex-shrink: 0; background: var(--s1); }
.dava  { width: 40px; height: 40px; border-radius: 50%; border: 2px solid var(--bdr2); object-fit: cover; background: var(--s3); }
.dname { font-size: 1rem; font-weight: 700; }
.dlogin { font-family: var(--mono); font-size: .72rem; color: var(--green); margin-top: 1px; }
.sgroup { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.sbadge { background: #0d2a1e; border: 1px solid var(--green); border-radius: 8px; padding: 6px 14px; font-family: var(--mono); font-weight: 600; font-size: 1.1rem; color: var(--green); }
.ssplit { font-family: var(--mono); font-size: .68rem; color: var(--muted2); text-align: right; line-height: 1.7; }
.ssplit .a { color: var(--blue); font-weight: 600; }
.ssplit .r { color: var(--orange); font-weight: 600; }

/* detail body */
.dbody { flex: 1; overflow-y: auto; padding: 14px 20px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; align-content: start; }

/* cards */
.card { background: var(--s1); border: 1px solid var(--bdr); border-radius: 8px; padding: 12px 14px; }
.card.s2 { grid-column: span 2; }
.card.s3 { grid-column: span 3; }
.ctitle { font-size: .67rem; font-weight: 600; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin-bottom: 10px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.stag   { font-family: var(--mono); font-size: .67rem; font-weight: 600; background: var(--s3); border-radius: 4px; padding: 1px 6px; text-transform: none; letter-spacing: 0; margin-left: auto; }
.row    { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: .78rem; border-bottom: 1px solid var(--bdr); }
.row:last-child { border-bottom: none; }
.lbl { color: var(--muted2); display: flex; align-items: center; gap: 4px; }
.val { font-family: var(--mono); font-weight: 600; }
.g { color: var(--green); } .b { color: var(--blue); } .o { color: var(--orange); } .p { color: var(--pink); } .d { color: var(--muted2); }

/* type tags */
.ttags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.ttag  { font-family: var(--mono); font-size: .65rem; padding: 2px 7px; border-radius: 4px; border: 1px solid; display: flex; align-items: center; gap: 4px; }
.ttag .mx { font-size: .6rem; opacity: .7; }

/* breakdown rows */
.bdr { display: flex; align-items: center; gap: 7px; padding: 5px 0; border-bottom: 1px solid var(--bdr); font-size: .76rem; }
.bdr:last-of-type { border-bottom: none; }
.bddot   { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.bdlabel { flex: 1; color: var(--muted2); display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.bdtag   { font-size: .6rem; padding: 0 4px; border-radius: 3px; font-family: var(--mono); flex-shrink: 0; }
.bdcalc  { font-family: var(--mono); font-size: .65rem; color: var(--muted); width: 150px; text-align: right; flex-shrink: 0; }
.bdbar   { width: 54px; flex-shrink: 0; }
.bdbg    { height: 5px; background: var(--s3); border-radius: 3px; overflow: hidden; }
.bdfill  { height: 100%; border-radius: 3px; }
.bdpts   { font-family: var(--mono); font-weight: 600; font-size: .82rem; width: 38px; text-align: right; flex-shrink: 0; }
.bdtotal { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; padding-top: 7px; border-top: 2px solid var(--bdr2); font-size: .75rem; }
.ok   { color: var(--green); font-family: var(--mono); font-size: .68rem; }
.warn { color: var(--orange); font-family: var(--mono); font-size: .68rem; }

/* cadence */
.cstats { display: flex; gap: 6px; margin-bottom: 10px; }
.cstat  { flex: 1; background: var(--s3); border-radius: 6px; padding: 7px 6px; text-align: center; }
.csv    { font-family: var(--mono); font-size: 1.15rem; font-weight: 700; line-height: 1; }
.csl    { font-size: .62rem; color: var(--muted2); margin-top: 3px; line-height: 1.3; }
.shdr   { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 3px; }
.shdr-l { font-size: .63rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
.shdr-r { font-family: var(--mono); font-size: .62rem; color: var(--muted); }
.swrap  { height: 68px; }
.sfoot  { display: flex; justify-content: space-between; margin-top: 2px; }
.sfoot span { font-family: var(--mono); font-size: .61rem; color: var(--muted); }
.sleg   { display: flex; align-items: center; gap: 5px; margin-top: 5px; }
.sleg-box { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.sleg-txt { font-size: .66rem; color: var(--muted2); }

/* vs-team */
.vrow { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid var(--bdr); font-size: .75rem; }
.vrow:last-child { border-bottom: none; }
.vlbl   { width: 82px; color: var(--muted2); flex-shrink: 0; font-size: .71rem; }
.vbg    { flex: 1; height: 5px; background: var(--s3); border-radius: 3px; overflow: hidden; }
.vfill  { height: 100%; border-radius: 3px; }
.vval   { font-family: var(--mono); font-size: .7rem; font-weight: 600; width: 38px; text-align: right; flex-shrink: 0; }
.vrank  { font-family: var(--mono); font-size: .66rem; color: var(--muted); width: 26px; text-align: right; flex-shrink: 0; }

/* recent PRs */
.prrow { display: flex; align-items: center; gap: 7px; padding: 5px 0; border-bottom: 1px solid var(--bdr); font-size: .75rem; }
.prrow:last-child { border-bottom: none; }
.prdot   { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.prtitle { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prnum   { font-family: var(--mono); font-size: .65rem; color: var(--muted); flex-shrink: 0; }
.prstate { font-family: var(--mono); font-size: .62rem; padding: 1px 5px; border-radius: 3px; flex-shrink: 0; font-weight: 600; }
.merged { background: #0d2a1e; color: var(--green); }

/* tooltip */
.tip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 13px; height: 13px; border-radius: 50%;
  background: var(--s3); border: 1px solid var(--bdr2);
  font-size: .58rem; color: var(--muted2); cursor: help; position: relative; flex-shrink: 0;
}
.tip:hover::after {
  content: attr(data-tip);
  position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
  background: var(--s3); border: 1px solid var(--bdr2); border-radius: 6px;
  padding: 7px 10px; font-family: var(--sans); font-size: .72rem; color: var(--text);
  white-space: pre-line; width: 230px; line-height: 1.5;
  z-index: 200; pointer-events: none; text-align: left; font-weight: 400;
}
</style>
</head>
<body>
<div class="shell">

<header>
  <div>
    <div class="hrepo">{{ meta.owner }}/{{ meta.repo }}</div>
    <div class="htitle">Engineer Impact</div>
  </div>
  <div class="pill">past {{ meta.days }}d</div>
  <div class="pill">{{ repo_stats.total_prs }} PRs</div>
  <div class="pill">{{ repo_stats.total_merged }} merged</div>
  <div class="pill">{{ repo_stats.active_contributors }} contributors</div>
  <div class="hmeta">Updated {{ meta.fetched_at[:10] if meta.fetched_at else '—' }}</div>
</header>

<div class="body">
  <div class="left-panel">
    <div class="left-hdr">
      <h2>Top 5 Engineers</h2>
      <p>by composite impact score</p>
    </div>
    <div class="rank-list" id="rank-list"></div>
  </div>
  <div class="right-panel">
    <div class="dhdr" id="dhdr">
      <span style="color:var(--muted2);font-size:.82rem">← Select an engineer</span>
    </div>
    <div class="dbody" id="dbody"></div>
  </div>
</div>
</div>

<script>
const DATA    = {{ impact_json | safe }};
const TOP5    = DATA.engineers.slice(0, 5);
const WEIGHTS = DATA.weights || {};
const MULTS   = DATA.pr_type_multipliers || {};

// type colours
const TC = {
  fix:'#f97316',hotfix:'#ef4444',revert:'#f87171',security:'#ef4444',
  feat:'#22d3a0',perf:'#c084fc',refactor:'#5b8fff',
  test:'#64748b',ci:'#64748b',build:'#64748b',
  chore:'#94a3b8',docs:'#8492b8',style:'#6b7280',wip:'#4b5563',
};
// group colours (used by score_components[].color field from analyze.py)
const GC = {
  authored:'#5b8fff', authored_dim:'#4a6fd0',
  review:'#f97316',   review_dim:'#b05010',
};

function fmtN(n) {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return (n/1000).toFixed(1)+'k';
  return Number(n).toLocaleString();
}
function fmtD(d) { return d != null ? d+'d' : '—'; }

// ── left panel ──────────────────────────────────────────────
function buildRankList() {
  document.getElementById('rank-list').innerHTML = TOP5.map((e, i) => {
    const nc = ['r1','r2','r3','rn','rn'][i];
    const aw = Math.round((e.authored_score / e.impact_score) * 200);
    const rw = Math.round((e.review_score   / e.impact_score) * 200);
    return `
      <div class="rank-item" id="ri-${i}" onclick="pick(${i})">
        <span class="rnum ${nc}">${i+1}</span>
        ${e.author_avatar
          ? `<img class="ravatar" src="${e.author_avatar}" alt="">`
          : `<div class="ravatar"></div>`}
        <div class="rinfo">
          <div class="rname">${e.author_name || e.login}</div>
          <div class="rlogin">@${e.login}</div>
        </div>
        <span class="rscore">${e.impact_score}</span>
      </div>
      <div class="rbar-wrap">
        <div class="rbar-seg" style="width:${aw}px;max-width:130px;background:#5b8fff55"></div>
        <div class="rbar-seg" style="width:${rw}px;max-width:80px;background:#f9731655"></div>
      </div>`;
  }).join('');
  pick(0);
}

function pick(idx) {
  document.querySelectorAll('.rank-item').forEach((el, i) =>
    el.classList.toggle('active', i === idx));
  render(TOP5[idx]);
}

// ── right panel ─────────────────────────────────────────────
function render(e) {

  // header
  document.getElementById('dhdr').innerHTML = `
    ${e.author_avatar
      ? `<img class="dava" src="${e.author_avatar}" alt="">`
      : `<div class="dava"></div>`}
    <div>
      <div class="dname">${e.author_name || e.login}</div>
      <div class="dlogin">@${e.login} · rank #${e.rank} of ${DATA.engineers.length}</div>
    </div>
    <div class="sgroup">
      <div class="ssplit">
        <div>authored <span class="a">${e.authored_score}</span></div>
        <div>reviews &nbsp;<span class="r">${e.review_score}</span></div>
      </div>
      <div class="sbadge">⚡ ${e.impact_score}</div>
    </div>`;

  // ── Score breakdown ──────────────────────────────────────
  // Read score_components written by analyze.py — each entry has:
  //   label, group, count, weight, mult (or null), calc, pts, color, tip (optional)
  // This is the authoritative source; we do NOT re-derive anything here.
  const comps = e.score_components || [];
  const compSum = +comps.reduce((s,c) => s + c.pts, 0).toFixed(1);
  const diff    = Math.abs(compSum - e.impact_score);
  const verified = diff < 0.6;

  function dotColor(c) {
    // PR-type rows: use the commit-type colour
    const m = c.label.match(/^(\w+) PRs (merged|opened)/);
    if (m) return TC[m[1]] || GC[c.color] || '#64748b';
    return GC[c.color] || '#64748b';
  }

  const bdHTML = comps.map(c => {
    const col  = dotColor(c);
    const barW = Math.min(100, Math.round((c.pts / (e.impact_score||1)) * 100));
    const isA  = c.group === 'authored';
    const gtag = `<span class="bdtag" style="background:${isA?'#1a2a50':'#2a1810'};color:${isA?'#5b8fff':'#f97316'}">${isA?'auth':'rev'}</span>`;
    const mtag = c.mult != null
      ? `<span style="font-size:.6rem;background:${col}22;color:${col};border-radius:3px;padding:0 4px;font-family:var(--mono);flex-shrink:0">${c.mult}×</span>`
      : '';
    const tipEl = c.tip
      ? `<span class="tip" data-tip="${c.tip}">?</span>`
      : '';
    return `<div class="bdr">
      <div class="bddot" style="background:${col}"></div>
      <div class="bdlabel">${c.label}${mtag}${gtag}${tipEl}</div>
      <div class="bdcalc">${c.calc}</div>
      <div class="bdbar"><div class="bdbg"><div class="bdfill" style="width:${barW}%;background:${col}99"></div></div></div>
      <div class="bdpts" style="color:${col}">${c.pts}</div>
    </div>`;
  }).join('');

  const bdTotal = `<div class="bdtotal">
    <span>
      <span style="color:var(--blue)">■ authored ${e.authored_score}</span>
      &nbsp;+&nbsp;
      <span style="color:var(--orange)">■ reviews ${e.review_score}</span>
      &nbsp;=&nbsp;
      <strong style="color:var(--text)">${e.impact_score} pts</strong>
    </span>
    <span class="${verified?'ok':'warn'}">
      ${verified
        ? `✓ all ${comps.length} components verified`
        : `⚠ sum=${compSum} vs stored=${e.impact_score} (diff ${diff.toFixed(1)} — re-run analyze.py)`}
    </span>
  </div>`;

  // ── Type tags ────────────────────────────────────────────
  const typeTags = (e.pr_type_breakdown || []).map(t => {
    const col  = TC[t.type] || '#64748b';
    const mult = MULTS[t.type] ? MULTS[t.type]+'×' : '1×';
    return `<span class="ttag" style="color:${col};border-color:${col}44;background:${col}10">
      ${t.type} <strong>${t.count}</strong><span class="mx">${mult}</span></span>`;
  }).join('');

  // ── Weekly sparkline ─────────────────────────────────────
  const weekly  = e.weekly_activity || [];
  const wkN     = weekly.length || 1;
  const wkTotal = weekly.reduce((s,w) => s + w.count, 0);
  const wkAvg   = (wkTotal / wkN).toFixed(1);
  const wkPeak  = weekly.length ? Math.max(...weekly.map(w => w.count)) : 0;
  const wkFirst = weekly.length ? weekly[0].week : '—';
  const wkLast  = weekly.length ? weekly[weekly.length-1].week : '—';
  const draftPct = e.prs_opened > 0 ? Math.round((e.prs_draft||0)/e.prs_opened*100) : 0;
  const sparkId  = 'sp_' + e.login.replace(/[^a-z0-9]/gi,'_');

  // ── vs-team rows ─────────────────────────────────────────
  const vsFields = [
    {label:'Impact score',    key:'impact_score',       color:'#22d3a0'},
    {label:'Merges',          key:'prs_merged',          color:'#5b8fff'},
    {label:'Reviews given',   key:'reviews_given',       color:'#f97316'},
    {label:'Net lines',       key:'net_lines',           color:'#c084fc'},
    {label:'1st approvals',   key:'first_approvals',     color:'#eab308'},
    {label:'Subst. comments', key:'comments_with_body',  color:'#e879a0'},
  ];
  const vsHTML = vsFields.map(f => {
    const maxV = Math.max(...TOP5.map(x => x[f.key]||0)) || 1;
    const val  = e[f.key] || 0;
    const pct  = Math.round((val/maxV)*100);
    const rank = DATA.engineers.filter(x => (x[f.key]||0) > val).length + 1;
    return `<div class="vrow">
      <span class="vlbl">${f.label}</span>
      <div class="vbg"><div class="vfill" style="width:${pct}%;background:${f.color}88"></div></div>
      <span class="vval" style="color:${f.color}">${fmtN(val)}</span>
      <span class="vrank">#${rank}</span>
    </div>`;
  }).join('');

  // ── Recent merged PRs ────────────────────────────────────
  const recent = (DATA.recent_prs||[])
    .filter(p => p.author === e.login && p.state === 'MERGED')
    .sort((a,b) => (b.merged_at||'').localeCompare(a.merged_at||''))
    .slice(0, 6);
  const recentHTML = recent.length
    ? recent.map(p => {
        const m   = p.title.match(/^([a-z]+)[\\/:(]/i);
        const col = TC[m ? m[1].toLowerCase() : ''] || '#64748b';
        return `<div class="prrow">
          <div class="prdot" style="background:${col}"></div>
          <a href="${p.url}" target="_blank" class="prtitle" style="color:var(--text);text-decoration:none" title="${p.title}">${p.title}</a>
          <span class="prnum">#${p.number}</span>
          <span class="prstate merged">merged</span>
        </div>`;
      }).join('')
    : `<span style="color:var(--muted);font-size:.75rem">No merged PRs in loaded dataset — re-run fetch_prs.py + analyze.py</span>`;

  // ── Inject HTML ──────────────────────────────────────────
  document.getElementById('dbody').innerHTML = `

    <!-- row 1 -->
    <div class="card">
      <div class="ctitle">Authored PRs <span class="stag" style="color:var(--blue)">${e.authored_score} pts</span></div>
      <div class="row"><span class="lbl">Merged</span><span class="val g">${e.prs_merged}</span></div>
      <div class="row"><span class="lbl">Merge rate</span><span class="val">${e.merge_rate_pct}%</span></div>
      <div class="row"><span class="lbl">Avg time to merge</span><span class="val d">${fmtD(e.avg_merge_time_days)}</span></div>
      <div class="row"><span class="lbl">Commits</span><span class="val d">${fmtN(e.total_commits)}</span></div>
      <div class="row"><span class="lbl">Files changed</span><span class="val d">${fmtN(e.total_files_changed)}</span></div>
      <div class="row"><span class="lbl">Net lines</span><span class="val d">${fmtN(e.net_lines)}</span></div>
    </div>

    <div class="card">
      <div class="ctitle">Reviews Given <span class="stag" style="color:var(--orange)">${e.review_score} pts</span></div>
      <div class="row">
        <span class="lbl">First approvals
          <span class="tip" data-tip="First approval unblocks a PR for merge.\nScores ${WEIGHTS.first_approval||8} pts each — higher than subsequent approvals.">?</span>
        </span>
        <span class="val g">${e.first_approvals||0}</span>
      </div>
      <div class="row">
        <span class="lbl">Subsequent approvals
          <span class="tip" data-tip="PR already had an approval — still valuable but not the critical unblock.\nScores ${WEIGHTS.subsequent_approval||3} pts each.">?</span>
        </span>
        <span class="val d">${e.subsequent_approvals||0}</span>
      </div>
      <div class="row">
        <span class="lbl">Change req (w/ body)
          <span class="tip" data-tip="Written change request with feedback.\nHighest-signal review action — ${WEIGHTS.change_request_body||7} pts each.">?</span>
        </span>
        <span class="val o">${e.change_requests_with_body||0}</span>
      </div>
      <div class="row"><span class="lbl">Change req (empty)</span><span class="val d">${e.change_requests_empty||0}</span></div>
      <div class="row">
        <span class="lbl">Comments (w/ body)
          <span class="tip" data-tip="Inline review comment with written feedback.\n${WEIGHTS.comment_body||3} pts each.">?</span>
        </span>
        <span class="val b">${e.comments_with_body||0}</span>
      </div>
      <div class="row"><span class="lbl">Comments (empty)</span><span class="val d">${e.comments_empty||0}</span></div>
      <div class="row"><span class="lbl">Unique PRs reviewed</span><span class="val d">${e.unique_prs_reviewed||0}</span></div>
    </div>

    <div class="card">
      <div class="ctitle">PR Type Breakdown</div>
      <div class="ttags">${typeTags||'<span style="color:var(--muted);font-size:.72rem">No type data</span>'}</div>
      <div class="row"><span class="lbl">Additions</span><span class="val g">+${fmtN(e.total_additions)}</span></div>
      <div class="row"><span class="lbl">Deletions</span><span class="val p">-${fmtN(e.total_deletions)}</span></div>
      <div class="row"><span class="lbl">Closed unmerged</span><span class="val d">${e.prs_closed_unmerged}</span></div>
      <div class="row"><span class="lbl">Drafts</span><span class="val d">${e.prs_draft}</span></div>
    </div>

    <!-- row 2 -->
    <div class="card s2">
      <div class="ctitle">
        Score Breakdown — every component that sums to ${e.impact_score} pts
        <span class="tip" data-tip="Every non-zero scoring factor is listed here.\nauth = authored work   rev = review work\nBar width = share of total score.\nBottom row verifies the sum matches the stored total.">?</span>
      </div>
      ${bdHTML || '<span style="color:var(--muted);font-size:.75rem">No components found — re-run analyze.py to regenerate impact.json</span>'}
      ${bdTotal}
    </div>

    <div class="card">
      <div class="ctitle">Consistency & Cadence</div>
      <div class="cstats">
        <div class="cstat">
          <div class="csv" style="color:var(--green)">${wkAvg}</div>
          <div class="csl">avg PRs<br>per week</div>
        </div>
        <div class="cstat">
          <div class="csv" style="color:var(--blue)">${fmtD(e.median_merge_time_days)}</div>
          <div class="csl">median<br>merge time</div>
        </div>
        <div class="cstat">
          <div class="csv" style="color:var(--orange)">${draftPct}%</div>
          <div class="csl">PRs<br>as drafts</div>
        </div>
      </div>
      <div class="shdr">
        <span class="shdr-l">PRs opened per week</span>
        <span class="shdr-r">${wkN} wks · peak&nbsp;${wkPeak}</span>
      </div>
      <div class="swrap"><canvas id="${sparkId}"></canvas></div>
      <div class="sfoot"><span>${wkFirst}</span><span>${wkLast}</span></div>
      <div class="sleg">
        <div class="sleg-box" style="background:#5b8fff88;border:1px solid #5b8fff99"></div>
        <span class="sleg-txt">1 bar = 1 week · height = # PRs opened · brightest bar = peak week · hover for exact count</span>
      </div>
    </div>

    <!-- row 3 -->
    <div class="card">
      <div class="ctitle">
        vs. Top 5
        <span class="tip" data-tip="Bar = value relative to the highest among the top 5.\n#N = global rank among all ${DATA.engineers.length} contributors in the dataset.">?</span>
      </div>
      ${vsHTML}
    </div>

    <div class="card s2">
      <div class="ctitle">Recent Merged PRs</div>
      ${recentHTML}
    </div>
  `;

  // draw sparkline — rendered after DOM paint so canvas is visible
  setTimeout(() => {
    const ctx = document.getElementById(sparkId);
    if (!ctx || !weekly.length) return;
    const peak = Math.max(...weekly.map(w => w.count));
    // Format ISO week label (YYYY-WWW) → short readable label
    function fmtWeek(w) {
      // w is like '2026-W08'
      const parts = w.split('-W');
      if (parts.length !== 2) return w;
      const jan1 = new Date(+parts[0], 0, 1);
      const dayOffset = (parseInt(parts[1]) - 1) * 7;
      const d = new Date(jan1.getTime() + dayOffset * 86400000);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: weekly.map(w => w.week),
        datasets: [{
          label: 'PRs opened',
          data: weekly.map(w => w.count),
          backgroundColor: weekly.map(w =>
            (w.count === peak && peak > 0) ? '#5b8fffdd' : '#5b8fff44'),
          borderColor: weekly.map(w =>
            (w.count === peak && peak > 0) ? '#5b8fff' : '#5b8fff66'),
          borderWidth: 1,
          borderRadius: 2,
        }]
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: items => `Week of ${fmtWeek(items[0].label)}`,
              label: c => `  ${c.raw} PR${c.raw !== 1 ? 's' : ''} opened this week`,
            },
            backgroundColor: '#1c2235',
            borderColor: '#28305a',
            borderWidth: 1,
            titleColor: '#8492b8',
            bodyColor: '#e8ecf4',
            padding: 8,
          }
        },
        scales: {
          x: {
            display: true,
            ticks: {
              maxTicksLimit: 5,
              color: '#5a6485',
              font: { family: "'JetBrains Mono'", size: 8 },
              callback: (_v, i) => {
                // only show first, last and one middle label
                const n = weekly.length;
                if (i === 0 || i === n-1 || i === Math.floor(n/2)) return fmtWeek(weekly[i].week);
                return '';
              },
              maxRotation: 0,
            },
            grid: { display: false },
            border: { display: false },
          },
          y: {
            display: true,
            beginAtZero: true,
            ticks: {
              maxTicksLimit: 4,
              color: '#5a6485',
              font: { family: "'JetBrains Mono'", size: 9 },
              stepSize: 1,
              callback: v => v === 0 ? '' : v,
            },
            grid: { color: '#1e264020' },
            border: { display: false },
          }
        }
      }
    });
  }, 50);
}

// pre-index recent_prs by author for O(1) lookup
window._prs = {};
(DATA.recent_prs || []).forEach(p => {
  if (!window._prs[p.author]) window._prs[p.author] = [];
  window._prs[p.author].push(p);
});

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
