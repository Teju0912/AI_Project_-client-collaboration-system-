"""
manager_merged.py

Merged version of manager.py + teju_manager.py.

After a full line-by-line comparison, manager.py was found to be a strict
superset of teju_manager.py: every function, page, and helper in
teju_manager.py exists in manager.py with the same or an improved
implementation. manager.py additionally includes:

  1. The full "Project Modules" workflow feature (imports:
     get_project_modules, create_project_module, insert_project_module,
     update_project_module, delete_project_module,
     reorder_project_modules; constants MODULE_STATUS_META /
     MODULE_ICON_OPTIONS; functions _get_project_modules,
     _resequence_module_locks, _inject_module_flow_css,
     _render_module_flow_card, _module_detail_dialog,
     _manage_modules_dialog, _render_project_modules_section) — entirely
     absent from teju_manager.py.
  2. A bug fix in the Tasks page dialog handling: opening/creating an
     issue now properly clears the other dialog's session-state flag
     (elif instead of two independent ifs), and switching sidebar pages
     clears module/task dialog state too — teju_manager.py did not have
     this fix.

No function from either file was removed.
"""

import datetime as dt
import html

import streamlit as st
import plotly.graph_objects as go

from api_client import (
    get_projects, get_tasks, list_documents, get_clients, get_users,
    get_team, create_project, update_project, assign_team,
    get_project_modules, create_project_module, insert_project_module,
    update_project_module, delete_project_module, reorder_project_modules,
    create_client, update_client, delete_client,
    patch_task_status, update_task, delete_task, download_document, create_task,
    upload_document, delete_document,
    get_task, create_subtask, add_comment, add_task_link, remove_task_link,
    generate_weekly_report, get_weekly_reports,
    analyze_requirement, get_requirement_analysis,
    approve_requirement_analysis, reject_requirement_analysis,
)
from views.shared import (
    render_sidebar_header,
    show_api_error,
    show_document_preview,
    session_token,
    session_user,
    render_meeting_panel,
    rag_status_label,
)

STATUS_META = {
    "todo":        {"label": "To Do",       "icon": "⚪", "color": "gray",   "hex": "#8B5CF6"},
    "in_progress": {"label": "In Progress", "icon": "🔵", "color": "blue",   "hex": "#3B82F6"},
    "testing":     {"label": "Testing",     "icon": "🟠", "color": "orange", "hex": "#F59E0B"},
    "done":        {"label": "Done",        "icon": "🟢", "color": "green",  "hex": "#22C55E"},
}
PRIORITY_META = {
    "low": {"label": "Low", "icon": "🟢", "pill": "pill-green"},
    "medium": {"label": "Medium", "icon": "🟡", "pill": "pill-orange"},
    "high": {"label": "High", "icon": "🟠", "pill": "pill-red"},
    "urgent": {"label": "Urgent", "icon": "🔴", "pill": "pill-red"},
}
PRIORITY_OPTIONS = list(PRIORITY_META)
LINK_TYPE_OPTIONS = ["blocks", "is blocked by", "relates to", "duplicates"]
CLIENT_STATUS_META = {
    "active":   {"icon": "🟢", "color": "green",  "hex": "#22C55E"},
    "pending":  {"icon": "🟡", "color": "orange", "hex": "#EAB308"},
    "inactive": {"icon": "⚪", "color": "gray",   "hex": "#6B7280"},
}
CLIENT_STATUS_OPTIONS = ["active", "pending", "inactive"]

PROJECT_STATUS_META = {
    "planning":  {"icon": "📝", "hex": "#F59E0B"},
    "active":    {"icon": "🟢", "hex": "#22C55E"},
    "on_hold":   {"icon": "⏸️", "hex": "#EAB308"},
    "completed": {"icon": "✅", "hex": "#3B82F6"},
}
MODULE_STATUS_META = {
    "completed":   {"label": "Completed",   "icon": "✅", "color": "#22C55E"},
    "in_progress": {"label": "In Progress", "icon": "🔵", "color": "#4F46E5"},
    "locked":      {"label": "Locked",      "icon": "🔒", "color": "#9CA3AF"},
}
MODULE_ICON_OPTIONS = ["🧩", "👤", "👥", "💳", "🔔", "⚙️", "🔐", "📦", "🔗", "📊", "🧪", "📁"]

ALL_PROJECTS_LABEL = "All Projects"
ACTIVE_PROJECT_KEY = "manager_active_project_id"
PROJECT_STATUS_OPTIONS = ["planning", "active", "on_hold", "completed"]

NAV_PAGES = [
    "🏠 Dashboard", "🏢 Clients", "📁 Projects", "✅ Tasks",
    "📄 Documents", "🎙️ Meetings", "📊 Weekly Reports", "🧠 Requirement Analyzer",
]

NAV_RADIO_KEY = "manager_nav_radio"


# --------------------------------------------------------------------------
# CLEAN LIGHT THEME — matches the "Affordable AI" dashboard screenshot:
# flat white cards, soft border + shadow, plain sidebar list, colored
# rounded icon badges. No gradients / glow / shimmer.
#
# IMPORTANT: Streamlit's selectbox / multiselect dropdown (BaseWeb "Select")
# renders its option list in a floating "popover" portal attached to
# <body>, OUTSIDE the .stApp container. Because our light theme only
# targeted .stApp and its descendants, that popover fell back to the
# app's dark base theme — white text on a near-black background — which
# is why the dropdown looked broken in the screenshot. The rules below
# specifically target that portal so it always renders with our light
# card styling, regardless of where it's mounted in the DOM.
#
# NOTE: the same "outside .stApp" issue applies to Streamlit's own top
# header bar ([data-testid='stHeader']), toolbar, and the decorative
# gradient strip beneath it — they render with the dark base theme by
# default, which is the black band seen at the very top of the app.
# The rules below force them to match the light theme background too.
# --------------------------------------------------------------------------
def _inject_light_theme():
    css_lines = [
        "<style>",
        ".stApp { background: #F7F8FA; }",
        "[data-testid='stHeader'] { background-color: #F8F9FF !important; }",
        "[data-testid='stToolbar'] { background-color: transparent !important; }",
        "[data-testid='stDecoration'] { background-image: none !important; background-color: #F8F9FF !important; }",
        "[data-testid='stAppViewContainer'] { background-color: #F8F9FF !important; }",
        "[data-testid='stMain'] { background-color: transparent !important; }",
        "[data-testid='stStatusWidget'] { background-color: #FFFFFF !important; }",
        "[data-testid='stStatusWidget'] * { color: #111827 !important; }",
        ".block-container { padding-top: 1.5rem; padding-bottom: 3rem; }",
        "",
        "h1, h2, h3, h4, h5, h6, p, span, label, li, div, .stMarkdown { color: #111827 !important; }",
        "[data-testid='stMarkdownContainer'], [data-testid='stMarkdownContainer'] * { color: #111827 !important; }",
        "[data-testid='stHeadingWithActionElements'], [data-testid='stHeadingWithActionElements'] * { color: #111827 !important; }",
        ".stCaption, [data-testid='stCaptionContainer'], [data-testid='stCaptionContainer'] * { color: #6B7280 !important; }",
        "[data-testid='stWidgetLabel'] p { color: #111827 !important; }",
        "",
        "section[data-testid='stSidebar'] {",
        "    background: #FFFFFF;",
        "    border-right: 1px solid #EEF0F3;",
        "}",
        "section[data-testid='stSidebar'] * { color: #374151 !important; }",
        "/* The role is rendered as inline code by render_sidebar_header. */",
        "section[data-testid='stSidebar'] code {",
        "    background: #E0E7FF !important;",
        "    color: #312E81 !important;",
        "    border: 1px solid #C7D2FE !important;",
        "    border-radius: 5px !important;",
        "    padding: 2px 6px !important;",
        "}",
        "",
        "/* Sidebar nav — plain list, simple selected highlight (like screenshot) */",
        "section[data-testid='stSidebar'] div[role='radiogroup'] {",
        "    display: flex;",
        "    flex-direction: column;",
        "    gap: 2px;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label {",
        "    background-color: transparent;",
        "    border: none;",
        "    border-radius: 8px;",
        "    padding: 9px 12px !important;",
        "    margin: 0 !important;",
        "    cursor: pointer;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:hover {",
        "    background-color: #F3F4F6;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label[data-checked='true'],",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) {",
        "    background-color: #EEF2FF !important;",
        "    border-left: 3px solid #4F46E5 !important;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) * {",
        "    color: #4338CA !important;",
        "    font-weight: 600;",
        "}",
        "/* Keep the selected Home/Dashboard label readable on its highlight. */",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked),",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) p,",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) span {",
        "    color: #312E81 !important;",
        "}",
        "/* Hide the round radio bullet so the nav reads as plain tabs, not",
        "   a radio-button list — the marker is the first child of each",
        "   label (a BaseWeb-rendered circle), separate from the emoji+text",
        "   which lives in the second child. */",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label > div:first-child {",
        "    display: none !important;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label {",
        "    gap: 0 !important;",
        "}",
        "/* Readable role chip used in the Project Team card. */",
        ".team-role-badge {",
        "    display: inline-block;",
        "    background: #E0E7FF !important;",
        "    color: #312E81 !important;",
        "    border: 1px solid #C7D2FE;",
        "    border-radius: 999px;",
        "    font-size: 0.75rem;",
        "    font-weight: 600;",
        "    line-height: 1.3;",
        "    padding: 1px 7px;",
        "}",
        "",
        "/* Cards — flat white, soft border + shadow, no motion */",
        "div[data-testid='stVerticalBlockBorderWrapper'] {",
        "    background-color: #FFFFFF !important;",
        "    border: 1px solid #EEF0F3 !important;",
        "    border-radius: 14px !important;",
        "    box-shadow: 0 1px 2px rgba(16,24,40,0.04);",
        "    padding: 0.35rem;",
        "}",
        "",
        "div[data-testid='stMetricValue'] { font-weight: 700; color: #111827 !important; }",
        "div[data-testid='stMetricLabel'] { color: #6B7280 !important; }",
        "",
        ".stButton button {",
        "    background-color: #FFFFFF;",
        "    color: #374151;",
        "    border: 1px solid #E5E7EB;",
        "    border-radius: 8px;",
        "}",
        ".stButton button:hover {",
        "    border-color: #4F46E5;",
        "    color: #4338CA;",
        "}",
        ".stButton button[kind='primary'] {",
        "    background-color: #4F46E5;",
        "    color: #FFFFFF !important;",
        "    border: 1px solid #4F46E5;",
        "}",
        ".stButton button[kind='primary']:hover {",
        "    background-color: #4338CA;",
        "    border-color: #4338CA;",
        "}",
        ".stButton button[kind='primary'] p { color: #FFFFFF !important; }",
        "",
        "/* Download button uses a separate wrapper (stDownloadButton) from",
        "   regular st.button (stButton), so it wasn't caught by the rules",
        "   above and fell back to the dark theme — solid black pill. */",
        "div[data-testid='stDownloadButton'] button {",
        "    background-color: #FFFFFF !important;",
        "    color: #374151 !important;",
        "    border: 1px solid #E5E7EB !important;",
        "    border-radius: 8px !important;",
        "}",
        "div[data-testid='stDownloadButton'] button p,",
        "div[data-testid='stDownloadButton'] button span,",
        "div[data-testid='stDownloadButton'] button div { color: #374151 !important; }",
        "div[data-testid='stDownloadButton'] button:hover {",
        "    border-color: #4F46E5 !important;",
        "    color: #4338CA !important;",
        "}",
        "div[data-testid='stDownloadButton'] button:hover p,",
        "div[data-testid='stDownloadButton'] button:hover span,",
        "div[data-testid='stDownloadButton'] button:hover div { color: #4338CA !important; }",
        "",
        ".stProgress > div > div > div > div { border-radius: 6px; }",
        ".stProgress > div > div { background-color: #F3F4F6; border-radius: 6px; }",
        "",
        "[data-testid='stDataFrame'] { color: #111827 !important; }",
        "",
        "/* Icon badge used on stat cards, matching screenshot's rounded squares */",
        ".icon-badge {",
        "    width: 44px; height: 44px; border-radius: 12px;",
        "    display: flex; align-items: center; justify-content: center;",
        "    font-size: 1.25rem; margin-bottom: 0.5rem;",
        "}",
        "",
        "/* Pill badges used for deadline / status tags */",
        ".pill {",
        "    display: inline-block; padding: 3px 10px; border-radius: 999px;",
        "    font-size: 0.75rem; font-weight: 600; white-space: nowrap;",
        "}",
        ".pill-red    { background:#FEE2E2; color:#B91C1C; }",
        ".pill-orange { background:#FEF3C7; color:#B45309; }",
        ".pill-green  { background:#DCFCE7; color:#15803D; }",
        ".pill-blue   { background:#DBEAFE; color:#1D4ED8; }",
        ".pill-gray   { background:#F3F4F6; color:#374151; }",
        "",
        "/* Status dot used in Team Activity rows */",
        ".status-dot {",
        "    width: 8px; height: 8px; border-radius: 50%;",
        "    display: inline-block; margin-right: 6px;",
        "}",
        "",
        "/* Quick action tiles */",
        ".qa-title { font-weight: 600; font-size: 0.92rem; margin-top: 2px; }",
        "",
        "/* ============================================================",
        "   FIX: BaseWeb Select / Multiselect dropdown popover.",
        "   This portal mounts at document.body, outside .stApp, so it",
        "   must be styled globally (not scoped to .stApp) to avoid the",
        "   dark, low-contrast look seen when the popover opens.",
        "   ============================================================ */",
        "div[data-baseweb='popover'] { z-index: 999999 !important; }",
        "div[data-baseweb='popover'] div[data-baseweb='menu'],",
        "div[data-baseweb='popover'] ul[role='listbox'] {",
        "    background-color: #FFFFFF !important;",
        "    border: 1px solid #E5E7EB !important;",
        "    border-radius: 10px !important;",
        "    box-shadow: 0 8px 24px rgba(16,24,40,0.14) !important;",
        "    padding: 4px !important;",
        "}",
        "div[data-baseweb='popover'] li[role='option'],",
        "div[data-baseweb='popover'] li {",
        "    background-color: #FFFFFF !important;",
        "    color: #111827 !important;",
        "    border-radius: 6px !important;",
        "}",
        "div[data-baseweb='popover'] li[role='option']:hover,",
        "div[data-baseweb='popover'] li:hover {",
        "    background-color: #F3F4F6 !important;",
        "    color: #111827 !important;",
        "}",
        "div[data-baseweb='popover'] li[aria-selected='true'] {",
        "    background-color: #EEF2FF !important;",
        "    color: #4338CA !important;",
        "    font-weight: 600;",
        "}",
        "div[data-baseweb='popover'] li[role='option'] * {",
        "    color: inherit !important;",
        "}",
        "",
        "/* The closed selectbox / multiselect control itself */",
        "div[data-baseweb='select'] > div {",
        "    background-color: #FFFFFF !important;",
        "    border-color: #E5E7EB !important;",
        "    color: #111827 !important;",
        "    border-radius: 8px !important;",
        "}",
        "div[data-baseweb='select'] > div:hover {",
        "    border-color: #4F46E5 !important;",
        "}",
        "div[data-baseweb='select'] input {",
        "    color: #111827 !important;",
        "}",
        "div[data-baseweb='select'] svg { fill: #6B7280 !important; }",
        "div[data-baseweb='select'] span { color: #111827 !important; }",
        "",
        "/* Multiselect selected-value chips/tags */",
        "span[data-baseweb='tag'] {",
        "    background-color: #EEF2FF !important;",
        "    color: #4338CA !important;",
        "    border-radius: 6px !important;",
        "}",
        "span[data-baseweb='tag'] span { color: #4338CA !important; }",
        "span[data-baseweb='tag'] svg { fill: #4338CA !important; }",
        "",
        "/* File uploader dropzone + file row — same portal/dark-theme issue */",
        "[data-testid='stFileUploaderDropzone'] {",
        "    background-color: #F9FAFB !important;",
        "    border: 1px dashed #D1D5DB !important;",
        "    border-radius: 10px !important;",
        "}",
        "[data-testid='stFileUploaderDropzone'] * { color: #374151 !important; }",
        "[data-testid='stFileUploaderDropzone'] svg { fill: #6B7280 !important; }",
        "[data-testid='stFileUploaderDropzone'] button {",
        "    background-color: #FFFFFF !important;",
        "    color: #374151 !important;",
        "    border: 1px solid #E5E7EB !important;",
        "    border-radius: 8px !important;",
        "}",
        "[data-testid='stFileUploaderDropzone'] button:hover {",
        "    border-color: #4F46E5 !important;",
        "    color: #4338CA !important;",
        "}",
        "[data-testid='stFileUploaderFile'] {",
        "    background-color: #FFFFFF !important;",
        "    color: #111827 !important;",
        "}",
        "[data-testid='stFileUploaderFile'] * { color: #111827 !important; }",
        "",
        "/* date input popover calendar */",
        "div[data-baseweb='calendar'] { background-color: #FFFFFF !important; }",
        "div[data-baseweb='calendar'] * { color: #111827 !important; }",
        "</style>",
    ]
    st.markdown("\n".join(css_lines), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _initials(text, max_letters=2):
    parts = [p for p in text.replace("_", " ").split() if p]
    return "".join(p[0] for p in parts[:max_letters]).upper() or "?"


def _days_left(deadline_str):
    if not deadline_str:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return (dt.datetime.strptime(str(deadline_str)[:10], fmt).date() - dt.date.today()).days
        except (ValueError, TypeError):
            continue
    return None


def _icon_badge(icon, bg, fg="#111827"):
    """Renders the small rounded colored icon badge used on stat cards."""
    st.markdown(
        f"<div class='icon-badge' style='background:{bg}; color:{fg};'>{icon}</div>",
        unsafe_allow_html=True,
    )


def _stat_card(icon, bg, label, value, sublabel):
    """A single flat stat card: icon badge, label, big value, small caption —
    matches the 'Projects in View / Tasks / Completed Tasks / Team Members'
    cards in the screenshot."""
    with st.container(border=True):
        _icon_badge(icon, bg)
        st.markdown(f"<div style='color:#6B7280; font-size:0.85rem;'>{label}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:1.7rem; font-weight:700; color:#111827;'>{value}</div>",
                    unsafe_allow_html=True)
        st.caption(sublabel)


def _pill_html(text, cls):
    return f"<span class='pill {cls}'>{text}</span>"


def _priority_pill(priority):
    """Return the display label and CSS class for a task priority."""
    key = (priority or "medium").strip().lower()
    meta = PRIORITY_META.get(key, PRIORITY_META["medium"])
    return meta["label"], meta["pill"]


def _labels_html(labels):
    """Render task labels safely because they are user-provided text."""
    return " ".join(
        f"<span class='label-chip'>{html.escape(str(label))}</span>"
        for label in labels
        if str(label).strip()
    )


def _issue_key(project_name, task_id):
    """Short, stable display key for the task board (for example, WEB-1A2B3C4D)."""
    prefix = "".join(
        part[0] for part in str(project_name or "TASK").split() if part
    ).upper()[:5] or "TASK"
    return f"{prefix}-{str(task_id).replace('-', '')[:8].upper()}"


def _ring(pct, color, height=170):
    """Plain completion ring (no motion) — matches the flat donut in the screenshot."""
    fig = go.Figure(data=[go.Pie(
        values=[pct, 100 - pct], hole=0.78,
        marker=dict(colors=[color, "#F1F5F9"]),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#111827"),
        annotations=[
            dict(text=f"<b style='font-size:26px;color:#111827'>{pct}%</b>",
                 x=0.5, y=0.56, showarrow=False),
            dict(text="<span style='font-size:12px;color:#6B7280'>Overall Progress</span>",
                 x=0.5, y=0.42, showarrow=False),
        ],
    )
    return fig


def _animated_ring(pct, color, height=220, steps=20):
    """
    Motion version of the completion ring. Shows the REAL percentage
    immediately on load/rerun; the ▶ Animate button replays the fill-in
    animation from 0 -> pct for visual flair, and returns to the real
    value afterward (never looks "stuck empty").
    """
    pct = max(0, min(100, int(pct)))
    step_size = max(1, pct // steps) if pct else 1
    frame_values = list(range(0, pct, step_size)) + [pct]

    def _pie(v):
        return [go.Pie(
            values=[v, 100 - v], hole=0.78,
            marker=dict(colors=[color, "#F1F5F9"]),
            textinfo="none", sort=False, direction="clockwise",
        )]

    fig = go.Figure(
        data=_pie(pct),
        frames=[
            go.Frame(
                data=_pie(v),
                name=str(v),
                layout=go.Layout(annotations=[
                    dict(text=f"<b style='font-size:26px;color:#111827'>{v}%</b>",
                         x=0.5, y=0.56, showarrow=False),
                    dict(text="<span style='font-size:12px;color:#6B7280'>Overall Progress</span>",
                         x=0.5, y=0.42, showarrow=False),
                ]),
            )
            for v in frame_values
        ],
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=10, l=0, r=0),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#111827"),
        annotations=[
            dict(text=f"<b style='font-size:26px;color:#111827'>{pct}%</b>",
                 x=0.5, y=0.56, showarrow=False),
            dict(text="<span style='font-size:12px;color:#6B7280'>Overall Progress</span>",
                 x=0.5, y=0.42, showarrow=False),
        ],
        updatemenus=[dict(
            type="buttons", direction="left",
            x=0.5, y=-0.1, xanchor="center",
            showactive=False,
            bgcolor="#FFFFFF", bordercolor="#E5E7EB",
            font=dict(color="#374151", size=11),
            buttons=[
                dict(label="▶ Animate", method="animate",
                     args=[None, dict(frame=dict(duration=45, redraw=True),
                                       transition=dict(duration=0),
                                       fromcurrent=True, mode="immediate")]),
            ],
        )],
    )
    return fig


def _phase_list(status_counts, total):
    """
    Flat 'Phases' list matching the screenshot: colored dot + label on the
    left, a thin horizontal progress bar in the middle, count/% on the
    right.
    """
    total = total or 1
    for key, meta in STATUS_META.items():
        count = status_counts.get(key, 0)
        pct = round(100 * count / total)
        dot_col, label_col, bar_col, val_col = st.columns([0.4, 2, 4, 1.3])
        with dot_col:
            st.markdown(
                f"<div style='width:10px;height:10px;border-radius:50%;"
                f"background:{meta['hex']};margin-top:8px;'></div>",
                unsafe_allow_html=True,
            )
        with label_col:
            st.markdown(f"<div style='margin-top:2px;'>{meta['label']}</div>", unsafe_allow_html=True)
        with bar_col:
            st.progress(pct / 100)
        with val_col:
            st.markdown(
                f"<div style='margin-top:2px; text-align:right; color:#374151;'>{count} ({pct}%)</div>",
                unsafe_allow_html=True,
            )


def _deadline_pill(days):
    if days < 0:
        return "Overdue", "pill-red"
    if days <= 3:
        return "Soon", "pill-orange"
    return "On track", "pill-green"


def _project_status_pill(status_text):
    s = (status_text or "").strip().lower()
    mapping = {
        "planning":  ("Planning", "pill-orange"),
        "active":    ("In Progress", "pill-orange"),
        "on_hold":   ("On Hold", "pill-red"),
        "completed": ("Completed", "pill-green"),
    }
    return mapping.get(s, (status_text or "—", "pill-gray"))


def _task_status_pill(status_text):
    s = (status_text or "").strip().lower()
    mapping = {
        "todo":        ("To Do", "pill-blue"),
        "in_progress": ("In Progress", "pill-orange"),
        "testing":     ("Testing", "pill-gray"),
        "done":        ("Done", "pill-green"),
    }
    return mapping.get(s, (status_text or "—", "pill-gray"))


def _animated_donut(labels, values, colors, center_label, height=230, steps=18):
    """
    Motion donut chart. Shows the REAL values immediately on load/rerun;
    ▶ Animate replays a grow-in from 0 -> real for visual flair only.
    """
    total = sum(values) or 1
    fracs = [i / steps for i in range(steps + 1)]

    def _pie(frac):
        scaled = [max(v * frac, 0.0001) for v in values]
        return [go.Pie(
            labels=labels, values=scaled, hole=0.72,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
            textinfo="none", sort=False, direction="clockwise",
        )]

    fig = go.Figure(
        data=_pie(1),
        frames=[go.Frame(data=_pie(f if f > 0 else 0.001), name=str(i))
                for i, f in enumerate(fracs)],
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=40, l=10, r=10),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#111827"),
        annotations=[dict(
            text=f"<b style='font-size:24px;color:#111827'>{total}</b>"
                 f"<br><span style='font-size:11px;color:#6B7280'>{center_label}</span>",
            x=0.5, y=0.5, showarrow=False,
        )],
        updatemenus=[dict(
            type="buttons", direction="left",
            x=0.5, y=-0.12, xanchor="center",
            showactive=False,
            bgcolor="#FFFFFF", bordercolor="#E5E7EB",
            font=dict(color="#374151", size=11),
            buttons=[dict(label="▶ Animate", method="animate",
                          args=[None, dict(frame=dict(duration=40, redraw=True),
                                            transition=dict(duration=0),
                                            fromcurrent=True, mode="immediate")])],
        )],
    )
    return fig


def _choose_active_project(projects, widget_key):
    """
    Project dropdown. Returns (project_id or None for all, label).
    `widget_key` MUST be unique per page.
    """
    if not projects:
        st.session_state[ACTIVE_PROJECT_KEY] = None
        return None, "No projects"

    labels = [ALL_PROJECTS_LABEL] + [p["name"] for p in projects]
    id_by_name = {p["name"]: str(p["id"]) for p in projects}
    name_by_id = {str(p["id"]): p["name"] for p in projects}

    current = st.session_state.get(ACTIVE_PROJECT_KEY)
    if current is not None and str(current) not in name_by_id:
        current = None

    # Default to "All Projects" (not the first project) whenever nothing
    # has been explicitly chosen yet, so every page — Dashboard, Clients,
    # Projects, Tasks, Documents, Meetings, etc. — opens showing all data.
    default_index = 0 if current is None else labels.index(name_by_id[str(current)])

    selected = st.selectbox(
        "📁 Project",
        labels,
        index=default_index,
        key=widget_key,
        help="Dashboard, tasks, documents, meetings, and reports update for the selected project.",
    )

    if selected == ALL_PROJECTS_LABEL:
        st.session_state[ACTIVE_PROJECT_KEY] = None
        return None, ALL_PROJECTS_LABEL

    project_id = id_by_name[selected]
    st.session_state[ACTIVE_PROJECT_KEY] = project_id
    return project_id, selected


def _load_scoped_data(token, active_project_id):
    """Fetch tasks/docs filtered by the chosen project on the server."""
    tasks_resp = get_tasks(token, project_id=active_project_id)
    docs_resp = list_documents(token, project_id=active_project_id)
    team = []
    if active_project_id:
        team_resp = get_team(token, active_project_id)
        if team_resp.status_code == 200:
            team = team_resp.json()
        else:
            show_api_error(team_resp)
    return tasks_resp, docs_resp, team


def _fetch_users_safely(token):
    """Returns (users, ok). ok=False when the /users call failed."""
    resp = get_users(token)
    if resp.status_code == 200:
        return resp.json(), True
    show_api_error(resp)
    return [], False


def _user_option_label(u):
    role = (u.get("role") or "").strip()
    role_tag = f" · {role}" if role else ""
    return f"{u.get('name', '—')} ({u.get('email', '—')}){role_tag}"


def _split_staff(users):
    managers = [u for u in users if (u.get("role") or "").lower() == "manager"]
    employees = [u for u in users if (u.get("role") or "").lower() == "employee"]
    return managers, employees


def _client_status_meta(status_text):
    return CLIENT_STATUS_META.get((status_text or "").strip().lower(),
                                   {"icon": "⚪", "color": "gray", "hex": "#6B7280"})


def _project_status_meta(status_text):
    return PROJECT_STATUS_META.get((status_text or "").strip().lower(),
                                    {"icon": "⚪", "hex": "#6B7280"})


def _go_to(page_label, **flags):
    """Callback that selects a manager page before Streamlit renders widgets."""
    st.session_state[NAV_RADIO_KEY] = page_label
    for k, v in flags.items():
        st.session_state[k] = v


# --------------------------------------------------------------------------
# DASHBOARD — restyled to match the reference screenshot:
# icon-badge stat cards, plain "Overall Completion" ring + phases list,
# a pill-badge "Upcoming Deadlines" panel, plus Recent Projects / Recent
# Tasks / Team Activity / Quick Actions rows.
# --------------------------------------------------------------------------
def _render_manager_dashboard(projects, token):
    user = session_user()

    hour = dt.datetime.now().hour
    salutation = "Good Morning" if hour < 12 else ("Good Afternoon" if hour < 18 else "Good Evening")
    header_col, avatar_col = st.columns([6, 1])
    with header_col:
        st.title(f"👋 {salutation}, {user['name'].split()[0]}!")
        st.caption("Here's an overview of your projects and team progress.")
    with avatar_col:
        st.write("")
        st.badge(_initials(user["name"]), color="violet")

    st.write("")

    active_project_id, project_label = _choose_active_project(
        projects, widget_key="manager_dashboard_project_dropdown"
    )
    st.caption(f"Showing data for: **{project_label}**")

    tasks_resp, docs_resp, team = _load_scoped_data(token, active_project_id)
    tasks = tasks_resp.json() if tasks_resp.status_code == 200 else []
    documents = docs_resp.json() if docs_resp.status_code == 200 else []
    if tasks_resp.status_code != 200:
        show_api_error(tasks_resp)
    if docs_resp.status_code != 200:
        show_api_error(docs_resp)

    scoped_projects = (
        projects if active_project_id is None
        else [p for p in projects if str(p.get("id")) == str(active_project_id)]
    )

    active_n = sum(1 for p in scoped_projects if (p.get("status") or "").lower() == "active")
    completed_n = sum(1 for t in tasks if (t.get("status") or "") == "done")

    st.write("")

    # ---- Stat cards (icon badge + label + value + sublabel) --------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("📁", "#EEF2FF", "Projects in View", len(scoped_projects), "Active Projects")
    with c2:
        _stat_card("✅", "#ECFDF5", "Tasks", len(tasks), "Total Tasks")
    with c3:
        _stat_card("🏅", "#EFF6FF", "Completed Tasks", completed_n, "Tasks Completed")
    with c4:
        if active_project_id:
            _stat_card("👥", "#F5F3FF", "Team Members", len(team), "Active Members")
        else:
            _stat_card("👥", "#F5F3FF", "Active Projects", active_n, "Active Members")

    st.write("")

    # ---- Overall Completion: full-width phase-colored donut + phases list --
    with st.container(border=True):
        st.subheader("Overall Completion")
        st.caption("Track overall progress across all your projects.")
        if tasks:
            status_counts = {k: 0 for k in STATUS_META}
            for t in tasks:
                sk = t.get("status") or "todo"
                status_counts[sk if sk in status_counts else "todo"] += 1

            ring_col, phase_col = st.columns([1, 2.2])
            with ring_col:
                phase_keys = list(STATUS_META)
                st.plotly_chart(
                    _animated_donut(
                        labels=[STATUS_META[key]["label"] for key in phase_keys],
                        values=[status_counts[key] for key in phase_keys],
                        colors=[STATUS_META[key]["hex"] for key in phase_keys],
                        center_label="Total Tasks",
                    ),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"mgr_phase_donut_{active_project_id or 'all'}",
                )
            with phase_col:
                st.markdown("**Phases**")
                _phase_list(status_counts, len(tasks))
        else:
            st.info("No tasks in this view.")

    st.write("")

    # ---- Documents (left) / Upcoming Deadlines + Project Team (right) ------
    doc_col, deadline_col = st.columns([1.6, 1])
    with doc_col:
        with st.container(border=True):
            st.subheader("📄 Documents")
            if not documents:
                st.caption("No documents for this project context.")
            else:
                for doc in documents[:5]:
                    row = st.columns([3, 1])
                    with row[0]:
                        st.write(doc["filename"])
                    with row[1]:
                        resp = download_document(token, str(doc["id"]))
                        if resp.status_code == 200:
                            st.download_button("Get", data=resp.content, file_name=doc["filename"],
                                                mime="application/octet-stream",
                                                key=f"mgr_dash_dl_{doc['id']}", use_container_width=True)
                        else:
                            show_api_error(resp)

    with deadline_col:
        with st.container(border=True):
            st.subheader("Upcoming Deadlines")
            st.caption("Stay on top of important deadlines.")
            dated = [(p["name"], p.get("deadline"), _days_left(p.get("deadline")))
                     for p in scoped_projects if p.get("deadline")]
            dated = [d for d in dated if d[2] is not None]
            dated.sort(key=lambda d: d[2])
            if not dated:
                st.caption("No deadlines in this view.")
            else:
                for name, deadline, days in dated[:5]:
                    pill_text, pill_class = _deadline_pill(days)
                    row_l, row_r = st.columns([3, 1])
                    with row_l:
                        st.markdown(f"📅 **{name}**")
                        st.caption(f"{deadline} ({days}d)")
                    with row_r:
                        st.markdown(_pill_html(pill_text, pill_class), unsafe_allow_html=True)
                    st.divider()
            st.button(
                "View all deadlines →", key="mgr_dash_view_deadlines",
                use_container_width=True, on_click=_go_to, args=("📁 Projects",),
            )

        if active_project_id and team:
            st.write("")
            with st.container(border=True):
                st.subheader("👥 Project Team")
                for member in team:
                    name = html.escape(str(member.get("name") or "—"))
                    role = html.escape(str(member.get("role") or "Member").title())
                    email = html.escape(str(member.get("email") or "—"))
                    st.markdown(
                        f"**{name}** · <span class='team-role-badge'>{role}</span> · {email}",
                        unsafe_allow_html=True,
                    )

    st.write("")

    # ---- Recent Tasks / Team Activity --------------------------------------
    rt_col, ta_col = st.columns(2)

    with rt_col:
        with st.container(border=True):
            st.subheader("Recent Tasks")
            st.caption("Latest tasks across your projects.")
            all_tasks_resp = get_tasks(token, project_id=None)
            all_tasks = all_tasks_resp.json() if all_tasks_resp.status_code == 200 else tasks
            recent_tasks = sorted(
                all_tasks, key=lambda t: str(t.get("created_at") or ""), reverse=True
            )[:5] or all_tasks[:5]
            if not recent_tasks:
                st.caption("No tasks yet.")
            else:
                proj_name_by_id = {str(p["id"]): p["name"] for p in projects}
                for t in recent_tasks:
                    with st.container(border=True):
                        pill_text, pill_class = _task_status_pill(t.get("status"))
                        title_col, tag_col = st.columns([3, 1.4])
                        with title_col:
                            st.markdown(f"🔸 **{t.get('title', '—')}**")
                        with tag_col:
                            st.markdown(_pill_html(pill_text, pill_class), unsafe_allow_html=True)
                        proj_name = proj_name_by_id.get(str(t.get("project_id")), "—")
                        due = t.get("due_date")
                        due_txt = f"📅 {str(due)[:10]}" if due else "📅 No due date"
                        st.caption(f"{proj_name} · {due_txt}")
            st.button(
                "View all tasks →", key="mgr_dash_view_tasks",
                use_container_width=True, on_click=_go_to, args=("✅ Tasks",),
            )

    with ta_col:
        with st.container(border=True):
            st.subheader("Team Activity")
            st.caption("What your team is working on.")
            users, users_ok = _fetch_users_safely(token)
            staff = [u for u in users if (u.get("role") or "").lower() in ("manager", "employee")]
            if not staff:
                st.caption("No team members found.")
            else:
                for member in staff[:5]:
                    row_l, row_r = st.columns([3, 1.2])
                    with row_l:
                        st.markdown(
                            f"<span class='status-dot' style='background:#22C55E;'></span>"
                            f"<b>{member.get('name', '—')}</b>",
                            unsafe_allow_html=True,
                        )
                        st.caption(member.get("email", "—"))
                    with row_r:
                        st.markdown(_pill_html("Active", "pill-green"), unsafe_allow_html=True)
            st.button(
                "View team →", key="mgr_dash_view_team",
                use_container_width=True, on_click=_go_to, args=("📁 Projects",),
            )

    # ---- Quick Actions -------------------------------------------------------
    with st.container(border=True):
        st.subheader("Quick Actions")
        st.caption("Common actions to save you time.")
        qa1, qa2, qa3, qa4, qa5 = st.columns(5)

        with qa1:
            with st.container(border=True):
                _icon_badge("➕", "#EEF2FF")
                st.markdown("<div class='qa-title'>New Project</div>", unsafe_allow_html=True)
                st.caption("Create a new project")
                st.button(
                    "Open", key="qa_new_project", use_container_width=True,
                    on_click=_go_to, args=("📁 Projects",),
                    kwargs={"mgr_expand_create_project": True},
                )

        with qa2:
            with st.container(border=True):
                _icon_badge("👥", "#ECFDF5")
                st.markdown("<div class='qa-title'>Invite Team</div>", unsafe_allow_html=True)
                st.caption("Add team members")
                st.button(
                    "Open", key="qa_invite_team", use_container_width=True,
                    on_click=_go_to, args=("📁 Projects",),
                    kwargs={"mgr_expand_assign_team": True},
                )

        with qa3:
            with st.container(border=True):
                _icon_badge("📤", "#FFF7ED")
                st.markdown("<div class='qa-title'>Upload Document</div>", unsafe_allow_html=True)
                st.caption("Share files & docs")
                st.button(
                    "Open", key="qa_upload_doc", use_container_width=True,
                    on_click=_go_to, args=("📄 Documents",),
                )

        with qa4:
            with st.container(border=True):
                _icon_badge("🎙️", "#F5F3FF")
                st.markdown("<div class='qa-title'>Schedule Meeting</div>", unsafe_allow_html=True)
                st.caption("Plan team meetings")
                st.button(
                    "Open", key="qa_schedule_meeting", use_container_width=True,
                    on_click=_go_to, args=("🎙️ Meetings",),
                )

        with qa5:
            with st.container(border=True):
                _icon_badge("✨", "#FEF9C3")
                st.markdown("<div class='qa-title'>Ask AI</div>", unsafe_allow_html=True)
                st.caption("Get AI insights")
                st.button(
                    "Open", key="qa_ask_ai", use_container_width=True,
                    on_click=_go_to, args=("🧠 Requirement Analyzer",),
                )

# --------------------------------------------------------------------------
# TASKS
# --------------------------------------------------------------------------
def _issue_detail_dialog(token, projects, task_id):
    """
    Renders the Jira-style issue detail modal for an EXISTING task.
    Used identically from every kanban column — same function, same
    fields, same behavior no matter which status column you opened it
    from.
    """
    project_by_id = {str(p["id"]): p["name"] for p in projects}
 
    @st.dialog("Issue details", width="large")
    def _dialog():
        resp = get_task(token, task_id)
        if resp.status_code != 200:
            show_api_error(resp)
            if st.button("Close"):
                st.session_state["mgr_open_issue_id"] = None
                st.rerun()
            return
        issue = resp.json()
 
        proj_name = project_by_id.get(str(issue.get("project_id")), "—")
        key_label = _issue_key(proj_name, issue["id"])
 
        st.markdown(
            f"<span class='issue-key'>{key_label}</span> &nbsp; "
            f"<span style='color:#6B7280;'>{proj_name}</span>",
            unsafe_allow_html=True,
        )
 
        users, users_ok = _fetch_users_safely(token)
        _, employees = _split_staff(users)
        managers, _ = _split_staff(users)
        assignable = managers + employees
        assignee_options = [("Unassigned", None)] + [
            (_user_option_label(u), u.get("id")) for u in assignable
        ]
        current_assignee_id = issue.get("assigned_to")
        assignee_index = next(
            (i for i, (_, uid) in enumerate(assignee_options) if str(uid or "") == str(current_assignee_id or "")),
            0,
        )
 
        left_col, right_col = st.columns([2.3, 1])
 
        with left_col:
            new_title = st.text_input("Title", value=issue.get("title", ""), key=f"mgr_issue_title_{task_id}")
            new_description = st.text_area(
                "Description", value=issue.get("description") or "",
                key=f"mgr_issue_desc_{task_id}", height=120,
            )
            new_epic = st.text_input("Epic", value=issue.get("epic") or "", key=f"mgr_issue_epic_{task_id}")
 
            if st.button("💾 Save changes", key=f"mgr_issue_save_{task_id}", type="primary"):
                payload = {
                    "title": new_title.strip() or issue.get("title"),
                    "description": new_description.strip() or None,
                    "epic": new_epic.strip() or None,
                }
                save_resp = update_task(token, task_id, payload)
                if save_resp.status_code == 200:
                    st.success("Saved.")
                    st.rerun()
                else:
                    show_api_error(save_resp)
 
            st.divider()
 
            # ---- Sub-tasks ----
            st.markdown(f"**🧩 Sub-tasks** ({len(issue.get('subtasks', []))})")
            for st_item in issue.get("subtasks", []):
                pill_text, pill_class = _task_status_pill(st_item.get("status"))
                srow_l, srow_r = st.columns([3, 1.3])
                with srow_l:
                    st.write(f"• {st_item.get('title', '—')}")
                    st.caption(st_item.get("assigned_to_name") or "Unassigned")
                with srow_r:
                    st.markdown(_pill_html(pill_text, pill_class), unsafe_allow_html=True)
 
            with st.form(f"mgr_add_subtask_form_{task_id}", clear_on_submit=True):
                st.caption("Add a sub-task")
                sub_title = st.text_input("Sub-task title", key=f"mgr_subtask_title_{task_id}")
                sub_assignee_label = st.selectbox(
                    "Assign to", [label for label, _ in assignee_options],
                    key=f"mgr_subtask_assignee_{task_id}",
                )
                if st.form_submit_button("Add sub-task"):
                    if not sub_title.strip():
                        st.error("Sub-task title is required.")
                    else:
                        sub_resp = create_subtask(token, task_id, {
                            "title": sub_title.strip(),
                            "status": "todo",
                            "priority": "medium",
                            "assigned_to": dict(assignee_options).get(sub_assignee_label),
                        })
                        if sub_resp.status_code in (200, 201):
                            st.success("Sub-task added.")
                            st.rerun()
                        else:
                            show_api_error(sub_resp)
 
            st.divider()
 
            # ---- Linked issues ----
            st.markdown(f"**🔗 Linked issues** ({len(issue.get('links', []))})")
            for link in issue.get("links", []):
                lrow_l, lrow_r = st.columns([4, 1])
                with lrow_l:
                    lpill_text, lpill_class = _task_status_pill(link.get("linked_task_status"))
                    st.markdown(
                        f"_{link.get('link_type')}_ — **{link.get('linked_task_title')}** "
                        + _pill_html(lpill_text, lpill_class),
                        unsafe_allow_html=True,
                    )
                with lrow_r:
                    if st.button("Remove", key=f"mgr_rm_link_{task_id}_{link['id']}"):
                        rm_resp = remove_task_link(token, task_id, link["id"])
                        if rm_resp.status_code in (200, 204):
                            st.rerun()
                        else:
                            show_api_error(rm_resp)
 
            other_tasks_resp = get_tasks(token, project_id=issue.get("project_id"))
            other_tasks = other_tasks_resp.json() if other_tasks_resp.status_code == 200 else []
            linkable = [t for t in other_tasks if str(t["id"]) != str(task_id)]
            if linkable:
                with st.form(f"mgr_add_link_form_{task_id}", clear_on_submit=True):
                    st.caption("Link another issue")
                    link_label_map = {f"{t['title']} · {str(t['id'])[:8]}": t["id"] for t in linkable}
                    link_target_label = st.selectbox(
                        "Issue", list(link_label_map.keys()), key=f"mgr_link_target_{task_id}",
                    )
                    link_type = st.selectbox("Relationship", LINK_TYPE_OPTIONS, key=f"mgr_link_type_{task_id}")
                    if st.form_submit_button("Add link"):
                        link_resp = add_task_link(
                            token, task_id, link_label_map[link_target_label], link_type
                        )
                        if link_resp.status_code in (200, 201):
                            st.success("Linked.")
                            st.rerun()
                        else:
                            show_api_error(link_resp)
 
            st.divider()
 
            # ---- Comments / activity ----
            st.markdown(f"**💬 Comments** ({len(issue.get('comments', []))})")
            for c in issue.get("comments", []):
                created = str(c.get("created_at", ""))[:16].replace("T", " ")
                st.markdown(
                    f"<div class='comment-box'><b>{html.escape(c.get('author_name','Unknown'))}</b> "
                    f"<span style='color:#9CA3AF;font-size:0.75rem;'>{created}</span><br>"
                    f"{html.escape(c.get('body',''))}</div>",
                    unsafe_allow_html=True,
                )
            with st.form(f"mgr_add_comment_form_{task_id}", clear_on_submit=True):
                comment_body = st.text_area("Add a comment", key=f"mgr_comment_body_{task_id}", height=70)
                if st.form_submit_button("Comment"):
                    if not comment_body.strip():
                        st.error("Comment can't be empty.")
                    else:
                        c_resp = add_comment(token, task_id, comment_body.strip())
                        if c_resp.status_code in (200, 201):
                            st.rerun()
                        else:
                            show_api_error(c_resp)
 
        with right_col:
            with st.container(border=True):
                st.markdown("**Status**")
                current_status = issue.get("status") or "todo"
                new_status = st.selectbox(
                    "Status", list(STATUS_META.keys()),
                    index=list(STATUS_META.keys()).index(current_status) if current_status in STATUS_META else 0,
                    format_func=lambda k: STATUS_META[k]["label"],
                    key=f"mgr_issue_status_{task_id}",
                    label_visibility="collapsed",
                )
 
                st.markdown("**Assignee**")
                new_assignee_label = st.selectbox(
                    "Assignee", [label for label, _ in assignee_options],
                    index=assignee_index, key=f"mgr_issue_assignee_{task_id}",
                    label_visibility="collapsed",
                )
 
                st.markdown("**Priority**")
                current_priority = issue.get("priority") or "medium"
                new_priority = st.selectbox(
                    "Priority", PRIORITY_OPTIONS,
                    index=PRIORITY_OPTIONS.index(current_priority) if current_priority in PRIORITY_OPTIONS else 1,
                    format_func=lambda p: f"{PRIORITY_META[p]['icon']} {PRIORITY_META[p]['label']}",
                    key=f"mgr_issue_priority_{task_id}",
                    label_visibility="collapsed",
                )
 
                st.markdown("**Story points**")
                new_points = st.number_input(
                    "Story points", min_value=0.0, step=0.5,
                    value=float(issue.get("story_points") or 0),
                    key=f"mgr_issue_points_{task_id}", label_visibility="collapsed",
                )
 
                # ---- NEW: start date / deadline ----
                st.markdown("**Start date**")
                existing_start = _parse_date_or_none(issue.get("start_date"))
                new_start_date = st.date_input(
                    "Start date", value=existing_start,
                    key=f"mgr_issue_start_{task_id}", label_visibility="collapsed",
                )
 
                st.markdown("**Deadline**")
                existing_deadline = _parse_date_or_none(issue.get("deadline"))
                new_deadline = st.date_input(
                    "Deadline", value=existing_deadline,
                    key=f"mgr_issue_deadline_{task_id}", label_visibility="collapsed",
                )
 
                st.markdown("**Labels** (comma-separated)")
                labels_str = ", ".join(issue.get("labels") or [])
                new_labels_str = st.text_input(
                    "Labels", value=labels_str, key=f"mgr_issue_labels_{task_id}",
                    label_visibility="collapsed",
                )
 
                if st.button("Update fields", key=f"mgr_issue_update_fields_{task_id}", use_container_width=True):
                    new_labels = [l.strip() for l in new_labels_str.split(",") if l.strip()]
                    field_payload = {
                        "status": new_status,
                        "assigned_to": dict(assignee_options).get(new_assignee_label),
                        "priority": new_priority,
                        "story_points": new_points,
                        "labels": new_labels,
                        "start_date": new_start_date.isoformat() if new_start_date else None,
                        "deadline": new_deadline.isoformat() if new_deadline else None,
                    }
                    field_resp = update_task(token, task_id, field_payload)
                    if field_resp.status_code == 200:
                        st.success("Updated.")
                        st.rerun()
                    else:
                        show_api_error(field_resp)
 
                if issue.get("labels"):
                    st.markdown(_labels_html(issue["labels"]), unsafe_allow_html=True)
 
                st.divider()
                st.caption(f"Reporter: {issue.get('created_by_name') or '—'}")
                st.caption(f"Created: {str(issue.get('created_at',''))[:16].replace('T',' ')}")
 
                st.divider()
                confirm_delete = st.checkbox("Confirm delete", key=f"mgr_issue_confirm_del_{task_id}")
                if st.button("🗑️ Delete issue", key=f"mgr_issue_delete_{task_id}",
                             use_container_width=True, disabled=not confirm_delete):
                    del_resp = delete_task(token, task_id)
                    if del_resp.status_code == 204:
                        st.session_state["mgr_open_issue_id"] = None
                        st.success("Issue deleted.")
                        st.rerun()
                    else:
                        show_api_error(del_resp)
 
        if st.button("Close", key=f"mgr_issue_close_{task_id}"):
            st.session_state["mgr_open_issue_id"] = None
            st.rerun()
 
    _dialog()
 
 
def _parse_date_or_none(value):
    """Small helper: turn an ISO date string from the API into a
    `date` object for st.date_input, or None if missing/unparseable."""
    if not value:
        return None
    import datetime
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
 
 
def _create_issue_dialog(token, projects, default_project_id):
    """Jira-style 'Create issue' modal — new-issue mode of the same fields."""
 
    @st.dialog("Create issue", width="large")
    def _dialog():
        users, users_ok = _fetch_users_safely(token)
        managers, employees = _split_staff(users)
        assignable = managers + employees
        assignee_options = [("Unassigned", None)] + [
            (_user_option_label(u), u.get("id")) for u in assignable
        ]
 
        project_names = [p["name"] for p in projects]
        default_index = 0
        if default_project_id is not None:
            matching = [p["name"] for p in projects if str(p.get("id")) == str(default_project_id)]
            if matching:
                default_index = project_names.index(matching[0])
 
        with st.form("mgr_create_issue_form", clear_on_submit=True):
            project_label = st.selectbox("Project", project_names, index=default_index)
            title = st.text_input("Title")
            description = st.text_area("Description", height=100)
            epic = st.text_input("Epic (optional)")
 
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                status = st.selectbox(
                    "Status", list(STATUS_META.keys()),
                    format_func=lambda k: STATUS_META[k]["label"],
                )
            with col_b:
                priority = st.selectbox(
                    "Priority", PRIORITY_OPTIONS, index=1,
                    format_func=lambda p: f"{PRIORITY_META[p]['icon']} {PRIORITY_META[p]['label']}",
                )
            with col_c:
                story_points = st.number_input("Story points", min_value=0.0, step=0.5, value=0.0)
 
            # ---- NEW: start date / deadline ----
            col_d, col_e = st.columns(2)
            with col_d:
                start_date = st.date_input("Start date", value=None)
            with col_e:
                deadline = st.date_input("Deadline", value=None)
 
            assignee_label = st.selectbox("Assign to", [label for label, _ in assignee_options])
            labels_str = st.text_input("Labels (comma-separated)", placeholder="frontend, bug")
 
            if st.form_submit_button("Create issue", type="primary"):
                project_id = next((p["id"] for p in projects if p["name"] == project_label), None)
                if not title.strip():
                    st.error("Title is required.")
                elif project_id is None:
                    st.error("Select a project.")
                elif start_date and deadline and deadline < start_date:
                    st.error("Deadline can't be before the start date.")
                else:
                    labels_list = [l.strip() for l in labels_str.split(",") if l.strip()]
                    payload = {
                        "title": title.strip(),
                        "description": description or None,
                        "epic": epic.strip() or None,
                        "status": status,
                        "priority": priority,
                        "story_points": story_points,
                        "labels": labels_list,
                        "project_id": project_id,
                        "assigned_to": dict(assignee_options).get(assignee_label),
                        "start_date": start_date.isoformat() if start_date else None,
                        "deadline": deadline.isoformat() if deadline else None,
                    }
                    resp = create_task(token, payload)
                    if resp.status_code in {200, 201}:
                        st.success("Issue created.")
                        st.session_state["mgr_show_create_issue"] = False
                        st.rerun()
                    else:
                        show_api_error(resp)
 
        if st.button("Cancel"):
            st.session_state["mgr_show_create_issue"] = False
            st.rerun()
 
    _dialog()
 
 
def _issue_card(t, project_by_id):
    """One kanban card. Used identically in all four status columns."""
    proj_name = project_by_id.get(str(t.get("project_id")), "—")
    key_label = _issue_key(proj_name, t["id"])
    priority_text, priority_class = _priority_pill(t.get("priority"))
 
    with st.container(border=True):
        st.markdown(f"<span class='issue-key'>{key_label}</span>", unsafe_allow_html=True)
        st.markdown(f"<span class='issue-title'>{html.escape(t.get('title','—'))}</span>",
                    unsafe_allow_html=True)
 
        meta_bits = []
        if t.get("story_points"):
            meta_bits.append(f"{t['story_points']} pts")
        if t.get("deadline"):
            meta_bits.append(f"due {str(t['deadline'])[:10]}")
        if meta_bits:
            st.caption(" · ".join(meta_bits))
 
        st.markdown(_pill_html(priority_text, priority_class), unsafe_allow_html=True)
 
        if t.get("labels"):
            st.markdown(_labels_html(t["labels"]), unsafe_allow_html=True)
 
        if st.button("Open", key=f"mgr_open_issue_{t['id']}", use_container_width=True):
            st.session_state["mgr_show_create_issue"] = False
            st.session_state["mgr_open_issue_id"] = t["id"]
            st.rerun()
 
 
def _render_manager_tasks(projects, token):
    st.title("✅ Tasks")
    st.caption("Jira-style issue tracker — search, filter, and open any issue for full detail.")
 
    active_project_id, project_label = _choose_active_project(
        projects, widget_key="manager_tasks_project_dropdown"
    )
 
    # ---- BUG FIX: clear any open dialog/create-form state when the
    # active project changes, so a stale dialog from the previous
    # project doesn't pop back open and hide the task list. ----
    if st.session_state.get("mgr_active_project_id") != active_project_id:
        st.session_state["mgr_active_project_id"] = active_project_id
        st.session_state["mgr_open_issue_id"] = None
        st.session_state["mgr_show_create_issue"] = False
 
    tasks_resp = get_tasks(token, project_id=active_project_id)
    if tasks_resp.status_code != 200:
        show_api_error(tasks_resp)
        return
    tasks = tasks_resp.json()
 
    project_by_id = {str(p["id"]): p["name"] for p in projects}
 
    # ---- Toolbar: search + filters + create ----
    toolbar_search, toolbar_status, toolbar_priority, toolbar_create = st.columns([2.4, 1.2, 1.2, 1])
    with toolbar_search:
        search_query = st.text_input(
            "🔍 Search issues", key="mgr_task_search", placeholder="Search by title…",
            label_visibility="collapsed",
        )
    with toolbar_status:
        status_filter = st.multiselect(
            "Status", list(STATUS_META.keys()),
            format_func=lambda k: STATUS_META[k]["label"],
            key="mgr_task_status_filter", placeholder="Status",
            label_visibility="collapsed",
        )
    with toolbar_priority:
        priority_filter = st.multiselect(
            "Priority", PRIORITY_OPTIONS,
            format_func=lambda p: PRIORITY_META[p]["label"],
            key="mgr_task_priority_filter", placeholder="Priority",
            label_visibility="collapsed",
        )
    with toolbar_create:
        if st.button("➕ Create issue", type="primary", use_container_width=True, key="mgr_create_issue_btn"):
            st.session_state["mgr_open_issue_id"] = None
            st.session_state["mgr_show_create_issue"] = True
 
    filtered = tasks
    if search_query.strip():
        q = search_query.strip().lower()
        filtered = [t for t in filtered if q in (t.get("title") or "").lower()]
    if status_filter:
        filtered = [t for t in filtered if (t.get("status") or "todo") in status_filter]
    if priority_filter:
        filtered = [t for t in filtered if (t.get("priority") or "medium") in priority_filter]
 
    st.caption(f"Showing **{len(filtered)}** of {len(tasks)} issues in **{project_label}**")
    st.write("")
 
    # ---- Kanban board: one column per status, same card/dialog in each ----
    status_keys = list(STATUS_META.keys())
    if not filtered and not tasks:
        st.info("No issues yet — create the first one.")
    elif not filtered:
        st.info("No issues match your filters.")
    else:
        board_cols = st.columns(len(status_keys))
        for col, status_key in zip(board_cols, status_keys):
            with col:
                col_tasks = [t for t in filtered if (t.get("status") or "todo") == status_key]
                st.markdown(f"**{STATUS_META[status_key]['label']}** ({len(col_tasks)})")
                st.divider()
                if not col_tasks:
                    st.caption("No issues here.")
                for t in col_tasks:
                    _issue_card(t, project_by_id)
 
    # ---- Launch dialogs based on session state ----
    if st.session_state.get("mgr_show_create_issue"):
        _create_issue_dialog(token, projects, active_project_id)
 
    elif st.session_state.get("mgr_open_issue_id"):
        _issue_detail_dialog(token, projects, st.session_state["mgr_open_issue_id"])


# --------------------------------------------------------------------------
# DOCUMENTS — upload (with project selection), view, preview, download, delete
# --------------------------------------------------------------------------
def _render_manager_documents(projects, token):
    st.title("📄 Documents")

    with st.container(border=True):
        st.subheader("⬆️ Upload a document")
        if not projects:
            st.info("No projects available to upload into yet.")
        else:
            if "manager_doc_uploader_key" not in st.session_state:
                st.session_state["manager_doc_uploader_key"] = 0

            with st.form("manager_upload_document_form", clear_on_submit=True):
                project_names = [p["name"] for p in projects]
                default_index = 0
                current_project_id = st.session_state.get(ACTIVE_PROJECT_KEY)
                if current_project_id is not None:
                    matching = [p["name"] for p in projects if str(p.get("id")) == str(current_project_id)]
                    if matching:
                        default_index = project_names.index(matching[0])

                upload_project_label = st.selectbox(
                    "Project", project_names, index=default_index,
                    key="manager_upload_project_select",
                )
                uploaded_file = st.file_uploader(
                    "Choose a file", type=None,
                    key=f"manager_doc_uploader_{st.session_state['manager_doc_uploader_key']}",
                )
                if st.form_submit_button("Upload", type="primary"):
                    if uploaded_file is None:
                        st.warning("Please choose a file first.")
                    else:
                        upload_project_id = next(
                            (p["id"] for p in projects if p["name"] == upload_project_label), None
                        )
                        resp = upload_document(token, uploaded_file, project_id=str(upload_project_id))
                        if resp.status_code in (200, 201):
                            st.session_state["manager_doc_uploader_key"] += 1
                            data = resp.json() if resp.content else {}
                            chunks = int(data.get("chunk_count") or 0)
                            if chunks > 0:
                                st.success(
                                    f"Uploaded to **{upload_project_label}** and "
                                    f"indexed for AI Chat ({chunks} chunk(s))."
                                )
                            else:
                                st.success(
                                    f"Uploaded to **{upload_project_label}**. "
                                    "No text extracted — use Reindex or a "
                                    "PDF/DOCX/PPTX/TXT file."
                                )
                            st.rerun()
                        else:
                            show_api_error(resp)

    st.write("")

    with st.container(border=True):
        st.subheader("All Documents")
        st.caption("Upload PDF/DOCX/PPTX/TXT to enable chat RAG. Files are indexed on upload.")

        active_project_id, project_label = _choose_active_project(
            projects, widget_key="manager_documents_project_dropdown"
        )
        st.caption(f"Showing: **{project_label}**")
        st.write("")

        docs_resp = list_documents(token, project_id=active_project_id)
        if docs_resp.status_code != 200:
            show_api_error(docs_resp)
            return
        documents = docs_resp.json()

        if not documents:
            st.info("No documents uploaded yet.")
        else:
            for doc in documents:
                row = st.columns([3, 1, 1, 1])
                with row[0]:
                    st.markdown(f"📄 **{doc['filename']}**")
                    st.caption(rag_status_label(doc))
                with row[1]:
                    resp = download_document(token, str(doc["id"]))
                    if resp.status_code == 200:
                        st.download_button(
                            "Download", data=resp.content, file_name=doc["filename"],
                            mime="application/octet-stream",
                            key=f"manager_dl_{doc['id']}", use_container_width=True,
                        )
                    else:
                        show_api_error(resp)
                with row[2]:
                    if st.button("Preview", key=f"manager_view_{doc['id']}", use_container_width=True):
                        show_document_preview(token, doc)
                with row[3]:
                    if st.button("Delete", key=f"manager_del_{doc['id']}", use_container_width=True):
                        delete_resp = delete_document(token, str(doc["id"]))
                        if delete_resp.status_code == 204:
                            st.success("Document deleted.")
                            st.rerun()
                        else:
                            show_api_error(delete_resp)
                st.divider()


# --------------------------------------------------------------------------
# PROJECTS (admin-style) — status meta / pill / progress helpers.
# Kept separate from the dashboard's PROJECT_STATUS_META / _pill_html so
# neither page's styling breaks the other.
# --------------------------------------------------------------------------
PROJECTS_PAGE_STATUS_META = {
    "completed": {"label": "Completed",    "color": "#22C55E"},
    "active":    {"label": "In Progress",  "color": "#3B82F6"},
    "on_hold":   {"label": "On Hold",      "color": "#F59E0B"},
    "planning":  {"label": "Not Started",  "color": "#EF4444"},
}


def _hex_pill(text, color):
    st.markdown(
        f"<span style='display:inline-block;padding:2px 10px;border-radius:999px;"
        f"font-size:0.75rem;font-weight:600;background:{color}1A;color:{color} !important;"
        f"border:1px solid {color}55;'>{text}</span>",
        unsafe_allow_html=True,
    )


def _color_dot(color):
    return (
        f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;"
        f"background:{color};'></span>"
    )


def _project_task_progress(project_id, tasks):
    linked = [t for t in tasks if str(t.get("project_id")) == str(project_id)]
    if not linked:
        return None, 0, 0
    done = sum(1 for t in linked if (t.get("status") or "") == "done")
    return round(100 * done / len(linked)), done, len(linked)


def _get_project_modules(token, project_id):
    """Load persisted modules from the backend, ordered by workflow position."""
    resp = get_project_modules(token, str(project_id))
    if resp.status_code == 200:
        return resp.json()
    show_api_error(resp)
    return []


def _resequence_module_locks(token, modules):
    """Keep exactly the first unfinished module active and persist status changes."""
    unlocked = False
    for m in modules:
        desired_status = "completed"
        if m["status"] == "completed":
            continue
        if not unlocked:
            desired_status = "in_progress"
            unlocked = True
        else:
            desired_status = "locked"
        if m["status"] != desired_status:
            resp = update_project_module(token, str(m["id"]), {"status": desired_status})
            if resp.status_code != 200:
                show_api_error(resp)
                return False
    return True


def _inject_module_flow_css():
    st.markdown(
        """
        <style>
        .module-anchor { display: none; }
        div[data-testid='stVerticalBlockBorderWrapper']:has(.module-anchor-completed) {
            border-left: 4px solid #22C55E !important;
        }
        div[data-testid='stVerticalBlockBorderWrapper']:has(.module-anchor-in_progress) {
            border: 1.5px solid #4F46E5 !important;
            box-shadow: 0 0 0 3px rgba(79,70,229,0.12) !important;
        }
        div[data-testid='stVerticalBlockBorderWrapper']:has(.module-anchor-locked) {
            opacity: 0.7;
        }
        .module-arrow {
            display:flex; align-items:center; justify-content:center;
            height:100%; font-size:1.4rem; color:#9CA3AF; font-weight:700;
            padding-top: 46px;
        }
        div[data-testid='stVerticalBlockBorderWrapper']:has(.module-anchor) {
            transition: box-shadow 0.15s ease, transform 0.15s ease;
        }
        div[data-testid='stVerticalBlockBorderWrapper']:has(.module-anchor):hover {
            border-color: #4F46E5 !important;
            box-shadow: 0 6px 16px rgba(79,70,229,0.18) !important;
            transform: translateY(-2px);
        }

        /* Horizontal-scroll wrapper for the module flow row so cards
           keep a fixed size instead of shrinking when many modules
           are added. */
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            overflow-y: hidden !important;
            padding-bottom: 12px !important;
            gap: 0 !important;
        }
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 0 0 auto !important;
            width: 210px !important;
            min-width: 210px !important;
        }
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"] > div[data-testid="column"]:has(.module-arrow),
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:has(.module-arrow) {
            width: 40px !important;
            min-width: 40px !important;
        }
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"]::-webkit-scrollbar {
            height: 8px;
        }
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"]::-webkit-scrollbar-thumb {
            background: #C7D2FE;
            border-radius: 999px;
        }
        .st-key-mgr_modules_flow_scroll [data-testid="stHorizontalBlock"]::-webkit-scrollbar-track {
            background: #F3F4F6;
            border-radius: 999px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    
def _render_module_flow_card(token, project_id, module):
    meta = MODULE_STATUS_META[module["status"]]
    with st.container(border=True):
        st.markdown(
            f"<span class='module-anchor module-anchor-{module['status']}'></span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
            f"<span style='font-size:1.4rem;line-height:1;'>{module.get('icon', '🧩')}</span>"
            f"<span style='font-weight:700;font-size:1rem;color:#111827;'>{module['name']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.write("")

        if st.button("👁️ Open", key=f"mod_open_{project_id}_{module['id']}",
                     use_container_width=True):
            st.session_state["mgr_module_detail_open"] = (project_id, module["id"])
            st.rerun()

        if st.button(
            "✅ Complete", key=f"mod_complete_{project_id}_{module['id']}",
            use_container_width=True, type="primary",
            disabled=module["status"] != "in_progress",
        ):
            resp = update_project_module(token, str(module["id"]), {"status": "completed"})
            if resp.status_code == 200:
                modules = _get_project_modules(token, project_id)
                if _resequence_module_locks(token, modules):
                    st.rerun()
            else:
                show_api_error(resp)

def _module_detail_dialog(token, project_id, module):
    @st.dialog("Module details", width="large")
    def _dialog():
        meta = MODULE_STATUS_META[module["status"]]
        st.markdown(f"### {module.get('icon', '🧩')} {module['name']}")
        _hex_pill(f"{meta['icon']} {meta['label']}", meta["color"])
        st.write("")
        st.markdown("**Description**")
        st.write(module.get("description") or "No description added yet.")

        st.write("")
        if module["status"] == "in_progress":
            if st.button(
                "✅ Mark Complete", key=f"mod_dialog_complete_{project_id}_{module['id']}",
                type="primary", use_container_width=True,
            ):
                resp = update_project_module(token, str(module["id"]), {"status": "completed"})
                if resp.status_code == 200:
                    modules = _get_project_modules(token, project_id)
                    if _resequence_module_locks(token, modules):
                        st.session_state["mgr_module_detail_open"] = None
                        st.rerun()
                else:
                    show_api_error(resp)

        if st.button("Close", key=f"mod_dialog_close_{project_id}_{module['id']}"):
            st.session_state["mgr_module_detail_open"] = None
            st.rerun()

    _dialog()


def _manage_modules_dialog(token, project_id):
    @st.dialog("Manage Project Modules", width="large")
    def _dialog():
        modules = _get_project_modules(token, project_id)

        st.markdown("**Current modules**")
        if not modules:
            st.caption("No modules yet — add the first one below.")
        else:
            for i, module in enumerate(modules):
                row = st.columns([0.6, 3, 1.6, 0.6, 0.6, 0.6])
                with row[0]:
                    st.write(module.get("icon", "🧩"))
                with row[1]:
                    new_label = st.text_input(
                        "Name", value=module["name"],
                        key=f"mgr_mod_dlg_name_{project_id}_{module['id']}",
                        label_visibility="collapsed",
                    )
                    if new_label.strip() and new_label.strip() != module["name"]:
                        resp = update_project_module(
                            token, str(module["id"]), {"name": new_label.strip()}
                        )
                        if resp.status_code != 200:
                            show_api_error(resp)
                with row[2]:
                    meta = MODULE_STATUS_META[module["status"]]
                    st.caption(f"{meta['icon']} {meta['label']}")
                with row[3]:
                    if i > 0 and st.button("↑", key=f"mgr_mod_dlg_up_{project_id}_{module['id']}",
                                            use_container_width=True):
                        ordered_ids = [str(m["id"]) for m in modules]
                        ordered_ids[i - 1], ordered_ids[i] = ordered_ids[i], ordered_ids[i - 1]
                        resp = reorder_project_modules(token, project_id, ordered_ids)
                        if resp.status_code == 200:
                            st.rerun()
                        else:
                            show_api_error(resp)
                with row[4]:
                    if i < len(modules) - 1 and st.button("↓", key=f"mgr_mod_dlg_down_{project_id}_{module['id']}",
                                                           use_container_width=True):
                        ordered_ids = [str(m["id"]) for m in modules]
                        ordered_ids[i + 1], ordered_ids[i] = ordered_ids[i], ordered_ids[i + 1]
                        resp = reorder_project_modules(token, project_id, ordered_ids)
                        if resp.status_code == 200:
                            st.rerun()
                        else:
                            show_api_error(resp)
                with row[5]:
                    if st.button("🗑️", key=f"mgr_mod_dlg_del_{project_id}_{module['id']}",
                                 use_container_width=True):
                        resp = delete_project_module(token, str(module["id"]))
                        if resp.status_code == 204:
                            remaining = [m for m in modules if m["id"] != module["id"]]
                            if _resequence_module_locks(token, remaining):
                                st.rerun()
                        else:
                            show_api_error(resp)

                with st.expander("📝 Description", expanded=False):
                    new_desc = st.text_area(
                        "Description", value=module.get("description", ""),
                        key=f"mgr_mod_dlg_desc_{project_id}_{module['id']}",
                        label_visibility="collapsed", height=60,
                        placeholder="Module description (optional)",
                    )
                    cleaned_desc = (new_desc or "").strip()
                    if cleaned_desc != (module.get("description") or ""):
                        resp = update_project_module(
                            token, str(module["id"]), {"description": cleaned_desc or None}
                        )
                        if resp.status_code != 200:
                            show_api_error(resp)

        st.divider()

        st.markdown("**➕ Add a module**")
        with st.form(f"mgr_mod_dlg_add_form_{project_id}", clear_on_submit=True):
            add_col1, add_col2 = st.columns([3, 1.4])
            with add_col1:
                add_name = st.text_input("Module name", placeholder="e.g. Authentication",
                                          label_visibility="collapsed")
            with add_col2:
                add_icon = st.selectbox("Icon", MODULE_ICON_OPTIONS,
                                         key=f"mgr_mod_dlg_add_icon_{project_id}",
                                         label_visibility="collapsed")
            add_description = st.text_area(
                "Description", placeholder="What does this module cover? (optional)",
                key=f"mgr_mod_dlg_add_desc_{project_id}", height=80,
            )
            if st.form_submit_button("Add to end of flow", use_container_width=True):
                if not add_name.strip():
                    st.error("Module name is required.")
                else:
                    resp = create_project_module(token, project_id, {
                        "name": add_name.strip(), "icon": add_icon, "status": "locked",
                        "description": add_description.strip() or None,
                    })
                    if resp.status_code == 201:
                        modules.append(resp.json())
                        if _resequence_module_locks(token, modules):
                            st.rerun()
                    else:
                        show_api_error(resp)

        if len(modules) >= 2:
            st.markdown("**🔀 Insert a module between two existing modules**")
            with st.form(f"mgr_mod_dlg_insert_form_{project_id}", clear_on_submit=True):
                position_labels = [
                    f"Between \"{modules[i]['name']}\" and \"{modules[i+1]['name']}\""
                    for i in range(len(modules) - 1)
                ]
                insert_position = st.selectbox("Insert position", position_labels,
                                                label_visibility="collapsed")
                ins_col1, ins_col2 = st.columns([3, 1.4])
                with ins_col1:
                    insert_name = st.text_input(
                        "New module name", key=f"mgr_mod_dlg_insert_name_{project_id}",
                        label_visibility="collapsed",
                    )
                with ins_col2:
                    insert_icon = st.selectbox(
                        "Icon", MODULE_ICON_OPTIONS,
                        key=f"mgr_mod_dlg_insert_icon_{project_id}",
                        label_visibility="collapsed",
                    )
                insert_description = st.text_area(
                    "Description", placeholder="What does this module cover? (optional)",
                    key=f"mgr_mod_dlg_insert_desc_{project_id}", height=80,
                )
                if st.form_submit_button("Insert between", use_container_width=True):
                    if not insert_name.strip():
                        st.error("Module name is required.")
                    else:
                        insert_at = position_labels.index(insert_position) + 1
                        resp = insert_project_module(token, project_id, insert_at, {
                            "name": insert_name.strip(), "icon": insert_icon, "status": "locked",
                            "description": insert_description.strip() or None,
                        })
                        if resp.status_code == 201:
                            modules.insert(insert_at, resp.json())
                            if _resequence_module_locks(token, modules):
                                st.rerun()
                        else:
                            show_api_error(resp)

        st.write("")
        if st.button("✅ Done", key=f"mgr_mod_dlg_done_{project_id}",
                     type="primary", use_container_width=True):
            st.session_state["mgr_modules_dialog_project"] = None
            st.rerun()

    _dialog()

def _render_project_modules_section(projects, token):
    st.subheader("🧩 Project Modules")
    st.caption("Break a project into a step-by-step workflow that your team completes in order.")

    if not projects:
        st.info("Create a project first to define its module workflow.")
        return

    _inject_module_flow_css()

    project_names = [p["name"] for p in projects]
    selected_name = st.selectbox("📁 Project", project_names, key="mgr_modules_project_select")
    project = next((p for p in projects if p["name"] == selected_name), None)
    if project is None:
        return
    project_id = str(project["id"])

    if st.button("➕ Create Module", key=f"mgr_open_modules_dialog_{project_id}", type="primary"):
        st.session_state["mgr_modules_dialog_project"] = project_id
        st.rerun()

    if st.session_state.get("mgr_modules_dialog_project") == project_id:
        _manage_modules_dialog(token, project_id)

    modules = _get_project_modules(token, project_id)
    st.write("")

    if not modules:
        st.info("No modules yet for this project — click **Create Module** to build the workflow.")
        return

    n = len(modules)
    col_spec = []
    for i in range(n):
        col_spec.append(3)
        if i < n - 1:
            col_spec.append(0.5)

    with st.container(key="mgr_modules_flow_scroll"):
        cols = st.columns(col_spec)

        col_i = 0
        for i, module in enumerate(modules):
            with cols[col_i]:
                _render_module_flow_card(token, project_id, module)
            col_i += 1
            if i < n - 1:
                with cols[col_i]:
                    st.markdown("<div class='module-arrow'>→</div>", unsafe_allow_html=True)
                col_i += 1

    open_target = st.session_state.get("mgr_module_detail_open")
    if open_target and open_target[0] == project_id:
        target_module = next((m for m in modules if m["id"] == open_target[1]), None)
        if target_module:
            _module_detail_dialog(token, project_id, target_module)
        else:
            st.session_state["mgr_module_detail_open"] = None

    st.write("")
    completed_n = sum(1 for m in modules if m["status"] == "completed")
    pct = round(100 * completed_n / len(modules))
    ring_col, bar_col = st.columns([1, 3])
    with ring_col:
        st.plotly_chart(
            _ring(pct, "#4F46E5", height=150),
            use_container_width=True, config={"displayModeBar": False},
            key=f"modules_ring_{project_id}",
        )
    with bar_col:
        st.write("")
        st.markdown(f"**{completed_n} of {len(modules)} modules complete**")
        st.progress(pct / 100, text=f"{pct}%")



# --------------------------------------------------------------------------
# PROJECT DETAILS — project picker + scoped data (lives inside Projects tab)
# --------------------------------------------------------------------------
def _render_manager_project_detail_section(projects, token):
    st.subheader("🔎 Project Details")
    if not projects:
        st.info("No projects yet — create one from the form below.")
        return

    project_names = [p["name"] for p in projects]
    selected_name = st.selectbox(
        "📁 Select project", project_names,
        key="manager_project_detail_select",
    )
    selected_project = next((p for p in projects if p["name"] == selected_name), None)
    if selected_project is None:
        return

    project_id = selected_project.get("id")

    tasks_resp = get_tasks(token, project_id=project_id)
    docs_resp = list_documents(token, project_id=project_id)
    scoped_tasks = tasks_resp.json() if tasks_resp.status_code == 200 else []
    scoped_docs = docs_resp.json() if docs_resp.status_code == 200 else []
    if tasks_resp.status_code != 200:
        show_api_error(tasks_resp)
    if docs_resp.status_code != 200:
        show_api_error(docs_resp)

    team = []
    team_resp = get_team(token, project_id)
    if team_resp.status_code == 200:
        team = team_resp.json()
    else:
        show_api_error(team_resp)

    pct, done, total = _project_task_progress(project_id, scoped_tasks)
    meta = PROJECTS_PAGE_STATUS_META.get(
        (selected_project.get("status") or "").lower(),
        {"label": selected_project.get("status", "—"), "color": "#6B7280"},
    )

    st.write("")
    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        st.caption("Status")
        _hex_pill(meta["label"], meta["color"])
    with top_col2:
        deadline = selected_project.get("deadline")
        days_left = _days_left(deadline)
        st.caption("Deadline")
        label = f"**{deadline or '—'}**"
        if days_left is not None:
            label += f"  ·  {days_left}d left"
        st.markdown(label)
    with top_col3:
        st.caption("Tasks")
        st.markdown(f"**{len(scoped_tasks)}**")

    st.write("")
    if pct is not None:
        st.progress(pct / 100, text=f"{pct}% · {done}/{total} tasks done")
    else:
        st.caption("No linked tasks yet for this project.")

    st.write("")
    doc_col, team_col = st.columns(2)
    with doc_col:
        st.markdown("**📄 Documents**")
        if not scoped_docs:
            st.caption("No documents for this project.")
        else:
            for doc in scoped_docs[:5]:
                st.write(f"- {doc.get('filename', '—')}")

    with team_col:
        st.markdown("**👥 Team**")
        if not team:
            st.caption("No team members linked to this project yet.")
        else:
            for member in team:
                st.write(f"- {member.get('name', '—')} · `{member.get('role', '—')}`")


# --------------------------------------------------------------------------
# PROJECTS — table of all projects, create (with team), edit, assign team
# --------------------------------------------------------------------------
def _render_manager_projects(projects, token):
    st.title("📁 Projects")
    st.caption("View, create, edit projects, and assign project teams.")
    st.write("")

    active_n = sum(1 for p in projects if (p.get("status") or "").lower() == "active")
    completed_n = sum(1 for p in projects if (p.get("status") or "").lower() == "completed")

    c1, c2, c3 = st.columns(3)
    with c1:
        _stat_card("📁", "#DBEAFE", "Total Projects", len(projects), "All projects")
    with c2:
        _stat_card("🟢", "#DCFCE7", "Active", active_n, "In progress")
    with c3:
        _stat_card("✅", "#EDE9FE", "Completed", completed_n, "Finished")

    st.write("")

    with st.container(border=True):
        recent_col, all_col = st.columns(2)

        with recent_col:
            st.subheader("🕓 Recent Projects")
            st.caption("Most recently created projects, newest first.")
            recent_projects = sorted(
                projects,
                key=lambda p: str(p.get("created_at") or p.get("id") or ""),
                reverse=True,
            )[:5]
            if not recent_projects:
                st.info("No projects yet.")
            else:
                with st.container(height=280):
                    for p in recent_projects:
                        with st.container(border=True):
                            rmeta = PROJECTS_PAGE_STATUS_META.get(
                                (p.get("status") or "").lower(),
                                {"label": p.get("status", "—"), "color": "#6B7280"},
                            )
                            row = st.columns([3, 1.3, 1.3])
                            with row[0]:
                                st.markdown(f"**{p.get('name', '—')}**")
                            with row[1]:
                                _hex_pill(rmeta["label"], rmeta["color"])
                            with row[2]:
                                st.caption(f"📅 {p.get('deadline', '—')}")

        with all_col:
            with st.container(key="manager-projects-all-col"):
                st.subheader("📋 All Projects")
                st.caption("Every project in your organization.")
                if not projects:
                    st.info("No projects yet.")
                else:
                    table_rows = [
                        {
                            "Name": p.get("name", "—"),
                            "Status": PROJECTS_PAGE_STATUS_META.get(
                                (p.get("status") or "").lower(), {}
                            ).get("label", p.get("status", "—")),
                            "Budget": p.get("budget", "—"),
                            "Deadline": p.get("deadline", "—"),
                        }
                        for p in projects
                    ]
                    st.dataframe(table_rows, use_container_width=True, hide_index=True)

        st.markdown(
            """
            <style>
            div[class*="st-key-manager-projects-all-col"] {
                border-left: 1px solid #EEF0F3;
                padding-left: 1.25rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    with st.expander("🔎 Project Details", expanded=True):
        _render_manager_project_detail_section(projects, token)

    st.write("")

    users, users_ok = _fetch_users_safely(token)
    managers, employees = _split_staff(users)

    clients_resp = get_clients(token)
    client_options = {}
    if clients_resp.status_code == 200:
        for c in clients_resp.json():
            client_options[c["company_name"]] = c["id"]
    else:
        show_api_error(clients_resp)

    create_project_expanded = st.session_state.pop("mgr_expand_create_project", False)
    with st.expander("➕ Create project", expanded=create_project_expanded):
        with st.form("manager_create_project_form", clear_on_submit=True):
            client_name = st.selectbox(
                "Client",
                list(client_options.keys()) or ["(no clients)"],
                key="manager_create_project_client",
            )
            name = st.text_input("Project name")
            description = st.text_area("Description")
            budget = st.number_input("Budget", min_value=0.0, step=100.0)
            status = st.selectbox("Status", PROJECT_STATUS_OPTIONS)
            deadline = st.date_input("Deadline", value=None)

            selected_managers = []
            selected_employees = []
            if users_ok and (managers or employees):
                selected_managers = st.multiselect(
                    "Project managers", managers,
                    format_func=_user_option_label,
                    key="manager_create_project_managers",
                )
                selected_employees = st.multiselect(
                    "Employees (optional)", employees,
                    format_func=_user_option_label,
                    key="manager_create_project_employees",
                )
                st.caption("You are always added to the team. Leave managers empty if you are the only PM.")
            elif not users_ok:
                st.caption("Could not load users — project will be created with you as the only team member.")

            if st.form_submit_button("Create project", type="primary"):
                if not client_options:
                    st.error("Create a client first (admin), then create the project.")
                elif not name.strip():
                    st.error("Project name is required.")
                else:
                    team_user_ids = (
                        [u.get("id") for u in selected_managers]
                        + [u.get("id") for u in selected_employees]
                    )
                    payload = {
                        "client_id": client_options[client_name],
                        "name": name.strip(),
                        "description": description.strip() or None,
                        "budget": float(budget) if budget else None,
                        "deadline": str(deadline) if deadline else None,
                        "status": status,
                        "team_user_ids": team_user_ids,
                    }
                    resp = create_project(token, payload)
                    if resp.status_code in {200, 201}:
                        st.success("Project created and connected to the selected team.")
                        st.rerun()
                    else:
                        show_api_error(resp)

    if projects:
        with st.expander("✏️ Edit project"):
            project_options = {f"{p['name']} ({p['id']})": p for p in projects}
            selected_label = st.selectbox("Select project to edit", list(project_options.keys()))
            selected_project = project_options[selected_label]

            with st.form("manager_edit_project_form"):
                name = st.text_input("Project name", value=selected_project.get("name", ""))
                current_status = (selected_project.get("status") or "active").lower()
                status = st.selectbox(
                    "Status", PROJECT_STATUS_OPTIONS,
                    index=PROJECT_STATUS_OPTIONS.index(current_status)
                    if current_status in PROJECT_STATUS_OPTIONS else 0,
                )
                existing_deadline = selected_project.get("deadline")
                deadline_value = None
                if existing_deadline:
                    try:
                        deadline_value = dt.datetime.strptime(str(existing_deadline)[:10], "%Y-%m-%d").date()
                    except ValueError:
                        deadline_value = None
                deadline = st.date_input("Deadline", value=deadline_value)

                if st.form_submit_button("Update project", type="primary"):
                    payload = {
                        "name": name.strip(),
                        "status": status,
                        "deadline": str(deadline) if deadline else None,
                    }
                    resp = update_project(token, selected_project["id"], payload)
                    if resp.status_code == 200:
                        st.success("Project updated.")
                        st.rerun()
                    else:
                        show_api_error(resp)

    st.write("")
    _render_project_modules_section(projects, token)

    st.write("")
    assign_team_expanded = st.session_state.pop("mgr_expand_assign_team", False)
    with st.container(border=True):
        st.subheader("👥 Assign / update project team")
        st.caption("Connect managers and employees to a project so they share its tasks and documents.")

        if not projects:
            st.info("Create a project first to assign a team.")
        elif not users_ok:
            st.info("Could not load users — team assignment needs /users access.")
        else:
            team_project_options = {p["name"]: p for p in projects}
            team_project_label = st.selectbox(
                "Project", list(team_project_options.keys()),
                key="manager_assign_team_project_select",
            )
            team_project = team_project_options[team_project_label]

            existing_team_ids = []
            team_resp = get_team(token, team_project["id"])
            if team_resp.status_code == 200:
                existing_team_ids = [str(m.get("id")) for m in team_resp.json()]
            else:
                show_api_error(team_resp)

            all_team_candidates = managers + employees
            preselected = [u for u in all_team_candidates if str(u.get("id")) in existing_team_ids]

            selected_team = st.multiselect(
                "Project team (managers + employees)",
                all_team_candidates,
                default=preselected,
                format_func=_user_option_label,
                key="manager_assign_team_multiselect",
            )

            if st.button("Save team members", key="manager_save_team_members", use_container_width=True):
                user_ids = [u.get("id") for u in selected_team]
                resp = assign_team(token, team_project["id"], user_ids)
                if resp.status_code in {200, 201, 204}:
                    st.success(f"Team updated for **{team_project_label}**.")
                    st.rerun()
                else:
                    show_api_error(resp)


# --------------------------------------------------------------------------
# CLIENTS — view, add, edit, delete
# --------------------------------------------------------------------------
def _render_manager_clients(token, projects):
    st.title("🏢 Clients")
    st.caption("View, add, edit, and delete your organization's client accounts.")
    st.write("")

    clients_resp = get_clients(token)
    if clients_resp.status_code != 200:
        show_api_error(clients_resp)
        return
    clients = clients_resp.json()

    active_n = sum(1 for c in clients if (c.get("status") or "").lower() == "active")
    pending_n = sum(1 for c in clients if (c.get("status") or "").lower() == "pending")
    inactive_n = sum(1 for c in clients if (c.get("status") or "").lower() == "inactive")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("🏢", "#EDE9FE", "Total Clients", len(clients), "All clients")
    with c2:
        _stat_card("🟢", "#DCFCE7", "Active", active_n, "Active clients")
    with c3:
        _stat_card("🟡", "#FEF9C3", "Pending", pending_n, "Pending clients")
    with c4:
        _stat_card("⚪", "#F3F4F6", "Inactive", inactive_n, "Inactive clients")

    st.write("")

    if not clients:
        st.info("No clients found for your organization yet. Add one below.")
    else:
        with st.container(border=True):
            st.subheader("Client Overview")
            counts = {}
            for c in clients:
                s = (c.get("status") or "unknown").lower()
                counts[s] = counts.get(s, 0) + 1
            labels = [s.title() for s in counts]
            values = list(counts.values())
            colors = [_client_status_meta(s)["hex"] for s in counts]

            chart_col, legend_col = st.columns([1.3, 1])
            with chart_col:
                st.plotly_chart(
                    _animated_donut(labels, values, colors, "Total Clients"),
                    use_container_width=True, config={"displayModeBar": False},
                    key="mgr_client_status_donut",
                )
            with legend_col:
                st.write("")
                for status, count in counts.items():
                    meta = _client_status_meta(status)
                    pct = round(100 * count / len(clients))
                    st.markdown(
                        f"**{status.title()}** &nbsp; **{pct}%** &nbsp; "
                        f"{_color_dot(meta['hex'])}"
                        f"&nbsp; <span style='color:#9CA3AF !important;font-size:0.8rem;'>({count})</span>",
                        unsafe_allow_html=True,
                    )
                    st.write("")

            st.write("")
            client_choice_labels = ["All Clients"] + [c.get("company_name", "—") for c in clients]
            selected_overview_client = st.selectbox(
                "🏢 All Clients", client_choice_labels,
                key="manager_client_overview_filter",
            )

            if selected_overview_client == "All Clients":
                with st.container(height=220):
                    for c in clients:
                        cmeta = _client_status_meta(c.get("status"))
                        st.markdown(f"**{c.get('company_name', '—')}**")
                        st.markdown(
                            f"{_color_dot(cmeta['hex'])}"
                            f"&nbsp;<span style='color:#4B5563 !important;font-size:0.82rem;font-weight:500;'>"
                            f"{cmeta['icon']} {c.get('status', '—')} · "
                            f"{c.get('contact_name', '—')} · {c.get('email', '—')}</span>",
                            unsafe_allow_html=True,
                        )
                        st.write("")
            else:
                overview_client = next(
                    (c for c in clients if c.get("company_name") == selected_overview_client), None
                )
                if overview_client:
                    ometa = _client_status_meta(overview_client.get("status"))
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        st.caption("Status")
                        _hex_pill(f"{ometa['icon']} {overview_client.get('status', '—')}", ometa["hex"])
                    with d2:
                        st.caption("Contact")
                        st.markdown(f"**{overview_client.get('contact_name', '—')}**")
                    with d3:
                        st.caption("Email")
                        st.markdown(f"**{overview_client.get('email', '—')}**")
                    st.write("")
                    st.caption(f"📞 {overview_client.get('phone', '—')}")

    st.write("")

    with st.expander("🔎 Client Details"):
        if not clients:
            st.info("No clients yet.")
        else:
            client_names = [c["company_name"] for c in clients]
            selected_client_name = st.selectbox(
                "🏢 Select client", client_names,
                key="manager_client_detail_select",
            )
            selected_client_detail = next(
                (c for c in clients if c["company_name"] == selected_client_name), None
            )
            if selected_client_detail:
                meta = _client_status_meta(selected_client_detail.get("status"))
                st.write("")
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.caption("Status")
                    _hex_pill(f"{meta['icon']} {selected_client_detail.get('status', '—')}", meta["hex"])
                with d2:
                    st.caption("Contact")
                    st.markdown(f"**{selected_client_detail.get('contact_name', '—')}**")
                with d3:
                    st.caption("Email")
                    st.markdown(f"**{selected_client_detail.get('email', '—')}**")
                st.write("")
                st.caption(f"📞 {selected_client_detail.get('phone', '—')}")

    with st.expander("➕ Add client"):
        with st.form("manager_add_client_form", clear_on_submit=True):
            company_name = st.text_input("Company name")
            contact_name = st.text_input("Contact name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            status = st.selectbox("Status", CLIENT_STATUS_OPTIONS)

            show_password = st.checkbox("👁 Show password", key="manager_add_client_show_pw")
            client_password = st.text_input(
                "Client login password (optional)",
                type="default" if show_password else "password",
                key="manager_add_client_password",
            )

            if st.form_submit_button("Add client", type="primary"):
                if not company_name.strip():
                    st.error("Company name is required.")
                elif not contact_name.strip():
                    st.error("Contact name is required.")
                else:
                    payload = {
                        "company_name": company_name.strip(),
                        "contact_name": contact_name.strip(),
                        "email": email.strip(),
                        "phone": phone.strip(),
                        "status": status,
                    }
                    if client_password.strip():
                        payload["password"] = client_password.strip()
                    resp = create_client(token, payload)
                    if resp.status_code in {200, 201}:
                        st.success(f"Client **{company_name}** added.")
                        st.rerun()
                    else:
                        show_api_error(resp)

    if clients:
        with st.expander("✏️ Edit client"):
            client_options = {f"{c['company_name']} ({c['id']})": c for c in clients}
            selected_label = st.selectbox("Select client to edit", list(client_options.keys()),
                                           key="manager_edit_client_select")
            selected_client = client_options[selected_label]

            current_status = (selected_client.get("status") or "active").lower()
            meta = _client_status_meta(current_status)
            st.caption(f"Current status: {meta['icon']} {current_status.title()}")

            with st.form("manager_edit_client_form"):
                company_name = st.text_input("Company name", value=selected_client.get("company_name", ""))
                contact_name = st.text_input("Contact name", value=selected_client.get("contact_name", ""))
                email = st.text_input("Email", value=selected_client.get("email", ""))
                phone = st.text_input("Phone", value=selected_client.get("phone", ""))
                status = st.selectbox(
                    "Status", CLIENT_STATUS_OPTIONS,
                    index=CLIENT_STATUS_OPTIONS.index(current_status)
                    if current_status in CLIENT_STATUS_OPTIONS else 0,
                )
                if st.form_submit_button("Update client", type="primary"):
                    if not company_name.strip():
                        st.error("Company name is required.")
                    else:
                        resp = update_client(token, selected_client["id"], {
                            "company_name": company_name.strip(),
                            "contact_name": contact_name.strip(),
                            "email": email.strip(),
                            "phone": phone.strip(),
                            "status": status,
                        })
                        if resp.status_code == 200:
                            st.success("Client updated.")
                            st.rerun()
                        else:
                            show_api_error(resp)

    if clients:
        with st.expander("🗑️ Delete client"):
            delete_options = {str(c["id"]): c for c in clients}
            selected_delete_id = st.selectbox(
                "Select client to delete", list(delete_options.keys()),
                key="manager_delete_client_select",
            )
            selected_delete_client = delete_options[selected_delete_id]
            st.caption(f"This will permanently remove **{selected_delete_client.get('company_name', '—')}**.")

            confirm = st.checkbox("I confirm deletion", key="manager_delete_client_confirm")

            if st.button("Delete client", key="manager_delete_client_button",
                         type="primary", disabled=not confirm):
                resp = delete_client(token, selected_delete_id)
                if resp.status_code in {200, 204}:
                    st.success("Client deleted.")
                    st.rerun()
                else:
                    show_api_error(resp)


# --------------------------------------------------------------------------
# MEETINGS — AI meeting summaries (upload + view), scoped by project
# --------------------------------------------------------------------------
def _render_manager_meetings(projects, token):
    st.title("🎙️ Meeting Summaries")
    st.caption("Upload recordings and view AI-generated summaries for your projects.")
    st.write("")

    active_project_id, project_label = _choose_active_project(
        projects, widget_key="manager_meetings_project_dropdown"
    )
    st.caption(f"Showing: **{project_label}**")
    st.write("")

    render_meeting_panel(
        token=token,
        projects=projects,
        allow_upload=True,
        key_prefix="manager",
        selected_project_id=active_project_id,
        show_project_selector=False,
    )


# --------------------------------------------------------------------------
# WEEKLY REPORTS — generate and view per-project AI reports
# --------------------------------------------------------------------------
def _render_weekly_reports(projects, token):
    st.title("📊 Weekly Reports")
    st.caption("Generate and view AI-powered weekly progress reports for your projects.")
    st.write("")

    if not projects:
        st.info("No projects found. Create a project first.")
        return

    active_project_id, project_label = _choose_active_project(
        projects, widget_key="manager_weekly_reports_project_dropdown"
    )

    if active_project_id is None:
        st.warning("Please select a specific project (not 'All Projects') to generate or view reports.")
        return

    st.caption(f"Project: **{project_label}**")
    st.write("")

    with st.container(border=True):
        st.subheader("Generate Report")
        st.caption("Creates a new AI-written summary of tasks, progress, and status for this week.")
        if st.button("Generate Weekly Report", key="mgr_gen_weekly_report", type="primary"):
            with st.spinner("Generating report..."):
                resp = generate_weekly_report(token, active_project_id)
            if resp.status_code in {200, 201}:
                report = resp.json()
                st.success("Report generated successfully.")
                st.markdown("**Report Preview:**")
                st.markdown(report.get("report_text", "—"))
            else:
                show_api_error(resp)

    st.write("")

    with st.container(border=True):
        st.subheader("Past Reports")
        resp = get_weekly_reports(token, active_project_id)
        if resp.status_code != 200:
            show_api_error(resp)
            return
        reports = resp.json()
        if not reports:
            st.info("No reports yet for this project. Generate one above.")
        else:
            for i, report in enumerate(reports):
                created = report.get("created_at", "")[:16].replace("T", " ")
                with st.expander(f"Report — {created}"):
                    st.markdown(report.get("report_text", "—"))


# --------------------------------------------------------------------------
# REQUIREMENT ANALYZER — AI Epics/Stories/Tasks breakdown with human review
# --------------------------------------------------------------------------
def _render_requirement_analyzer(projects, token):
    st.title("🧠 Requirement Analyzer")
    st.caption(
        "Select an uploaded requirement document and let AI break it into "
        "Epics → User Stories → Tasks. Review & edit the result, then click "
        "Approve to create real tasks (nothing is created until you approve)."
    )
    st.write("")

    if not projects:
        st.info("No projects found. Create a project and upload a requirement document first.")
        return

    project_labels = [p["name"] for p in projects]
    project_label = st.selectbox(
        "Project", project_labels, key="mgr_req_project_select"
    )
    selected_project = next(
        (p for p in projects if p["name"] == project_label), None
    )
    if not selected_project:
        return
    project_id = str(selected_project["id"])

    docs_resp = list_documents(token, project_id=project_id)
    if docs_resp.status_code != 200:
        show_api_error(docs_resp)
        return
    documents = docs_resp.json()

    if not documents:
        st.warning("No documents uploaded for this project yet. Upload a requirement file first.")
        return

    doc_labels = {d["filename"]: d for d in documents}
    doc_label = st.selectbox(
        "Requirement document", list(doc_labels.keys()), key="mgr_req_doc_select"
    )
    selected_doc = doc_labels[doc_label]
    document_id = str(selected_doc["id"])

    if st.button("Analyze", key="mgr_req_analyze", type="primary"):
        with st.spinner("Analyzing requirement document with AI..."):
            resp = analyze_requirement(token, document_id, project_id)
        if resp.status_code in {200, 201}:
            data = resp.json()
            st.session_state["mgr_req_analysis"] = data
            st.success(f"Analysis ready (id: {data['id']}). Review it below.")
            st.rerun()
        else:
            show_api_error(resp)

    analysis = st.session_state.get("mgr_req_analysis")
    if not analysis:
        st.info("Click 'Analyze' to generate a structured breakdown.")
        return

    if analysis.get("status") == "approved":
        st.success("This analysis has already been approved and tasks were created.")
        return
    if analysis.get("status") == "rejected":
        st.info("This analysis was rejected. No tasks were created.")
        return

    epics = analysis.get("breakdown", {}).get("epics", [])

    st.divider()
    st.subheader("Review & Edit Epics / Stories")

    if "mgr_req_edited" not in st.session_state:
        st.session_state["mgr_req_edited"] = epics

    edited = st.session_state["mgr_req_edited"]

    epic_to_delete = None
    story_deletes = {}
    for ei, epic in enumerate(list(edited)):
        with st.container(border=True):
            col_t, col_d = st.columns([5, 1])
            with col_t:
                epic["title"] = st.text_input(
                    f"Epic {ei + 1} title", value=epic.get("title", ""),
                    key=f"mgr_req_epic_title_{ei}",
                )
            with col_d:
                if st.button("🗑️ Delete epic", key=f"mgr_req_del_epic_{ei}"):
                    epic_to_delete = ei

            for si, story in enumerate(list(epic.get("stories", []))):
                with st.container(border=True):
                    st.markdown(f"**Story {si + 1}**")
                    story["title"] = st.text_input(
                        "Title", value=story.get("title", ""),
                        key=f"mgr_req_story_title_{ei}_{si}",
                    )
                    story["description"] = st.text_area(
                        "Description", value=story.get("description", ""),
                        key=f"mgr_req_story_desc_{ei}_{si}",
                    )
                    priority = story.get("priority", "medium")
                    if priority not in ("low", "medium", "high"):
                        priority = "medium"
                    story["priority"] = st.selectbox(
                        "Priority", ["low", "medium", "high"],
                        index=["low", "medium", "high"].index(priority),
                        key=f"mgr_req_story_pri_{ei}_{si}",
                    )
                    if st.button(
                        "🗑️ Delete story", key=f"mgr_req_del_story_{ei}_{si}"
                    ):
                        story_deletes[(ei, si)] = True

    if epic_to_delete is not None:
        del edited[epic_to_delete]
        st.rerun()

    if story_deletes:
        for (ei, si) in list(story_deletes.keys()):
            if ei < len(edited):
                stories = edited[ei].get("stories", [])
                if si < len(stories):
                    del stories[si]
        st.rerun()

    st.divider()

    col_app, col_rej = st.columns(2)
    with col_app:
        if st.button("✅ Approve & Create Tasks", key="mgr_req_approve", type="primary"):
            with st.spinner("Creating tasks via project task logic..."):
                resp = approve_requirement_analysis(token, analysis["id"], edited)
            if resp.status_code in {200, 201}:
                data = resp.json()
                task_ids = data.get("task_ids", [])
                st.success(
                    f"Approved! Created {len(task_ids)} task(s). "
                    f"Task IDs: {', '.join(str(t) for t in task_ids[:5])}"
                )
                st.session_state["mgr_req_analysis"]["status"] = "approved"
                st.rerun()
            else:
                show_api_error(resp)
    with col_rej:
        if st.button("❌ Reject", key="mgr_req_reject"):
            resp = reject_requirement_analysis(token, analysis["id"])
            if resp.status_code in {200, 204}:
                st.info("Analysis rejected. No tasks were created.")
                st.session_state["mgr_req_analysis"]["status"] = "rejected"
                st.rerun()
            else:
                show_api_error(resp)


# --------------------------------------------------------------------------
# APP ENTRY — navigation lives in the sidebar
# --------------------------------------------------------------------------
def render_manager_app():
    _inject_light_theme()

    token = session_token()
    user = session_user()
    if not token or not user:
        st.error("Your session expired. Please log in again.")
        if st.button("Back to login", key="manager_back_to_login"):
            st.session_state.clear()
            st.rerun()
        return

    projects_resp = get_projects(token)
    projects = projects_resp.json() if projects_resp.status_code == 200 else []
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)

    if NAV_RADIO_KEY not in st.session_state:
        st.session_state[NAV_RADIO_KEY] = NAV_PAGES[0]

    with st.sidebar:
        render_sidebar_header()
        st.markdown("### 🧭 Manager Workspace")
        page = st.radio(
            "Go to",
            NAV_PAGES,
            label_visibility="collapsed",
            key=NAV_RADIO_KEY,
        )

    # Clear task-dialog flags on navigation so a dialog closed with X/Esc
    # cannot reopen automatically after returning to the Tasks page.
    if st.session_state.get("mgr_last_page") != page:
        st.session_state["mgr_last_page"] = page
        st.session_state["mgr_open_issue_id"] = None
        st.session_state["mgr_show_create_issue"] = False
        st.session_state["mgr_modules_dialog_project"] = None
        st.session_state["mgr_module_detail_open"] = None

    if page == "🏠 Dashboard":
        _render_manager_dashboard(projects, token)
    elif page == "🏢 Clients":
        _render_manager_clients(token, projects)
    elif page == "📁 Projects":
        _render_manager_projects(projects, token)
    elif page == "✅ Tasks":
        _render_manager_tasks(projects, token)
    elif page == "📄 Documents":
        _render_manager_documents(projects, token)
    elif page == "🎙️ Meetings":
        _render_manager_meetings(projects, token)
    elif page == "📊 Weekly Reports":
        _render_weekly_reports(projects, token)
    elif page == "🧠 Requirement Analyzer":
        _render_requirement_analyzer(projects, token)