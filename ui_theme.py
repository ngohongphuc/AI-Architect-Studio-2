"""Thành phần và phong cách dùng chung của AI Architect Studio."""
from __future__ import annotations

import html
from base64 import b64encode
from functools import lru_cache
from pathlib import Path

import streamlit as st

TONES = {
    "neutral": ("#45565E", "#F0EFEB", "#E3E0D8"),
    "info": ("#185B76", "#E2EFF4", "#D6E7EF"),
    "brand": ("#08656D", "#DFEFEE", "#CFE6E5"),
    "success": ("#235F35", "#E5F1E3", "#D6E8D6"),
    "warning": ("#8B460C", "#FCEED9", "#F1DEC0"),
    "danger": ("#9B302B", "#FAEAE6", "#EFCFC9"),
}

AGENT_STATUS = {
    "skipped": ("Đã tắt", "neutral"),  # trạng thái agent -> (nhãn, tông)
    "waiting": ("Chờ", "neutral"), "running": ("Đang chạy", "info"), "revising": ("Đang sửa", "warning"),
    "done": ("Hoàn thành", "success"), "error": ("Lỗi", "danger"), "paused": ("Tạm dừng", "neutral"),
}
RUN_STATUS_TONE = {
    "not_passed": ("Chưa đạt", "danger"), "needs_input": ("Cần bổ sung yêu cầu", "warning"),
    "running": ("Đang chạy", "warning"), "paused": ("Tạm dừng", "neutral"), "awaiting_approval": ("Chờ duyệt", "info"),
    "done": ("Hoàn thành", "success"), "stopped": ("Đã dừng", "neutral"), "error": ("Lỗi", "danger"),
    "idle": ("Chưa chạy", "neutral"),
}

CSS = """
<style>
:root {
  --aa-bg: #F6F5F1; --aa-paper: #FFFEFC; --aa-text: #112C39; --aa-muted: #4D6169;
  --aa-line: #DEDFDA; --aa-teal: #087B81; --aa-teal-dark: #075E65; --aa-soft: #DDEEEB;
  --aa-wood: #A25D28; --aa-radius: 12px; --aa-shadow: 0 1px 3px #2030360d;
}
[data-testid="stMainBlockContainer"] {
  max-width: 1680px; padding: 3.15rem clamp(1rem, 2vw, 2rem) 2.25rem;
}
/* Thanh công cụ Streamlit cao 3.75rem và đặt ngoài luồng cuộn. */
[data-testid="stMainBlockContainer"]:has(.st-key-page_heading) { padding-block-start: 3.75rem; }
[data-testid="stHeader"] { background: var(--aa-bg); }
[data-testid="stSidebarContent"] { border-right: 1px solid var(--aa-line); position: relative; }
[data-testid="stSidebarUserContent"] { padding: .4rem .75rem 1rem; }
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] button {
  opacity: 1; visibility: visible;
}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: .28rem; }
.aa-wordmark { display: flex; align-items: center; gap: .62rem; padding: 0 .35rem .95rem;
  margin: 0 .2rem .54rem; border-bottom: 1px solid var(--aa-line); font-size: 1.16rem; line-height: 1.15;
  font-weight: 780; letter-spacing: -.032em; color: var(--aa-text); }
.aa-mark { width: 4.05rem; height: 3.55rem; flex: none; color: var(--aa-wood); }
.st-key-sidebar_art { position: absolute; inset: auto 0 0; pointer-events: none; }
.aa-house-art { display: block; width: 100%; height: auto; }
.st-key-sidebar_art .aa-house-art { max-height: min(38dvh, 340px); object-fit: cover; object-position: center 69%; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { padding: .62rem .78rem; min-height: 2.78rem;
  border-radius: 8px; font-weight: 620; color: var(--aa-text); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-weight: inherit; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: #EFEEE8; }
[data-testid="stSidebar"] .st-key-nav_active a[data-testid="stPageLink-NavLink"] {
  background: var(--aa-soft); color: var(--aa-teal-dark); font-weight: 700;
}
[data-testid="stSidebar"] .st-key-nav_active a[data-testid="stPageLink-NavLink"]:hover { background: #D3E9E5; }
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 { color: var(--aa-text); }
.aa-heading-line { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem .8rem; }
.aa-title { margin: 0; padding: 0; font-size: clamp(1.85rem, 2.7vw, 2.55rem); line-height: 1.12;
  font-weight: 800; letter-spacing: -.04em; }
.aa-heading-project { min-width: 0; overflow-wrap: anywhere; font-size: .91rem; line-height: 1.45;
  color: var(--aa-muted); font-weight: 640; }
.aa-heading-project::before {
  content: ""; display: inline-block; width: .35rem; height: .35rem; margin-inline-end: .45rem;
  vertical-align: .12em; border-radius: 50%; background: var(--aa-wood);
}
.aa-sub { font-size: .96rem; color: var(--aa-muted); margin: .25rem 0 0; line-height: 1.55; }
.st-key-page_heading [role="radiogroup"] { justify-content: flex-end; }
.aa-section h2 { margin: 0; padding: 0; font-size: 1.3rem; line-height: 1.22; font-weight: 750; letter-spacing: -.022em; }
.aa-section p { margin: .25rem 0 0; color: var(--aa-muted); font-size: .87rem; }
.aa-eyebrow { font-size: .83rem; font-weight: 680; color: var(--aa-muted); margin-bottom: .25rem; }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--aa-paper); border-radius: var(--aa-radius);
  box-shadow: var(--aa-shadow); }
.st-key-project_brief, .st-key-project_defaults { background: var(--aa-paper); }
.st-key-project_defaults { border-top: 2px solid var(--aa-wood); }
.st-key-project_resume, .st-key-project_empty { background: var(--aa-paper); }
.aa-resume-name { font-size: 1.4rem; font-weight: 750; overflow-wrap: anywhere; }
.aa-project-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem;
  color: var(--aa-muted); font-size: .85rem; }
.aa-studio-run { display: flex; flex-wrap: wrap; align-items: center; column-gap: 1rem; row-gap: .4rem;
  font-size: .84rem; color: var(--aa-muted); }
.aa-studio-run b { color: var(--aa-text); margin-inline-start: .25rem; }
.aa-brief-assumptions { display: grid; gap: .25rem; margin: 0; padding-inline-start: 1.15rem;
  color: var(--aa-muted); font-size: .86rem; }
.st-key-workflow_settings, .st-key-model_settings, .st-key-reference_settings, .st-key-result_downloads {
  background: var(--aa-paper);
}
.st-key-result_downloads [data-testid="stVerticalBlock"] { gap: .65rem; }
.st-key-result_downloads [data-stale="true"] [data-testid="stDownloadButton"] button {
  pointer-events: none; opacity: .55;
}
[data-testid="stTable"] th, [data-testid="stTable"] td { overflow-wrap: anywhere; }
[data-testid="stTextArea"] textarea { line-height: 1.55; }
[data-testid="stDataFrame"], [data-testid="stExpander"] details, [data-testid="stAlert"] { border-radius: var(--aa-radius); }
[data-testid="stExpander"] details { background: var(--aa-paper); }
[data-testid="stExpander"] summary p { font-weight: 600; }
[data-testid="stMetric"] { padding: .7rem .85rem; border-radius: var(--aa-radius); background: var(--aa-paper);
  border: 1px solid var(--aa-line); }
[data-testid="stMetricLabel"] p { font-size: .83rem; font-weight: 610; color: var(--aa-muted); }
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 680; letter-spacing: -.025em; }
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  font-weight: 630; min-height: 2.45rem; transition: background-color .15s, border-color .15s;
}
button[kind="primary"]:hover:not(:disabled), button[kind="primaryFormSubmit"]:hover:not(:disabled) {
  background: var(--aa-teal-dark); border-color: var(--aa-teal-dark);
}
button:disabled { cursor: not-allowed; }
button:focus-visible, a:focus-visible, [role="tab"]:focus-visible {
  outline: 2px solid var(--aa-teal); outline-offset: 2px;
}
[data-testid="stTabs"] [role="tablist"] { gap: .35rem; }
[data-testid="stTabs"] [role="tab"] { padding-inline: .72rem; min-height: 2.55rem; border-radius: 8px 8px 0 0; }
[data-testid="stTabs"] [role="tab"]:hover { background: var(--aa-soft); }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { background: var(--aa-paper); color: var(--aa-teal); }
[data-testid="stTabs"] [role="tab"] p { font-size: .9rem; font-weight: 650; }

.aa-pill { display: inline-flex; align-items: center; gap: .4rem; padding: .22rem .57rem;
  font-size: .78rem; font-weight: 650; line-height: 1.4; border: 1px solid; border-radius: 999px; }
.aa-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.aa-pill.live .dot { animation: aa-pulse 1.4s ease-in-out infinite; }
@keyframes aa-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
.aa-approval-head { display: flex; justify-content: space-between; align-items: flex-start; gap: .9rem;
  border-bottom: 1px solid var(--aa-line); padding-bottom: .8rem; flex-wrap: wrap; }
.aa-approval-head h3 { font-size: 1.15rem; margin: 0; padding: 0; }
.aa-stepper { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); align-items: center;
  gap: .7rem; background: var(--aa-paper); padding: 1rem; border-radius: var(--aa-radius); }
.aa-step { display: flex; align-items: center; gap: .6rem; }
.aa-step-dot { width: 29px; height: 29px; border-radius: 50%; display: grid; place-items: center;
  flex: none; color: var(--aa-muted); background: #EFEEE8; font-size: .8rem; font-weight: 690; }
.aa-step-label { font-weight: 640; font-size: .87rem; }
.aa-step-sub, .aa-tl-meta { color: var(--aa-muted); font-size: .75rem; }
.aa-step.done .aa-step-dot { background: #E9F2E9; color: #256249; }
.aa-step.active .aa-step-dot { background: var(--aa-teal); color: #fff; }
.aa-step.warn .aa-step-dot { background: #FEF0E1; color: #864208; }
.aa-step.err .aa-step-dot { background: #FAEAE6; color: #9B302B; }
.aa-tl-item { display: grid; grid-template-columns: 62px 10px minmax(0, 1fr); align-items: start;
  gap: .6rem; padding: .6rem 0; border-bottom: 1px solid var(--aa-line); }
.aa-tl-item:last-child { border-bottom: none; }
.aa-tl-time { font-variant-numeric: tabular-nums; font-size: .79rem; color: var(--aa-muted); }
.aa-tl-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 7px; background: var(--aa-teal); }
.aa-tl-item.bad .aa-tl-dot { background: #B74B32; }
.aa-tl-item.user .aa-tl-dot { background: var(--aa-wood); }
.aa-tl-route { font-size: .88rem; font-weight: 640; }
.aa-tl-route .arrow { padding: 0 .35em; color: var(--aa-muted); }
.aa-tl-msg { color: var(--aa-muted); font-size: .875rem; margin: .18rem 0; }
.aa-kv { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, auto); gap: .5rem 1rem; font-size: .87rem; }
.aa-kv span { color: var(--aa-muted); }
.aa-kv b { font-weight: 650; text-align: right; overflow-wrap: anywhere; }
@media (max-width: 640px) {
  .st-key-page_heading [data-testid="stHorizontalBlock"] { gap: .45rem; }
  .st-key-page_heading [role="radiogroup"] { justify-content: flex-start; }
}
@media (prefers-reduced-motion: reduce) {
  .aa-pill.live .dot { animation: none; }
  .stButton > button { transition: none; }
}
</style>
"""


ASSETS = Path(__file__).with_name("assets")


def inject() -> None:
    st.html(CSS)
    st.html(ASSETS / "studio.css")


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def html_block(markup: str) -> None:
    st.html(markup)


# ---------------------------------------------------------------------------
# Thành phần
# ---------------------------------------------------------------------------
ICONS = {
    "layers": "M12 3 2 8l10 5 10-5-10-5ZM2 12l10 5 10-5M2 16l10 5 10-5",
    "target": "M21 12a9 9 0 1 1-3-6.7M17 12a5 5 0 1 1-5-5m0 5 8-8m-1 0h3v3",
    "check": "M22 12a10 10 0 1 1-5.5-9M7 12l3.2 3.3L21 5",
    "clock": "M22 12a10 10 0 1 1-3-7.1M12 6v6l4 2",
    "calendar": "M3 6h18v15H3zM7 3v6m10-6v6M3 11h18",
    "clipboard": "M9 5H5v16h14V5h-4M9 3h6v5H9zM8 14l2 2 5-5",
    "bed": "M3 17v3m18-3v3M3 17v-5h18v5H3Zm2-5V6h14v6M8 9h3m2 0h3",
    "area": "M4 3h6v7h5V3h5v18H4zM4 14h6v7m5-11v6h5",
    "coins": "M13 7c0 2-2.5 3-5 3S3 9 3 7s2.5-3 5-3 5 1 5 3ZM3 7v9c0 2 2.5 3 5 3m-5-8c0 2 2.5 3 5 3m8-4c3 0 5 1 5 3s-2 3-5 3-5-1-5-3 2-3 5-3Zm-5 3v5c0 2 2 3 5 3s5-1 5-3v-5",
    "shield": "M12 22s8-4.5 8-11V5l-8-3-8 3v6c0 6.5 8 11 8 11Zm-4-10 3 3 5-6",
    "download": "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
    "file": "M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6",
    "repeat": "M4 10a8 8 0 0 1 14-5l2 2m0-4v4h-4M20 14a8 8 0 0 1-14 5l-2-2m0 4v-4h4",
    "leaf": "M19 4c1 11-3 15-8 15-4 0-6-3-5-6 1-4 6-6 13-9ZM4 22l11-11",
    "idea": "M9 18h6m-6 3h6m-6-6c0-2-3-3-3-7a6 6 0 0 1 12 0c0 4-3 5-3 7",
    "warning": "M12 3 2 21h20L12 3Zm0 6v5m0 3v1",
    "house": "M3 11 12 3l9 8m-2-2v12H5V9m5 12v-7h4v7",
    "info": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-11v5m0-9v1",
    "arrow": "M4 12h15m-6-6 6 6-6 6",
}


def svg_uri(width: int, height: int, path: str, color: str) -> str:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" fill="none" stroke="{color}" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="{path}"/></svg>')
    return "data:image/svg+xml;base64," + b64encode(svg.encode("ascii")).decode("ascii")


@lru_cache(maxsize=len(ICONS))
def icon(name: str) -> str:
    uri = svg_uri(24, 24, ICONS[name], "black")
    return f'<span class="aa-icon" aria-hidden="true" style="--aa-glyph:url({uri})"></span>'


@lru_cache(maxsize=1)
def _house_uri() -> str:
    return "data:image/svg+xml;base64," + b64encode((ASSETS / "studio-townhouse.svg").read_bytes()).decode("ascii")


def house_art() -> str:
    return f'<img class="aa-house-art" aria-hidden="true" alt="" src="{_house_uri()}">'


def brand() -> None:
    uri = svg_uri(88, 72, "M2 68h84M14 68V43L62 4v64M49 68V25l31 19v24M32 68V57l5-4 5 4v11", "#A25D28")
    html_block(f'<div class="aa-wordmark"><img class="aa-mark" alt="" src="{uri}">'
               '<span>AI Architect<br>Studio</span></div>')


def emblem(glyph: str, tone: str = "brand") -> str:
    fg, bg, _ = TONES[tone]
    return f'<span class="aa-emblem" style="color:{fg};background:{bg}">{icon(glyph)}</span>'


def kpi(title: str, value, glyph: str, tone: str = "brand", note: str = "", *, compact: bool = False) -> str:
    caption = f'<small class="aa-kpi-note">{esc(note)}</small>' if note else ""
    variant = ' data-compact="true"' if compact else ""
    return (f'<div class="aa-kpi">{emblem(glyph, tone)}<div class="aa-kpi-body">'
            f'<span class="aa-kpi-title">{esc(title)}</span><strong class="aa-kpi-value"{variant}>{esc(value)}</strong>'
            f'{caption}</div></div>')


def kpi_grid(cards: list[str]) -> None:
    html_block(f'<div class="aa-kpi-grid">{"".join(cards)}</div>')


def fact(title: str, value: str, glyph: str, tone: str = "brand", *, status: bool = False) -> str:
    rendered = pill(value, tone) if status else esc(value)
    return (f'<div class="aa-fact">{emblem(glyph, tone)}<span>{esc(title)}</span>'
            f'<span class="aa-fact-value">{rendered}</span></div>')


def pill(text: str, tone: str = "neutral", live: bool = False, glyph: str = "") -> str:
    fg, bg, bd = TONES.get(tone, TONES["neutral"])
    return (f'<span class="aa-pill{" live" if live else ""}" style="color:{fg};background:{bg};border-color:{bd}">'
            f'{icon(glyph) if glyph else "<span class=dot></span>"}{esc(text)}</span>')


def run_pill(status: str) -> str:
    text, tone = RUN_STATUS_TONE.get(status, (status, "neutral"))
    glyph = {"done": "check", "running": "clock", "awaiting_approval": "clock", "error": "warning"}.get(status, "")
    return pill(text, tone, live=status == "running", glyph=glyph)


def page_header(title: str, subtitle: str = "", *, project: str = "", live_badge: bool = True) -> None:
    name = f'<span class="aa-heading-project">{esc(project)}</span>' if project else ""
    mode = pill("Dữ liệu thật", "brand") if live_badge else ""
    description = f'<p class="aa-sub">{esc(subtitle)}</p>' if subtitle else ""
    st.html(f'<div class="aa-header"><div class="aa-heading-line"><h1 class="aa-title">{esc(title)}</h1>'
            f'{name}{mode}</div>{description}</div>')


def section(title: str, subtitle: str = "", *, glyph: str = "") -> None:
    mark = icon(glyph) + " " if glyph else ""
    html_block(f'<div class="aa-section"><h2>{mark}{esc(title)}</h2>' + (f"<p>{esc(subtitle)}</p>" if subtitle else "")
               + "</div>")


def stepper(steps: list[tuple[str, str, str]]) -> None:
    """steps: [(nhãn, phụ đề, trạng thái: todo|active|done|warn|err)]."""
    parts = []
    for i, (lab, sub, stt) in enumerate(steps, start=1):
        mark = "✓" if stt == "done" else ("!" if stt in ("warn", "err") else str(i))
        cls = {"done": "done", "active": "active", "warn": "warn", "err": "err"}.get(stt, "")
        parts.append(f'<div class="aa-step {cls}"><div class="aa-step-dot">{mark}</div><div>'
                     f'<div class="aa-step-label">{esc(lab)}</div><div class="aa-step-sub">{esc(sub)}</div></div></div>')
    html_block(f'<div class="aa-stepper">{"".join(parts)}</div>')


def timeline(items: list[dict], label_fn) -> None:
    """items: sự kiện AgentEvent (đã lọc done/error)."""
    if not items:
        st.caption("Chưa có hoạt động.")
        return
    rows = []
    for e in items:
        cls = "bad" if (e.get("feedback") or e.get("status") == "error") else ("user" if e["agent"] == "user" else "ok")
        to = label_fn(e["to_agent"]) if e.get("to_agent") else "Kết thúc"
        meta = ""
        if e["agent"] != "user":
            meta = f'<div class="aa-tl-meta">v{e.get("version", 0)} · {float(e.get("duration_s") or 0):.1f}s · ' \
                   f'{e.get("tokens") or 0} token</div>'
        rows.append(f'<div class="aa-tl-item {cls}"><div class="aa-tl-time">{esc(e["time"])}</div>'
                    f'<div class="aa-tl-dot"></div><div><div class="aa-tl-route">{esc(label_fn(e["agent"]))}'
                    f'<span class="arrow">→</span>{esc(to)}</div><div class="aa-tl-msg">{esc(e["summary"])}</div>{meta}'
                    f'</div></div>')
    html_block(f'<div class="aa-tl">{"".join(rows)}</div>')


def kv(rows: list[tuple[str, str]]) -> str:
    return '<div class="aa-kv">' + "".join(f"<span>{esc(k)}</span><b>{v}</b>" for k, v in rows) + "</div>"
