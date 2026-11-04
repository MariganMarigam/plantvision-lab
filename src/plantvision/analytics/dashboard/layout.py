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
 border-radius:6px;padding:5px 8px;font-size:11.5px;font-variant-numeric:tabular-nums;box-shadow:0 8px 20px rgba(10,8,24,.4)}
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
        f'<button type="button" class="pv-lang" id="pv-lang" aria-label="Language">'
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
    """Overview status board with a per-panel area sparkline."""
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
            "<tr>"
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
    return (
        '<div class="pv-tablewrap"><table class="pv-table">'
        f'<caption data-en="Panel status" data-ru="Состояние панелей">{caption}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
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
        )
        for field in ("what", "how", "now", "do")
    )
    return (
        f'<article class="pv-card" id="pv-card-{card_id}" data-chart="{card_id}" '
        f'data-tab="{esc(str(card["tab"]))}" data-sub="{esc(str(card["sub"]))}" '
        f'data-span="{clamped}" '
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
            f"{hidden}>{heading}{body}</section>"
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
            _card(card, svgs.get(str(card["id"]), ""), payload, lang, cols)
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
        + f'<main class="pv-main" id="pv-main">{panels_html}</main>'
        "</div></div>"
        + _drawer(lang)
        + _templates(cards, payload, lang)
        + f'<script type="application/json" id="pv-data">{data_json}</script>'
        + f'<script type="application/json" id="pv-labels">{labels_json}</script>'
        + f"<script>{js}</script>"
        "</body></html>"
    )
    return document


JS = r"""
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
      return { tab: "overview", sub: subsFor("overview")[0] || "", chart: null };
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
    return { tab: tab, sub: sub, chart: chart };
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
      location.hash = "#/" + (template.getAttribute("data-tab") || "overview") + "/" +
        (template.getAttribute("data-sub") || "") + "~" + cardId;
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
      location.hash = "#/" + tab + (sub ? "/" + sub : "");
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
    if (target === backdrop) { closeDrawer(true); return; }
    var subtab = target.closest && target.closest(".pv-subtab");
    if (subtab) {
      location.hash = "#/" + subtab.getAttribute("data-tab") + "/" + subtab.getAttribute("data-sub");
      return;
    }
    var railButton = target.closest && target.closest(".pv-rail [role=tab]");
    if (railButton) { location.hash = "#/" + railButton.getAttribute("data-tab"); return; }
    if (target.closest && target.closest("#pv-lang")) {
      applyLang(state.lang === "en" ? "ru" : "en", document);
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
      var first = payload.panels && payload.panels[0];
      var series = first && first.series && first.series[key];
      if (!figure || !series || !series.runs || !series.runs.length) { hideTip(); return; }
      var points = [];
      series.runs.forEach(function (run) { points = points.concat(run); });
      if (!points.length) { hideTip(); return; }
      var rect = figure.getBoundingClientRect();
      if (!rect.width) { hideTip(); return; }
      var ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      var low = points[0][0];
      var high = points[points.length - 1][0];
      var wanted = low + ratio * (high - low);
      var best = points[0];
      var distance = Math.abs(best[0] - wanted);
      points.forEach(function (point) {
        var current = Math.abs(point[0] - wanted);
        if (current < distance) { distance = current; best = point; }
      });
      var when = new Date(best[0]).toISOString().slice(5, 16).replace("T", " ");
      var value = Number(best[1]).toFixed(series.decimals || 0);
      var node = ensureTip();
      node.textContent = when + " · " + value + " " + (series.unit || "");
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
  detectTier();
  applyRoute(parseRoute(location.hash), true);
})();
"""



