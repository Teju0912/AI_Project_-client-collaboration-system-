"""
employee.py
Employee interface: Dashboard, My Tasks (status workflow for own tasks),
My Projects (read-only), and Documents (view/download/preview + upload to
assigned projects).

Design system matches admin.py exactly: same _inject_light_theme() CSS
(flat white cards, soft border + shadow, violet accents), same _stat_card
helper for summary boxes, and the same emoji-prefixed sidebar nav style.

PERMISSIONS: employees cannot create/edit/delete projects or assign tasks.
They can advance status on tasks assigned to them. Documents can be viewed,
downloaded, previewed, and uploaded to projects they belong to (no delete).

DATA POLICY: every number, chart, and list is computed from live API
responses (FastAPI → Postgres) — nothing is fabricated.
"""

import datetime as dt

import streamlit as st
import plotly.graph_objects as go

from api_client import (
    get_tasks,
    list_documents,
    get_projects,
    get_team,
    download_document,
    patch_task_status,
    upload_document,
)
from views.shared import (
    render_sidebar_header,
    show_api_error,
    show_document_preview,
    session_token,
    session_user,
    rag_status_label,
)

STATUS_META = {
    "todo":        {"label": "To Do",       "icon": "⚪", "color": "#8B5CF6"},
    "in_progress": {"label": "In Progress", "icon": "🔵", "color": "#3B82F6"},
    "testing":     {"label": "Testing",     "icon": "🟠", "color": "#F59E0B"},
    "done":        {"label": "Done",        "icon": "🟢", "color": "#22C55E"},
}
PROJECT_STATUS_META = {
    "planning":  {"label": "Planning",  "color": "#8B5CF6"},
    "active":    {"label": "Active",    "color": "#22C55E"},
    "completed": {"label": "Completed", "color": "#3B82F6"},
    "on_hold":   {"label": "On Hold",   "color": "#F59E0B"},
}

ALL_PROJECTS_LABEL = "All My Projects"
ACTIVE_PROJECT_KEY = "employee_active_project_id"
# NOTE: one shared widget key used by Dashboard/My Tasks/Documents so the
# project filter stays in sync no matter which page set it last.
PROJECT_WIDGET_KEY = "employee_project_dropdown_shared"
# Separate key just for the My Projects tab's single-project dropdown so it
# doesn't interfere with the shared "All Projects" filter used elsewhere.
MY_PROJECTS_WIDGET_KEY = "employee_myprojects_dropdown"

# Sidebar nav — emoji-prefixed labels, same convention as admin.py's
# NAV_PAGES. The radio widget key is fixed so page selection can be
# programmatically set (e.g. from a "View all" button) the same way
# admin.py's _go_to() does, if that's ever wired up here too.
NAV_PAGES = ["🏠 Dashboard", "✅ My Tasks", "📁 My Projects", "📄 Documents"]
NAV_RADIO_KEY = "employee_nav_radio"


# --------------------------------------------------------------------------
# LIGHT THEME — brand/component CSS on top of Streamlit's light base
# (.streamlit/config.toml). Cards, sidebar nav, popovers, uploaders, and
# inputs stay explicitly light with dark readable text.
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
        "/* Forms and uploader panels: never inherit a dark browser surface. */",
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
        ".completion-vdivider {",
        "    width: 1px; height: 100%; min-height: 220px;",
        "    background-color: #EEF0F3; margin: 0 auto;",
        "}",
        ".completion-hdivider {",
        "    border: none; border-top: 1px solid #EEF0F3; margin: 0.75rem 0;",
        "}",
        "",
        "div[data-testid='stExpander'] {",
        "    border: 1px solid #EEF0F3 !important;",
        "    border-radius: 14px !important;",
        "    background-color: #FFFFFF !important;",
        "}",
        "hr { border-color: #EEF0F3 !important; }",
        "",
        "div[data-testid='stPopover'] button {",
        "    background-color: #FFFFFF !important; color: #374151 !important;",
        "    border: 1px solid #E5E7EB !important;",
        "}",
        "div[data-baseweb='popover'] { z-index: 999999 !important; }",
        "div[data-testid='stPopoverBody'], div[data-baseweb='popover'] > div {",
        "    background-color: #FFFFFF !important;",
        "    border: 1px solid #E5E7EB !important;",
        "    border-radius: 10px !important;",
        "    box-shadow: 0 8px 24px rgba(16,24,40,0.14) !important;",
        "}",
        "div[data-testid='stPopoverBody'] * { color: #111827 !important; }",
        "",
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
# Shared visual helpers — copied 1:1 from admin.py so both roles render
# identically-styled cards, badges, and pills.
# --------------------------------------------------------------------------
def _icon_badge(icon, bg):
    st.markdown(f"<div class='icon-badge' style='background:{bg};'>{icon}</div>", unsafe_allow_html=True)


def _color_dot(color, size=10):
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
    """Flat white stat card: icon badge, label, big value, small caption.
    Identical sizing/spacing to admin.py's _stat_card — this is what
    keeps the Dashboard boxes the same size as the admin dashboard's."""
    with st.container(border=True, key=key):
        _icon_badge(icon, bg)
        st.markdown(f"<div style='color:#6B7280; font-size:0.82rem;'>{label}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:1.6rem; font-weight:700; color:#111827;'>{value}</div>",
                    unsafe_allow_html=True)
        st.caption(sublabel)


def _inject_stat_card_hover_css():
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


def _initials(text, max_letters=2):
    parts = [p for p in (text or "").replace("_", " ").split() if p]
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


def _safe_json_list(response):
    """Parse a successful list response; show errors and return []."""
    if response is None:
        return []
    if response.status_code != 200:
        show_api_error(response)
        return []
    try:
        data = response.json()
    except Exception:
        st.error("Could not parse API response. Is the backend running?")
        return []
    return data if isinstance(data, list) else []


def _ring(pct, color, height=170):
    fig = go.Figure(data=[go.Pie(
        values=[pct, 100 - pct], hole=0.72,
        marker=dict(colors=[color, "#F1F5F9"]),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(text=f"<b style='font-size:16px;color:#111827'>{pct}%</b>",
                           x=0.5, y=0.5, showarrow=False)],
    )
    return fig


def _vertical_divider():
    """Static vertical line used to visually split a box into two boxes."""
    st.markdown('<div class="completion-vdivider"></div>', unsafe_allow_html=True)


def _horizontal_divider():
    """Static horizontal line separating the phase legend from the
    graph/list section below it."""
    st.markdown('<hr class="completion-hdivider">', unsafe_allow_html=True)


def _project_name_map(projects):
    return {str(p["id"]): p.get("name", "—") for p in projects}


def _project_task_progress(project_id, tasks):
    linked = [t for t in tasks if str(t.get("project_id")) == str(project_id)]
    if not linked:
        return None, 0, 0
    done = sum(1 for t in linked if (t.get("status") or "") == "done")
    return round(100 * done / len(linked)), done, len(linked)


def _choose_active_project(projects):
    """Project dropdown scoped to the employee's own projects, including an
    'All My Projects' option. Returns (project_id or None for all, label).

    Uses ONE shared widget key (PROJECT_WIDGET_KEY) across Dashboard/My
    Tasks/Documents so the selection made on one page is reflected on the
    others.
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

    default_index = 0
    if current is not None:
        default_index = labels.index(name_by_id[str(current)])

    selected = st.selectbox(
        "📁 Project",
        labels,
        index=default_index,
        key=PROJECT_WIDGET_KEY,
        help="Tasks and documents update for the selected project.",
    )

    if selected == ALL_PROJECTS_LABEL:
        st.session_state[ACTIVE_PROJECT_KEY] = None
        return None, ALL_PROJECTS_LABEL

    project_id = id_by_name[selected]
    st.session_state[ACTIVE_PROJECT_KEY] = project_id
    return project_id, selected


def _load_scoped_data(token, active_project_id):
    """Fetch tasks/docs filtered by the chosen project from the backend/DB."""
    tasks_resp = get_tasks(token, project_id=active_project_id)
    docs_resp = list_documents(token, project_id=active_project_id)
    return tasks_resp, docs_resp


def _task_due_days(task):
    """Best-effort due-date lookup for a task. Different backends may name
    this field differently — try the common ones, degrade to None if absent."""
    for key in ("due_date", "deadline", "due"):
        if task.get(key):
            days = _days_left(task[key])
            if days is not None:
                return days
    return None


def _build_notifications(all_tasks, all_projects):
    """Build a real notification list from live task/project data — overdue
    tasks, tasks due soon, and projects whose deadline has passed. No
    fabricated data, no extra API calls (reuses whatever was fetched)."""
    notifications = []

    for t in all_tasks:
        if (t.get("status") or "") == "done":
            continue
        days = _task_due_days(t)
        if days is None:
            continue
        if days < 0:
            notifications.append(
                ("🔴", f"**{t.get('title', '—')}** is overdue by {abs(days)}d", days)
            )
        elif days <= 3:
            notifications.append(
                ("🟠", f"**{t.get('title', '—')}** is due in {days}d", days)
            )

    for p in all_projects:
        days = _days_left(p.get("deadline"))
        if days is not None and days < 0:
            notifications.append(
                ("🔴", f"Project **{p.get('name', '—')}** deadline passed ({abs(days)}d ago)", days)
            )

    notifications.sort(key=lambda n: n[2])
    return notifications


def _render_notification_bell(token):
    """Bell button + dropdown at the top of the app. Pulls the employee's
    full (unscoped) task and project list so the bell always reflects
    everything, regardless of which project filter is active elsewhere."""
    all_tasks = _safe_json_list(get_tasks(token))
    all_projects = _safe_json_list(get_projects(token))
    notifications = _build_notifications(all_tasks, all_projects)
    count = len(notifications)

    label = f"🔔 {count}" if count else "🔔"
    with st.popover(label, use_container_width=True):
        st.markdown("**Notifications**")
        if not notifications:
            st.caption("You're all caught up. 🎉")
        else:
            for icon, text, _ in notifications:
                st.markdown(f"{icon} {text}")
                st.divider()


# --------------------------------------------------------------------------
# DASHBOARD
# --------------------------------------------------------------------------
def _render_employee_dashboard(projects, token):
    user = session_user() or {}
    first_name = (user.get("name") or "there").split()[0]

    hour = dt.datetime.now().hour
    salutation = "Good Morning" if hour < 12 else ("Good Afternoon" if hour < 18 else "Good Evening")
    header_col, bell_col, avatar_col = st.columns([5, 1, 1])
    with header_col:
        st.title(f"👋 {salutation}, {first_name}!")
        st.caption("Here's an overview of your work today.")
    with bell_col:
        st.write("")
        _render_notification_bell(token)
    with avatar_col:
        st.write("")
        st.badge(_initials(user.get("name", "?")), color="violet")

    st.write("")

    if not projects:
        st.info(
            "You haven't been added to a project yet. Once your manager "
            "assigns you to one, your tasks and documents will show up here."
        )
        return

    active_project_id, project_label = _choose_active_project(projects)
    st.caption(f"Showing data for: **{project_label}**")

    tasks_resp, docs_resp = _load_scoped_data(token, active_project_id)
    tasks = _safe_json_list(tasks_resp)
    # documents intentionally not shown on this page in the new design
    # (the Documents tab already covers this) — response is still fetched
    # via _load_scoped_data so that shared helper stays untouched.

    scoped_projects = (
        projects if active_project_id is None
        else [p for p in projects if str(p.get("id")) == str(active_project_id)]
    )

    done_n = sum(1 for t in tasks if (t.get("status") or "") == "done")
    pending_n = len(tasks) - done_n
    total_n = len(tasks) or 1
    completion_pct = round(100 * done_n / total_n)
    overdue_n = sum(
        1 for t in tasks
        if (t.get("status") or "") != "done"
        and _task_due_days(t) is not None
        and _task_due_days(t) < 0
    )

    st.write("")

    # ---- Stat cards row: Total Tasks / Completed / Pending / Overdue ----
    # Same _stat_card used across every page in admin.py — same box size,
    # same icon-badge + label + value + caption layout.
    _inject_stat_card_hover_css()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("📋", "#EDE9FE", "Total Tasks", len(tasks), "All assigned tasks", key="stat-card-emp-dash-0")
    with c2:
        _stat_card("✅", "#DCFCE7", "Completed", done_n, "Marked done", key="stat-card-emp-dash-1")
    with c3:
        _stat_card("🟡", "#FEF9C3", "Pending", pending_n, "Still in progress", key="stat-card-emp-dash-2")
    with c4:
        _stat_card("🔴", "#FEE2E2", "Overdue", overdue_n, "Past due date", key="stat-card-emp-dash-3")

    st.write("")

    # ---- Performance: one overall ring + simple Completed/Pending legend ----
    with st.container(border=True):
        st.subheader("Performance")
        if not tasks:
            st.info("No tasks assigned yet for this selection.")
        else:
            ring_col, legend_col = st.columns([1, 1.4])
            with ring_col:
                st.plotly_chart(
                    _ring(completion_pct, "#4F46E5", height=170),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="employee_performance_ring",
                )
                st.caption(f"{done_n} of {len(tasks)} tasks completed")
            with legend_col:
                st.write("")
                st.write("")
                st.markdown(
                    f"<span style='color:#4F46E5;font-size:1.1rem;'>●</span> "
                    f"&nbsp; **Completed task** — {done_n}",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<span style='color:#CBD5E1;font-size:1.1rem;'>●</span> "
                    f"&nbsp; **Pending task** — {pending_n}",
                    unsafe_allow_html=True,
                )

    st.write("")

    # ---- Project Information ----
    with st.container(border=True):
        st.subheader("Project Information")

        if active_project_id is None:
            selected_name = st.selectbox(
                "📁 Project", [p["name"] for p in projects],
                key="employee_dashboard_project_info_select",
            )
            info_project = next(p for p in projects if p["name"] == selected_name)
        else:
            info_project = scoped_projects[0]
            st.caption(f"📁 {info_project.get('name', '—')}")

        pct, done, total = _project_task_progress(info_project.get("id"), tasks)

        name_col, progress_col, deadline_col = st.columns([2, 1.4, 1.2])
        with name_col:
            st.markdown("**Project name**")
            st.write(info_project.get("name", "—"))
        with progress_col:
            st.markdown("**Progress**")
            if pct is not None:
                st.progress(pct / 100, text=f"{pct}% · {done}/{total} of your tasks")
            else:
                st.caption("No linked tasks yet.")
        with deadline_col:
            st.markdown("**Deadline**")
            days_left = _days_left(info_project.get("deadline"))
            deadline_text = info_project.get("deadline", "—")
            if days_left is not None:
                tag = "🔴 overdue" if days_left < 0 else ("🟠 soon" if days_left <= 3 else "🟢 on track")
                st.write(f"{deadline_text} ({days_left}d) — {tag}")
            else:
                st.write(deadline_text)

        st.markdown("**Team**")
        team_resp = get_team(token, info_project.get("id"))
        if team_resp.status_code == 200:
            try:
                team = team_resp.json()
            except Exception:
                team = []
            if team:
                for member in team:
                    st.write(f"- {member.get('name', '—')} · `{member.get('role', '—')}`")
            else:
                st.caption("No team members listed.")
        else:
            show_api_error(team_resp)


# --------------------------------------------------------------------------
# MY TASKS — status workflow (assignee can update own tasks)
# --------------------------------------------------------------------------
def _render_employee_tasks(projects, token):
    st.title("✅ My Tasks")
    st.caption("Tasks assigned to you. Move them through the workflow as you progress.")

    active_project_id, project_label = _choose_active_project(projects)
    st.caption(f"Showing: **{project_label}**")
    st.write("")

    tasks_resp = get_tasks(token, project_id=active_project_id)
    tasks = _safe_json_list(tasks_resp)
    if tasks_resp.status_code != 200:
        return

    if not tasks:
        st.info("No tasks assigned to you for this selection.")
        return

    name_by_id = _project_name_map(projects)
    grouped = {k: [] for k in STATUS_META}
    for t in tasks:
        sk = t.get("status") or "todo"
        grouped[sk if sk in grouped else "todo"].append(t)

    # ---- Status count row — same _stat_card boxes as the Dashboard, one
    # per workflow stage (To Do / In Progress / Testing / Done). ----
    status_bg = {
        "todo": "#EDE9FE", "in_progress": "#DBEAFE",
        "testing": "#FEF3C7", "done": "#DCFCE7",
    }
    st.write("")
    _inject_stat_card_hover_css()
    status_cols = st.columns(4)
    for i, (col, key) in enumerate(zip(status_cols, STATUS_META)):
        meta = STATUS_META[key]
        with col:
            _stat_card(meta["icon"], status_bg[key], meta["label"], len(grouped[key]), "Tasks in this stage", key=f"stat-card-emp-tasks-{i}")
    st.write("")

    # ---- One expandable section per workflow stage.
    #   To Do        -> Accept            (todo -> in_progress)
    #   In Progress  -> Submit for Review  (in_progress -> testing)
    #   Testing      -> waiting on manager, no button
    #   Done         -> no button
    # Employees never set a task to Done themselves — that's the
    # manager's call after reviewing it in Testing.
    for key in STATUS_META:
        meta = STATUS_META[key]
        section_tasks = grouped[key]
        with st.expander(
            f"{meta['icon']} {meta['label']}  ·  {len(section_tasks)}",
            expanded=(key in ("todo", "in_progress")),
        ):
            if not section_tasks:
                st.caption("No tasks here.")
                continue

            for t in section_tasks:
                pid = t.get("project_id")
                proj_name = name_by_id.get(str(pid), "Project") if pid else "—"
                days = _task_due_days(t)

                row = st.columns([3, 1.4, 1.3])
                with row[0]:
                    st.markdown(f"**{t.get('title', '—')}**")
                    st.caption(f"📁 {proj_name}")
                with row[1]:
                    if days is not None and key != "done":
                        tag_color = "#EF4444" if days < 0 else ("#F59E0B" if days <= 3 else "#22C55E")
                        tag_text = "overdue" if days < 0 else ("due soon" if days <= 3 else "on track")
                        st.markdown(
                            f"<span style='font-size:0.78rem;color:{tag_color};font-weight:600;'>"
                            f"● {tag_text} · {abs(days)}d</span>",
                            unsafe_allow_html=True,
                        )
                with row[2]:
                    if key == "todo":
                        if st.button("✅ Accept", key=f"accept_{t['id']}", use_container_width=True, type="primary"):
                            resp = patch_task_status(token, str(t["id"]), {"status": "in_progress"})
                            if resp.status_code == 200:
                                st.success("Task accepted — moved to In Progress.")
                                st.rerun()
                            else:
                                show_api_error(resp)
                    elif key == "in_progress":
                        if st.button("📤 Submit for Review", key=f"submit_{t['id']}", use_container_width=True, type="primary"):
                            resp = patch_task_status(token, str(t["id"]), {"status": "testing"})
                            if resp.status_code == 200:
                                st.success("Sent to your manager for review.")
                                st.rerun()
                            else:
                                show_api_error(resp)
                    elif key == "testing":
                        st.caption("⏳ In review for manager")
                    else:
                        st.caption("✅ Completed")
                st.divider()


# --------------------------------------------------------------------------
# MY PROJECTS — read-only, single-project dropdown (no "All Projects")
# --------------------------------------------------------------------------
def _render_employee_projects(projects, token):
    st.title("📁 My Projects")
    st.caption("Projects you're assigned to. View only.")
    st.write("")

    if not projects:
        st.info("You're not assigned to any projects yet.")
        return

    # Single-project dropdown — no "All Projects" option, and only the
    # selected project is rendered below.
    project_names = [p["name"] for p in projects]
    selected_name = st.selectbox(
        "📁 Project",
        project_names,
        key=MY_PROJECTS_WIDGET_KEY,
    )
    p = next(pr for pr in projects if pr["name"] == selected_name)

    tasks = _safe_json_list(get_tasks(token))

    with st.container(border=True):
        top_col1, top_col2, top_col3 = st.columns([3, 1, 1])
        with top_col1:
            st.subheader(p.get("name", "—"))
        with top_col2:
            meta = PROJECT_STATUS_META.get(
                (p.get("status") or "").lower(),
                {"label": p.get("status", "—"), "color": "#6B7280"},
            )
            _pill(meta["label"], meta["color"])
        with top_col3:
            days_left = _days_left(p.get("deadline"))
            st.caption(f"Deadline: {p.get('deadline', '—')}")
            if days_left is not None:
                st.caption(f"{days_left}d left")

        if p.get("description"):
            st.caption(p["description"])

        pct, done, total = _project_task_progress(p.get("id"), tasks)
        if pct is not None:
            st.progress(pct / 100, text=f"{pct}% · {done}/{total} tasks done")
        else:
            st.caption("No linked tasks yet.")

        team_resp = get_team(token, p.get("id"))
        if team_resp.status_code == 200:
            try:
                team = team_resp.json()
            except Exception:
                team = []
            if team:
                st.markdown("**👥 Team**")
                for member in team:
                    st.write(
                        f"- {member.get('name', '—')} · `{member.get('role', '—')}`"
                    )
        else:
            show_api_error(team_resp)


# --------------------------------------------------------------------------
# DOCUMENTS — upload + view/download/preview, scoped to own projects
# (Reindex button removed — employees no longer trigger re-indexing.)
# --------------------------------------------------------------------------
def _render_employee_documents(projects, token):
    st.title("📄 Documents")
    st.caption("View and download project documents. Upload files to projects you're on.")
    st.write("")

    # ---- Upload -------------------------------------------------------
    with st.container(border=True):
        st.subheader("⬆️ Upload a document")
        if not projects:
            st.info("You're not on any projects yet — nothing to upload into.")
        else:
            if "employee_doc_uploader_key" not in st.session_state:
                st.session_state["employee_doc_uploader_key"] = 0

            with st.form("employee_upload_document_form", clear_on_submit=True):
                project_names = [p["name"] for p in projects]
                upload_project_label = st.selectbox(
                    "Project", project_names, key="employee_upload_project_select",
                )
                uploaded_file = st.file_uploader(
                    "Choose a file", type=None,
                    key=f"employee_doc_uploader_{st.session_state['employee_doc_uploader_key']}",
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
                            st.session_state["employee_doc_uploader_key"] += 1
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
                                    "No text extracted — use a "
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
    documents = _safe_json_list(docs_resp)

    if not documents:
        st.info("No documents to show for this selection.")
        return

    name_by_id = _project_name_map(projects)

    # ---- All Documents — filterable by project -------------------------
    with st.container(border=True):
        st.subheader("All Documents")
        st.caption("Upload PDF/DOCX/PPTX/TXT to enable chat RAG. Files are indexed on upload.")

        doc_filter_options = ["All Documents"] + [p.get("name", "—") for p in projects]
        selected_doc_filter = st.selectbox(
            "📁 Filter by project", doc_filter_options,
            key="employee_documents_project_filter",
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
            row = st.columns([3, 1, 1])
            with row[0]:
                st.markdown(f"📄 **{doc.get('filename', '—')}**")
                pid = doc.get("project_id")
                if pid:
                    st.caption(f"📁 {name_by_id.get(str(pid), 'Project')}")
                st.caption(rag_status_label(doc))
            with row[1]:
                resp = download_document(token, str(doc["id"]))
                if resp.status_code == 200:
                    st.download_button(
                        "Download", data=resp.content, file_name=doc["filename"],
                        mime="application/octet-stream",
                        key=f"employee_dl_{doc['id']}", use_container_width=True,
                    )
                else:
                    show_api_error(resp)
            with row[2]:
                if st.button("Preview", key=f"employee_view_{doc['id']}", use_container_width=True):
                    show_document_preview(token, doc)
            st.divider()

# --------------------------------------------------------------------------
# APP ENTRY
# --------------------------------------------------------------------------
def render_employee_app():
    _inject_light_theme()

    token = session_token()
    if not token:
        st.error("Your session expired. Please log in again.")
        if st.button("Back to login"):
            st.session_state.clear()
            st.rerun()
        return

    projects_resp = get_projects(token)
    projects = _safe_json_list(projects_resp)

    if st.session_state.get(NAV_RADIO_KEY) not in NAV_PAGES:
        st.session_state[NAV_RADIO_KEY] = NAV_PAGES[0]

    with st.sidebar:
        render_sidebar_header()
        st.caption("EMPLOYEE MENU")
        page = st.radio(
            "Go to",
            NAV_PAGES,
            label_visibility="collapsed",
            key=NAV_RADIO_KEY,
        )

    if page == "🏠 Dashboard":
        _render_employee_dashboard(projects, token)
    elif page == "✅ My Tasks":
        _render_employee_tasks(projects, token)
    elif page == "📁 My Projects":
        _render_employee_projects(projects, token)
    elif page == "📄 Documents":
        _render_employee_documents(projects, token)