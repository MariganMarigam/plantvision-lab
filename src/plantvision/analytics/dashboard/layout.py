"""Document shell, CSS and vanilla JS for the static dashboard page.

Everything is a string; the only escape hatch is :func:`render_page`, which
stitches the payload, the pre-rendered SVG map and the drawer templates into a
single self-contained document. No external asset is ever referenced.
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from .charts import ChartSpec, chart_defs, sparkline
from .copy import CARDS, TEXTS
from .svg import esc
from .tokens import FONT_STACK, ICONS, css_root

TAB_ORDER: tuple[str, ...] = (
    "overview",
    "crops",
    "growth",
    "shape",
    "data-quality",
    "alerts",
    "compare",
    "capture",
    "method",
)
POPULATED: frozenset[str] = frozenset({"overview", "growth"})
_ICON_KEY: dict[str, str] = {"data-quality": "quality"}
SUBS: dict[str, tuple[str, ...]] = {
    "overview": ("status", "kpi"),
    "growth": ("area-px", "area-cm2", "rate", "daily"),
}

# Filters the controls disable on a tab (mirrors the client ``sync`` rules).
_SCOPE_DISABLED: dict[str, tuple[str, ...]] = {
    "alerts": ("window", "agg", "mode"),
    "method": ("window", "agg", "mode"),
}
_SCOPE_KEYS: tuple[tuple[str, str], ...] = (
    ("crop", "ui.scope.crop"),
    ("window", "ui.scope.window"),
    ("agg", "ui.scope.agg"),
    ("mode", "ui.scope.mode"),
)

# Every UI term the client renderer needs; shipped as compact JSON instead of
# hidden DOM nodes (smaller page, one source for both languages).
JS_TERMS: tuple[str, ...] = (
    "ui.controls.cropAll",
    "ui.filter.invalid",
    "ui.filter.keepOne",
    "ui.filter.capped",
    "ui.filter.aggregate",
    "ui.filter.noFrames",
    "ui.filter.emptyWindow",
    "ui.thr.caption",
    "ui.conclusion.single",
    "ui.chip.not-computable",
    "ui.chip.not-measured",
    "ui.snap.badSchema",
    "ui.snap.filtersDiffer",
    "ui.snap.onlyA",
    "ui.snap.onlyB",
    "ui.snap.unchanged",
    "ui.snap.notComputable",
    "ui.snap.waiting",
    "ui.snap.empty",
    "ui.snap.path",
    "ui.snap.delta",
    "ui.snap.showAll",
    "ui.snap.raw",
    "ui.snap.rawCount",
    "ui.snap.kpi.area",
    "ui.snap.kpi.scale",
    "ui.snap.kpi.freshness",
    "ui.snap.kpi.alerts",
    "ui.snap.h.generated",
    "ui.snap.h.filters",
    "ui.snap.h.window",
    "ui.snap.g.panels",
    "ui.snap.g.alerts",
    "ui.snap.g.sources",
    "ui.snap.col.panel",
    "ui.snap.col.state",
    "ui.snap.col.csv",
    "ui.snap.col.first",
    "ui.snap.col.last",
    "ui.snap.col.frames",
    "ui.snap.shaChanged",
    "ui.snap.shaSame",
    "ui.snap.change.added",
    "ui.snap.change.removed",
    "ui.snap.change.severity",
    "ui.snap.change.value",
    "ui.snap.trend",
    "ui.board.showing",
)

CSS = """
*{box-sizing:border-box}
html{background:var(--pv-bg)}
body{margin:0;background:transparent;color:var(--pv-ink);font:13.5px/1.5 FONT_STACK;
 background-image:radial-gradient(1100px 560px at 12% -12%,rgba(245,112,94,.10),transparent 62%),
 radial-gradient(900px 520px at 102% 4%,rgba(123,63,224,.18),transparent 60%);background-attachment:fixed}
a{color:var(--pv-a1);text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--pv-focus);outline-offset:2px}
.pv-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.pv-skip{position:absolute;left:8px;top:-60px;z-index:100;background:var(--pv-card-2);color:var(--pv-head);padding:8px 14px;border-radius:var(--pv-r-ctrl)}
.pv-skip:focus{top:8px}
.pv-app{display:grid;grid-template-columns:64px minmax(0,1fr);min-height:100dvh}
.pv-rail{position:sticky;top:0;height:100dvh;display:flex;flex-direction:column;align-items:center;gap:6px;
 padding:12px 8px;background:linear-gradient(180deg,#241F42,#1B1730);border-right:1px solid var(--pv-grid);z-index:30}
.pv-rail button{width:48px;height:48px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
 border:0;border-radius:8px;background:transparent;color:var(--pv-mut);cursor:pointer;font:inherit;transition:background .18s,color .18s}
.pv-rail button:hover{background:rgba(255,255,255,.06);color:var(--pv-head)}
.pv-rail button[aria-selected=true]{background:linear-gradient(155deg,var(--pv-a0),var(--pv-a1));color:#241F42}
.pv-rail svg{width:20px;height:20px;flex:none}
.pv-rail-lbl{font-size:9.5px;line-height:1;letter-spacing:.02em;max-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pv-badge{position:absolute;transform:translate(16px,-14px);background:var(--pv-pos);color:#10251C;border-radius:999px;font-size:9px;font-weight:700;padding:1px 5px}
.pv-shell{min-width:0}
.pv-topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:18px;padding:10px 20px;
 background:rgba(27,23,48,.88);backdrop-filter:blur(12px);border-bottom:1px solid var(--pv-grid)}
.pv-crumb{display:flex;align-items:baseline;gap:7px;font-size:13px;color:var(--pv-mut);white-space:nowrap}
.pv-crumb strong{color:var(--pv-head);font-weight:600;font-size:14px}
.pv-subtabs{display:flex;align-items:center;gap:4px;overflow-x:auto;scrollbar-width:none;flex:1;min-width:0}
.pv-subtabs::-webkit-scrollbar{display:none}
.pv-subgroup{display:flex;gap:4px}
.pv-subgroup[hidden]{display:none}
.pv-subtab{border:0;background:transparent;color:var(--pv-mut);font:inherit;font-size:12.5px;padding:6px 10px;border-radius:var(--pv-r-ctrl);
 cursor:pointer;white-space:nowrap;position:relative}
.pv-subtab:hover{color:var(--pv-head);background:rgba(255,255,255,.05)}
.pv-subtab[aria-selected=true]{color:var(--pv-head)}
.pv-subtab[aria-selected=true]::after{content:"";position:absolute;left:8px;right:8px;bottom:0;height:2px;background:var(--pv-a0);border-radius:2px}
.pv-actions{display:flex;align-items:center;gap:10px;margin-left:auto}
.pv-lang{border:1px solid rgba(251,196,144,.45);background:transparent;color:var(--pv-a1);border-radius:var(--pv-r-ctrl);
 font:inherit;font-size:11.5px;font-weight:700;padding:5px 9px;cursor:pointer;letter-spacing:.06em}
.pv-lang:hover{background:rgba(251,196,144,.12)}
.pv-asof{font-size:11.5px;color:var(--pv-mut);font-variant-numeric:tabular-nums;white-space:nowrap}
.pv-main{padding:20px;max-width:1680px;margin:0 auto;overflow-x:clip}
.pv-grid{display:grid;gap:var(--pv-gap);grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-columns:0;align-items:start}
.pv-grid[data-cols="2"]{grid-template-columns:repeat(2,minmax(0,1fr))}
.pv-grid[data-cols="1"]{grid-template-columns:minmax(0,1fr)}
.pv-grid>.pv-card[data-span="2"]{grid-column:span 2}
.pv-grid>.pv-card[data-span="3"]{grid-column:span 3}
.pv-subpanel[hidden]{display:none}
.pv-card{position:relative;background:linear-gradient(155deg,var(--pv-card),#2A254B);border:1px solid transparent;
 border-radius:var(--pv-r-card);padding:var(--pv-pad);min-width:0;transition:transform .18s,border-color .18s}
[data-tier=high] .pv-card:hover{transform:translateY(-2px);border-color:rgba(251,196,144,.4)}
.pv-card-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.pv-card-head h3{margin:0;font-size:16px;font-weight:600;color:var(--pv-head)}
.pv-figure{position:relative;margin:0;min-height:0}
.pv-figure .pv-chart{width:100%;height:auto;display:block}
.pv-chart text{font-size:11.5px;fill:var(--pv-mut);font-family:FONT_STACK}
.pv-chart .pv-ax{fill:var(--pv-mut)}
.pv-chart .pv-last{fill:var(--pv-head);font-size:11.5px;font-weight:600}
.pv-chart .pv-bar-val{fill:var(--pv-head);font-size:11.5px}
.pv-chart .pv-ring-val{fill:var(--pv-head);font-size:19px;font-weight:700}
.pv-chart .pv-donut-val{fill:var(--pv-head);font-size:30px;font-weight:700}
.pv-chart .pv-donut-lbl{fill:var(--pv-mut);font-size:11.5px}
.pv-chart .pv-legend{fill:var(--pv-ink);font-size:11.5px}
.pv-chart .pv-ax-title{fill:var(--pv-mut);font-size:11px}
[data-tier=high] .pv-draw{stroke-dasharray:1;stroke-dashoffset:1;animation:pv-draw 900ms .1s ease-out forwards}
@keyframes pv-draw{to{stroke-dashoffset:0}}
.pv-ringrow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.pv-ring{min-width:0;text-align:center}
.pv-ring svg{width:100%;height:auto;max-width:132px}
.pv-ring-lbl{display:block;font-size:11.5px;color:var(--pv-mut);margin-top:-2px}
.pv-open{position:absolute;inset:0;width:100%;height:100%;border:0;background:transparent;cursor:pointer;border-radius:6px}
.pv-open:focus-visible{outline:2px solid var(--pv-focus);outline-offset:2px}
.pv-explain{display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 10px;font-size:14px;
 border-top:1px solid var(--pv-grid);padding-top:8px;margin:10px 0 0}
.pv-explain dt{color:var(--pv-mut);white-space:nowrap}
.pv-explain dd{margin:0;color:var(--pv-ink);min-width:0}
.pv-concl{font-size:14px;color:var(--pv-ink);border-left:2px solid var(--pv-a0);padding-left:8px;margin:10px 0 0}
.pv-zero{opacity:.6}
.pv-chip{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;
 white-space:nowrap;border:1px solid transparent}
.pv-chip::before{font-size:9px;line-height:1}
.pv-chip[data-state=critical]{background:rgba(245,112,94,.18);color:#FFD2CA;border-color:rgba(245,112,94,.45)}
.pv-chip[data-state=critical]::before{content:"▲"}
.pv-chip[data-state=warn]{background:rgba(251,196,144,.16);color:#FFE1BF;border-color:rgba(251,196,144,.4)}
.pv-chip[data-state=warn]::before{content:"●"}
.pv-chip[data-state=ok]{background:rgba(47,227,167,.14);color:#B9F7DF;border-color:rgba(47,227,167,.35)}
.pv-chip[data-state=ok]::before{content:"✓"}
.pv-chip[data-state=not-measured],.pv-chip[data-state=not-recorded],.pv-chip[data-state=not-computable],.pv-chip[data-state=unknown]{
 background:rgba(255,255,255,.07);color:var(--pv-mut);border-color:rgba(255,255,255,.12)}
.pv-chip[data-state=not-measured]::before,.pv-chip[data-state=not-recorded]::before,
.pv-chip[data-state=not-computable]::before,.pv-chip[data-state=unknown]::before{content:"?"}
.pv-tablewrap{overflow-x:auto;max-width:100%}
.pv-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:12.5px}
.pv-card .pv-table{font-size:12.5px}
.pv-card .pv-table td,.pv-card .pv-table th{padding:4px 6px}
.pv-table caption{text-align:left;color:var(--pv-mut);padding-bottom:6px;font-size:12.5px}
.pv-table th{position:sticky;top:0;background:var(--pv-card);color:var(--pv-mut);text-transform:uppercase;
 letter-spacing:.04em;font-size:11.5px;font-weight:600;padding:6px 8px;text-align:left;border-bottom:1px solid var(--pv-grid)}
.pv-table td{padding:6px 8px;border-bottom:1px solid var(--pv-grid);vertical-align:top}
.pv-table tr:last-child td{border-bottom:0}
.pv-table .num{text-align:right}
.pv-empty{color:var(--pv-mut);background:rgba(255,255,255,.04);border:1px dashed rgba(255,255,255,.12);
 border-radius:8px;padding:14px;margin:0}
.pv-empty-t{color:var(--pv-head);font-weight:600;margin:0 0 4px}
.pv-coming{grid-column:1/-1;text-align:center;padding:56px 20px}
.pv-coming h2{margin:0 0 8px;color:var(--pv-head);font-size:18px}
.pv-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--pv-mut);margin-top:6px}
.pv-legend span{display:inline-flex;align-items:center;gap:5px}
.pv-legend i{width:10px;height:10px;border-radius:2px;display:inline-block}
.pv-backdrop{position:fixed;inset:0;background:rgba(10,8,24,.6);z-index:40;opacity:0;pointer-events:none;transition:opacity .2s}
[data-drawer=open] .pv-backdrop{opacity:1;pointer-events:auto}
.pv-drawer{position:fixed;inset:0 0 0 auto;width:min(76vw,1120px);background:linear-gradient(165deg,#332D5B,#282249);
 z-index:50;overflow-y:auto;transform:translateX(100%);visibility:hidden;transition:transform .24s cubic-bezier(.3,.8,.3,1),visibility 0s .24s;
 box-shadow:-30px 0 60px rgba(10,8,24,.45)}
[data-drawer=open] .pv-drawer{transform:none;visibility:visible;transition:transform .24s cubic-bezier(.3,.8,.3,1)}
.pv-drawer-head{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;padding:12px 18px;
 background:rgba(40,34,73,.94);border-bottom:1px solid var(--pv-grid)}
.pv-close{border:0;border-radius:var(--pv-r-ctrl);background:rgba(255,255,255,.08);color:var(--pv-head);
 font:inherit;font-size:12px;padding:7px 12px;cursor:pointer}
.pv-close:hover{background:rgba(255,255,255,.14)}
.pv-drawer-body{padding:18px 22px 40px;font-size:13.5px}
.pv-drawer-h2{margin:0 0 14px;font-size:19px;color:var(--pv-head)}
.pv-drawer-figure{margin:0 0 16px;background:rgba(27,23,48,.45);border-radius:8px;padding:10px}
.pv-drawer-figure .pv-chart{width:100%;height:auto;max-height:44vh}
.pv-drawer-block{margin:0 0 14px}
.pv-drawer-block h3{margin:0 0 4px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--pv-mut)}
.pv-drawer-block p{margin:0;color:var(--pv-ink)}
.pv-drawer-block dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 14px;margin:0;font-size:13.5px}
.pv-drawer-block dt{color:var(--pv-mut)}
.pv-drawer-block dd{margin:0;font-variant-numeric:tabular-nums}
.pv-thr{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:4px}
.pv-thr i{width:14px;height:2px;border-radius:1px}
.pv-tip{position:fixed;z-index:60;pointer-events:none;background:#221D3E;color:var(--pv-head);border:1px solid rgba(255,255,255,.14);
 border-radius:6px;padding:5px 8px;font-size:11.5px;font-variant-numeric:tabular-nums;white-space:pre-line;box-shadow:0 8px 20px rgba(10,8,24,.4)}
.pv-tip[hidden]{display:none}
@media (max-width:1199px){.pv-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
 .pv-grid>.pv-card[data-span="2"],.pv-grid>.pv-card[data-span="3"]{grid-column:span 2!important}}
@media (max-width:899px){
 .pv-app{grid-template-columns:1fr}
 .pv-rail{position:sticky;top:0;height:auto;flex-direction:row;overflow-x:auto;padding:8px 10px;scroll-snap-type:x proximity}
 .pv-rail button{scroll-snap-align:center}
 .pv-topbar{position:static;flex-wrap:wrap;gap:8px}
 .pv-main{padding:14px}
 .pv-grid{grid-template-columns:minmax(0,1fr)}
 .pv-grid>.pv-card[data-span]{grid-column:span 1!important}
 .pv-card{padding:16px}
 .pv-drawer{width:100vw;border-radius:0}
 .pv-ringrow{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
@media (pointer:coarse){.pv-tip{display:none}}
@media print{
 .pv-rail,.pv-topbar,.pv-drawer,.pv-backdrop,.pv-open{display:none!important}
 .pv-card{break-inside:avoid;background:#fff;color:#111;border-color:#ddd}
 body{background:#fff;color:#111}
 .pv-chart text{fill:#333}
}
""".replace("FONT_STACK", FONT_STACK)

CONTROL_CSS: str = """
.pv-controls{display:flex;align-items:center;gap:6px;min-width:0;overflow:visible;scrollbar-width:none}
.pv-ctl{display:inline-flex;align-items:center;gap:5px;min-height:32px;padding:4px 9px;border:1px solid rgba(251,196,144,.35);border-radius:var(--pv-r-ctrl);background:var(--pv-card-2);color:var(--pv-ink);font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.pv-ctl:hover{border-color:var(--pv-a1);background:#3d3670}.pv-ctl:disabled,.pv-ctl[aria-disabled=true]{opacity:.5;cursor:not-allowed}
.pv-ctl-val{color:var(--pv-a1);font-weight:600}
.pv-pop-wrap{position:relative;display:inline-flex;min-width:0;flex:0 0 auto}
.pv-pop{position:absolute;top:calc(100% + 6px);left:0;z-index:40;padding:10px;min-width:220px;background:var(--pv-card-2);border:1px solid rgba(251,196,144,.35);border-radius:var(--pv-r-card)}
.pv-pop-list{max-height:min(60vh, 420px);overflow:auto}
.pv-pop-done{display:flex;justify-content:center;width:100%;margin-top:8px}
.pv-pop label{display:flex;gap:8px;align-items:center;padding:6px 4px;min-height:32px;cursor:pointer}.pv-pop input{width:16px;height:16px;accent-color:var(--pv-a0)}.pv-pop label .pv-zero{margin-left:auto}
.pv-note{grid-column:1/-1;font-size:12px;color:var(--pv-a1)}.pv-note[hidden]{display:none}
.pv-fresh{display:inline-flex;gap:4px;align-items:center;padding:2px 7px;border-radius:999px;font-size:11px}
.pv-fresh[data-state=fresh]{background:rgba(47,227,167,.16);color:var(--pv-pos)}.pv-fresh[data-state=warn]{background:rgba(251,196,144,.16);color:var(--pv-a1)}.pv-fresh[data-state=stale]{background:rgba(245,112,94,.16);color:var(--pv-neg)}
.pv-snap-backdrop{position:fixed;inset:0;background:rgba(10,8,22,.72);z-index:60}
.pv-snap{position:fixed;inset:5vh 5vw auto;max-height:90vh;overflow:auto;background:var(--pv-card);border:1px solid var(--pv-grid);border-radius:var(--pv-r-card);z-index:61;padding:20px}
.pv-snap[hidden],.pv-snap-backdrop[hidden]{display:none}
.pv-snap textarea{width:100%;min-height:160px;font:12px/1.4 ui-monospace,monospace;background:var(--pv-bg);color:var(--pv-ink);border:1px solid var(--pv-grid);padding:8px}
.pv-framegrid{display:flex;flex-wrap:wrap;gap:8px}.pv-frame{border:0;padding:0;background:transparent;cursor:pointer}.pv-frame img{width:100%;height:auto}
@media (max-width:899px){.pv-topbar{flex-wrap:wrap;overflow-x:clip}.pv-actions{flex:1 1 100%;margin-left:0;flex-wrap:wrap;min-width:0;max-width:100%}.pv-controls{order:3;flex:0 1 100%;width:100%;max-width:100%;overflow:visible;flex-wrap:wrap}.pv-ctl,.pv-lang,.pv-subtab{min-height:44px;min-width:44px}.pv-pop label{min-height:44px}.pv-pop input{width:20px;height:20px}}
@media (max-width:599px){.pv-topbar{backdrop-filter:none}.pv-pop{position:fixed;left:0;right:0;top:auto;bottom:0;max-height:70vh;border-radius:var(--pv-r-card) var(--pv-r-card) 0 0}}
@media print{.pv-controls,.pv-snap,.pv-snap-backdrop{display:none!important}}
"""
B16_CSS: str = """
.pv-panel-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:0 0 10px}
.pv-panel-head .pv-h2{margin:0}
.pv-scope{display:flex;align-items:baseline;gap:6px;margin:0;font-size:12px;color:var(--pv-mut)}
.pv-scope-k{font-weight:600}
.pv-scope .off{text-decoration:line-through;opacity:.6}
.pv-scope-sep{opacity:.45}
.pv-table tfoot td{color:var(--pv-mut);font-size:11.5px;border-top:1px solid var(--pv-grid);border-bottom:0}
tr[hidden]{display:none}
.pv-snap-inputs{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0 10px}
.pv-snap-inputs label{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--pv-mut)}
.pv-diff{display:grid;gap:12px;font-size:12.5px}
.pv-diff-block{min-width:0}
.pv-diff-block h4{margin:0 0 4px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--pv-mut)}
.pv-diff-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.pv-diff-kpi{background:rgba(27,23,48,.42);border:1px solid var(--pv-grid);border-radius:8px;padding:8px 10px;min-width:0}
.pv-diff-kpi h5{margin:0 0 3px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--pv-mut);font-weight:600}
.pv-diff-kpi .pv-kpi-val{font-size:18px;font-weight:700;color:var(--pv-head);font-variant-numeric:tabular-nums}
.pv-diff table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.pv-diff th,.pv-diff td{padding:4px 6px;border-bottom:1px solid var(--pv-grid);text-align:left;vertical-align:middle}
.pv-diff th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--pv-mut);font-weight:600}
.pv-diff td.num,.pv-diff th.num{text-align:right}
.pv-diff tr:last-child td{border-bottom:0}
.pv-diff .pv-side-a{color:#F5705E;font-weight:600}
.pv-diff .pv-side-b{color:#C159F5;font-weight:600}
.pv-diff-spark{width:72px;height:18px;display:block}
.pv-diff .pv-csv{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--pv-mut);font-size:11.5px}
.pv-diff-h{display:grid;gap:2px;font-size:12px;color:var(--pv-mut)}
.pv-diff-h b{color:var(--pv-ink);font-weight:600}
.pv-more{margin-top:6px}
.pv-raw{margin-top:12px}
.pv-raw summary{cursor:pointer;color:var(--pv-mut);font-size:12px}
.pv-raw table{width:100%;border-collapse:collapse;font-size:11.5px;margin-top:6px}
.pv-raw td,.pv-raw th{padding:3px 6px;border-bottom:1px solid var(--pv-grid);text-align:left}
@media (max-width:899px){.pv-diff-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:599px){.pv-diff-kpis{grid-template-columns:minmax(0,1fr)}}
"""

CSS = CSS + CONTROL_CSS + B16_CSS


def _txt(key: str, lang: str) -> str:
    """Localised UI string."""
    return TEXTS[lang].get(key, TEXTS["en"].get(key, key))


def _leaf(
    tag: str,
    en: str,
    ru: str,
    lang: str,
    *,
    attrs: str = "",
    cls: str = "",
) -> str:
    """One translatable leaf element carrying both languages."""
    class_attr = f' class="{cls}"' if cls else ""
    text = en if lang == "en" else ru
    return (
        f'<{tag}{class_attr}{attrs} data-en="{esc(en)}" data-ru="{esc(ru)}">'
        f"{esc(text)}</{tag}>"
    )


def _chip_html(state: str, lang: str) -> str:
    """State chip with its glyph and both translations."""
    en = TEXTS["en"].get(f"ui.chip.{state}", state)
    ru = TEXTS["ru"].get(f"ui.chip.{state}", state)
    return _leaf(
        "span", en, ru, lang, attrs=f' data-state="{esc(state)}"', cls="pv-chip"
    )


def _tab_label(tab: str, lang: str) -> str:
    """Rail/breadcrumb label for a tab."""
    return _txt(f"ui.tab.{tab}", lang)


def _sub_label(tab: str, sub: str, lang: str) -> str:
    """Sub-tab label."""
    return _txt(f"ui.sub.{tab}.{sub}", lang)


def _rail(payload: dict[str, object], active: str, lang: str) -> str:
    """Nine icon tabs with a finding badge on Alerts."""
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    badge = len(findings)
    buttons: list[str] = []
    for tab in TAB_ORDER:
        selected = "true" if tab == active else "false"
        tabindex = "0" if tab == active else "-1"
        label_en = TEXTS["en"][f"ui.tab.{tab}"]
        label_ru = TEXTS["ru"][f"ui.tab.{tab}"]
        short_en = TEXTS["en"][f"ui.rail.{tab}"]
        short_ru = TEXTS["ru"][f"ui.rail.{tab}"]
        full_label = label_en if lang == "en" else label_ru
        badge_html = (
            f'<span class="pv-badge">{badge}</span>'
            if tab == "alerts" and badge
            else ""
        )
        buttons.append(
            f'<button type="button" role="tab" id="pv-tab-{tab}" data-tab="{tab}" '
            f'aria-controls="pv-panel-{tab}" aria-selected="{selected}" '
            f'tabindex="{tabindex}" title="{esc(full_label)}" '
            f'aria-label="{esc(full_label)}">'
            f'<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true"><path d="{esc(ICONS[_ICON_KEY.get(tab, tab)])}"/></svg>'
            f'<span class="pv-rail-lbl" data-en="{esc(short_en)}" '
            f'data-ru="{esc(short_ru)}">{esc(short_en if lang == "en" else short_ru)}</span>'
            f"{badge_html}</button>"
        )
    return (
        '<aside class="pv-rail" id="pv-rail" role="tablist" '
        'aria-label="Dashboard sections">' + "".join(buttons) + "</aside>"
    )


def _overall_verdict(payload: dict[str, object]) -> str:
    """Highest severity across all panel verdicts."""
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    order = {"critical": 0, "warn": 1, "ok": 2, "unknown": 3}
    if not panels:
        return "unknown"
    return min(
        (str(panel.get("verdict", "unknown")) for panel in panels),
        key=lambda value: order.get(value, 9),
    )


def _topbar(
    payload: dict[str, object], active: str, sub: str, lang: str
) -> str:
    """Breadcrumb, sub-tabs, language toggle and status pill."""
    tab_en = _tab_label(active, "en")
    tab_ru = _tab_label(active, "ru")
    crumb = (
        '<div class="pv-crumb"><strong>PLANT_LAB</strong><span>›</span>'
        + _leaf("span", tab_en, tab_ru, lang, attrs=' data-crumb="tab"')
        + f'<span data-crumb="sep"{"" if sub else " hidden"}>›</span>'
        + _leaf(
            "span",
            _sub_label(active, sub, "en") if sub else "",
            _sub_label(active, sub, "ru") if sub else "",
            lang,
            attrs=f' data-crumb="sub"{" hidden" if not sub else ""}',
        )
        + "</div>"
    )
    groups: list[str] = []
    for tab in TAB_ORDER:
        subs = SUBS.get(tab, ())
        if not subs:
            continue
        buttons = []
        for name in subs:
            selected = "true" if tab == active and name == sub else "false"
            label = _leaf(
                "span",
                TEXTS["en"][f"ui.sub.{tab}.{name}"],
                TEXTS["ru"][f"ui.sub.{tab}.{name}"],
                lang,
            )
            buttons.append(
                f'<button type="button" class="pv-subtab" data-tab="{tab}" '
                f'data-sub="{name}" role="tab" aria-selected="{selected}">{label}</button>'
            )
        hidden = "" if tab == active else " hidden"
        groups.append(
            f'<div class="pv-subgroup" data-for-tab="{tab}"{hidden}>'
            + "".join(buttons)
            + "</div>"
        )
    verdict = _overall_verdict(payload)
    if payload.get("generated_at"):
        stamp_en = TEXTS["en"]["ui.generated"].format(
            ts=str(payload["generated_at"])[:16]
        )
        stamp_ru = TEXTS["ru"]["ui.generated"].format(
            ts=str(payload["generated_at"])[:16]
        )
    else:
        stamp_en = TEXTS["en"]["ui.asof"].format(now=str(payload.get("now", ""))[:16])
        stamp_ru = TEXTS["ru"]["ui.asof"].format(now=str(payload.get("now", ""))[:16])
    lang_en, lang_ru = TEXTS["en"]["ui.lang"], TEXTS["ru"]["ui.lang"]
    actions = (
        '<div class="pv-actions">'
        + controls(payload, lang)
        + f'<button type="button" class="pv-lang" id="pv-lang" aria-label="Language">'
        f'<span data-en="{esc(lang_en)}" data-ru="{esc(lang_ru)}">'
        f'{esc(lang_en if lang == "en" else lang_ru)}</span></button>'
        + _leaf("span", stamp_en, stamp_ru, lang, cls="pv-asof")
        + _chip_html(verdict, lang)
        + "</div>"
    )
    return (
        '<header class="pv-topbar">'
        + crumb
        + '<div class="pv-subtabs" role="tablist" aria-label="Sub sections">'
        + "".join(groups)
        + "</div>"
        + actions
        + "</header>"
    )


def _num(value: float | None, decimals: int = 0, lang: str = "en") -> str:
    """Format an optional number with a localized missing label."""
    missing = _txt("ui.chip.not-measured", lang)
    if value is None:
        return missing
    return f"{value:,.{decimals}f}"


def _table(
    caption_en: str,
    caption_ru: str,
    columns: Sequence[tuple[str, str]],
    rows: Sequence[Sequence[str]],
    lang: str,
    *,
    aligns: Sequence[str] | None = None,
) -> str:
    """Accessible table with a caption and scoped column headers."""
    alignment = list(aligns or [""] * len(columns))
    head = "".join(
        f'<th scope="col"{(" class=\"num\"" if alignment[index] == "num" else "")}>'
        f'<span data-en="{esc(en)}" data-ru="{esc(ru)}">{esc(en if lang == "en" else ru)}</span></th>'
        for index, (en, ru) in enumerate(columns)
    )
    if not rows:
        body = (
            f'<tr><td colspan="{len(columns)}" class="pv-empty">'
            + _leaf(
                "span",
                TEXTS["en"]["ui.empty.notmeasured"],
                TEXTS["ru"]["ui.empty.notmeasured"],
                lang,
            )
            + "</td></tr>"
        )
    else:
        body = "".join(
            "<tr>"
            + "".join(
                f'<td{(" class=\"num\"" if alignment[index] == "num" else "")}>'
                f"{esc(str(cell))}</td>"
                for index, cell in enumerate(row)
            )
            + "</tr>"
            for row in rows
        )
    return (
        '<div class="pv-tablewrap"><table class="pv-table">'
        f'<caption data-en="{esc(caption_en)}" data-ru="{esc(caption_ru)}">'
        f"{esc(caption_en if lang == 'en' else caption_ru)}</caption>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _board_table(payload: dict[str, object], lang: str) -> str:
    """Overview status board with a per-panel area sparkline.

    Rows carry ``data-panel`` so the client can hide the panels the crop filter
    drops; the footer count follows the visible rows.
    """
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    settings = {"en": ("Panel", "Frames", "Days", "Age", "Verdict", "Area px"),
                "ru": ("Панель", "Кадры", "Дни", "Возраст", "Вердикт", "Площадь px")}
    columns = list(zip(settings["en"], settings["ru"]))
    rows: list[str] = []
    for panel in panels:
        series = panel.get("series") if isinstance(panel.get("series"), dict) else {}
        area = series.get("area_px") if isinstance(series.get("area_px"), dict) else {}
        values = [value for run in area.get("runs", []) for _ts, value in run]
        spark = (
            sparkline(
                ChartSpec(
                    chart_id=f"sp-{panel.get('id', '')}",
                    title=str(panel.get("label", "")),
                    desc="Projected area trend for this panel.",
                ),
                values,
                width=140,
                height=36,
            )
            if len(values) >= 2
            else esc(_txt("ui.chip.not-measured", lang))
        )
        rows.append(
            f'<tr data-panel="{esc(str(panel.get("id", "")))}">'
            f"<td>{esc(str(panel.get('label', '')))}</td>"
            f'<td class="num">{esc(str(panel.get("rows", 0)))}</td>'
            f'<td class="num">{esc(str(panel.get("days", 0)))}</td>'
            f'<td class="num">{esc(_num(panel.get("age_days"), 1, lang))}</td>'
            f"<td>{_chip_html(str(panel.get('verdict', 'unknown')), lang)}</td>"
            f"<td>{spark}</td>"
            "</tr>"
        )
    head = "".join(
        f'<th scope="col">'
        + _leaf("span", en, ru, lang)
        + "</th>"
        for en, ru in columns
    )
    caption = "Panel status" if lang == "en" else "Состояние панелей"
    count = _txt("ui.board.showing", lang).replace("{n}", str(len(panels))).replace(
        "{total}", str(len(panels))
    )
    return (
        '<div class="pv-tablewrap"><table class="pv-table" data-board="1">'
        f'<caption data-en="Panel status" data-ru="Состояние панелей">{caption}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}"
        '<tr data-board-empty hidden><td colspan="6" class="pv-empty">'
        + _leaf(
            "span",
            TEXTS["en"]["ui.filter.emptyWindow"],
            TEXTS["ru"]["ui.filter.emptyWindow"],
            lang,
        )
        + "</td></tr></tbody><tfoot><tr><td colspan=\"6\" class=\"num\">"
        f'<span data-board-count>{esc(count)}</span>'
        "</td></tr></tfoot></table></div>"
    )


def _daily_table(payload: dict[str, object], lang: str) -> str:
    """Daily summary table (frames, median/min/max, delta vs previous day)."""
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    settings = {
        "en": ("Panel", "Day", "Frames", "Median", "Min", "Max", "Δ"),
        "ru": ("Панель", "День", "Кадры", "Медиана", "Мин", "Макс", "Δ"),
    }
    columns = list(zip(settings["en"], settings["ru"]))
    rows: list[Sequence[str]] = []
    missing = _txt("ui.chip.not-measured", lang)
    for panel in panels:
        previous: float | None = None
        label = str(panel.get("label", "")).split(" · ")[0]
        for bucket in panel.get("daily", []):
            median = bucket.get("median_area_px")
            delta = (
                float(median) - previous
                if median is not None and previous is not None
                else None
            )
            rows.append(
                [
                    label,
                    str(bucket.get("date", ""))[8:10] + "." + str(bucket.get("date", ""))[5:7],
                    str(bucket.get("frames", 0)),
                    _num(median, 0, lang) if median is not None else missing,
                    _num(bucket.get("min_area_px"), 0, lang) if bucket.get("min_area_px") is not None else missing,
                    _num(bucket.get("max_area_px"), 0, lang) if bucket.get("max_area_px") is not None else missing,
                    f"{delta:+,.0f}" if delta is not None else "—",
                ]
            )
            if median is not None:
                previous = float(median)
    return _table(
        "Daily summary",
        "Сводка по дням",
        columns,
        rows,
        lang,
        aligns=("", "", "num", "num", "num", "num", "num"),
    )


def _card(
    card: dict[str, object],
    svg: str,
    payload: dict[str, object],
    lang: str,
    cols: int = 3,
    frames: dict[str, str] | None = None,
) -> str:
    """One bento card with its explainer strip and conclusion."""
    card_id = str(card["id"])
    span = max(1, int(card.get("span", 1) or 1))
    clamped = max(1, min(span, cols))
    chart = str(card.get("chart", ""))
    if chart == "board":
        figure = _board_table(payload, lang)
    elif chart == "table":
        figure = _daily_table(payload, lang)
    elif chart == "image":
        figure = _image_grid(payload, card_id, frames or {})
    elif svg:
        figure = svg
    else:
        figure = (
            '<div class="pv-empty" role="note" data-state="not-measured">'
            + _leaf(
                "p",
                TEXTS["en"]["ui.empty.notmeasured"],
                TEXTS["ru"]["ui.empty.notmeasured"],
                lang,
                cls="pv-empty-t",
            )
            + _leaf(
                "p",
                TEXTS["en"]["ui.empty.notmeasured.body"],
                TEXTS["ru"]["ui.empty.notmeasured.body"],
                lang,
            )
            + "</div>"
        )
    title_en = str(card["title_en"])
    title_ru = str(card["title_ru"])
    open_label = _txt("ui.open", lang).format(title=title_en if lang == "en" else title_ru)
    explain = "".join(
        _leaf("dt", TEXTS["en"][f"ui.explain.{field}"], TEXTS["ru"][f"ui.explain.{field}"], lang)
        + _leaf(
            "dd",
            str(card[f"{field}_en"]),
            str(card[f"{field}_ru"]),
            lang,
            attrs=f' data-field="{field}"',
        )
        for field in ("what", "how", "now", "do")
    )
    return (
        f'<article class="pv-card" id="pv-card-{card_id}" data-chart="{card_id}" '
        f'data-tab="{esc(str(card["tab"]))}" data-sub="{esc(str(card["sub"]))}" '
        f'data-span="{clamped}" '
        f'data-render="{esc(str(card.get("render", "static")))}" '
        f'data-filter-scope="{esc(str(card.get("filter_scope", "all-panels")))}" '
        f'data-card-key="{esc(str(card.get("key", "")))}" '
        f'data-key="{esc("area_cm2" if "cm2" in card_id else "area_px" if "area-px" in card_id else "")}">'
        '<header class="pv-card-head">'
        + _leaf("h3", title_en, title_ru, lang)
        + _chip_html(str(card.get("state", "ok")), lang)
        + "</header>"
        '<figure class="pv-figure">'
        + figure
        + f'<button type="button" class="pv-open" aria-label="{esc(open_label)}">'
        '<span class="pv-sr">Open detail</span></button>'
        "</figure>"
        f'<dl class="pv-explain">{explain}</dl>'
        + _leaf(
            "p",
            str(card["conclusion_en"]),
            str(card["conclusion_ru"]),
            lang,
            attrs=' data-concl="1"',
            cls="pv-concl",
        )
        + "</article>"
    )


def _panel(
    tab: str,
    payload: dict[str, object],
    svgs: dict[str, str],
    frames: dict[str, str],
    lang: str,
    active: str,
) -> str:
    """One tabpanel; populated tabs get cards, the rest a gate-2 notice."""
    hidden = "" if tab == active else " hidden"
    label_en = TEXTS["en"][f"ui.tab.{tab}"]
    label_ru = TEXTS["ru"][f"ui.tab.{tab}"]
    heading = _leaf("h2", label_en, label_ru, lang, attrs=' tabindex="-1"', cls="pv-h2")
    if tab not in POPULATED:
        body = (
            '<div class="pv-empty pv-coming">'
            + _leaf("h2", TEXTS["en"]["ui.coming.title"], TEXTS["ru"]["ui.coming.title"], lang)
            + _leaf("p", TEXTS["en"]["ui.coming.body"], TEXTS["ru"]["ui.coming.body"], lang)
            + "</div>"
        )
        return (
            f'<section role="tabpanel" id="pv-panel-{tab}" aria-labelledby="pv-tab-{tab}"'
            f'{hidden}><div class="pv-panel-head">{heading}</div>'
            f"{body}</section>"
        )
    cards = [
        card
        for card in payload.get("cards", [])
        if isinstance(card, dict) and card.get("tab") == tab
    ]
    groups: list[str] = []
    for index, sub in enumerate(SUBS.get(tab, ())):
        sub_hidden = "" if index == 0 else " hidden"
        sub_cards = [card for card in cards if card.get("sub") == sub]
        cols = max(1, min(len(sub_cards), 3))
        markup = "".join(
            _card(card, svgs.get(str(card["id"]), ""), payload, lang, cols, frames)
            for card in sub_cards
        )
        groups.append(
            f'<div class="pv-subpanel" data-tab="{tab}" data-sub="{sub}"{sub_hidden}>'
            f'<div class="pv-grid" data-cols="{cols}">{markup or ""}</div></div>'
        )
    return (
        f'<section role="tabpanel" id="pv-panel-{tab}" aria-labelledby="pv-tab-{tab}"'
        f'{hidden}><div class="pv-panel-head">{heading}</div>'
        + "".join(groups)
        + "</section>"
    )


def _source_text(payload: dict[str, object]) -> str:
    """CSV path and pipeline version per panel."""
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    return "; ".join(
        f"{panel.get('label', '')}: {panel.get('source', '')} "
        f"({panel.get('pipeline_version', '')})"
        for panel in panels
    )


def _drawer(lang: str) -> str:
    """Static drawer shell; the body is filled by cloning a template."""
    return (
        '<div class="pv-backdrop"></div>'
        '<aside id="pv-drawer" class="pv-drawer" role="dialog" aria-modal="true" '
        f'aria-label="{esc(_txt("ui.close", lang))}">'
        '<div class="pv-drawer-head">'
        f'<button type="button" class="pv-close" data-close data-en="'
        f'{esc(TEXTS["en"]["ui.close"])}" data-ru="{esc(TEXTS["ru"]["ui.close"])}">'
        f'{esc(_txt("ui.close", lang))}</button>'
        "</div>"
        '<div class="pv-drawer-body" id="pv-drawer-body"></div>'
        "</aside>"
    )


def freshness_chips(payload: dict[str, object], lang: str) -> str:
    """One freshness chip per panel: label · age, state fresh|warn|stale."""
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    chips: list[str] = []
    title = _txt("ui.fresh.label", lang)
    for panel in panels:
        age = panel.get("age_days")
        if age is None:
            state = "stale"
            value = _txt("ui.chip.not-measured", lang)
        else:
            age_value = float(age)
            state = "fresh" if age_value < 2 else "warn" if age_value < 7 else "stale"
            value = f"{age_value:.1f} d"
        chips.append(
            f'<span class="pv-fresh" data-state="{state}" '
            f'data-panel="{esc(str(panel.get("id", "")))}" title="{esc(title)}">'
            f'{esc(str(panel.get("label", "")))} · {esc(value)}</span>'
        )
    return "".join(chips)


def _select(
    control_id: str,
    values: Sequence[object],
    labels: Sequence[str],
    lang: str,
) -> str:
    """One filter select with bilingual option labels."""
    options: list[str] = []
    for value, label in zip(values, labels):
        en = TEXTS["en"][label]
        ru = TEXTS["ru"][label]
        options.append(
            f'<option value="{esc(str(value))}" data-en="{esc(en)}" '
            f'data-ru="{esc(ru)}">{esc(en if lang == "en" else ru)}</option>'
        )
    return (
        f'<select class="pv-ctl" id="{control_id}" aria-label="{esc(labels[0])}">'
        + "".join(options)
        + "</select>"
    )


def controls(payload: dict[str, object], lang: str) -> str:
    """Crop popover, window/aggregation/mode selects, reset and snapshot buttons."""
    crops = payload.get("crops") if isinstance(payload.get("crops"), list) else []
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    crop_label = _leaf(
        "span", TEXTS["en"]["ui.controls.crop"], TEXTS["ru"]["ui.controls.crop"], lang
    )
    crop_value = _leaf(
        "span",
        TEXTS["en"]["ui.controls.cropAll"],
        TEXTS["ru"]["ui.controls.cropAll"],
        lang,
        cls="pv-ctl-val",
    ).replace("<span", '<span id="pv-f-crop-val"', 1)
    rows: list[str] = []
    for crop in crops:
        name = str(crop.get("name", ""))
        count = int(crop.get("rows", 0) or 0)
        rows.append(
            f'<label><input type="checkbox" class="pv-crop-box" '
            f'value="{esc(name)}" checked>'
            f'<span>{esc(name)}</span><span class="pv-zero">{count}</span></label>'
        )
    done = _leaf(
        "button",
        TEXTS["en"]["ui.controls.done"],
        TEXTS["ru"]["ui.controls.done"],
        lang,
        attrs=' type="button" id="pv-crop-done"',
        cls="pv-ctl pv-ctl-btn pv-pop-done",
    )
    popover = (
        f'<div id="pv-crop-pop" class="pv-pop" hidden role="dialog" '
        f'aria-label="{esc(_txt("ui.controls.crop", lang))}">'
        '<div class="pv-pop-list">'
        + "".join(rows)
        + "</div>"
        + done
        + "</div>"
    )
    crop_filter = (
        '<div class="pv-pop-wrap">'
        f'<button type="button" id="pv-f-crop" class="pv-ctl" aria-expanded="false" '
        f'aria-haspopup="true" aria-controls="pv-crop-pop">'
        f"{crop_label}{crop_value}</button>"
        + popover
        + "</div>"
    )
    windows = _select(
        "pv-f-window",
        filters.get("windows", ()),
        ("ui.controls.w24", "ui.controls.w7", "ui.controls.w30", "ui.controls.wAll"),
        lang,
    )
    aggs = _select(
        "pv-f-agg",
        filters.get("aggs", ()),
        ("ui.controls.raw", "ui.controls.hourly", "ui.controls.daily"),
        lang,
    )
    modes = _select(
        "pv-f-mode",
        filters.get("modes", ()),
        ("ui.controls.abs", "ui.controls.idx", "ui.controls.delta"),
        lang,
    )
    reset = (
        f'<button type="button" id="pv-f-reset" class="pv-ctl pv-ctl-btn" disabled>'
        f"{esc(_txt('ui.controls.reset', lang))}</button>"
    )
    snap = (
        f'<button type="button" id="pv-f-snap" class="pv-ctl pv-ctl-btn" '
        f'aria-haspopup="dialog" aria-controls="pv-snap">'
        f"{esc(_txt('ui.controls.snapshot', lang))}</button>"
    )
    return (
        '<div class="pv-controls" role="group" aria-label="Filters">'
        + crop_filter
        + windows
        + aggs
        + modes
        + reset
        + snap
        + '</div><div id="pv-filter-note" role="status" class="pv-note" hidden></div>'
    )


def snapshot_dialog(lang: str) -> str:
    """Modal with an Export pane and a Diff pane (two file inputs + result table)."""
    title = _leaf("h2", TEXTS["en"]["ui.snap.title"], TEXTS["ru"]["ui.snap.title"], lang)
    title = title.replace("<h2", '<h2 id="pv-snap-h2"', 1)
    export_label = _leaf(
        "span", TEXTS["en"]["ui.snap.export"], TEXTS["ru"]["ui.snap.export"], lang
    )
    diff_label = _leaf(
        "span", TEXTS["en"]["ui.snap.diff"], TEXTS["ru"]["ui.snap.diff"], lang
    )
    return (
        '<div class="pv-snap-backdrop" hidden></div>'
        '<div id="pv-snap" class="pv-snap" role="dialog" aria-modal="true" '
        'aria-labelledby="pv-snap-h2" hidden>'
        '<div class="pv-snap-head">'
        + title
        + '<button type="button" class="pv-close" data-snap-close>'
        + esc(_txt("ui.snap.close", lang))
        + "</button></div>"
        '<div class="pv-snap-tabs" role="tablist">'
        f'<button type="button" class="pv-subtab" data-snap-tab="export" '
        f'role="tab" aria-selected="true">{export_label}</button>'
        f'<button type="button" class="pv-subtab" data-snap-tab="diff" '
        f'role="tab" aria-selected="false">{diff_label}</button>'
        "</div>"
        '<section data-snap-pane="export">'
        f'<button type="button" class="pv-ctl" id="pv-snap-dl">'
        f'{esc(_txt("ui.snap.download", lang))}</button>'
        f'<button type="button" class="pv-ctl" id="pv-snap-copy">'
        f'{esc(_txt("ui.snap.copy", lang))}</button>'
        '<code id="pv-snap-name"></code>'
        '<textarea id="pv-snap-text" readonly '
        f'aria-label="{esc(_txt("ui.snap.title", lang))}"></textarea>'
        "</section>"
        '<section data-snap-pane="diff" hidden>'
        f'<div class="pv-snap-inputs"><label><span>{esc(_txt("ui.snap.diff", lang))} A</span>'
        '<input type="file" accept="application/json, .json" id="pv-snap-a"></label>'
        f'<label><span>{esc(_txt("ui.snap.diff", lang))} B</span>'
        '<input type="file" accept="application/json, .json" id="pv-snap-b"></label></div>'
        '<div id="pv-snap-banner" role="status" hidden></div>'
        '<div id="pv-snap-diff" class="pv-diff" role="region" '
        f'aria-label="{esc(_txt("ui.snap.diff", lang))}"></div>'
        '<details class="pv-raw" id="pv-snap-raw">'
        f'<summary>{esc(_txt("ui.snap.raw", lang))}</summary>'
        f'<table id="pv-snap-table"><caption>{esc(_txt("ui.snap.diff", lang))}</caption>'
        '<thead><tr><th scope="col">path</th><th scope="col">A</th>'
        '<th scope="col">B</th><th scope="col">Δ</th></tr></thead>'
        "<tbody></tbody></table>"
        "</details>"
        "</section>"
        "</div>"
    )


def _image_grid(
    payload: dict[str, object], card_id: str, frames: dict[str, str]
) -> str:
    """Last-frame tiles (or the full gallery) with an honest missing state."""
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    records = payload.get("frames") if isinstance(payload.get("frames"), list) else []
    selected: list[dict[str, object]] = []
    if card_id == "ca-gallery":
        selected = [record for record in records if isinstance(record, dict)]
    else:
        for panel in panels:
            panel_id = str(panel.get("id", ""))
            last = None
            for record in records:
                if not isinstance(record, dict) or record.get("panel") != panel_id:
                    continue
                total = int(record.get("total", 0) or 0)
                index = int(record.get("index", -1) or -1)
                if total > 0 and index == total - 1:
                    last = record
            if last is not None:
                selected.append(last)
    tiles: list[str] = []
    for record in selected:
        frame_id = str(record.get("id", ""))
        source = frames.get(frame_id, "")
        alt = str(record.get("alt", ""))
        if not source:
            continue
        tiles.append(
            f'<button class="pv-frame" data-frame="{esc(frame_id)}" '
            f'aria-label="{esc(alt)}"><img src="{source}" alt="{esc(alt)}" '
            'width="288" height="162" loading="lazy"></button>'
        )
    if tiles:
        return '<div class="pv-framegrid">' + "".join(tiles) + "</div>"
    return _leaf(
        "div",
        TEXTS["en"]["ui.chip.not-recorded"],
        TEXTS["ru"]["ui.chip.not-recorded"],
        "en",
        attrs=' data-state="not-recorded"',
        cls="pv-empty",
    )


def _templates(cards: Sequence[dict[str, object]], payload: dict[str, object], lang: str) -> str:
    """One data template per card: the drawer's only content source."""
    source = _source_text(payload)
    templates: list[str] = []
    for card in cards:
        card_id = str(card["id"])
        axes = card.get("axes") if isinstance(card.get("axes"), dict) else {}
        thresholds = card.get("thresholds") if isinstance(card.get("thresholds"), list) else []
        stats = card.get("stats") if isinstance(card.get("stats"), list) else []
        blocks = [
            '<section class="pv-drawer-block" data-block="what">'
            + _leaf("h3", TEXTS["en"]["ui.explain.what"], TEXTS["ru"]["ui.explain.what"], lang)
            + _leaf("p", str(card["what_en"]), str(card["what_ru"]), lang)
            + "</section>",
            '<section class="pv-drawer-block" data-block="how">'
            + _leaf("h3", TEXTS["en"]["ui.explain.how"], TEXTS["ru"]["ui.explain.how"], lang)
            + _leaf("p", str(card["how_en"]), str(card["how_ru"]), lang)
            + "</section>",
            '<section class="pv-drawer-block" data-block="now">'
            + _leaf("h3", TEXTS["en"]["ui.explain.now"], TEXTS["ru"]["ui.explain.now"], lang)
            + _leaf("p", str(card["now_en"]), str(card["now_ru"]), lang)
            + "</section>",
            '<section class="pv-drawer-block" data-block="do">'
            + _leaf("h3", TEXTS["en"]["ui.explain.do"], TEXTS["ru"]["ui.explain.do"], lang)
            + _leaf("p", str(card["do_en"]), str(card["do_ru"]), lang)
            + "</section>",
        ]
        if axes:
            blocks.append(
                '<section class="pv-drawer-block" data-block="axes">'
                + _leaf("h3", TEXTS["en"]["ui.drawer.axes"], TEXTS["ru"]["ui.drawer.axes"], lang)
                + "<dl>"
                + _leaf("dt", TEXTS["en"]["ui.axes.x"], TEXTS["ru"]["ui.axes.x"], lang)
                + _leaf("dd", str(axes.get("x_en", "")), str(axes.get("x_ru", "")), lang)
                + _leaf("dt", TEXTS["en"]["ui.axes.y"], TEXTS["ru"]["ui.axes.y"], lang)
                + _leaf("dd", str(axes.get("y_en", "")), str(axes.get("y_ru", "")), lang)
                + _leaf("dt", TEXTS["en"]["ui.axes.step"], TEXTS["ru"]["ui.axes.step"], lang)
                + _leaf("dd", str(axes.get("step_en", "")), str(axes.get("step_ru", "")), lang)
                + "</dl></section>"
            )
        if thresholds:
            rows = []
            for threshold in thresholds:
                colour = "#FBC490" if threshold.get("kind") == "warn" else "#F5705E"
                rows.append(
                    f'<div class="pv-thr"><i style="background:{colour}"></i>'
                    + _leaf(
                        "span",
                        str(threshold.get("label_en", "")),
                        str(threshold.get("label_ru", "")),
                        lang,
                    )
                    + f"<strong>{esc(str(threshold.get('value', '')))}</strong></div>"
                )
            blocks.append(
                '<section class="pv-drawer-block" data-block="thresholds">'
                + _leaf("h3", TEXTS["en"]["ui.drawer.thresholds"], TEXTS["ru"]["ui.drawer.thresholds"], lang)
                + "".join(rows)
                + "</section>"
            )
        if stats:
            rows = []
            for item in stats:
                rows.append(
                    _leaf("dt", str(item.get("label_en", "")), str(item.get("label_ru", "")), lang)
                    + _leaf("dd", str(item.get("value_en", "")), str(item.get("value_ru", "")), lang)
                )
            blocks.append(
                '<section class="pv-drawer-block" data-block="stats">'
                + _leaf("h3", TEXTS["en"]["ui.drawer.stats"], TEXTS["ru"]["ui.drawer.stats"], lang)
                + f'<dl>{"".join(rows)}</dl></section>'
            )
        blocks.append(
            '<section class="pv-drawer-block" data-block="source">'
            + _leaf("h3", TEXTS["en"]["ui.drawer.source"], TEXTS["ru"]["ui.drawer.source"], lang)
            + _leaf("p", source, source, lang)
            + "</section>"
        )
        blocks.append(
            '<section class="pv-drawer-block" data-block="plain">'
            + _leaf("h3", TEXTS["en"]["ui.explain.plain"], TEXTS["ru"]["ui.explain.plain"], lang)
            + _leaf("p", str(card["conclusion_en"]), str(card["conclusion_ru"]), lang)
            + "</section>"
        )
        templates.append(
            f'<template id="pv-tpl-{card_id}" data-tab="{esc(str(card["tab"]))}" '
            f'data-sub="{esc(str(card["sub"]))}" data-title-en="{esc(str(card["title_en"]))}" '
            f'data-title-ru="{esc(str(card["title_ru"]))}">'
            + _leaf(
                "h2",
                str(card["title_en"]),
                str(card["title_ru"]),
                lang,
                attrs=f' id="pv-drawer-title-{card_id}"',
                cls="pv-drawer-h2",
            )
            + f'<figure class="pv-drawer-figure" data-clone-chart="{card_id}"></figure>'
            + "".join(blocks)
            + "</template>"
        )
    return "".join(templates)


def _strip_defs(svgs: dict[str, str]) -> dict[str, str]:
    """Remove per-chart ``<defs>`` blocks; the page carries one global copy.

    Args:
        svgs: Chart markup keyed by card id.

    Returns:
        A map with all defs blocks removed.
    """
    return {
        card_id: re.sub(r"<defs>.*?</defs>", "", markup, flags=re.S)
        for card_id, markup in svgs.items()
    }


def render_page(
    payload: dict[str, object],
    svgs: dict[str, str],
    *,
    frames: dict[str, str] | None = None,
    js: str = "",
    lang: str = "en",
) -> str:
    """Assemble the complete self-contained HTML document.

    Args:
        payload: Page payload (``cards`` must already be filled).
        svgs: Pre-rendered chart markup keyed by card id.
        frames: Base64 frame assets keyed by frame id (unused in gate 1 cards).
        js: Inline JavaScript text.
        lang: Initial language, ``en`` or ``ru``.

    Returns:
        The HTML document.

    Raises:
        ValueError: For an unknown language, no panels, or duplicate card ids.
    """
    if lang not in {"en", "ru"}:
        raise ValueError(f"unsupported language: {lang}")
    panels = payload.get("panels")
    if not panels:
        raise ValueError("payload has no panels")
    cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
    ids = [str(card.get("id", "")) for card in cards]
    if len(set(ids)) != len(ids):
        duplicate = next(card_id for card_id in ids if ids.count(card_id) > 1)
        raise ValueError(f"duplicate card id: {duplicate}")
    active = TAB_ORDER[0]
    svgs = _strip_defs(svgs)
    data_json = json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True
    ).replace("</", "<\\/")
    labels_json = json.dumps(
        {
            "tabs": {
                tab: {"en": TEXTS["en"][f"ui.tab.{tab}"], "ru": TEXTS["ru"][f"ui.tab.{tab}"]}
                for tab in TAB_ORDER
            },
            "subs": {
                f"{tab}/{sub}": {
                    "en": TEXTS["en"][f"ui.sub.{tab}.{sub}"],
                    "ru": TEXTS["ru"][f"ui.sub.{tab}.{sub}"],
                }
                for tab, subtabs in SUBS.items()
                for sub in subtabs
            },
            "terms": {
                key: {"en": TEXTS["en"][key], "ru": TEXTS["ru"][key]}
                for key in JS_TERMS
            },
            "scope": {
                "label": {
                    "en": TEXTS["en"]["ui.scope.label"],
                    "ru": TEXTS["ru"]["ui.scope.label"],
                },
                "keys": [
                    {"key": key, "en": TEXTS["en"][text_key], "ru": TEXTS["ru"][text_key]}
                    for key, text_key in _SCOPE_KEYS
                ],
                "off": {tab: list(keys) for tab, keys in _SCOPE_DISABLED.items()},
            },
        },
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    ).replace("</", "<\\/")
    panels_html = "".join(
        _panel(tab, payload, svgs, frames or {}, lang, active) for tab in TAB_ORDER
    )
    document = (
        "<!doctype html>"
        f'<html lang="{lang}">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(str(payload.get('title', 'dashboard')))}</title>"
        f"<style>{css_root()}{CSS}</style>"
        "</head>"
        f'<body data-drawer="closed" data-tab="{active}" data-lang="{lang}">'
        '<svg class="pv-defs" aria-hidden="true" focusable="false" '
        'style="position:absolute;width:0;height:0;overflow:hidden">'
        f"{chart_defs()}</svg>"
        f'<a class="pv-skip" href="#pv-main" data-en="{esc(TEXTS["en"]["ui.skip"])}" '
        f'data-ru="{esc(TEXTS["ru"]["ui.skip"])}">{esc(_txt("ui.skip", lang))}</a>'
        '<div class="pv-app">'
        + _rail(payload, active, lang)
        + '<div class="pv-shell">'
        + _topbar(payload, active, SUBS[active][0], lang)
        + '<main class="pv-main" id="pv-main">'
        + '<p class="pv-scope" id="pv-scope"></p>'
        + f"{panels_html}</main>"
        "</div></div>"
        + _drawer(lang)
        + snapshot_dialog(lang)
        + _templates(cards, payload, lang)
        + f'<script type="application/json" id="pv-data">{data_json}</script>'
        + f'<script type="application/json" id="pv-labels">{labels_json}</script>'
        + f"<script>{js}</script>"
        "</body></html>"
    )
    return document


_JS_CORE = r"""
(function () {
  "use strict";
  var state = { lang: document.documentElement.lang === "ru" ? "ru" : "en", opener: null, tab: null };
  var payload = null;
  try { payload = JSON.parse(document.getElementById("pv-data").textContent); } catch (err) { payload = null; }
  var labels = null;
  try { labels = JSON.parse(document.getElementById("pv-labels").textContent); } catch (err) { labels = null; }
  var rail = document.getElementById("pv-rail");
  var main = document.getElementById("pv-main");
  var drawer = document.getElementById("pv-drawer");
  var drawerBody = document.getElementById("pv-drawer-body");
  var backdrop = document.querySelector(".pv-backdrop");
  var tip = null;

  function tabs() {
    return Array.prototype.map.call(rail.querySelectorAll("[role=tab]"), function (button) {
      return button.getAttribute("data-tab");
    });
  }

  function subsFor(tab) {
    var group = document.querySelector('.pv-subgroup[data-for-tab="' + tab + '"]');
    if (!group) { return []; }
    return Array.prototype.map.call(group.querySelectorAll(".pv-subtab"), function (button) {
      return button.getAttribute("data-sub");
    });
  }

  function parseRoute(hash) {
    var raw = (hash || "").replace(/^#\/?/, "");
    var bang = raw.indexOf("!");
    var filterRaw = bang >= 0 ? raw.slice(bang + 1) : "";
    if (bang >= 0) { raw = raw.slice(0, bang); }
    var chart = null;
    var tilde = raw.indexOf("~");
    if (tilde >= 0) {
      chart = decodeURIComponent(raw.slice(tilde + 1));
      raw = raw.slice(0, tilde);
    }
    var parts = raw.split("/").filter(Boolean);
    var known = tabs();
    var tab = parts[0] || "overview";
    if (known.indexOf(tab) < 0) {
      return { tab: "overview", sub: subsFor("overview")[0] || "", chart: null, filter: parseFilters(filterRaw) };
    }
    var subs = subsFor(tab);
    var sub = parts[1] || subs[0] || "";
    if (subs.length && subs.indexOf(sub) < 0) { sub = subs[0]; }
    if (chart) {
      var template = document.getElementById("pv-tpl-" + chart);
      if (template) {
        tab = template.getAttribute("data-tab") || tab;
        sub = template.getAttribute("data-sub") || sub;
      }
    }
    return { tab: tab, sub: sub, chart: chart, filter: parseFilters(filterRaw) };
  }

  function renderScope(tab) {
    var el = document.getElementById("pv-scope");
    if (!el || !labels || !labels.scope) { return; }
    var block = labels.scope, lang = state.lang, off = (block.off || {})[tab] || [], parts = ['<span class="pv-scope-k">' + E(block.label[lang] || block.label.en) + "</span>"];
    block.keys.forEach(function (k, i) {
      if (i) { parts.push('<span class="pv-scope-sep">·</span>'); }
      parts.push('<span class="' + (off.indexOf(k.key) >= 0 ? "off" : "") + '">' + E(k[lang] || k.en) + "</span>");
    });
    el.innerHTML = parts.join(" ");
  }

  function updateCrumb(route) {
    var tab = document.querySelector('[data-crumb="tab"]');
    var sub = document.querySelector('[data-crumb="sub"]');
    var separator = document.querySelector('[data-crumb="sep"]');
    var tabLabel = labels && labels.tabs && labels.tabs[route.tab];
    var subLabel = labels && labels.subs && labels.subs[route.tab + "/" + route.sub];
    if (tab && tabLabel) {
      tab.setAttribute("data-en", tabLabel.en);
      tab.setAttribute("data-ru", tabLabel.ru);
      tab.textContent = tabLabel[state.lang] || tabLabel.en;
    }
    if (sub) {
      var visible = Boolean(subLabel);
      sub.hidden = !visible;
      if (separator) { separator.hidden = !visible; }
      if (subLabel) {
        sub.setAttribute("data-en", subLabel.en);
        sub.setAttribute("data-ru", subLabel.ru);
        sub.textContent = subLabel[state.lang] || subLabel.en;
      }
    }
  }

  function applyRoute(route, initial) {
    var changed = state.tab !== null && state.tab !== route.tab;
    document.body.setAttribute("data-tab", route.tab);
    updateCrumb(route);
    renderScope(route.tab);
    try { applyFilters(route.filter || null, route); } catch (err) { /* static page wins */ }
    Array.prototype.forEach.call(rail.querySelectorAll("[role=tab]"), function (button) {
      var active = button.getAttribute("data-tab") === route.tab;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.setAttribute("tabindex", active ? "0" : "-1");
    });
    Array.prototype.forEach.call(document.querySelectorAll("[role=tabpanel]"), function (panel) {
      panel.hidden = panel.id !== "pv-panel-" + route.tab;
    });
    Array.prototype.forEach.call(document.querySelectorAll(".pv-subgroup"), function (group) {
      group.hidden = group.getAttribute("data-for-tab") !== route.tab;
    });
    Array.prototype.forEach.call(document.querySelectorAll(".pv-subtab"), function (button) {
      var active = button.getAttribute("data-tab") === route.tab && button.getAttribute("data-sub") === route.sub;
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    Array.prototype.forEach.call(document.querySelectorAll(".pv-subpanel"), function (panel) {
      panel.hidden = panel.getAttribute("data-tab") !== route.tab || panel.getAttribute("data-sub") !== route.sub;
    });
    if (route.chart && document.getElementById("pv-tpl-" + route.chart)) {
      openDrawer(route.chart, false);
    } else {
      closeDrawer(false);
    }
    if (changed) { window.scrollTo(0, 0); }
    state.tab = route.tab;
    if (initial) { state.tab = route.tab; }
  }

  function applyLang(lang, root) {
    if (lang !== "en" && lang !== "ru") { return; }
    root = root || document;
    Array.prototype.forEach.call(root.querySelectorAll("[data-en][data-ru]"), function (node) {
      var value = node.getAttribute("data-" + lang);
      if (value !== null) { node.textContent = value; }
    });
    document.documentElement.lang = lang;
    document.body.setAttribute("data-lang", lang);
    state.lang = lang;
    try { localStorage.setItem("pv-lang", lang); } catch (err) { /* storage disabled */ }
  }

  function openDrawer(cardId, push) {
    var template = document.getElementById("pv-tpl-" + cardId);
    if (!template) { return; }
    state.opener = document.activeElement;
    while (drawerBody.firstChild) { drawerBody.removeChild(drawerBody.firstChild); }
    drawerBody.appendChild(template.content.cloneNode(true));
    var target = drawerBody.querySelector("[data-clone-chart]");
    var source = document.querySelector("#pv-card-" + cardId + " .pv-figure");
    if (target && source) {
      var chart = source.querySelector("svg, .pv-tablewrap, .pv-empty");
      if (chart) {
        var clone = chart.cloneNode(true);
        Array.prototype.forEach.call(clone.querySelectorAll("[id]"), function (node) {
          node.removeAttribute("id");
        });
        if (clone.tagName && clone.tagName.toLowerCase() === "svg") {
          clone.removeAttribute("aria-labelledby");
          clone.setAttribute("aria-label", template.getAttribute("data-title-" + state.lang) || "");
        }
        target.appendChild(clone);
      }
    }
    var title = drawerBody.querySelector(".pv-drawer-h2");
    if (title) { drawer.setAttribute("aria-labelledby", title.id); }
    document.body.setAttribute("data-drawer", "open");
    main.inert = true;
    rail.inert = true;
    document.body.style.overflow = "hidden";
    applyLang(state.lang, drawer);
    var close = drawer.querySelector("[data-close]");
    if (close) { close.focus(); }
    if (push) {
      writeHash(template.getAttribute("data-tab") || "overview",
        template.getAttribute("data-sub") || "", cardId);
    }
  }

  function closeDrawer(restoreHash) {
    document.body.setAttribute("data-drawer", "closed");
    main.inert = false;
    rail.inert = false;
    document.body.style.overflow = "";
    drawer.removeAttribute("aria-labelledby");
    while (drawerBody.firstChild) { drawerBody.removeChild(drawerBody.firstChild); }
    if (state.opener && document.contains(state.opener) && typeof state.opener.focus === "function") {
      state.opener.focus();
    }
    state.opener = null;
    if (restoreHash) {
      var tab = document.body.getAttribute("data-tab") || "overview";
      var activeGroup = document.querySelector('.pv-subgroup[data-for-tab="' + tab + '"] .pv-subtab[aria-selected="true"]');
      var sub = activeGroup ? activeGroup.getAttribute("data-sub") : "";
      writeHash(tab, sub, null);
    }
  }

  function trapFocus(event) {
    var focusable = drawer.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    var visible = Array.prototype.filter.call(focusable, function (node) {
      return !node.disabled && node.offsetParent !== null;
    });
    if (!visible.length) { return; }
    var first = visible[0];
    var last = visible[visible.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function ensureTip() {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "pv-tip";
      tip.hidden = true;
      tip.setAttribute("aria-hidden", "true");
      document.body.appendChild(tip);
    }
    return tip;
  }

  function hideTip() { if (tip) { tip.hidden = true; } }

  document.addEventListener("click", function (event) {
    var target = event.target;
    var open = target.closest && target.closest(".pv-open");
    if (open) {
      var card = open.closest("[data-chart]");
      if (card) { openDrawer(card.getAttribute("data-chart"), true); }
      return;
    }
    if (target.closest && target.closest("[data-close]")) { closeDrawer(true); return; }
    var more = target.closest && target.closest(".pv-more");
    if (more) {
      var block = more.closest(".pv-diff-block");
      if (block) {
        Array.prototype.forEach.call(block.querySelectorAll(".pv-extra"), function (row) { row.hidden = false; });
        more.hidden = true;
      }
      return;
    }
    if (target === backdrop) { closeDrawer(true); return; }
    var subtab = target.closest && target.closest(".pv-subtab");
    if (subtab) {
      writeHash(subtab.getAttribute("data-tab"), subtab.getAttribute("data-sub"), null);
      return;
    }
    var railButton = target.closest && target.closest(".pv-rail [role=tab]");
    if (railButton) { writeHash(railButton.getAttribute("data-tab"), "", null); return; }
    if (target.closest && target.closest("#pv-lang")) {
      applyLang(state.lang === "en" ? "ru" : "en", document);
      renderScope((state.route || {}).tab || "overview");
      try { renderDiff((readFiles.d || {}).a, (readFiles.d || {}).b); } catch (err) { /* dialog closed */ }
      try { renderOverview(); } catch (err) { /* static text is already bilingual */ }
    }
  });

  document.addEventListener("keydown", function (event) {
    if (document.body.getAttribute("data-drawer") === "open") {
      if (event.key === "Escape") { event.preventDefault(); closeDrawer(true); return; }
      if (event.key === "Tab") { trapFocus(event); }
    }
  });

  rail.addEventListener("keydown", function (event) {
    var buttons = Array.prototype.slice.call(rail.querySelectorAll("[role=tab]"));
    var index = buttons.indexOf(document.activeElement);
    if (index < 0) { return; }
    var next = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") { next = (index + 1) % buttons.length; }
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") { next = (index - 1 + buttons.length) % buttons.length; }
    if (event.key === "Home") { next = 0; }
    if (event.key === "End") { next = buttons.length - 1; }
    if (next !== null) { event.preventDefault(); buttons[next].focus(); }
  });

  document.addEventListener("pointermove", function (event) {
    try {
      if (!payload || !window.matchMedia || !window.matchMedia("(pointer: fine)").matches) { hideTip(); return; }
      var card = event.target.closest && event.target.closest("[data-chart][data-key]");
      if (!card) { hideTip(); return; }
      var key = card.getAttribute("data-key");
      if (!key) { hideTip(); return; }
      var figure = card.querySelector(".pv-figure");
      if (!figure) { hideTip(); return; }
      var rect = figure.getBoundingClientRect();
      if (!rect.width || typeof pick !== "function" || typeof agg !== "function") { hideTip(); return; }
      var panels = pick();
      var seriesList = panels.map(function (panel, index) {
        var block = (panel.series || {})[key] || {};
        return {
          label: panel.label,
          points: agg(panel, key, state.filters, bd(state.filters)),
          unit: block.unit || "",
          decimals: block.decimals || 0,
          slot: "ABC"[index % 3]
        };
      });
      var times = [];
      seriesList.forEach(function (item) {
        item.points.forEach(function (point) {
          if (point[1] !== null && isFinite(point[1])) { times.push(point[0]); }
        });
      });
      if (!times.length) { hideTip(); return; }
      times.sort(function (a, b) { return a - b; });
      var low = times[0], high = times[times.length - 1];
      var ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      var wanted = low + ratio * (high - low);
      var best = times[0], distance = Math.abs(best - wanted);
      times.forEach(function (point) {
        var current = Math.abs(point - wanted);
        if (current < distance) { distance = current; best = point; }
      });
      var tolerance = Math.max(2 * 3600000, (high - low) / 12);
      var when = iso(best).slice(0, 16).replace("T", " ");
      var lines = [when];
      seriesList.forEach(function (item) {
        var nearest = null, nearestDistance = Infinity;
        item.points.forEach(function (point) {
          if (point[1] === null || !isFinite(point[1])) { return; }
          var current = Math.abs(point[0] - best);
          if (current < nearestDistance) { nearestDistance = current; nearest = point; }
        });
        if (nearest && nearestDistance <= tolerance) {
          lines.push(item.label + ": " + Number(nearest[1]).toFixed(item.decimals) + " " + (item.unit || ""));
        }
      });
      if (lines.length < 2) { hideTip(); return; }
      var node = ensureTip();
      node.textContent = lines.join("\n");
      node.hidden = false;
      var left = event.clientX + 14;
      if (left > window.innerWidth - 190) { left = event.clientX - 190; }
      node.style.left = left + "px";
      node.style.top = (event.clientY + 16) + "px";
    } catch (err) {
      hideTip();
    }
  });

  window.addEventListener("hashchange", function () {
    applyRoute(parseRoute(location.hash), false);
  });

  function detectTier() {
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var fine = window.matchMedia && window.matchMedia("(pointer: fine)").matches;
    document.documentElement.dataset.tier = reduced || !fine ? "low" : "high";
  }

  try {
    var saved = localStorage.getItem("pv-lang");
    if ((saved === "en" || saved === "ru") && saved !== state.lang) {
      applyLang(saved, document);
    }
  } catch (err) { /* storage disabled */ }
  function E(v){return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function P(v){return v<10?"0"+v:String(v);}
  function R6(v){return Math.round(v*1e6)/1e6;}
  function num(v){var t=Number(v).toFixed(2);return t==="-0.00"?"0.00":t;}
  function N(){return payload&&payload.crops?payload.crops.map(function(c){return String(c.name);}):[];}
  function EN(k){return payload&&payload.filters&&payload.filters[k]?payload.filters[k]:[];}
  function def(){return{crops:null,window:"all",agg:"raw",mode:"abs",notices:[]};}

  function med(a){
    var s=a.slice().sort(function(x,y){return x-y;}),m=Math.floor(s.length/2);
    return s.length%2?s[m]:(s[m-1]+s[m])/2;
  }
  function sc(dom,out){
    var a=dom[0],b=dom[1];if(b===a){a-=.5;b+=.5;}
    return function(v){return out[0]+(v-a)*(out[1]-out[0])/(b-a);};
  }
  function yd(v){
    var lo=Math.min.apply(null,v),hi=Math.max.apply(null,v),sp=hi-lo,pd=sp===0?1:sp*.07;
    return[lo-pd,hi+pd];
  }
  function xd(t){
    var lo=Math.min.apply(null,t),hi=Math.max.apply(null,t);
    return lo===hi?[lo-H,hi+H]:[lo,hi];
  }
  function ticks(lo,hi){
    if(hi===lo)return[lo];
    var raw=(hi-lo)/4,mag=Math.pow(10,Math.floor(Math.log(raw)/Math.LN10)),st=[1,2,2.5,5,10],step=st[0]*mag,best=Math.abs(step-raw);
    st.forEach(function(m){var c=Math.abs(m*mag-raw);if(c<best){best=c;step=m*mag;}});
    var out=[],v=Math.ceil(lo/step-1e-9)*step;
    while(v<=hi+1e-9){out.push(Math.round(v*1e10)/1e10);v+=step;}
    return out;
  }
  function lbl(ms,sp){
    var d=new Date(ms);
    if(sp<=3*D)return P(d.getUTCDate())+" "+MON[d.getUTCMonth()]+" "+P(d.getUTCHours())+":"+P(d.getUTCMinutes());
    if(sp<=30*D)return P(d.getUTCDate())+" "+MON[d.getUTCMonth()];
    return MON[d.getUTCMonth()];
  }
  function iso(ms){return new Date(ms).toISOString().replace(/\.\d{3}Z$/,"Z");}
  function frame(card,h){
    var id=card.getAttribute("data-chart")||"chart",t=card.querySelector("h3");
    return '<svg class="pv-chart" viewBox="0 0 '+G.w+" "+h+'" role="img" aria-labelledby="'+E(id)+'-t" preserveAspectRatio="xMidYMid meet" data-chart="'+E(id)+'"><title id="'+E(id)+'-t">'+E(t.textContent)+"</title>";
  }
  function clear(fig){Array.prototype.forEach.call(fig.querySelectorAll("svg,.pv-tablewrap,.pv-empty"),function(n){n.parentNode.removeChild(n);});}
  function empty(t){return '<div class="pv-empty" role="note" data-state="not-measured"><p class="pv-empty-t">'+E(T("ui.filter.emptyWindow"))+"</p><p>"+E(t||T("ui.filter.emptyWindow"))+"</p></div>";}

  function stable(v,lvl){
    var i=0,pad="";
    lvl=lvl||0;
    for(i=0;i<lvl;i++)pad+="  ";
    if(v===null||typeof v!=="object")return JSON.stringify(v);
    var inner=pad+"  ";
    if(Object.prototype.toString.call(v)==="[object Array]"){
      if(!v.length)return"[]";
      return"[\n"+v.map(function(x){return inner+stable(x,lvl+1);}).join(",\n")+"\n"+pad+"]";
    }
    var ks=Object.keys(v).sort();
    if(!ks.length)return"{}";
    return"{\n"+ks.map(function(k){return inner+JSON.stringify(k)+": "+stable(v[k],lvl+1);}).join(",\n")+"\n"+pad+"}";
  }
  function flat(v,p,out,skip){
    if(v===null||typeof v!=="object"){out[p]=v;return;}
    if(Object.prototype.toString.call(v)==="[object Array]"){v.forEach(function(x,i){flat(x,p+"["+i+"]",out,skip);});return;}
    Object.keys(v).forEach(function(k){if(skip&&skip.indexOf(k)>=0)return;flat(v[k],p?p+"."+k:k,out,skip);});
  }
  function pts(p,k){
    var g=(p&&p.points)||{},ts=g.ts||[],vs=g[k]||[],o=[];
    for(var i=0;i<ts.length&&i<vs.length;i++)o.push([Number(ts[i]),vs[i]===null||vs[i]===undefined?null:Number(vs[i])]);
    return o.sort(function(a,b){return a[0]-b[0];});
  }
  function down(a){
    if(a.length<=240)return a;
    var st=Math.ceil(a.length/240),out=[];
    for(var i=0;i<a.length;i+=st){
      var g=a.slice(i,i+st);if(!g.length)continue;
      var mv=g.map(function(q,j){return[q,j];}).filter(function(x){return x[0][1]!==null&&isFinite(x[0][1]);}),c=[0,g.length-1];
      if(mv.length){
        var lo=0,hi=0;
        for(var j=1;j<mv.length;j++){if(mv[j][0][1]<mv[lo][0][1])lo=j;if(mv[j][0][1]>mv[hi][0][1])hi=j;}
        c.push(mv[lo][1],mv[hi][1]);
      }
      c.sort(function(x,y){return x-y;}).forEach(function(o){if(out.indexOf(g[o])<0)out.push(g[o]);});
    }
    return out.sort(function(x,y){return x[0]-y[0];});
  }
  function runs(a){
    var p=a.filter(function(q){return q[1]!==null&&isFinite(q[1]);});
    if(!p.length)return[];
    var gaps=[],i;
    for(i=1;i<p.length;i++)gaps.push(p[i][0]-p[i-1][0]);
    var th=gaps.length?Math.max(3*med(gaps),2*H):2*H,out=[[p[0]]];
    for(i=1;i<p.length;i++){if(p[i][0]-p[i-1][0]>th)out.push([p[i]]);else out[out.length-1].push(p[i]);}
    return out;
  }
  function agg(p,k,f,b){
    var a=pts(p,k).filter(function(q){return q[0]>=b.lo&&q[0]<=b.hi;});
    if(f.agg==="raw")return a;
    var sz=f.agg==="hourly"?H:D,bk={};
    a.forEach(function(q){
      if(q[1]===null||!isFinite(q[1]))return;
      var s=Math.floor(q[0]/sz)*sz;if(!bk[s])bk[s]=[];bk[s].push(q[1]);
    });
    return Object.keys(bk).map(Number).sort(function(x,y){return x-y;}).map(function(s){return[s,R6(med(bk[s]))];});
  }
  function tr(a,m){
    if(m==="abs")return{points:a};
    var base=null;
    a.forEach(function(q){if(base===null&&q[1]!==null&&isFinite(q[1]))base=q[1];});
    if(base===null||base<=0)return{points:[],error:"not computable"};
    return{points:a.map(function(q){return[q[0],q[1]===null||!isFinite(q[1])?null:(m==="idx"?100*q[1]/base:100*(q[1]-base)/base)];})};
  }
  /*__FILTER__*/
  detectTier();
  applyRoute(parseRoute(location.hash), true);
})();
"""

JS_FILTER: str = r"""var H=36e5,D=864e5;
state.filters={crops:null,window:"all",agg:"raw",mode:"abs",notices:[]};
state.route={tab:document.body.getAttribute("data-tab")||"overview",sub:"",chart:null};
var G=(payload&&payload.renderer)||{w:720,h:240,hm:266,pl:44,pt:18,pr:18,pb:40,pw:658,ph:182,legendY:258,xLabelY:226,xTitleY:238,lastX:700,tickY:30};
var SLOT={A:{s:"url(#pv-grad-a)",d:"",w:"#F5705E"},B:{s:"url(#pv-grad-b)",d:' stroke-dasharray="6 4"',w:"#C159F5"},C:{s:"var(--pv-pos)",d:' stroke-dasharray="1 3"',w:"var(--pv-pos)"}};
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
var EK={w:"windows",a:"aggs",m:"modes"},EF={w:"window",a:"agg",m:"mode"};

function T(k){var t=labels&&labels.terms&&labels.terms[k];return t?(t[state.lang]||t.en):k;}
function parseFilters(raw){
  var o=def(),all=N();
  (raw||"").split("&").forEach(function(p){
    if(!p)return;
    var i=p.indexOf("=");
    if(i<0){o.notices.push(p);return;}
    var k=p.slice(0,i),v=p.slice(i+1),c=[];
    if(k==="c"){
      v.split(",").forEach(function(t){
        var n=t;try{n=decodeURIComponent(t);}catch(e){n=t;}
        if(all.indexOf(n)>=0){if(c.indexOf(n)<0)c.push(n);}else if(n)o.notices.push(n);
      });
      o.crops=c.length?all.filter(function(n){return c.indexOf(n)>=0;}):null;
      if(!c.length&&v)o.notices.push(v);
    }else if(EK[k]&&EN(EK[k]).indexOf(v)>=0){o[EF[k]]=v;}else{o.notices.push(v||k);}
  });
  return o;
}
function canon(f){
  f=f||state.filters;
  var all=N(),sel=f.crops?all.filter(function(n){return f.crops.indexOf(n)>=0;}):all,p=[];
  if(sel.length&&sel.length<all.length)p.push("c="+sel.map(encodeURIComponent).join(","));
  if(f.window!=="all")p.push("w="+f.window);
  if(f.agg!=="raw")p.push("a="+f.agg);
  if(f.mode!=="abs")p.push("m="+f.mode);
  return p.length?"!"+p.join("&"):"";
}
function writeHash(t,s,c){
  var n="#/"+t+(s?"/"+s:"")+(c?"~"+encodeURIComponent(c):"")+canon(state.filters);
  if(n!==location.hash)location.hash=n;
}
function commit(){var r=state.route||{tab:"overview",sub:"",chart:null};writeHash(r.tab,r.sub,r.chart);}

function pick(f){
  f=f||state.filters;var ps=(payload&&payload.panels)||[];
  return f.crops?ps.filter(function(p){return f.crops.indexOf(String(p.crop||""))>=0;}):ps.slice();
}
function bd(f){
  var now=payload?Date.parse(payload.now):0;
  if(f.window==="24h")return{lo:now-D,hi:now};
  if(f.window==="7d")return{lo:now-7*D,hi:now};
  if(f.window==="30d")return{lo:now-30*D,hi:now};
  var lo=null,hi=null;
  pick(f).forEach(function(p){
    var a=Date.parse(p.first_at||""),b=Date.parse(p.last_at||"");
    if(isFinite(a))lo=lo===null?a:Math.min(lo,a);
    if(isFinite(b))hi=hi===null?b:Math.max(hi,b);
  });
  return lo===null||hi===null?{lo:now-D,hi:now}:{lo:lo,hi:Math.min(hi,now)};
}
function renderRings(){var card=document.getElementById("pv-card-ch-ov-kpi-rings");if(!card)return;var sets=(payload&&payload.overview&&payload.overview.ring_sets)||{},vals=sets[ringKey(state.filters)]||sets[ringKey(def())];if(!vals)return;var keys=["scale","freshness","pressure","shape"];Array.prototype.forEach.call(card.querySelectorAll(".pv-ring"),function(div,i){var raw=vals[keys[i]],v=(raw===null||raw===undefined||!isFinite(Number(raw)))?null:Math.max(0,Math.min(100,Number(raw)));var circles=div.querySelectorAll("svg circle"),track=circles[0];if(!track)return;var r=Number(track.getAttribute("r")),sw=Number(track.getAttribute("stroke-width")),c=2*Math.PI*r,arc=circles[1];div.setAttribute("data-state",v===null?"not-measured":"ok");if(v===null){if(arc&&arc.parentNode)arc.parentNode.removeChild(arc);}else{if(!arc){arc=track.cloneNode(false);track.parentNode.appendChild(arc);}arc.setAttribute("fill","none");arc.setAttribute("stroke",ringStroke(v));arc.setAttribute("stroke-width",String(sw));arc.setAttribute("stroke-linecap","round");arc.setAttribute("transform","rotate(-90 "+track.getAttribute("cx")+" "+track.getAttribute("cy")+")");arc.setAttribute("stroke-dasharray",String(R6(c)));arc.setAttribute("stroke-dashoffset",String(R6(c*(1-v/100))));}var txt=div.querySelector(".pv-ring-val");if(txt)txt.textContent=v===null?T("ui.chip.not-measured"):v.toFixed(0)+"%";});}function ringKey(f){return pick(f).map(function(p){return String(p.id);}).join("+");}function ringStroke(v){return v>=90?"var(--pv-pos)":v>=50?"#E0A800":"url(#pv-grad-a)";}function renderBoard(){var card=document.getElementById("pv-card-ch-ov-status-board");if(!card)return;var rows=card.querySelectorAll("tbody tr[data-panel]");if(!rows.length)return;var sel={};pick().forEach(function(p){sel[String(p.id)]=1;});var n=0;Array.prototype.forEach.call(rows,function(tr){var on=!!sel[tr.getAttribute("data-panel")];tr.hidden=!on;if(on)n++;});var emptyRow=card.querySelector("[data-board-empty]");if(emptyRow)emptyRow.hidden=n>0;var foot=card.querySelector("[data-board-count]");if(foot)foot.textContent=T("ui.board.showing").replace("{n}",n).replace("{total}",rows.length);}function renderFramesBars(){var card=document.getElementById("pv-card-ch-ov-frames-bars");if(!card)return;var fig=card.querySelector(".pv-figure");if(!fig)return;var ps=pick(),cal=payload&&payload.calendar,cells=(cal&&cal.rows&&cal.rows[0]&&cal.rows[0].cells)||[],days=[];cells.forEach(function(cell){days.push(String(cell.date));});if(!ps.length||!days.length){clear(fig);fig.insertAdjacentHTML("afterbegin",empty());return;}var series=ps.length,counts=ps.map(function(p){var m={};((p.daily)||[]).forEach(function(b){m[String(b.date)]=Number(b.frames||0);});return m;});var items=[],hi=1,i,j;for(i=0;i<days.length;i++)for(j=0;j<series;j++){var val=counts[j][days[i]]||0;items.push(val);if(val>hi)hi=val;}var plotW=Math.max(G.pw,days.length*series*10),viewW=G.pl+plotW+G.pr,groupW=plotW/days.length,gap=4,barW=Math.min(18,Math.max(6,(groupW-gap*(series-1))/series)),content=series*barW+gap*(series-1),top=G.pt,bottom=G.pt+142,fills={A:"url(#pv-grad-a)",B:"url(#pv-hatch-b)",C:"var(--pv-pos)"},o=['<svg class="pv-chart" viewBox="0 0 '+viewW+' 240" role="img"><title id="ch-ov-frames-live-t">'+E(card.querySelector("h3").textContent)+"</title>"];ps.forEach(function(p,k){var x=G.pl+k*150,slot="ABC"[k%3];o.push('<rect x="'+x+'" y="2" width="10" height="10" rx="2" fill="'+fills[slot]+'" stroke="var(--pv-b1)"/><text x="'+(x+14)+'" y="11" class="pv-legend">'+E(p.label)+"</text>");});for(i=0;i<days.length;i++){var gx=G.pl+i*groupW+(groupW-content)/2;for(j=0;j<series;j++){var value=items[i*series+j],y=bottom-(bottom-top)*(Math.max(0,value)/hi),x=gx+j*(barW+gap);o.push('<rect class="pv-bar" x="'+num(x)+'" width="'+num(barW)+'" y="'+num(y)+'" height="'+num((bottom-y)||1)+'" rx="2" fill="'+fills["ABC"[j%3]]+'" stroke="var(--pv-track)"/>');}o.push('<text x="'+num(G.pl+i*groupW+groupW/2)+'" y="180" class="pv-ax" text-anchor="middle">'+E(days[i].slice(5))+"</text>");}o.push("</svg>");clear(fig);fig.insertAdjacentHTML("afterbegin",o.join(""));}function renderOverview(){renderRings();renderBoard();renderFramesBars();}
function thrCaption(thresholds){
  var labs=[];
  (thresholds||[]).forEach(function(t){
    var lab=state.lang==="ru"?(t.label_ru||t.label_en):(t.label_en||"");
    if(lab)labs.push(lab);
  });
  if(!labs.length)return"";
  var head=labs[0],pre=head.split(" ")[0],parts=[head];
  for(var i=1;i<labs.length;i++)parts.push(pre&&labs[i].indexOf(pre+" ")===0?labs[i].slice(pre.length+1):labs[i]);
  return T("ui.thr.caption").replace("{list}",parts.join(", "));
}
function drawLine(card,list,opt){
  var fig=card.querySelector(".pv-figure");if(!fig)return;clear(fig);
  var ss=[],vv=[],tt=[],drawn=0;
  list.forEach(function(it){var r=tr(it.points,state.filters.mode),a=r.points||[],m=a.filter(function(q){return q[1]!==null&&isFinite(q[1]);});if(m.length)drawn++;m.forEach(function(q){vv.push(q[1]);tt.push(q[0]);});ss.push({slot:it.slot,label:it.label,points:down(a),panel:it.panel});});
  if(!vv.length){fig.insertAdjacentHTML("afterbegin",empty());return;}
  var cap=thrCaption(opt.thresholds),gap=cap?16:0,multi=drawn>1,h=(multi?G.hm:G.h)+gap,ly=G.legendY+gap,y=yd(vv),x=xd(tt),ys=sc(y,[G.pt+G.ph,G.pt]),xs=sc(x,[G.pl,G.pl+G.pw]),o=[frame(card,h)],i,dec=y[1]>=10?0:2;
  ticks(y[0],y[1]).forEach(function(v){var py=ys(v);o.push('<line x1="'+G.pl+'" y1="'+num(py)+'" x2="'+(G.pl+G.pw)+'" y2="'+num(py)+'" stroke="var(--pv-grid)"/>','<text x="'+(G.pl-6)+'" y="'+num(py)+'" class="pv-ax" text-anchor="end">'+v.toFixed(dec)+"</text>");});
  var sp=x[1]-x[0];
  if(sp){var lastLab="";for(i=0;i<6;i++){var ms=x[0]+sp*i/5,px=xs(ms),lab=lbl(ms,sp);if(lab===lastLab)continue;lastLab=lab;o.push('<text x="'+num(px)+'" y="'+G.xLabelY+'" class="pv-ax" text-anchor="middle">'+E(lab)+"</text>");}}
  o.push('<text x="'+num(G.pl+G.pw/2)+'" y="'+G.xTitleY+'" class="pv-ax-title" text-anchor="middle">captured_at (UTC)</text>');
  if(cap)o.push('<text x="'+num(G.pl)+'" y="'+(G.xTitleY+14)+'" class="pv-ax-title" text-anchor="start">'+E(cap)+"</text>");
  (opt.thresholds||[]).forEach(function(t){if(t.unit&&opt.unit&&t.unit!==opt.unit)return;var tv=Number(t.at);if(!isFinite(tv)||tv<y[0]||tv>y[1])return;var py=ys(tv),c=t.kind==="warn"?"#FBC490":"#F5705E",lab=state.lang==="ru"?(t.label_ru||t.label_en):(t.label_en||"");o.push('<line x1="'+G.pl+'" x2="'+(G.pl+G.pw)+'" y1="'+num(py)+'" y2="'+num(py)+'" stroke="'+c+'" stroke-dasharray="'+(t.kind==="warn"?"4 3":"2 2")+'"/>','<text x="'+G.lastX+'" y="'+num(Math.max(10,py-4))+'" class="pv-ax" text-anchor="end">'+E(lab||String(tv))+"</text>");});
  var medv=med(vv),medp=ys(medv);
  o.push('<line x1="'+G.pl+'" x2="'+(G.pl+G.pw)+'" y1="'+num(medp)+'" y2="'+num(medp)+'" stroke="#FBC490" stroke-dasharray="4 3"/>','<text x="'+num(G.pl+4)+'" y="'+num(Math.max(10,medp-4))+'" class="pv-ax" text-anchor="start">'+E(Number(medv).toFixed(opt.decimals||0))+"</text>");
  ss.forEach(function(it){
    var st=SLOT[it.slot]||SLOT.A,rs=runs(it.points);
    o.push('<g data-series="'+it.slot+'" data-label="'+E(it.label)+'">');
    rs.forEach(function(r){if(r.length<2)return;o.push('<path class="pv-line pv-draw" d="'+r.map(function(q,j){return(j?"L":"M")+num(xs(q[0]))+" "+num(ys(q[1]));}).join(" ")+'" fill="none" stroke="'+st.s+'" stroke-width="2" vector-effect="non-scaling-stroke" pathLength="1"'+st.d+"/>");});
    rs.forEach(function(r){r.forEach(function(q){o.push('<circle cx="'+num(xs(q[0]))+'" cy="'+num(ys(q[1]))+'" r="1.9" fill="'+st.s+'"/>');});});
    if(it.points.length&&!multi){var last=it.points[it.points.length-1];o.push('<text x="700" y="30" class="pv-last" text-anchor="end">'+E(Number(last[1]).toFixed(opt.decimals||0)+(opt.unit?" "+opt.unit:""))+"</text>");}
    o.push("</g>");
  });
  (opt.missing||[]).forEach(function(m){if(m.ts<x[0]||m.ts>x[1])return;var st=SLOT[m.slot]||SLOT.A;o.push('<circle cx="'+num(xs(m.ts))+'" cy="'+num(G.pt+G.ph-6)+'" r="2.4" fill="none" stroke="'+st.w+'" stroke-width="1.4"/>');});
  if(multi){
    o.push('<g class="pv-series-legend">');var w=G.pw/ss.length;
    ss.forEach(function(it,j){var sx=G.pl+j*w,st=SLOT[it.slot]||SLOT.A,rs=runs(it.points),tx=it.label;tx+=rs.length?" · "+Number(rs[rs.length-1][rs[rs.length-1].length-1][1]).toFixed(opt.decimals||0)+" "+(opt.unit||""):" · "+T("ui.filter.noFrames").replace("{window}",state.filters.window);o.push('<line x1="'+num(sx)+'" y1="'+num(ly)+'" x2="'+num(sx+16)+'" y2="'+num(ly)+'" stroke="'+st.w+'" stroke-width="3"'+st.d+'/>','<text x="'+num(sx+22)+'" y="'+(ly+4)+'" class="pv-legend"'+(rs.length?"":' opacity="0.55"')+">"+E(tx)+"</text>");});
    o.push("</g>");
  }
  o.push("</svg>");fig.insertAdjacentHTML("afterbegin",o.join(""));
}
function days(p,k,b){
  var bk={};
  pts(p,k).forEach(function(q){
    if(q[0]<b.lo||q[0]>b.hi||q[1]===null||!isFinite(q[1]))return;
    var d=Math.floor(q[0]/D)*D;if(!bk[d])bk[d]=[];bk[d].push(q[1]);
  });
  return Object.keys(bk).map(Number).sort(function(a,b){return a-b;}).map(function(d){
    var v=bk[d];return{day:d,median:med(v),low:Math.min.apply(null,v),high:Math.max.apply(null,v),frames:v.length};
  });
}
function drawBars(card,panels,kind,thresholds){
  var fig=card.querySelector(".pv-figure");if(!fig)return;clear(fig);
  var b=bd(state.filters),items=[];
  panels.forEach(function(p,i){var d=days(p,"area_px",b);if(kind==="ch-gr-rate-bars")items.push({label:p.label,value:d.length>1?d[d.length-1].median-d[d.length-2].median:null,slot:"ABC"[i%3]});else d.forEach(function(x){items.push({label:iso(x.day).slice(5,10),value:x.median,low:x.low,high:x.high,slot:"ABC"[i%3]});});});
  var vv=items.filter(function(x){return x.value!==null;}).map(function(x){return x.value;});
  if(!vv.length){fig.insertAdjacentHTML("afterbegin",empty());return;}
  vv.push(0);var y=yd(vv),ys=sc(y,[G.pt+G.ph,G.pt]),cap=thrCaption(thresholds),o=[frame(card,G.h+(cap?16:0))],zero=ys(0),w=G.pw/Math.max(1,items.length);
  ticks(y[0],y[1]).forEach(function(v){o.push('<line x1="'+G.pl+'" y1="'+num(ys(v))+'" x2="'+(G.pl+G.pw)+'" y2="'+num(ys(v))+'" stroke="var(--pv-grid)"/>');});
  o.push('<text x="'+num(G.pl+G.pw/2)+'" y="'+G.xTitleY+'" class="pv-ax-title" text-anchor="middle">captured_at (UTC)</text>');
  if(cap)o.push('<text x="'+num(G.pl)+'" y="'+(G.xTitleY+14)+'" class="pv-ax-title" text-anchor="start">'+E(cap)+"</text>");
  items.forEach(function(it,i){if(it.value===null)return;var cx=G.pl+w*(i+.5),bw=Math.max(2,w*.62);o.push('<rect x="'+num(cx-bw/2)+'" y="'+num(Math.min(ys(it.value),zero))+'" width="'+num(bw)+'" height="'+num(Math.abs(ys(it.value)-zero)||1)+'" fill="'+((SLOT[it.slot]||SLOT.A).w)+'"/>');if(i%Math.max(1,Math.ceil(items.length/6))===0)o.push('<text x="'+num(cx)+'" y="'+G.xLabelY+'" class="pv-ax" text-anchor="middle">'+E(it.label)+"</text>");});

  fig.insertAdjacentHTML("afterbegin",o.join(""));
}
function drawTable(card,panels){
  var body=card.querySelector(".pv-tablewrap tbody");if(!body)return;
  var b=bd(state.filters),rows=[];
  panels.forEach(function(p){
    var prev=null;
    days(p,"area_px",b).forEach(function(d){
      var dt=iso(d.day).slice(0,10),de=prev===null?null:d.median-prev;
      rows.push("<tr><td>"+E(String(p.label).split(" · ")[0])+'</td><td>'+dt.slice(8,10)+"."+dt.slice(5,7)+'</td><td class="num">'+d.frames+'</td><td class="num">'+d.median.toFixed(0)+'</td><td class="num">'+d.low.toFixed(0)+'</td><td class="num">'+d.high.toFixed(0)+'</td><td class="num">'+(de===null?"—":(de>=0?"+":"")+de.toFixed(0))+"</td></tr>");
      prev=d.median;
    });
  });
  body.innerHTML=rows.length?rows.join(""):'<tr><td colspan="7" class="pv-empty">'+E(T("ui.filter.emptyWindow"))+"</td></tr>";
}

function spanText(h,lang){
  var v=Number(h);if(h===null||h===undefined||!isFinite(v)||v<0)return"";
  return v>=48?(v/24).toFixed(1)+" "+(lang==="ru"?"дн.":"days"):v.toFixed(1)+" "+(lang==="ru"?"ч":"h");
}
function singleConclusion(c,p,lang){
  var v=((c.single_values||{})[String(p.id)]);
  if(!v)return T("ui.chip.not-computable");
  var sp=spanText(v.span_hours,lang);
  if(!sp)return T("ui.chip.not-computable");
  var vals={panel:String(p.label||""),delta:String(v.delta||""),span:sp,first:String(v.first||""),last:String(v.last||""),unit:String(v.unit||"")};
  return T("ui.conclusion.single").replace(/\{(\w+)\}/g,function(m,k){return vals[k]!==undefined?vals[k]:m;});
}
function joinField(c,field,sel,all){
  function one(lang){
    if(sel.length===all.length)return String(c[field+"_"+lang]||"");
    if(field==="conclusion"&&sel.length>=2)return String(c["conclusion_"+lang]||"");
    if(field==="conclusion"&&sel.length===1&&(c.single_values||{})[String(sel[0].id)])return singleConclusion(c,sel[0],lang);
    var map=c[field+"_parts"]||{},parts=[];
    sel.forEach(function(p){var q=map[String(p.id)];if(q)parts.push(q[lang]||q.en||"");});
    parts=parts.filter(function(x){return x;});
    var tpl=(c[field+"_join"]||{})[lang]||"{parts}",body=tpl.replace("{parts}",parts.map(function(x){return x.replace(/\.$/,"");}).join("; "));
    return body&&!/\.$/.test(body)?body+".":body;
  }
  return{en:one("en"),ru:one("ru")};
}
function setCopy(node,texts){node.setAttribute("data-en",texts.en);node.setAttribute("data-ru",texts.ru);node.textContent=state.lang==="ru"?texts.ru:texts.en;}
function updateCopy(){
  if(!payload||!payload.cards)return;
  var sel=pick(),all=(payload&&payload.panels)||[];
  payload.cards.forEach(function(c){
    if(!c.now_parts||!Object.keys(c.now_parts).length)return;
    var card=document.getElementById("pv-card-"+c.id);if(!card)return;
    var n=card.querySelector('[data-field="now"]');if(n)setCopy(n,joinField(c,"now",sel,all));
    var q=card.querySelector(".pv-concl");if(q)setCopy(q,joinField(c,"conclusion",sel,all));
    var d=card.querySelector('[data-field="do"]');
    if(d){
      var base={en:String(c.do_en||""),ru:String(c.do_ru||"")};
      if(sel.length<all.length){
        var allOk=sel.length>0&&sel.every(function(p){return String(p.verdict||"")==="ok";});
        if(allOk){base={en:(c.do_ok||{}).en||base.en,ru:(c.do_ok||{}).ru||base.ru};}
        else{
          var crit=sel.filter(function(p){return String(p.verdict||"")==="critical";})[0];
          var act=crit&&(c.do_actions||{})[String(crit.id)];
          if(act&&act.en)base={en:act.en,ru:act.ru||act.en};
        }
      }
      setCopy(d,base);
    }
  });
}
function active(f){f=f||state.filters;return !!f.crops||f.window!=="all"||f.agg!=="raw"||f.mode!=="abs";}
function visibility(){
  var sel=pick(),ps=(payload&&payload.panels)||[];
  Array.prototype.forEach.call(document.querySelectorAll('.pv-card[data-filter-scope="hide"]'),function(card){
    Array.prototype.forEach.call(card.querySelectorAll("[data-series]"),function(g){
      var i=ps.findIndex(function(x){return x.label===g.getAttribute("data-label");});
      g.style.display=i<0||sel.indexOf(ps[i])>=0?"":"none";
    });
  });
}
function cap(card,total,drawn){
  var head=card.querySelector(".pv-card-head"),chip=card.querySelector(".pv-filter-chip");
  if(total>drawn){
    if(!chip){chip=document.createElement("span");chip.className="pv-chip pv-filter-chip";chip.setAttribute("data-state","warn");if(head)head.appendChild(chip);}
    chip.textContent=T("ui.filter.capped").replace("{n}",total);
  }else if(chip)chip.parentNode.removeChild(chip);
}
function renderAll(){
  if(!payload)return;
  Array.prototype.forEach.call(document.querySelectorAll('[data-render="client"]'),function(card){
    var id=card.getAttribute("data-chart")||"",key=card.getAttribute("data-card-key")||"area_px",all=pick(),ps=all.slice(0,3),b=bd(state.filters);
    if(id==="ch-gr-daily-table"){drawTable(card,ps);cap(card,all.length,ps.length);return;}
    if(id==="ch-gr-rate-bars"||id==="ch-gr-daily-bars"){var barMeta=((payload.cards||[]).filter(function(c){return c.id===id;})[0])||{};drawBars(card,ps,id,barMeta.thresholds||[]);cap(card,all.length,ps.length);return;}
    var s=((ps[0]||{}).series||{})[key]||{},cardMeta=((payload.cards||[]).filter(function(c){return c.id===id;})[0])||{},missing=[];
    if(key==="area_cm2")ps.forEach(function(p,i){(p.scale_missing||[]).forEach(function(ts){missing.push({slot:"ABC"[i%3],ts:Number(ts)});});});
    var list=ps.map(function(p,i){return{label:p.label,slot:"ABC"[i%3],panel:p,points:agg(p,key,state.filters,b)};});
    drawLine(card,list,{key:key,unit:s.unit||"",decimals:s.decimals||0,thresholds:cardMeta.thresholds||[],missing:missing});
    cap(card,all.length,ps.length);
  });
}
function sync(){
  var f=state.filters,all=N(),sel=f.crops||all,v=document.getElementById("pv-f-crop-val");
  Array.prototype.forEach.call(document.querySelectorAll(".pv-crop-box"),function(b){b.checked=sel.indexOf(b.value)>=0;});
  if(v)v.textContent=sel.length===all.length?T("ui.controls.cropAll"):sel.join(", ");
  [["pv-f-window","window"],["pv-f-agg","agg"],["pv-f-mode","mode"]].forEach(function(p){var e=document.getElementById(p[0]);if(e)e.value=f[p[1]];});
  var r=document.getElementById("pv-f-reset");if(r)r.disabled=!active(f);
  var tab=(state.route&&state.route.tab)||"overview",sub=(state.route&&state.route.sub)||"",nt=tab==="alerts"||tab==="method";
  var w=document.getElementById("pv-f-window"),a=document.getElementById("pv-f-agg"),m=document.getElementById("pv-f-mode");
  if(w)w.disabled=nt;if(a)a.disabled=nt;if(m){m.disabled=sub==="rate"||sub==="daily";}
}
function note(){var el=document.getElementById("pv-filter-note");if(!el)return;var n=state.filters.notices||[];el.hidden=!n.length;el.textContent=n.length?T("ui.filter.invalid").replace("{token}",n[0]):"";}
function applyFilters(f,route){
  state.filters=f||def();
  if(route)state.route={tab:route.tab,sub:route.sub,chart:route.chart};
  if(!payload)return;
  sync();visibility();renderAll();renderOverview();updateCopy();note();
}

function stats(a){
  var v=a.filter(function(q){return q[1]!==null&&isFinite(q[1]);}).map(function(q){return Number(q[1]);});
  if(!v.length)return null;
  var s=v.slice().sort(function(x,y){return x-y;});
  return{n:v.length,min:R6(s[0]),median:R6(med(v)),max:R6(s[s.length-1]),first:R6(v[0]),last:R6(v[v.length-1])};
}
function snapName(f){
  var d=payload?new Date(payload.now):new Date(NaN),st=isFinite(d.getTime())?d.toISOString().replace(/[-:]/g,"").replace(/\.\d{3}Z$/,"Z"):"nodate";
  var all=N(),sel=f.crops||all,slug=sel.length>=all.length?"all":sel.map(function(n){return String(n).toLowerCase().replace(/[^a-z0-9]+/g,"_");}).join("+");
  return"pv-snapshot-"+st+"-"+slug+"-"+f.window+"-"+f.agg+"-"+f.mode+".json";
}
function buildSnap(){
  var f=state.filters,b=bd(f),ps=pick(f),allPanels=(payload&&payload.panels)||[],all=N(),sel=f.crops||all;
  var panels=ps.map(function(p){
    var s={},n=0;
    ["area_px","area_cm2"].forEach(function(k){var a=pts(p,k).filter(function(q){return q[0]>=b.lo&&q[0]<=b.hi;}),st=stats(a),m=a.filter(function(q){return q[1]!==null&&isFinite(q[1]);});n=Math.max(n,a.length);s[k]={unit:((p.series||{})[k]||{}).unit||"",points:m.map(function(q){return[iso(q[0]),R6(q[1])];}),stats:st,index_first:st&&st.first>0?100:null,index_last:st&&st.first>0?R6(100*st.last/st.first):null,delta_pct:st&&st.first>0?R6(100*(st.last-st.first)/st.first):null};});
    return{id:p.id,label:p.label,crop:p.crop,method:p.method,rows:p.rows,frames_in_window:n,state:n?"ok":"no-frames",kpi:p.kpi||{},alerts:p.alerts||{},series:s};
  });
  var cards=((payload&&payload.cards)||[]).map(function(c){
    var k=c.key||"area_px",bl=((panels[0]||{}).series||{})[k]||{},full=!!(c.filter&&c.filter.crop==="full"),
        jn=full?joinField(c,"now",ps,allPanels):{en:c.now_en,ru:c.now_ru},
        jc=full?joinField(c,"conclusion",ps,allPanels):{en:c.conclusion_en,ru:c.conclusion_ru};
    return{id:c.id,tab:c.tab,sub:c.sub,title_en:c.title_en,title_ru:c.title_ru,state:c.state,now_en:jn.en,now_ru:jn.ru,conclusion_en:jc.en,conclusion_ru:jc.ru,metrics:{last:(bl.stats||{}).last===undefined?null:bl.stats.last,unit:bl.unit||"",mode_value:bl.index_last}};
  });
  var fr=(payload&&payload.frames)||[],sources=ps.map(function(p){var rs=fr.filter(function(r){return r.panel===p.id;}),a=rs[0]||{},z=rs[rs.length-1]||{};return{panel:p.id,csv:p.source,sha256_first:a.sha256||"",sha256_last:z.sha256||""};}),thumbs=[];
  ps.forEach(function(p){var last=null;fr.forEach(function(r){if(r.panel===p.id&&r.total>0&&r.index===r.total-1)last=r;});if(last)thumbs.push({panel:p.id,frame_id:last.id,sha16:String(last.sha256||"").slice(0,16),with_mask:!!last.mask});});
  var findings=((payload&&payload.findings)||[]).map(function(f){return{panel:f.panel,rule_id:f.rule_id,severity:f.severity,value:f.value===undefined?null:f.value,threshold:f.threshold===undefined?null:f.threshold};});
  return{schema:"pv-snapshot/1",generated_at:payload.now,now_source:payload.now_source,page:{build:payload.schema,lang:state.lang,renderer:"client",bytes_note:"summary only"},filters:{crops:sel,crop_state:sel.length>=all.length?"all":"subset",window:f.window,window_label:f.window,aggregation:f.agg,mode:f.mode},window:{start_ms:b.lo,end_ms:b.hi,start:iso(b.lo),end:iso(b.hi)},panels:panels,cards:cards,findings:findings,sources:sources,thumbnails:thumbs,thumbnail_state:thumbs.length?"embedded":"not built"};
}
function exportSnap(){
  var text=stable(buildSnap()),name=snapName(state.filters),a=document.getElementById("pv-snap-text"),n=document.getElementById("pv-snap-name");
  if(a)a.value=text;if(n)n.textContent=name;return{text:text,name:name};
}
function downloadSnap(){
  var o=exportSnap(),blob=new Blob([o.text],{type:"application/json"}),url=URL.createObjectURL(blob),a=document.createElement("a");
  a.download=o.name;a.href=url;document.body.appendChild(a);a.click();document.body.removeChild(a);
  setTimeout(function(){URL.revokeObjectURL(url);},1000);
}
function copySnap(){
  var a=document.getElementById("pv-snap-text");if(!a)return;
  exportSnap();a.focus();a.select();try{document.execCommand("copy");}catch(e){}
}

/*pv-diff-begin*/function snapDiff(a,b){function isArr(v){return Object.prototype.toString.call(v)==="[object Array]";}function arr(v){return isArr(v)?v:[];}function num(v){return typeof v==="number"&&isFinite(v)?v:null;}function panels(s){var m={};arr(s&&s.panels).forEach(function(p){if(p&&p.id!==undefined)m[String(p.id)]=p;});return m;}function lastArea(p){var st=((p&&p.series&&p.series.area_px)||{}).stats||{};return num(st.last);}function sumArea(s){var t=0,n=0;arr(s&&s.panels).forEach(function(p){var x=lastArea(p);if(x!==null){t+=x;n++;}});return n?t:null;}function meanKpi(s,k){var t=0,n=0;arr(s&&s.panels).forEach(function(p){var x=num((p.kpi||{})[k]);if(x!==null){t+=x;n++;}});return n?t/n:null;}function alertCount(s){var n=0,f=arr(s&&s.findings);if(f.length){f.forEach(function(x){if(x&&(x.severity==="critical"||x.severity==="warn"))n++;});return n;}arr(s&&s.panels).forEach(function(p){var al=(p||{}).alerts||{};n+=Number(al.critical||0)+Number(al.warn||0);});return n;}function delta(x,y){return x===null||y===null?null:y-x;}function pct(x,y){var d=delta(x,y);return d===null||!x?null:100*d/Math.abs(x);}function kpi(key,x,y){return{key:key,a:x,b:y,delta:delta(x,y),delta_pct:pct(x,y)};}function amap(s){var m={};arr(s&&s.findings).forEach(function(f){if(!f)return;var k=String(f.panel)+"|"+String(f.rule_id);m[k]={key:k,panel:String(f.panel),rule:String(f.rule_id),severity:String(f.severity||""),value:num(f.value)};});return m;}function smap(s){var m={};arr(s&&s.sources).forEach(function(x){if(x)m[String(x.panel)]=x;});return m;}function flat(v,p,out,skip){if(v===null||typeof v!=="object"){out[p]=v;return;}if(isArr(v)){v.forEach(function(x,i){flat(x,p+"["+i+"]",out,skip);});return;}Object.keys(v).forEach(function(k){if(skip&&skip.indexOf(k)>=0)return;flat(v[k],p?p+"."+k:k,out,skip);});}function same(x,y){return typeof x==="number"&&typeof y==="number"?Math.abs(x-y)<=1e-9:String(x)===String(y);}var pa=panels(a),pb=panels(b),ids=Object.keys(pa).concat(Object.keys(pb)).filter(function(k,i,l){return l.indexOf(k)===i;}).sort();var kpis=[kpi("area",sumArea(a),sumArea(b)),kpi("scale",meanKpi(a,"scale_pct"),meanKpi(b,"scale_pct")),kpi("freshness",meanKpi(a,"freshness_pct"),meanKpi(b,"freshness_pct")),kpi("alerts",alertCount(a),alertCount(b))];var rows=ids.map(function(id){var A=lastArea(pa[id]),B=lastArea(pb[id]),src=pb[id]||pa[id]||{},spark=[];arr(((src.series||{}).area_px||{}).points).slice(-12).forEach(function(q){var v=num(q&&q[1]);if(v!==null)spark.push(v);});return{panel:id,label:String((pb[id]||pa[id]||{}).label||id),a:A,b:B,delta:delta(A,B),delta_pct:pct(A,B),spark:spark};});var am=amap(a),bm=amap(b),alerts=[],akeys=Object.keys(am);Object.keys(bm).forEach(function(k){if(akeys.indexOf(k)<0)akeys.push(k);});akeys.sort().forEach(function(k){var x=am[k],y=bm[k],e=null;if(!x)e={key:k,panel:y.panel,rule:y.rule,change:"added",from:"",to:y.severity};else if(!y)e={key:k,panel:x.panel,rule:x.rule,change:"removed",from:x.severity,to:""};else if(x.severity!==y.severity)e={key:k,panel:y.panel,rule:y.rule,change:"severity",from:x.severity,to:y.severity};else if(x.value!==y.value)e={key:k,panel:y.panel,rule:y.rule,change:"value",from:String(x.value),to:String(y.value)};if(e)alerts.push(e);});var sa=smap(a),sb=smap(b),sources=ids.map(function(id){var x=sa[id]||{},y=sb[id]||{},na=pa[id]||{},nb=pb[id]||{},fa=String(x.sha256_first||""),la=String(x.sha256_last||""),fb=String(y.sha256_first||""),lb=String(y.sha256_last||"");return{panel:id,csv:String(y.csv||x.csv||""),first_a:fa,last_b:lb,sha_changed:!!(fa||la)&&!!(fb||lb)&&(fa!==fb||la!==lb),frames:Number(nb.frames_in_window||0)-Number(na.frames_in_window||0)};});var left={},right={},skip=["generated_at","page","thumbnails"];flat(a,"",left,skip);flat(b,"",right,skip);var pkeys=Object.keys(left).concat(Object.keys(right));pkeys=pkeys.filter(function(p,i){return pkeys.indexOf(p)===i;}).sort();var raw=[],unchanged=0;pkeys.forEach(function(p){var ina=Object.prototype.hasOwnProperty.call(left,p),inb=Object.prototype.hasOwnProperty.call(right,p);if(!ina||!inb){raw.push({path:p,a:ina?String(left[p]):null,b:inb?String(right[p]):null});return;}if(same(left[p],right[p])){unchanged++;return;}raw.push({path:p,a:String(left[p]),b:String(right[p])});});function ftext(s){var f=(s&&s.filters)||{};return[arr(f.crops).join(", ")||"all",String(f.window||""),String(f.aggregation||""),String(f.mode||"")].join(" · ");}function wtext(s){var w=(s&&s.window)||{};return String(w.start||"")+" → "+String(w.end||"");}var header=[{key:"generated",a:String((a&&a.generated_at)||""),b:String((b&&b.generated_at)||"")},{key:"filters",a:ftext(a),b:ftext(b)},{key:"window",a:wtext(a),b:wtext(b)}];return{header:header,kpis:kpis,kpi:kpis,panels:rows,alerts:alerts,sources:sources,unchanged:unchanged,raw:raw};}/*pv-diff-end*/
function snapNum(v,d,unit){if(v===null||v===undefined||!isFinite(v))return T("ui.chip.not-measured");var t=Number(v).toFixed(d===undefined?0:d).split(".");t[0]=t[0].replace(/\B(?=(\d{3})+(?!\d))/g,",");return t.join(".")+(unit?" "+unit:"");}function snapDelta(d,p,dec,unit){if(d===null||d===undefined||!isFinite(d))return '<span class="pv-chip" data-state="unknown">'+E(T("ui.snap.notComputable"))+"</span>";if(Math.abs(d)<1e-9)return '<span class="pv-chip" data-state="unknown">'+E(T("ui.snap.unchanged"))+"</span>";var sign=d>0?"+":"";return '<span class="pv-chip" data-state="'+(d>0?"ok":"critical")+'">'+E(sign+snapNum(d,dec,unit)+(p===null||p===undefined?"":" ("+sign+Number(p).toFixed(1)+" %)"))+"</span>";}function snapSpark(v){if(!v||v.length<2)return "";var lo=Math.min.apply(null,v),hi=Math.max.apply(null,v),sp=hi-lo||1,w=72,h=18,pts=[];v.forEach(function(x,i){pts.push((i*(w/(v.length-1))).toFixed(1)+","+(h-((x-lo)/sp)*(h-4)-2).toFixed(1));});return '<svg class="pv-diff-spark" viewBox="0 0 '+w+' '+h+'"><polyline points="'+pts.join(" ")+'" fill="none" stroke="#C159F5" stroke-width="1.6"/></svg>';}function snapBlock(title,head,rows){if(!rows.length)return "";var extra=rows.length>8,html='<section class="pv-diff-block"><h4>'+E(title)+'</h4><div class="pv-tablewrap"><table><thead><tr>'+head+'</tr></thead><tbody>'+rows.slice(0,8).join("")+rows.slice(8).map(function(r){return r.replace(/^<tr/,'<tr class="pv-extra" hidden');}).join("")+'</tbody></table></div>';if(extra)html+='<button type="button" class="pv-more pv-ctl">'+E(T("ui.snap.showAll").replace("{n}",rows.length))+"</button>";return html+"</section>";}function renderDiff(a,b){var root=document.getElementById("pv-snap-diff"),banner=document.getElementById("pv-snap-banner"),table=document.getElementById("pv-snap-table"),rawBox=document.getElementById("pv-snap-raw");if(!root)return;var body=table?table.querySelector("tbody"):null;function message(text){root.innerHTML='<p class="pv-empty">'+E(text)+"</p>";if(body)body.innerHTML="";if(rawBox)rawBox.hidden=true;}if(!a||!b){message(T("ui.snap.waiting"));return;}if(a.schema!=="pv-snapshot/1"||b.schema!=="pv-snapshot/1"){message(T("ui.snap.badSchema"));return;}var diff=snapDiff(a,b);if(banner){var fa=a.filters||{},fb=b.filters||{},ch=JSON.stringify(fa.crops)!==JSON.stringify(fb.crops)||fa.window!==fb.window||fa.aggregation!==fb.aggregation||fa.mode!==fb.mode;banner.hidden=!ch;banner.textContent=ch?T("ui.snap.filtersDiffer"):"";}var o=['<div class="pv-diff-h">'];diff.header.forEach(function(h){o.push("<div>"+E(T("ui.snap.h."+h.key)+": ")+'<span class="pv-side-a">'+E(h.a||"—")+'</span> → <span class="pv-side-b">'+E(h.b||"—")+"</span></div>");});o.push("</div>");var kc={area:[0,"px"],scale:[1,"%"],freshness:[1,"%"],alerts:[0,""]},k=[];diff.kpis.forEach(function(x){var f=kc[x.key]||[0,""];k.push('<div class="pv-diff-kpi"><h5>'+E(T("ui.snap.kpi."+x.key))+'</h5><div class="pv-kpi-val">'+E(snapNum(x.b,f[0],f[1]))+'</div>'+snapDelta(x.delta,x.delta_pct,f[0],f[1])+"</div>");});o.push('<div class="pv-diff-kpis">'+k.join("")+"</div>");var ph='<th scope="col">'+E(T("ui.snap.col.panel"))+'</th><th scope="col" class="num">A</th><th scope="col" class="num">B</th><th scope="col" class="num">'+E(T("ui.snap.delta"))+'</th><th scope="col">'+E(T("ui.snap.trend"))+"</th>";o.push(snapBlock(T("ui.snap.g.panels"),ph,diff.panels.map(function(r){return "<tr><td>"+E(r.label)+'</td><td class="num pv-side-a">'+E(snapNum(r.a,0))+'</td><td class="num pv-side-b">'+E(snapNum(r.b,0))+'</td><td class="num">'+snapDelta(r.delta,r.delta_pct,0)+"</td><td>"+snapSpark(r.spark)+"</td></tr>";})));var ah='<th scope="col">'+E(T("ui.snap.col.panel"))+'</th><th scope="col">'+E(T("ui.snap.col.state"))+"</th>";o.push(snapBlock(T("ui.snap.g.alerts"),ah,diff.alerts.map(function(r){return "<tr><td>"+E(r.panel)+" · "+E(r.rule)+'</td><td><span class="pv-chip" data-state="'+(r.change==="removed"?"unknown":r.change==="severity"?"critical":"warn")+'">'+E(T("ui.snap.change."+r.change))+"</span> "+E(String(r.from))+" → "+E(String(r.to))+"</td></tr>";})));var sh='<th scope="col">'+E(T("ui.snap.col.panel"))+'</th><th scope="col">'+E(T("ui.snap.col.csv"))+'</th><th scope="col">'+E(T("ui.snap.col.first"))+'</th><th scope="col">'+E(T("ui.snap.col.last"))+'</th><th scope="col" class="num">'+E(T("ui.snap.col.frames"))+"</th>";o.push(snapBlock(T("ui.snap.g.sources"),sh,diff.sources.map(function(r){function short(s){return s?String(s).slice(0,10):"—";}return '<tr><td>'+E(r.panel)+'</td><td class="pv-csv">'+E(r.csv)+'</td><td class="pv-side-a">'+E(short(r.first_a))+'</td><td class="'+(r.sha_changed?"pv-side-b":"")+'">'+E(short(r.last_b))+'</td><td class="num">'+E((r.frames>=0?"+":"")+r.frames)+"</td></tr>";})));if(body){body.innerHTML=diff.raw.length?diff.raw.map(function(r){var d=(r.a!==null&&r.b!==null&&isFinite(Number(r.a))&&isFinite(Number(r.b)))?Number(r.b)-Number(r.a):null;return "<tr><td>"+E(r.path)+"</td><td>"+E(r.a===null?T("ui.snap.onlyB"):r.a)+"</td><td>"+E(r.b===null?T("ui.snap.onlyA"):r.b)+"</td><td>"+E(d===null?"":(d>=0?"+":"")+R6(d))+"</td></tr>";}).join(""):'<tr><td colspan="4">'+E(T("ui.snap.empty"))+"</td></tr>";}if(rawBox){rawBox.hidden=false;var summary=rawBox.querySelector("summary");if(summary)summary.textContent=T("ui.snap.rawCount").replace("{n}",diff.unchanged);}root.innerHTML=o.join("");}function readFiles(){
  var a=document.getElementById("pv-snap-a"),b=document.getElementById("pv-snap-b"),store=readFiles.d||(readFiles.d={});
  function read(input,key){
    if(!input||!input.files||!input.files.length)return;
    var r=new FileReader();
    r.onload=function(){try{store[key]=JSON.parse(r.result);}catch(e){store[key]={schema:""};}renderDiff(store.a,store.b);};
    r.readAsText(input.files[0]);
  }
  if(a)a.onchange=function(){read(a,"a");};
  if(b)b.onchange=function(){read(b,"b");};
}
function openSnap(){
  var d=document.getElementById("pv-snap"),bg=document.querySelector(".pv-snap-backdrop");if(!d)return;
  exportSnap();
  var store=readFiles.d||{};
  renderDiff(store.a,store.b);
  d.hidden=false;if(bg)bg.hidden=false;
}
function closeSnap(){
  var d=document.getElementById("pv-snap"),bg=document.querySelector(".pv-snap-backdrop");
  if(d)d.hidden=true;if(bg)bg.hidden=true;
  var o=document.getElementById("pv-f-snap");if(o)o.focus();
}
function initControls(){
  try{
    if(!payload)return;
    var cb=document.getElementById("pv-f-crop"),pop=document.getElementById("pv-crop-pop"),nt=document.getElementById("pv-filter-note");
    function placeCropPop(){
      if(!pop||pop.hidden)return;
      pop.style.left="";pop.style.right="";pop.style.top="";pop.style.bottom="";
      if(window.matchMedia&&window.matchMedia("(max-width:599px)").matches)return;
      var r=pop.getBoundingClientRect();
      if(r.right>window.innerWidth-8){pop.style.left="auto";pop.style.right="0";r=pop.getBoundingClientRect();}
      if(r.left<8){pop.style.right="auto";pop.style.left="0";}
      if(r.top<8){pop.style.top="calc(100% + 6px)";pop.style.bottom="auto";}
    }
    function openCropPop(){
      if(!cb||!pop)return;
      pop.hidden=false;cb.setAttribute("aria-expanded","true");placeCropPop();
    }
    function closeCropPop(){
      if(!pop)return;
      pop.hidden=true;if(cb)cb.setAttribute("aria-expanded","false");
    }
    if(cb&&pop)cb.addEventListener("click",function(ev){
      ev.stopPropagation();
      if(pop.hidden)openCropPop();else closeCropPop();
    });
    if(cb&&pop)document.addEventListener("pointerdown",function(ev){
      if(pop.hidden)return;
      var t=ev.target;
      if(pop.contains(t)||cb.contains(t))return;
      closeCropPop();
    });
    var done=document.getElementById("pv-crop-done");
    if(done)done.addEventListener("click",function(){closeCropPop();if(cb)cb.focus();});
    if(typeof window.addEventListener==="function")window.addEventListener("resize",placeCropPop);
    Array.prototype.forEach.call(document.querySelectorAll(".pv-crop-box"),function(box){
      box.addEventListener("change",function(){
        var wasOpen=!!(pop&&!pop.hidden);
        var on=Array.prototype.filter.call(document.querySelectorAll(".pv-crop-box"),function(x){return x.checked;});
        if(!on.length){box.checked=true;if(nt){nt.textContent=T("ui.filter.keepOne");nt.hidden=false;}return;}
        var nm=on.map(function(x){return x.value;});
        state.filters.crops=nm.length===N().length?null:N().filter(function(n){return nm.indexOf(n)>=0;});
        state.filters.notices=[];commit();applyFilters(state.filters,state.route);
        if(wasOpen&&pop){pop.hidden=false;if(cb)cb.setAttribute("aria-expanded","true");box.focus();}
      });
    });
    [["pv-f-window","window"],["pv-f-agg","agg"],["pv-f-mode","mode"]].forEach(function(p){
      var s=document.getElementById(p[0]);if(s)s.addEventListener("change",function(){state.filters[p[1]]=s.value;state.filters.notices=[];commit();applyFilters(state.filters,state.route);});
    });
    var reset=document.getElementById("pv-f-reset");if(reset)reset.addEventListener("click",function(){state.filters=def();commit();applyFilters(state.filters,state.route);});
    var snap=document.getElementById("pv-f-snap");if(snap)snap.addEventListener("click",openSnap);
    var close=document.querySelector("[data-snap-close]");if(close)close.addEventListener("click",closeSnap);
    Array.prototype.forEach.call(document.querySelectorAll("[data-snap-tab]"),function(btn){
      btn.addEventListener("click",function(){
        var want=btn.getAttribute("data-snap-tab");
        Array.prototype.forEach.call(document.querySelectorAll("[data-snap-tab]"),function(o){o.setAttribute("aria-selected",o===btn?"true":"false");});
        Array.prototype.forEach.call(document.querySelectorAll("[data-snap-pane]"),function(p){p.hidden=p.getAttribute("data-snap-pane")!==want;});
      });
    });
    var dl=document.getElementById("pv-snap-dl");if(dl)dl.addEventListener("click",downloadSnap);
    var cp=document.getElementById("pv-snap-copy");if(cp)cp.addEventListener("click",copySnap);
    readFiles();
    document.addEventListener("keydown",function(ev){
      if(ev.key!=="Escape")return;
      if(pop&&!pop.hidden){closeCropPop();if(cb)cb.focus();return;}
      var d=document.getElementById("pv-snap");if(d&&!d.hidden)closeSnap();
    });
  }catch(err){if(window.console&&window.console.log)window.console.log("dashboard filters disabled",err);}
}
initControls();
"""


JS: str = _JS_CORE.replace("/*__FILTER__*/", JS_FILTER)
