"""
admin.py

Merged version: combines teju_admin.py + admin.py so no function is lost.

- Hover-highlighted stat cards (_inject_stat_card_hover_css) applied on
  EVERY page: Dashboard, Users & Roles, Clients, Projects — this behavior
  was only in teju_admin.py; admin.py only had it on the Dashboard.
- "Overall System Overview" card uses PROJECT MODULES data
  (get_project_modules) — this was only in admin.py; teju_admin.py used
  task-status counts instead. Kept the modules version since it's the
  richer/more complete feature.
- Extra stStatusWidget theming CSS from admin.py included.
"""

import datetime as dt
import html

import streamlit as st
import plotly.graph_objects as go

from api_client import (
    get_clients, get_projects, get_tasks, list_documents, get_users,
    get_team, create_project, update_project, assign_team,
    get_project_modules, create_project_module,
    create_client, update_client, delete_client,
    patch_task_status, create_task, update_task, delete_task,
    upload_document, download_document, delete_document,
    generate_weekly_report, get_weekly_reports,
    analyze_requirement, get_requirement_analysis, list_requirement_analyses,
    approve_requirement_story, approve_requirement_analysis, reject_requirement_analysis,
)
from views.shared import (
    render_sidebar_header,
    show_api_error,
    show_document_preview,
    render_meeting_panel,
    session_token,
    session_user,
    rag_status_label,
    trigger_reindex,
)

STATUS_META = {
    "todo":        {"label": "To Do",       "icon": "🔵", "color": "#3B82F6"},
    "in_progress": {"label": "In Progress", "icon": "🟠", "color": "#F59E0B"},
    "testing":     {"label": "Testing",     "icon": "🟣", "color": "#8B5CF6"},
    "done":        {"label": "Done",        "icon": "🟢", "color": "#22C55E"},
}

# Order here drives legend/pie order — matches the reference screenshot
# (Completed -> In Progress -> On Hold -> Not Started).
PROJECT_STATUS_META = {
    "completed": {"label": "Completed",    "color": "#22C55E"},
    "active":    {"label": "In Progress",  "color": "#3B82F6"},
    "on_hold":   {"label": "On Hold",      "color": "#F59E0B"},
    "planning":  {"label": "Not Started",  "color": "#EF4444"},
}
PROJECT_STATUS_OPTIONS = ["planning", "active", "on_hold", "completed"]

CLIENT_STATUS_META = {
    "active":   {"icon": "🟢", "color": "#22C55E"},
    "pending":  {"icon": "🟡", "color": "#EAB308"},
    "inactive": {"icon": "⚪", "color": "#6B7280"},
}
CLIENT_STATUS_OPTIONS = ["active", "pending", "inactive"]

NAV_PAGES = [
    "🏠 Dashboard", "🏢 Clients", "📁 Projects",
    "📄 Documents", "🎙️ Meetings", "📊 Weekly Reports",
    "🧠 Requirement Analyzer",
]
IMPLEMENTED_PAGES = {
    "🏠 Dashboard", "🏢 Clients", "📁 Projects",
    "📄 Documents", "🎙️ Meetings", "📊 Weekly Reports",
    "🧠 Requirement Analyzer",
}
NAV_RADIO_KEY = "admin_nav_radio"

# Requirement Analyzer tabs and session keys
MODULE_ICON_OPTIONS = ["🧩", "👤", "👥", "💳", "🔔", "⚙️", "🔐", "📦", "🔗", "📊", "🧪", "📁"]
ALL_PROJECTS_LABEL = "All Projects"
REQ_ANALYZER_TAB_ANALYZE = "Analyze Document"
REQ_ANALYZER_TAB_REVIEW = "Review Drafts"
REQ_ANALYZER_TAB_KEY = "admin_req_analyzer_view"


# --------------------------------------------------------------------------
# LIGHT THEME — flat white cards, soft border + shadow, violet accents.
# Matches the reference screenshot. BaseWeb's Select/Multiselect dropdown
# portal mounts at document.body (outside .stApp), so it's styled globally
# below — otherwise it would fall back to the browser default look.
# --------------------------------------------------------------------------
def _inject_light_theme():
    """
    Brand/component CSS on top of Streamlit's light base theme
    (.streamlit/config.toml: base=light). Keeps cards, sidebar nav,
    popovers, uploaders, and pills readable; does not re-define the
    framework background/text defaults except for the soft #F8F9FF tint.
    """
    css_lines = [
        "<style>",
        # Soft page tint — config.toml already sets base light/white.
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
        ".stCaption, [data-testid='stCaptionContainer'], [data-testid='stCaptionContainer'] * { color: #4B5563 !important; font-weight: 500; }",
        "[data-testid='stWidgetLabel'] p { color: #111827 !important; }",
        "",
        "section[data-testid='stSidebar'] {",
        "    background: #FFFFFF;",
        "    border-right: 1px solid #EEF0F3;",
        "}",
        "section[data-testid='stSidebar'] * { color: #374151 !important; }",
        "section[data-testid='stSidebar'] code {",
        "    background: #E0E7FF !important;",
        "    color: #312E81 !important;",
        "    border: 1px solid #C7D2FE !important;",
        "    border-radius: 5px !important;",
        "    padding: 2px 6px !important;",
        "}",
        "",
        "section[data-testid='stSidebar'] div[role='radiogroup'] {",
        "    display: flex; flex-direction: column; gap: 2px;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label {",
        "    background-color: transparent; border: none; border-radius: 8px;",
        "    padding: 9px 12px !important; margin: 0 !important; cursor: pointer;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:hover {",
        "    background-color: #F3F4F6;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) {",
        "    background-color: #EEF2FF !important;",
        "    border-left: 3px solid #4F46E5 !important;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked),",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) p,",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) span {",
        "    color: #312E81 !important; font-weight: 600;",
        "}",
        "/* Hide the radio indicator; the whole navigation row remains clickable. */",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label > div:first-child { display: none !important; }",
        "",
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
        "    background-color: #FFFFFF; color: #374151;",
        "    border: 1px solid #E5E7EB; border-radius: 8px;",
        "}",
        ".stButton button:hover { border-color: #4F46E5; color: #4338CA; }",
        ".stButton button[kind='primary'] {",
        "    background-color: #4F46E5; color: #FFFFFF !important; border: 1px solid #4F46E5;",
        "}",
        ".stButton button[kind='primary']:hover { background-color: #4338CA; border-color: #4338CA; }",
        ".stButton button[kind='primary'] p { color: #FFFFFF !important; }",
        ".stButton button p, .stButton button span { color: inherit !important; }",
        ".stButton button[kind='primary'] p, .stButton button[kind='primary'] span { color: #FFFFFF !important; }",
        "/* Download controls and document previews must stay light/readable. */",
        ".stDownloadButton button {",
        "    background-color: #FFFFFF !important; color: #374151 !important;",
        "    border: 1px solid #E5E7EB !important; border-radius: 8px !important;",
        "}",
        ".stDownloadButton button:hover { border-color: #4F46E5 !important; color: #4338CA !important; }",
        ".stDownloadButton button * { color: inherit !important; }",
        "[data-testid='stCodeBlock'], [data-testid='stCodeBlock'] pre, pre, code {",
        "    background-color: #FFFFFF !important; color: #111827 !important;",
        "    border: 1px solid #E5E7EB !important; border-radius: 8px !important;",
        "}",
        "[data-testid='stJson'], [data-testid='stJson'] * { background-color: #FFFFFF !important; color: #111827 !important; }",
        "[data-testid='stText'] pre { background-color: #FFFFFF !important; color: #111827 !important; }",
        "[data-testid='stDialog'], [data-testid='stDialog'] > div { background-color: #FFFFFF !important; }",
        "[data-testid='stDialog'] * { color: #111827 !important; }",
        "iframe, [data-testid='stImage'] { background-color: #FFFFFF !important; border-radius: 8px !important; }",
        "/* Forms / uploaders / alerts stay light with dark text. */",
        "div[data-testid='stAlert'] { background-color: #F9FAFB !important; border-radius: 10px !important; }",
        "div[data-testid='stAlert'] * { color: #111827 !important; }",
        "[data-testid='stFileUploaderDropzone'] { background-color: #F9FAFB !important; border: 1px dashed #D1D5DB !important; }",
        "[data-testid='stFileUploaderDropzone'] * { color: #374151 !important; }",
        "[data-testid='stFileUploaderFile'] { background-color: #FFFFFF !important; border: 1px solid #E5E7EB !important; border-radius: 8px !important; }",
        "[data-testid='stFileUploaderFile'] * { color: #111827 !important; }",
        "[data-testid='stFileUploaderDropzone'] button, [data-testid='stFileUploader'] button { background-color: #FFFFFF !important; color: #374151 !important; border: 1px solid #E5E7EB !important; }",
        ".stTextInput input, .stTextArea textarea { background-color: #FFFFFF !important; color: #111827 !important; border-color: #E5E7EB !important; }",
        "",
        ".stProgress > div > div > div > div { border-radius: 6px; }",
        ".stProgress > div > div { background-color: #F3F4F6; border-radius: 6px; }",
        "",
        "[data-testid='stDataFrame'] { color: #111827 !important; }",
        "",
        ".icon-badge {",
        "    width: 44px; height: 44px; border-radius: 12px;",
        "    display: flex; align-items: center; justify-content: center;",
        "    font-size: 1.25rem; margin-bottom: 0.5rem;",
        "}",
        ".status-pill {",
        "    display: inline-block; padding: 2px 10px; border-radius: 999px;",
        "    font-size: 0.75rem; font-weight: 600;",
        "}",
        "",
        "div[data-testid='stExpander'] {",
        "    border: 1px solid #EEF0F3 !important;",
        "    border-radius: 14px !important;",
        "    background-color: #FFFFFF !important;",
        "}",
        "hr { border-color: #EEF0F3 !important; }",
        "",
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
        "    background-color: #FFFFFF !important; color: #111827 !important; border-radius: 6px !important;",
        "}",
        "div[data-baseweb='popover'] li[role='option']:hover,",
        "div[data-baseweb='popover'] li:hover {",
        "    background-color: #F3F4F6 !important; color: #111827 !important;",
        "}",
        "div[data-baseweb='popover'] li[aria-selected='true'] {",
        "    background-color: #EEF2FF !important; color: #4338CA !important; font-weight: 600;",
        "}",
        "div[data-baseweb='popover'] li[role='option'] * { color: inherit !important; }",
        "",
        "div[data-baseweb='select'] > div {",
        "    background-color: #FFFFFF !important; border-color: #E5E7EB !important;",
        "    color: #111827 !important; border-radius: 8px !important;",
        "}",
        "div[data-baseweb='select'] > div:hover { border-color: #4F46E5 !important; }",
        "div[data-baseweb='select'] input { color: #111827 !important; }",
        "div[data-baseweb='select'] svg { fill: #6B7280 !important; }",
        "div[data-baseweb='select'] span { color: #111827 !important; }",
        "",
        "/* Selectbox virtual dropdown list (Streamlit renders this in a",
        "   separate virtualized container the generic popover rules above",
        "   don't reach). */",
        "div[data-testid='stSelectboxVirtualDropdown'] { background-color: #FFFFFF !important; }",
        "div[data-testid='stSelectboxVirtualDropdown'] * { background-color: #FFFFFF !important; color: #111827 !important; }",
        "div[data-testid='stSelectboxVirtualDropdown'] li:hover,",
        "div[data-testid='stSelectboxVirtualDropdown'] div[aria-selected='true'] { background-color: #F3F4F6 !important; }",
        "",
        "span[data-baseweb='tag'] {",
        "    background-color: #EEF2FF !important; color: #4338CA !important; border-radius: 6px !important;",
        "}",
        "span[data-baseweb='tag'] span { color: #4338CA !important; }",
        "span[data-baseweb='tag'] svg { fill: #4338CA !important; }",
        "",
        "div[data-baseweb='calendar'] { background-color: #FFFFFF !important; }",
        "div[data-baseweb='calendar'] * { color: #111827 !important; }",
        "</style>",
    ]
    st.markdown("\n".join(css_lines), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Shared visual helpers
# --------------------------------------------------------------------------
def _icon_badge(icon, bg):
    st.markdown(f"<div class='icon-badge' style='background:{bg};'>{icon}</div>", unsafe_allow_html=True)


def _color_dot(color, size=10):
    """
    Small filled circle used for status legends (Projects by Status,
    Client Overview, etc). Uses background-color rather than a colored
    text bullet ('●' + color:) because the global theme CSS forces
    `color: #111827 !important` on every element inside a markdown
    block, which fights a text-color bullet. background-color isn't
    touched by that rule, so this renders reliably.
    """
    return (
        f"<span style='display:inline-block;width:{size}px;height:{size}px;"
        f"border-radius:50%;background-color:{color};vertical-align:middle;'></span>"
    )


def _pill(text, color):
    st.markdown(
        f"<span class='status-pill' style='background:{color}1A;color:{color} !important;"
        f"border:1px solid {color}55;'>{text}</span>",
        unsafe_allow_html=True,
    )


def _stat_card(icon, bg, label, value, sublabel, key=None):
    """Flat white stat card: icon badge, label, big value, small caption."""
    with st.container(border=True, key=key):
        _icon_badge(icon, bg)
        st.markdown(f"<div style='color:#6B7280; font-size:0.82rem;'>{label}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:1.6rem; font-weight:700; color:#111827;'>{value}</div>",
                    unsafe_allow_html=True)
        st.caption(sublabel)


def _hover_stat_card(icon, bg, label, value, sublabel, key):
    """
    Same as _stat_card, but given a unique container `key` so the boxed
    look + hover highlight (see _inject_stat_card_hover_css) can target
    exactly these summary cards — not every bordered container app-wide.
    Streamlit adds a `st-key-<key>` class to the container's wrapper div,
    which is what the CSS below matches on.
    """
    _stat_card(icon, bg, label, value, sublabel, key=key)


def _inject_stat_card_hover_css():
    """
    Scoped CSS for stat-card containers: a clearly visible white box at
    rest, plus a strong highlight + lift-on-hover. Targets containers via
    their `st-key-stat-card-*` class (set by passing key= to st.container),
    which is reliable regardless of DOM nesting — unlike sibling-selector
    tricks. Applied on every page that renders stat cards (Dashboard,
    Users & Roles, Clients, Projects).
    """
    st.markdown(
        """
        <style>
        div[class*="st-key-stat-card-"] {
            background-color: #FFFFFF !important;
            border: 1.5px solid #D8DCE5 !important;
            border-radius: 14px !important;
            box-shadow: 0 2px 6px rgba(16,24,40,0.08) !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease,
                        border-color 0.15s ease, background-color 0.15s ease;
            cursor: pointer;
        }
        div[class*="st-key-stat-card-"]:hover {
            background-color: #F5F3FF !important;
            border-color: #818CF8 !important;
            transform: translateY(-4px);
            box-shadow: 0 12px 28px rgba(79,70,229,0.22) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _donut(labels, values, colors, center_line1, center_line2, height=230):
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.68,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=3)),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=f"<b style='font-size:26px;color:#111827'>{center_line1}</b><br>"
                 f"<span style='font-size:12px;color:#6B7280'>{center_line2}</span>",
            x=0.5, y=0.5, showarrow=False,
        )],
    )
    return fig


def _progress_ring(pct, color, height=190):
    """Single-value completion ring, used for the Overall System Overview card."""
    pct = max(0, min(100, int(pct)))
    fig = go.Figure(data=[go.Pie(
        values=[pct, 100 - pct], hole=0.75,
        marker=dict(colors=[color, "#F1F5F9"], line=dict(color="#FFFFFF", width=2)),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(text=f"<b style='font-size:26px;color:#111827'>{pct}%</b>",
                 x=0.5, y=0.56, showarrow=False),
            dict(text="<span style='font-size:12px;color:#6B7280'>Overall Progress</span>",
                 x=0.5, y=0.42, showarrow=False),
        ],
    )
    return fig


def _phase_rows(status_counts, total):
    """Colored-dot + label + progress bar + count(%) row, one per task status."""
    total = total or 1
    for key, meta in STATUS_META.items():
        count = status_counts.get(key, 0)
        pct = round(100 * count / total)
        dot_col, label_col, bar_col, val_col = st.columns([0.4, 2, 4, 1.4])
        with dot_col:
            st.markdown(
                f"<div style='width:10px;height:10px;border-radius:50%;"
                f"background:{meta['color']};margin-top:8px;'></div>",
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


def _fetch_users_safely(token):
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


def _pill_html(text, cls):
    """Render a pill badge as HTML with a CSS class."""
    return f"<span class='pill {cls}'>{text}</span>"


def _get_project_modules(token, project_id):
    """Load persisted modules from the backend, ordered by workflow position."""
    resp = get_project_modules(token, str(project_id))
    if resp.status_code == 200:
        return resp.json()
    show_api_error(resp)
    return []


def _project_task_progress(project_id, tasks):
    linked = [t for t in tasks if str(t.get("project_id")) == str(project_id)]
    if not linked:
        return None, 0, 0
    done = sum(1 for t in linked if (t.get("status") or "") == "done")
    return round(100 * done / len(linked)), done, len(linked)


def _client_status_meta(status_text):
    return CLIENT_STATUS_META.get((status_text or "").strip().lower(),
                                   {"icon": "⚪", "color": "#6B7280"})


def _go_to(page_label):
    st.session_state[NAV_RADIO_KEY] = page_label


# --------------------------------------------------------------------------
# PROJECT DETAILS — project picker + scoped data (lives inside Projects tab)
# --------------------------------------------------------------------------
def _render_project_detail_section(projects, token):
    st.subheader("🔎 Project Details")
    if not projects:
        st.info("No projects yet — create one from the form below.")
        return

    project_names = [p["name"] for p in projects]
    selected_name = st.selectbox(
        "📁 Select project", project_names,
        key="admin_project_detail_select",
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
    meta = PROJECT_STATUS_META.get(
        (selected_project.get("status") or "").lower(),
        {"label": selected_project.get("status", "—"), "color": "#6B7280"},
    )

    st.write("")
    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        st.caption("Status")
        _pill(meta["label"], meta["color"])
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
# DASHBOARD
# --------------------------------------------------------------------------
def _render_admin_dashboard():
    user = session_user()
    token = session_token()

    _inject_stat_card_hover_css()

    title_col, date_col, avatar_col = st.columns([6, 2, 1])
    with title_col:
        hour = dt.datetime.now().hour
        salutation = "Morning" if hour < 12 else ("Afternoon" if hour < 18 else "Evening")
        st.title(f"Good {salutation}, {user['name'].split()[0]}! 👋")
        st.caption("Here's an overview of the system and organization performance.")
    with date_col:
        st.write("")
        st.markdown(
            f"<div style='text-align:right; padding-top:10px; color:#6B7280; font-weight:600;'>"
            f"📅 {dt.date.today().strftime('%B %d, %Y')}</div>",
            unsafe_allow_html=True,
        )
    with avatar_col:
        st.write("")
        initials = "".join(p[0] for p in user["name"].split()[:2]).upper()
        st.badge(initials, color="violet")

    st.write("")

    # ---- Live fetches — single source of truth for every card/graph below --
    clients_resp = get_clients(token)
    projects_resp = get_projects(token)
    tasks_resp = get_tasks(token)
    docs_resp = list_documents(token)
    users_resp = get_users(token)

    clients = clients_resp.json() if clients_resp.status_code == 200 else []
    projects = projects_resp.json() if projects_resp.status_code == 200 else []
    tasks = tasks_resp.json() if tasks_resp.status_code == 200 else []
    documents = docs_resp.json() if docs_resp.status_code == 200 else []
    users = users_resp.json() if users_resp.status_code == 200 else []

    for resp in (clients_resp, projects_resp, tasks_resp, docs_resp, users_resp):
        if resp.status_code != 200:
            show_api_error(resp)

    # ---- Stat cards (4 cards: Clients, Projects, Members, Documents) ----
    stat_cards = [
        ("👥", "#EDE9FE", "Total Clients", len(clients), "Active Clients"),
        ("📁", "#DBEAFE", "Total Projects", len(projects), "Active Projects"),
        ("👤", "#EDE9FE", "Total Members", len(users), "Team Members"),
        ("📄", "#FEE2E2", "Documents", len(documents), "Uploaded Files"),
    ]
    cols = st.columns(4)
    for i, (col, (icon, bg, label, value, sub)) in enumerate(zip(cols, stat_cards)):
        with col:
            _hover_stat_card(icon, bg, label, value, sub, key=f"stat-card-dash-{i}")

    st.write("")

    # ---- Projects by Status — moved to top, full width, split horizontally
    with st.container(border=True):
        st.subheader("Projects by Status")
        st.caption("Distribution of projects across different status.")
        if not projects:
            st.info("No projects yet.")
        else:
            status_counts = {k: 0 for k in PROJECT_STATUS_META}
            for p in projects:
                sk = (p.get("status") or "planning").lower()
                status_counts[sk if sk in status_counts else "planning"] += 1
            total = len(projects)
            shown = [k for k in PROJECT_STATUS_META if status_counts[k] > 0]
            labels = [PROJECT_STATUS_META[k]["label"] for k in shown]
            values = [status_counts[k] for k in shown]
            colors = [PROJECT_STATUS_META[k]["color"] for k in shown]

            chart_col, legend_col = st.columns([1.1, 1.3])
            with chart_col:
                st.plotly_chart(
                    _donut(labels, values, colors, str(total), "Projects", height=260),
                    use_container_width=True, config={"displayModeBar": False},
                    key="admin_project_status_donut",
                )
            with legend_col:
                st.write("")
                for key in shown:
                    meta = PROJECT_STATUS_META[key]
                    val = status_counts[key]
                    pct = round(100 * val / total) if total else 0
                    st.markdown(
                        f"{_color_dot(meta['color'])}"
                        f"&nbsp; {meta['label']}"
                        f"<span style='float:right;color:#6B7280 !important;'>{val} ({pct}%)</span>",
                        unsafe_allow_html=True,
                    )
                    st.write("")
                if st.button("View all projects →", key="admin_dash_view_projects",
                             use_container_width=True, on_click=_go_to, args=("📁 Projects",)):
                    st.rerun()

    st.divider()

    # ---- Overall System Overview — module completion across projects.
    # Pick a project to filter, or view all. Uses get_project_modules()
    # (real module-level data) rather than task-status counts.
    with st.container(border=True):
        st.subheader("Overall System Overview")
        st.caption("Module completion across projects — pick a project to filter, or view all.")

        project_choice_labels = ["All Projects"] + [p.get("name", "—") for p in projects]
        selected_project_label = st.selectbox(
            "📁 Filter by project", project_choice_labels,
            key="admin_overview_project_filter",
        )

        selected_projects = projects
        if selected_project_label != "All Projects":
            selected_projects = [
                p for p in projects if p.get("name") == selected_project_label
            ]

        module_items = []
        for project in selected_projects:
            resp = get_project_modules(token, str(project["id"]))
            if resp.status_code != 200:
                show_api_error(resp)
                continue
            for module in resp.json():
                module_items.append({**module, "project_name": project.get("name", "—")})

        if not module_items:
            st.info("No project modules yet for this selection.")
        else:
            completed_modules = [m for m in module_items if m.get("status") == "completed"]
            todo_modules = [m for m in module_items if m.get("status") != "completed"]
            complete_pct = round(100 * len(completed_modules) / len(module_items))

            list_col, ring_col = st.columns([2, 1])
            with list_col:
                st.markdown(f"**Completed · {len(completed_modules)}**")
                if completed_modules:
                    for module in completed_modules:
                        st.markdown(
                            "<span style='color:#6D28D9;'>●</span> "
                            f"{module.get('project_name')} · {module.get('name', '—')}",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No completed modules.")

                st.write("")
                st.markdown(f"**To Do · {len(todo_modules)}**")
                if todo_modules:
                    for module in todo_modules:
                        st.markdown(
                            "<span style='color:#9CA3AF;'>●</span> "
                            f"{module.get('project_name')} · {module.get('name', '—')}",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No modules left to complete.")
            with ring_col:
                st.plotly_chart(
                    _progress_ring(complete_pct, "#6D28D9"),
                    use_container_width=True, config={"displayModeBar": False},
                    key="admin_overall_module_ring",
                )
                st.caption(f"{len(completed_modules)} of {len(module_items)} modules complete")

    st.divider()

    # ---- Recent Activities — horizontally scrollable strip of the 4 most
    # ---- recent items, with a trailing arrow hinting at more content ----
    with st.container(border=True):
        st.subheader("Recent Activities")
        st.caption("Latest activity recorded across the platform.")

        activity_items = []
        for t in sorted(tasks, key=lambda t: str(t.get("created_at") or t.get("id") or ""),
                         reverse=True)[:3]:
            meta = STATUS_META.get(t.get("status") or "todo", STATUS_META["todo"])
            activity_items.append(("✅", f"Task **{t.get('title', '—')}**", meta["label"]))
        for d in sorted(documents, key=lambda d: str(d.get("created_at") or d.get("id") or ""),
                         reverse=True)[:2]:
            activity_items.append(("📄", f"Document **{d.get('filename', '—')}**", "Uploaded"))
        for p in sorted(projects, key=lambda p: str(p.get("created_at") or ""), reverse=True)[:1]:
            activity_items.append(("📁", f"Project **{p.get('name', '—')}**", "Created"))

        if not activity_items:
            st.caption("No recent activity yet.")
        else:
            shown_items = activity_items[:6]

            def _bold(text):
                # Convert the first "**...**" markdown-bold span to <b> for
                # raw-HTML rendering inside the scroll strip.
                return text.replace("**", "<b>", 1).replace("**", "</b>", 1)

            cards_html = "".join(
                "<div class='activity-card'>"
                f"<div style='font-size:1.3rem;'>{icon}</div>"
                f"<div style='color:#111827;font-size:0.9rem;margin-top:4px;'>{_bold(text)}</div>"
                f"<div style='color:#6B7280;font-size:0.78rem;margin-top:2px;'>{tag}</div>"
                "</div>"
                for icon, text, tag in shown_items
            )
            # Trailing arrow — a visual + functional cue that the strip
            # scrolls horizontally, only shown when there's more content
            # than what's currently displayed.
            arrow_html = (
                "<div class='activity-arrow' title='Scroll for more'>&#8594;</div>"
                if len(activity_items) > len(shown_items) else ""
            )

            st.markdown(
                "<style>"
                ".activity-scroll {"
                "    display:flex; gap:12px; overflow-x:auto; padding:4px 4px 10px 4px;"
                "    scroll-behavior:smooth;"
                "}"
                ".activity-card {"
                "    min-width:160px; flex:0 0 auto; background:#FFFFFF;"
                "    border:1px solid #E5E7EB; border-radius:10px; padding:12px;"
                "}"
                ".activity-arrow {"
                "    flex:0 0 auto; display:flex; align-items:center; justify-content:center;"
                "    width:40px; min-width:40px; border-radius:10px; background:#EEF2FF;"
                "    font-size:1.3rem; color:#4F46E5; font-weight:700;"
                "}"
                ".activity-scroll::-webkit-scrollbar { height:6px; }"
                ".activity-scroll::-webkit-scrollbar-thumb { background:#D8DCE5; border-radius:6px; }"
                "</style>"
                f"<div class='activity-scroll'>{cards_html}{arrow_html}</div>",
                unsafe_allow_html=True,
            )
        st.caption("Reflects the latest records returned by the API — add timestamps to your API for exact times.")

    st.write("")

    # ---- System Users | Documents — 2 columns, each independently
    # ---- scrollable -------------------------------------------------------
    users_col, docs_col = st.columns(2)

    non_admin_users = [u for u in users if (u.get("role") or "").lower() != "admin"]
    managers, employees = _split_staff(users)

    with users_col:
        with st.container(border=True):
            st.subheader("System Users")
            st.caption("Managers, employees, and clients — excluding admins.")

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Managers", len(managers))
            with m2:
                st.metric("Employees", len(employees))
            with m3:
                st.metric("Clients", len(clients))

            st.write("")
            with st.container(height=220):
                category_options = ["Managers", "Employees", "Clients"]
                selected_category = st.selectbox(
                    "🔎 Select category", category_options,
                    key="admin_dash_user_category",
                )

                if selected_category == "Managers":
                    category_records = managers
                elif selected_category == "Employees":
                    category_records = employees
                else:
                    category_records = clients

                st.write("")
                if not category_records:
                    st.caption(f"No {selected_category.lower()} yet.")
                else:
                    for record in category_records:
                        if selected_category == "Clients":
                            title_line = f"{record.get('company_name', '—')} — ID: {record.get('id', '—')}"
                            sub_line = f"{record.get('contact_name', '—')} · {record.get('email', '—')}"
                        else:
                            title_line = f"{record.get('name', '—')} — ID: {record.get('id', '—')}"
                            sub_line = f"{record.get('email', '—')}"
                        st.markdown(
                            "<div style='background:#FFFFFF; border:1px solid #E5E7EB; "
                            "border-radius:10px; padding:10px 12px; margin-bottom:8px;'>"
                            f"<div style='font-weight:600; color:#111827;'>{title_line}</div>"
                            f"<div style='font-size:0.82rem; color:#6B7280; margin-top:2px;'>{sub_line}</div>"
                            "</div>",
                            unsafe_allow_html=True,
                        )

    with docs_col:
        with st.container(border=True):
            st.subheader("Documents")
            st.caption("All uploaded files across projects.")
            with st.container(height=280):
                if not documents:
                    st.caption("No documents uploaded yet.")
                else:
                    for doc in documents:
                        st.markdown(
                            "<div style='background:#FFFFFF; border:1px solid #E5E7EB; "
                            "border-radius:10px; padding:10px 12px; margin-bottom:8px;'>"
                            f"<div style='font-weight:600; color:#111827;'>📄 {doc.get('filename', '—')}</div>"
                            "</div>",
                            unsafe_allow_html=True,
                        )


# --------------------------------------------------------------------------
# USERS & ROLES — moved off the dashboard so the role breakdown isn't
# shown twice (dashboard only shows the Total Users count card).
# --------------------------------------------------------------------------
def _render_admin_users_roles():
    token = session_token()
    st.title("👤 Users & Roles")
    st.caption("Breakdown of every non-admin user by role.")
    st.write("")

    users, users_ok = _fetch_users_safely(token)
    if not users_ok:
        return
    if not users:
        st.info("No users found.")
        return

    team_users = [u for u in users if (u.get("role") or "").lower() != "admin"]

    _inject_stat_card_hover_css()
    c1, c2 = st.columns(2)
    with c1:
        _stat_card("👤", "#EDE9FE", "Total Users", len(users), "Including admins", key="stat-card-users-0")
    with c2:
        _stat_card("🧑‍🤝‍🧑", "#DBEAFE", "Team Members", len(team_users), "Excluding admins", key="stat-card-users-1")

    st.write("")

    if not team_users:
        st.caption("No non-admin team members yet.")
        return

    with st.container(border=True):
        st.subheader("By Role")
        role_counts = {}
        for u in team_users:
            role_counts[u["role"]] = role_counts.get(u["role"], 0) + 1
        role_colors = ["#3B82F6", "#22C55E", "#F97316", "#EC4899", "#EAB308", "#8B5CF6"]

        for i, (role, count) in enumerate(sorted(role_counts.items(), key=lambda x: -x[1])):
            color = role_colors[i % len(role_colors)]
            row = st.columns([3, 1])
            with row[0]:
                st.markdown(f"**{role.title()}**")
                st.progress(count / len(team_users))
            with row[1]:
                st.write("")
                st.markdown(f"**{count}**")

        st.write("")
        role_options = sorted(role_counts.keys())
        selected_role = st.selectbox(
            "View names by role", role_options,
            format_func=lambda r: r.title(),
            key="admin_users_role_filter",
        )
        st.caption(f"**{selected_role.title()}** ({role_counts[selected_role]}):")
        for u in team_users:
            if (u.get("role") or "") == selected_role:
                st.markdown(f"- {u.get('name', '—')} · {u.get('email', '—')}")


# --------------------------------------------------------------------------
# CLIENTS — view, add, edit, delete
# --------------------------------------------------------------------------
def _render_admin_clients():
    token = session_token()

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

    _inject_stat_card_hover_css()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("🏢", "#EDE9FE", "Total Clients", len(clients), "All clients", key="stat-card-clients-0")
    with c2:
        _stat_card("🟢", "#DCFCE7", "Active", active_n, "Active clients", key="stat-card-clients-1")
    with c3:
        _stat_card("🟡", "#FEF9C3", "Pending", pending_n, "Pending clients", key="stat-card-clients-2")
    with c4:
        _stat_card("⚪", "#F3F4F6", "Inactive", inactive_n, "Inactive clients", key="stat-card-clients-3")

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
            colors = [_client_status_meta(s)["color"] for s in counts]

            chart_col, legend_col = st.columns([1.3, 1])
            with chart_col:
                st.plotly_chart(
                    _donut(labels, values, colors, str(len(clients)), "Total Clients"),
                    use_container_width=True, config={"displayModeBar": False},
                    key="admin_client_status_donut",
                )
            with legend_col:
                st.write("")
                for status, count in counts.items():
                    meta = _client_status_meta(status)
                    pct = round(100 * count / len(clients))
                    st.markdown(
                        f"**{status.title()}** &nbsp; **{pct}%** &nbsp; "
                        f"{_color_dot(meta['color'])}"
                        f"&nbsp; <span style='color:#9CA3AF !important;font-size:0.8rem;'>({count})</span>",
                        unsafe_allow_html=True,
                    )
                    st.write("")

            st.write("")
            client_choice_labels = ["All Clients"] + [c.get("company_name", "—") for c in clients]
            selected_overview_client = st.selectbox(
                "🏢 All Clients", client_choice_labels,
                key="admin_client_overview_filter",
            )

            if selected_overview_client == "All Clients":
                with st.container(height=220):
                    for c in clients:
                        cmeta = _client_status_meta(c.get("status"))
                        st.markdown(f"**{c.get('company_name', '—')}**")
                        st.markdown(
                            f"{_color_dot(cmeta['color'])}"
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
                        _pill(f"{ometa['icon']} {overview_client.get('status', '—')}", ometa["color"])
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
                key="admin_client_detail_select",
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
                    _pill(f"{meta['icon']} {selected_client_detail.get('status', '—')}", meta["color"])
                with d2:
                    st.caption("Contact")
                    st.markdown(f"**{selected_client_detail.get('contact_name', '—')}**")
                with d3:
                    st.caption("Email")
                    st.markdown(f"**{selected_client_detail.get('email', '—')}**")
                st.write("")
                st.caption(f"📞 {selected_client_detail.get('phone', '—')}")

    with st.expander("➕ Add client"):
        with st.form("admin_add_client_form", clear_on_submit=True):
            company_name = st.text_input("Company name")
            contact_name = st.text_input("Contact name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            status = st.selectbox("Status", CLIENT_STATUS_OPTIONS)

            show_password = st.checkbox("👁 Show password", key="admin_add_client_show_pw")
            client_password = st.text_input(
                "Client login password (optional)",
                type="default" if show_password else "password",
                key="admin_add_client_password",
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
                                           key="admin_edit_client_select")
            selected_client = client_options[selected_label]

            current_status = (selected_client.get("status") or "active").lower()
            meta = _client_status_meta(current_status)
            st.caption(f"Current status: {meta['icon']} {current_status.title()}")

            with st.form("admin_edit_client_form"):
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
                key="admin_delete_client_select",
            )
            selected_delete_client = delete_options[selected_delete_id]
            st.caption(f"This will permanently remove **{selected_delete_client.get('company_name', '—')}**.")

            confirm = st.checkbox("I confirm deletion", key="admin_delete_client_confirm")

            if st.button("Delete client", key="admin_delete_client_button",
                         type="primary", disabled=not confirm):
                resp = delete_client(token, selected_delete_id)
                if resp.status_code in {200, 204}:
                    st.success("Client deleted.")
                    st.rerun()
                else:
                    show_api_error(resp)


# --------------------------------------------------------------------------
# PROJECTS — create (with team), edit, assign/update team
# --------------------------------------------------------------------------
def _render_admin_projects():
    token = session_token()

    st.title("📁 Projects")
    st.caption("View, create, edit projects, and assign project teams.")
    st.write("")

    projects_resp = get_projects(token)
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)
        return
    projects = projects_resp.json()

    active_n = sum(1 for p in projects if (p.get("status") or "").lower() == "active")
    completed_n = sum(1 for p in projects if (p.get("status") or "").lower() == "completed")

    _inject_stat_card_hover_css()
    c1, c2, c3 = st.columns(3)
    with c1:
        _stat_card("📁", "#DBEAFE", "Total Projects", len(projects), "All projects", key="stat-card-projects-0")
    with c2:
        _stat_card("🟢", "#DCFCE7", "Active", active_n, "In progress", key="stat-card-projects-1")
    with c3:
        _stat_card("✅", "#EDE9FE", "Completed", completed_n, "Finished", key="stat-card-projects-2")

    st.write("")

    # ---- Recent Projects | All Projects — side by side (recent on the
    # ---- left, full table on the right), separated by a vertical rule --
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
                            rmeta = PROJECT_STATUS_META.get(
                                (p.get("status") or "").lower(),
                                {"label": p.get("status", "—"), "color": "#6B7280"},
                            )
                            row = st.columns([3, 1.3, 1.3])
                            with row[0]:
                                st.markdown(f"**{p.get('name', '—')}**")
                            with row[1]:
                                _pill(rmeta["label"], rmeta["color"])
                            with row[2]:
                                st.caption(f"📅 {p.get('deadline', '—')}")

        with all_col:
            with st.container(key="projects-all-col"):
                st.subheader("📋 All Projects")
                st.caption("Every project in your organization.")
                if not projects:
                    st.info("No projects yet.")
                else:
                    table_rows = [
                        {
                            "Name": p.get("name", "—"),
                            "Status": PROJECT_STATUS_META.get(
                                (p.get("status") or "").lower(), {}
                            ).get("label", p.get("status", "—")),
                            "Budget": p.get("budget", "—"),
                            "Deadline": p.get("deadline", "—"),
                        }
                        for p in projects
                    ]
                    st.dataframe(table_rows, use_container_width=True, hide_index=True)

        # Vertical divider between the two columns above (scoped to this
        # card only, via the "projects-all-col" container key).
        st.markdown(
            """
            <style>
            div[class*="st-key-projects-all-col"] {
                border-left: 1px solid #EEF0F3;
                padding-left: 1.25rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    with st.expander("🔎 Project Details", expanded=True):
        _render_project_detail_section(projects, token)

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

    with st.expander("➕ Create project"):
        with st.form("admin_create_project_form", clear_on_submit=True):
            client_name = st.selectbox(
                "Client",
                list(client_options.keys()) or ["(no clients)"],
                key="admin_create_project_client",
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
                    key="admin_create_project_managers",
                )
                selected_employees = st.multiselect(
                    "Employees (optional)", employees,
                    format_func=_user_option_label,
                    key="admin_create_project_employees",
                )
                st.caption("Tip: if you leave managers empty, all org managers are auto-assigned.")
            elif not users_ok:
                st.caption("Could not load users — org managers will still be auto-assigned.")

            if st.form_submit_button("Create project", type="primary"):
                if not client_options:
                    st.error("Create a client first, then create the project.")
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
            selected_label = st.selectbox("Select project to edit", list(project_options.keys()),
                                           key="admin_edit_project_select")
            selected_project = project_options[selected_label]

            with st.form("admin_edit_project_form"):
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
                key="admin_assign_team_project_select",
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
                key="admin_assign_team_multiselect",
            )

            if st.button("Save team members", key="admin_save_team_members", use_container_width=True):
                user_ids = [u.get("id") for u in selected_team]
                resp = assign_team(token, team_project["id"], user_ids)
                if resp.status_code in {200, 201, 204}:
                    st.success(f"Team updated for **{team_project_label}**.")
                    st.rerun()
                else:
                    show_api_error(resp)


# --------------------------------------------------------------------------
# TASKS — kanban board + create
# (Kept for reference / reuse; no longer wired into the sidebar nav.)
# --------------------------------------------------------------------------
def _render_admin_tasks():
    token = session_token()

    st.title("✅ Tasks")
    st.write("")

    projects_resp = get_projects(token)
    projects = projects_resp.json() if projects_resp.status_code == 200 else []

    tasks_resp = get_tasks(token)
    if tasks_resp.status_code != 200:
        show_api_error(tasks_resp)
        return
    tasks = tasks_resp.json()

    if not tasks:
        st.info("No tasks yet — create one below.")
    else:
        grouped = {k: [] for k in STATUS_META}
        for t in tasks:
            sk = t.get("status") or "todo"
            grouped[sk if sk in grouped else "todo"].append(t)

        status_keys = [k for k in STATUS_META if grouped[k]]
        cols = st.columns(len(status_keys) or 1)
        for col, key in zip(cols, status_keys):
            meta = STATUS_META[key]
            with col:
                st.markdown(f"**{meta['icon']} {meta['label']}** · {len(grouped[key])}")
                for t in grouped[key]:
                    with st.container(border=True):
                        st.markdown(f"**{t['title']}**")
                        if t.get("description"):
                            st.caption(t["description"])
                        if key != "done":
                            keys_order = list(STATUS_META.keys())
                            idx = keys_order.index(key)
                            next_key = keys_order[idx + 1] if idx + 1 < len(keys_order) else "done"
                            if st.button(f"Move to {STATUS_META[next_key]['label']} →",
                                         key=f"admin_move_{t['id']}", use_container_width=True):
                                resp = patch_task_status(token, str(t["id"]), {"status": next_key})
                                if resp.status_code == 200:
                                    st.success("Updated.")
                                    st.rerun()
                                else:
                                    show_api_error(resp)

    st.divider()
    with st.expander("➕ Create task"):
        users, users_ok = _fetch_users_safely(token)
        _, employees = _split_staff(users)
        assignee_options = [("Unassigned", None)] + [
            (_user_option_label(u), u.get("id")) for u in employees
        ]

        with st.form("admin_create_task_form", clear_on_submit=True):
            project_for_task = None
            if projects:
                proj_label = st.selectbox(
                    "Project",
                    [p["name"] for p in projects],
                    key="admin_create_task_project_select",
                )
                project_for_task = next(
                    (p.get("id") for p in projects if p["name"] == proj_label),
                    None,
                )
            else:
                st.caption("Create a project first so the task can be linked.")

            assignee_labels = [label for label, _ in assignee_options]
            assignee_label = st.selectbox(
                "Assign to (employee)",
                assignee_labels,
                key="admin_create_task_assignee",
            )
            if not users_ok:
                st.caption("Could not load employees for assignment.")

            title = st.text_input("Title")
            description = st.text_area("Description")
            status = st.selectbox(
                "Status",
                list(STATUS_META.keys()),
                format_func=lambda k: STATUS_META[k]["label"],
            )

            if st.form_submit_button("Create task", type="primary"):
                if not title.strip():
                    st.error("Title is required.")
                elif project_for_task is None:
                    st.error("Select a project for this task.")
                else:
                    assignee_id = dict(assignee_options).get(assignee_label)
                    payload = {
                        "title": title.strip(),
                        "description": description,
                        "status": status,
                        "project_id": project_for_task,
                        "assigned_to": assignee_id,
                    }
                    resp = create_task(token, payload)
                    if resp.status_code in {200, 201}:
                        st.success("Task created.")
                        st.rerun()
                    else:
                        show_api_error(resp)

    if tasks:
        with st.expander("✏️ Edit task"):
            task_options = {f"{t['title']} ({t['id']})": t for t in tasks}
            selected_label = st.selectbox("Select task to edit", list(task_options.keys()),
                                           key="admin_edit_task_select")
            selected_task = task_options[selected_label]

            users, users_ok = _fetch_users_safely(token)
            _, employees = _split_staff(users)
            assignee_options = [("Unassigned", None)] + [
                (_user_option_label(u), u.get("id")) for u in employees
            ]
            assignee_labels = [label for label, _ in assignee_options]
            current_assignee_id = selected_task.get("assigned_to")
            current_assignee_label = next(
                (label for label, uid in assignee_options if str(uid) == str(current_assignee_id)),
                "Unassigned",
            )

            with st.form("admin_edit_task_form"):
                title = st.text_input("Title", value=selected_task.get("title", ""))
                description = st.text_area("Description", value=selected_task.get("description", "") or "")
                current_status = selected_task.get("status") or "todo"
                status_keys = list(STATUS_META.keys())
                status = st.selectbox(
                    "Status", status_keys,
                    index=status_keys.index(current_status) if current_status in STATUS_META else 0,
                    format_func=lambda k: STATUS_META[k]["label"],
                )
                if not users_ok:
                    st.caption("Could not load employees for assignment.")
                assignee_label = st.selectbox(
                    "Assign to (employee)", assignee_labels,
                    index=assignee_labels.index(current_assignee_label)
                    if current_assignee_label in assignee_labels else 0,
                    key="admin_edit_task_assignee",
                )

                if st.form_submit_button("Update task", type="primary"):
                    if not title.strip():
                        st.error("Title is required.")
                    else:
                        assignee_id = dict(assignee_options).get(assignee_label)
                        payload = {
                            "title": title.strip(),
                            "description": description,
                            "status": status,
                            "assigned_to": assignee_id,
                        }
                        resp = update_task(token, str(selected_task["id"]), payload)
                        if resp.status_code == 200:
                            st.success("Task updated.")
                            st.rerun()
                        else:
                            show_api_error(resp)

    if tasks:
        with st.expander("🗑️ Delete task"):
            delete_options = {f"{t['title']} ({t['id']})": t for t in tasks}
            selected_delete_label = st.selectbox(
                "Select task to delete", list(delete_options.keys()),
                key="admin_delete_task_select",
            )
            selected_delete_task = delete_options[selected_delete_label]
            st.caption(f"This will permanently remove **{selected_delete_task.get('title', '—')}**.")

            confirm = st.checkbox("I confirm deletion", key="admin_delete_task_confirm")

            if st.button("Delete task", key="admin_delete_task_button",
                         type="primary", disabled=not confirm):
                resp = delete_task(token, str(selected_delete_task["id"]))
                if resp.status_code in {200, 204}:
                    st.success("Task deleted.")
                    st.rerun()
                else:
                    show_api_error(resp)

# --------------------------------------------------------------------------
# DOCUMENTS — upload, preview, download, delete
# --------------------------------------------------------------------------
def _render_admin_documents():
    token = session_token()

    st.title("📄 Documents")
    st.write("")

    projects_resp = get_projects(token)
    projects = projects_resp.json() if projects_resp.status_code == 200 else []

    with st.container(border=True):
        st.subheader("⬆️ Upload a document")
        if not projects:
            st.info("No projects available to upload into yet.")
        else:
            if "admin_doc_uploader_key" not in st.session_state:
                st.session_state["admin_doc_uploader_key"] = 0

            with st.form("admin_upload_document_form", clear_on_submit=True):
                project_names = [p["name"] for p in projects]
                upload_project_label = st.selectbox(
                    "Project", project_names, key="admin_upload_project_select",
                )
                uploaded_file = st.file_uploader(
                    "Choose a file", type=None,
                    key=f"admin_doc_uploader_{st.session_state['admin_doc_uploader_key']}",
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
                            st.session_state["admin_doc_uploader_key"] += 1
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

    docs_resp = list_documents(token)
    if docs_resp.status_code != 200:
        show_api_error(docs_resp)
        return
    documents = docs_resp.json()

    if not documents:
        st.info("No documents uploaded yet.")
        return

    with st.container(border=True):
        st.subheader("All Documents")
        st.caption("Upload PDF/DOCX/PPTX/TXT to enable chat RAG. Files are indexed on upload.")

        doc_filter_options = ["All Documents"] + [p.get("name", "—") for p in projects]
        selected_doc_filter = st.selectbox(
            "📁 Filter by project", doc_filter_options,
            key="admin_documents_project_filter",
        )

        if selected_doc_filter == "All Documents":
            filtered_documents = documents
        else:
            filter_project = next(
                (p for p in projects if p.get("name") == selected_doc_filter), None
            )
            filtered_documents = [
                d for d in documents if str(d.get("project_id")) == str(filter_project.get("id"))
            ] if filter_project else []

        if not filtered_documents:
            st.info("No documents for this selection.")
        for doc in filtered_documents:
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
                        key=f"admin_dl_{doc['id']}", use_container_width=True,
                    )
                else:
                    show_api_error(resp)
            with row[2]:
                if st.button("Preview", key=f"admin_view_{doc['id']}", use_container_width=True):
                    show_document_preview(token, doc)
            with row[3]:
                if st.button("Delete", key=f"admin_del_{doc['id']}", use_container_width=True):
                    delete_resp = delete_document(token, str(doc["id"]))
                    if delete_resp.status_code == 204:
                        st.success("Document deleted.")
                        st.rerun()
                    else:
                        show_api_error(delete_resp)
            st.divider()


# --------------------------------------------------------------------------
# MEETINGS — read-only meeting summaries across every project (admin view)
# --------------------------------------------------------------------------
def _render_admin_weekly_reports():
    """Generate and view reports without requiring any file uploads."""
    st.title("📊 Weekly Reports")
    st.caption("Generate and review AI-powered weekly progress reports for any project.")
    token = session_token()
    projects_resp = get_projects(token)
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)
        return
    projects = projects_resp.json()
    if not projects:
        st.info("No projects found. Create a project first.")
        return
    project_by_name = {project["name"]: project for project in projects}
    selected_name = st.selectbox("Project", list(project_by_name), key="admin_weekly_report_project")
    project_id = str(project_by_name[selected_name]["id"])
    if st.button("Generate Weekly Report", key="admin_generate_weekly_report", type="primary"):
        with st.spinner("Generating report..."):
            response = generate_weekly_report(token, project_id)
        if response.status_code in {200, 201}:
            st.success("Report generated successfully.")
            st.markdown(response.json().get("report_text", "—"))
        else:
            show_api_error(response)
    st.subheader("Past Reports")
    response = get_weekly_reports(token, project_id)
    if response.status_code != 200:
        show_api_error(response)
        return
    reports = response.json()
    if not reports:
        st.info("No reports yet for this project.")
    for report in reports:
        created = report.get("created_at", "")[:16].replace("T", " ")
        with st.expander(f"Report — {created}"):
            st.markdown(report.get("report_text", "—"))


# --------------------------------------------------------------------------
# REQUIREMENT ANALYZER — Analyze (creates draft) + Review Drafts (assign
# Module/Employee/Priority/Deadline per story, approve one at a time)
# --------------------------------------------------------------------------

def _req_analyzer_priority_options():
    return ["low", "medium", "high"]


def _inject_requirement_analyzer_css():
    """Page-scoped polish for the Requirement Analyzer — matches the
    admin violet theme (#4F46E5) already used app-wide."""
    st.markdown(
        """
        <style>
        /* Segmented pill toggle (Analyze / Review Drafts) */
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] > div {
            background: #F3F4F6 !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 999px !important;
            padding: 4px !important;
            gap: 4px !important;
            box-shadow: inset 0 1px 2px rgba(16,24,40,0.04);
        }
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] label {
            border-radius: 999px !important;
            border: none !important;
            padding: 8px 18px !important;
            font-weight: 600 !important;
            color: #6B7280 !important;
            background: transparent !important;
            transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
        }
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] label:hover {
            background: #FFFFFF !important;
            color: #4338CA !important;
        }
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] label[data-checked="true"],
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] label:has(input:checked) {
            background: #4F46E5 !important;
            color: #FFFFFF !important;
            box-shadow: 0 1px 3px rgba(79,70,229,0.35);
        }
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] label[data-checked="true"] *,
        .st-key-admin_req_analyzer_view [data-testid="stSegmentedControl"] label:has(input:checked) * {
            color: #FFFFFF !important;
        }

        /* Section / story cards on this page */
        .st-key-admin_req_page_root div[data-testid="stVerticalBlockBorderWrapper"] {
            background: #FFFFFF !important;
            border: 1px solid #EEF0F3 !important;
            border-radius: 14px !important;
            box-shadow: 0 1px 3px rgba(16,24,40,0.06), 0 1px 2px rgba(16,24,40,0.04) !important;
            padding: 0.55rem 0.65rem !important;
        }

        /* Typography helpers used only on this page */
        .req-page-subtitle {
            color: #6B7280 !important;
            font-size: 0.95rem;
            line-height: 1.45;
            margin: 0 0 1rem 0;
        }
        .req-section-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: #111827 !important;
            margin: 0 0 0.25rem 0;
        }
        .req-muted {
            color: #6B7280 !important;
            font-size: 0.85rem;
        }
        .req-epic-title {
            font-size: 1rem;
            font-weight: 700;
            color: #312E81 !important;
            margin: 1rem 0 0.5rem 0;
            padding-bottom: 0.35rem;
            border-bottom: 1px solid #EEF2FF;
        }
        .req-story-title {
            font-size: 0.98rem;
            font-weight: 650;
            color: #111827 !important;
            margin-bottom: 0.15rem;
        }
        .req-draft-meta {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            color: #6B7280;
            font-size: 0.82rem;
            margin-top: 0.25rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_requirement_analyzer_analyze_tab(projects, token):
    """Step 1: pick a doc, run AI analysis -> saves as pending_review DRAFT only.
    Nothing appears anywhere else until it's approved in Review Drafts."""
    with st.container(border=True):
        st.markdown("<div class='req-section-title'>Analyze a requirement document</div>", unsafe_allow_html=True)

        if not projects:
            st.info("No projects found. Create a project and upload a requirement document first.")
            return

        project_labels = [p["name"] for p in projects]
        project_label = st.selectbox("Project", project_labels, key="admin_req_project_select")
        selected_project = next((p for p in projects if p["name"] == project_label), None)
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
            "Requirement document", list(doc_labels.keys()), key="admin_req_doc_select"
        )
        selected_doc = doc_labels[doc_label]
        document_id = str(selected_doc["id"])

        st.write("")
        if st.button("Analyze document", key="admin_req_analyze", type="primary"):
            with st.spinner("Analyzing requirement document with AI..."):
                resp = analyze_requirement(token, document_id, project_id)
            if resp.status_code in {200, 201}:
                data = resp.json()
                st.session_state[REQ_ANALYZER_TAB_KEY] = REQ_ANALYZER_TAB_REVIEW
                st.session_state["admin_reqdraft_selected_id"] = str(data["id"])
                st.success(
                    f"Draft ready (id: {data['id']}). Assign a Module and Employee, "
                    "then approve stories into real tasks."
                )
                st.rerun()
            else:
                show_api_error(resp)


def _render_review_drafts_list(projects, token):
    """List all pending_review draft analyses. Admin clicks one to open it."""
    with st.container(border=True):
        st.markdown("<div class='req-section-title'>Pending drafts</div>", unsafe_allow_html=True)

        project_names = [p["name"] for p in projects]
        filter_label = st.selectbox(
            "Filter by project",
            [ALL_PROJECTS_LABEL] + project_names,
            key="admin_reqdraft_project_filter",
        )
        filter_project_id = None
        if filter_label != ALL_PROJECTS_LABEL:
            matching = next((p for p in projects if p["name"] == filter_label), None)
            filter_project_id = str(matching["id"]) if matching else None

    resp = list_requirement_analyses(
        token, status="pending_review", project_id=filter_project_id
    )
    if resp.status_code != 200:
        show_api_error(resp)
        return
    drafts = resp.json()

    st.write("")
    if not drafts:
        st.info("No pending drafts. Run an analysis from the Analyze Document view.")
        return

    for d in drafts:
        with st.container(border=True):
            row = st.columns([3.2, 1.2, 1.2, 1.3, 1])
            with row[0]:
                st.markdown(
                    f"<div class='req-story-title'>{html.escape(str(d.get('document_filename') or 'Untitled document'))}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<span class='req-muted'>{html.escape(str(d.get('project_name') or 'No project'))}</span>",
                    unsafe_allow_html=True,
                )
            with row[1]:
                st.markdown(
                    f"<span class='req-muted'>📦 {d.get('epic_count', 0)} epics</span>",
                    unsafe_allow_html=True,
                )
            with row[2]:
                st.markdown(
                    f"<span class='req-muted'>📝 {d.get('story_count', 0)} stories</span>",
                    unsafe_allow_html=True,
                )
            with row[3]:
                pending_n = d.get("pending_story_count", 0)
                if pending_n:
                    st.markdown(
                        _pill_html(f"{pending_n} pending", "pill-orange"),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        _pill_html("all created", "pill-green"),
                        unsafe_allow_html=True,
                    )
            with row[4]:
                if st.button(
                    "Open",
                    key=f"admin_reqdraft_open_{d['id']}",
                    width="stretch",
                ):
                    st.session_state["admin_reqdraft_selected_id"] = str(d["id"])
                    st.rerun()


def _render_review_draft_detail(token, analysis_id):
    """Open one draft: assign Module + Employee + Priority + Deadline per
    story, then 'Approve & Create Task' calls the EXISTING create_task path
    (via approve-story) for that one story only."""
    resp = get_requirement_analysis(token, analysis_id)
    if resp.status_code != 200:
        show_api_error(resp)
        if st.button("Back to Review Drafts", key="admin_reqdraft_back_err"):
            st.session_state["admin_reqdraft_selected_id"] = None
            st.rerun()
        return
    analysis = resp.json()

    with st.container(border=True):
        top_l, top_r = st.columns([4, 1])
        with top_l:
            st.markdown(
                f"<div class='req-section-title'>{html.escape(str(analysis.get('document_filename') or 'Draft'))}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<span class='req-muted'>Project: {html.escape(str(analysis.get('project_name') or '—'))} · "
                f"Status: {html.escape(str(analysis.get('status') or '—'))}</span>",
                unsafe_allow_html=True,
            )
        with top_r:
            if st.button("Back", key="admin_reqdraft_back", width="stretch"):
                st.session_state["admin_reqdraft_selected_id"] = None
                st.rerun()

    if analysis.get("status") == "rejected":
        st.info("This draft was rejected. No tasks were created.")
        return

    project_id = analysis.get("project_id")
    if not project_id:
        st.error("This draft has no linked project, so tasks can't be created from it.")
        return
    project_id = str(project_id)

    # Existing modules for this project only — no separate module system.
    modules = _get_project_modules(token, project_id)
    module_options = [(f"{m.get('icon', '🧩')} {m['name']}", str(m["id"])) for m in modules]

    st.write("")
    with st.expander("Create a new module for this project", expanded=False):
        with st.form(f"admin_reqdraft_new_module_{analysis_id}", clear_on_submit=True):
            nm_col1, nm_col2 = st.columns([3, 1.4])
            with nm_col1:
                new_mod_name = st.text_input(
                    "Module name", placeholder="e.g. Authentication"
                )
            with nm_col2:
                new_mod_icon = st.selectbox(
                    "Icon",
                    MODULE_ICON_OPTIONS,
                    key=f"admin_reqdraft_mod_icon_{analysis_id}",
                )
            new_mod_description = st.text_area(
                "Description",
                placeholder="Brief description of this module",
                height=90,
                key=f"admin_reqdraft_mod_desc_{analysis_id}",
            )
            if st.form_submit_button("Add module", type="primary"):
                if not new_mod_name.strip():
                    st.error("Module name is required.")
                else:
                    create_resp = create_project_module(
                        token,
                        project_id,
                        {
                            "name": new_mod_name.strip(),
                            "icon": new_mod_icon,
                            "status": "locked",
                            "description": new_mod_description.strip() or None,
                        },
                    )
                    if create_resp.status_code == 201:
                        st.success(f"Module '{new_mod_name.strip()}' created.")
                        st.rerun()
                    else:
                        show_api_error(create_resp)

    users, _users_ok = _fetch_users_safely(token)
    managers, employees = _split_staff(users)
    assignable = managers + employees
    employee_options = [(_user_option_label(u), str(u.get("id"))) for u in assignable]

    if not module_options:
        st.warning("This project has no modules yet — add one above before approving stories.")
    if not employee_options:
        st.warning("No assignable users found — an employee is required before approving stories.")

    epics = (analysis.get("parsed") or {}).get("epics", [])

    st.write("")
    st.markdown("<div class='req-section-title'>Review & assign</div>", unsafe_allow_html=True)
    st.markdown(
        "<p class='req-muted'>Assign a module, employee, priority, and deadline for each story, "
        "then approve one at a time.</p>",
        unsafe_allow_html=True,
    )

    for ei, epic in enumerate(epics):
        st.markdown(
            f"<div class='req-epic-title'>Epic: {html.escape(str(epic.get('title') or '—'))}</div>",
            unsafe_allow_html=True,
        )
        for si, story in enumerate(epic.get("stories", [])):
            created_task_id = story.get("created_task_id")
            with st.container(border=True):
                st.markdown(
                    f"<div class='req-story-title'>{html.escape(str(story.get('title') or '—'))}</div>",
                    unsafe_allow_html=True,
                )
                if story.get("description"):
                    st.markdown(
                        f"<span class='req-muted'>{html.escape(str(story.get('description')))}</span>",
                        unsafe_allow_html=True,
                    )

                if created_task_id:
                    st.write("")
                    st.markdown(
                        _pill_html("Task created", "pill-green"),
                        unsafe_allow_html=True,
                    )
                    continue

                st.write("")
                f1, f2, f3, f4 = st.columns([1.6, 1.6, 1, 1.2])
                with f1:
                    if module_options:
                        module_label = st.selectbox(
                            "Module",
                            [label for label, _ in module_options],
                            key=f"admin_reqdraft_mod_{analysis_id}_{ei}_{si}",
                        )
                        module_id = dict(module_options).get(module_label)
                    else:
                        st.selectbox(
                            "Module",
                            ["(none available)"],
                            key=f"admin_reqdraft_mod_disabled_{analysis_id}_{ei}_{si}",
                            disabled=True,
                        )
                        module_id = None
                with f2:
                    if employee_options:
                        employee_label = st.selectbox(
                            "Employee",
                            [label for label, _ in employee_options],
                            key=f"admin_reqdraft_emp_{analysis_id}_{ei}_{si}",
                        )
                        assigned_to = dict(employee_options).get(employee_label)
                    else:
                        st.selectbox(
                            "Employee",
                            ["(none available)"],
                            key=f"admin_reqdraft_emp_disabled_{analysis_id}_{ei}_{si}",
                            disabled=True,
                        )
                        assigned_to = None
                with f3:
                    default_priority = story.get("priority", "medium")
                    priority_choices = _req_analyzer_priority_options()
                    priority = st.selectbox(
                        "Priority",
                        priority_choices,
                        index=(
                            priority_choices.index(default_priority)
                            if default_priority in priority_choices
                            else 1
                        ),
                        key=f"admin_reqdraft_pri_{analysis_id}_{ei}_{si}",
                    )
                with f4:
                    deadline = st.date_input(
                        "Deadline",
                        value=None,
                        key=f"admin_reqdraft_deadline_{analysis_id}_{ei}_{si}",
                    )

                st.write("")
                can_approve = bool(module_id and assigned_to)
                if st.button(
                    "Approve & create task",
                    key=f"admin_reqdraft_approve_{analysis_id}_{ei}_{si}",
                    type="primary",
                    disabled=not can_approve,
                ):
                    approve_resp = approve_requirement_story(
                        token,
                        analysis_id,
                        epic_index=ei,
                        story_index=si,
                        priority=priority,
                        module_id=module_id,
                        assigned_to=assigned_to,
                        deadline=deadline.isoformat() if deadline else None,
                    )
                    if approve_resp.status_code in {200, 201}:
                        st.success("Task created.")
                        st.rerun()
                    else:
                        show_api_error(approve_resp)
                if not can_approve:
                    st.caption("Select a Module and an Employee to enable approval.")

    st.write("")
    with st.container(border=True):
        st.markdown(
            "<div class='req-section-title'>Danger zone</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p class='req-muted'>Rejecting discards every remaining unapproved story in this draft. "
            "Already-created tasks are not deleted.</p>",
            unsafe_allow_html=True,
        )
        if st.button("Reject entire draft", key=f"admin_reqdraft_reject_{analysis_id}"):
            reject_resp = reject_requirement_analysis(token, analysis_id)
            if reject_resp.status_code in {200, 204}:
                st.info("Draft rejected. No further tasks will be created from it.")
                st.session_state["admin_reqdraft_selected_id"] = None
                st.rerun()
            else:
                show_api_error(reject_resp)


def _render_requirement_analyzer(projects, token):
    """Main Requirement Analyzer page with Analyze and Review Drafts tabs."""
    _inject_requirement_analyzer_css()

    with st.container(key="admin_req_page_root"):
        st.title("🧠 Requirement Analyzer")
        st.markdown(
            "<p class='req-page-subtitle'>Turn uploaded requirement documents into reviewable "
            "drafts, then assign modules and employees before creating real tasks.</p>",
            unsafe_allow_html=True,
        )

        if REQ_ANALYZER_TAB_KEY not in st.session_state:
            st.session_state[REQ_ANALYZER_TAB_KEY] = REQ_ANALYZER_TAB_ANALYZE

        active_view = st.segmented_control(
            "Requirement Analyzer view",
            options=[REQ_ANALYZER_TAB_ANALYZE, REQ_ANALYZER_TAB_REVIEW],
            key=REQ_ANALYZER_TAB_KEY,
            label_visibility="collapsed",
            required=True,
            width="content",
        )

        st.write("")

        if active_view == REQ_ANALYZER_TAB_REVIEW:
            selected_id = st.session_state.get("admin_reqdraft_selected_id")
            if selected_id:
                _render_review_draft_detail(token, selected_id)
            else:
                _render_review_drafts_list(projects, token)
        else:
            # Leaving the detail view when switching tabs keeps state clean.
            if st.session_state.get("admin_reqdraft_selected_id"):
                st.session_state["admin_reqdraft_selected_id"] = None
            _render_requirement_analyzer_analyze_tab(projects, token)


def _render_admin_requirement_analyzer():
    """Render the Requirement Analyzer page — Analyze documents or review pending drafts."""
    token = session_token()
    projects_resp = get_projects(token)
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)
        return
    projects = projects_resp.json()
    if not projects:
        st.info("No projects found. Create a project and upload a requirement document first.")
        return
    _render_requirement_analyzer(projects, token)


def _render_admin_meetings():
    st.title("🎙️ Meeting Summaries")
    st.caption("Read-only view across every project in your organization.")
    token = session_token()

    projects_resp = get_projects(token)
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)
        return
    projects = projects_resp.json()

    render_meeting_panel(token=token, projects=projects, allow_upload=False, key_prefix="admin")


# --------------------------------------------------------------------------
# PLACEHOLDER — sidebar items shown in the reference design but not yet
# wired to any endpoint in this codebase. Honest placeholder, no fake data.
# --------------------------------------------------------------------------
def _render_coming_soon(page_label):
    label = page_label.split(" ", 1)[1] if " " in page_label else page_label
    st.title(page_label)
    st.info(f"**{label}** isn't wired up to your API yet — add the corresponding "
            f"endpoint(s) in `api_client.py` and this page can be built out.")


# --------------------------------------------------------------------------
# APP ENTRY
# --------------------------------------------------------------------------
def render_admin_app():
    _inject_light_theme()

    # This view can be reached directly during development, bypassing the
    # session check in app.py.  Do not make protected API calls unless the
    # login flow has stored the JWT first; otherwise every dashboard request
    # is sent without an Authorization header and returns 401.
    token = session_token()
    user = session_user()
    if not token or not user:
        st.error("Your session expired. Please log in again.")
        if st.button("Back to login", key="admin_back_to_login"):
            st.session_state.clear()
            st.rerun()
        return

    if st.session_state.get(NAV_RADIO_KEY) not in NAV_PAGES:
        st.session_state[NAV_RADIO_KEY] = NAV_PAGES[0]

    with st.sidebar:
        render_sidebar_header()
        st.caption("MANAGEMENT")
        page = st.radio(
            "Go to",
            NAV_PAGES,
            label_visibility="collapsed",
            key=NAV_RADIO_KEY,
        )

    if page == "🏠 Dashboard":
        _render_admin_dashboard()
    elif page == "🏢 Clients":
        _render_admin_clients()
    elif page == "📁 Projects":
        _render_admin_projects()
    elif page == "📄 Documents":
        _render_admin_documents()
    elif page == "🎙️ Meetings":
        _render_admin_meetings()
    elif page == "📊 Weekly Reports":
        _render_admin_weekly_reports()
    elif page == "🧠 Requirement Analyzer":
        _render_admin_requirement_analyzer()