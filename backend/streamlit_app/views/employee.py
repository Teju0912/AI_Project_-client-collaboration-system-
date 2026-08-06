"""
employee.py
Employee interface: My Work dashboard, My Tasks (kanban with status updates
for own tasks), My Projects (read-only), and Documents (view/download/preview
+ upload to assigned projects).

Matches the dark "AI Project OS" theme used in admin.py / manager.py.

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
    trigger_reindex,
)

STATUS_META = {
    "todo":        {"label": "To Do",       "icon": "⚪", "color": "#8B5CF6"},
    "in_progress": {"label": "In Progress", "icon": "🔵", "color": "#3B82F6"},
    "testing":     {"label": "Testing",     "icon": "🟠", "color": "#F59E0B"},
    "done":        {"label": "Done",        "icon": "🟢", "color": "#22C55E"},
}
# Phase -> completion % used for the per-task rings on the Dashboard's
# "My Completion" card (e.g. a task in "Testing" shows as 75%).
PHASE_PERCENT = {
    "todo": 25,
    "in_progress": 50,
    "testing": 75,
    "done": 100,
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


# --------------------------------------------------------------------------
# DARK THEME (same look as admin/manager)
# --------------------------------------------------------------------------
def _inject_dark_theme():
    st.markdown("""
    <style>
    .stApp { background-color: #0B0F1A; }
    .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }

    h1, h2, h3, h4, p, span, label, .stMarkdown { color: #E5E7EB !important; }
    .stCaption, [data-testid="stCaptionContainer"] { color: #9CA3AF !important; }

    section[data-testid="stSidebar"] {
        background-color: #111527;
        border-right: 1px solid #1F2937;
    }
    section[data-testid="stSidebar"] * { color: #D1D5DB !important; }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #131A2E !important;
        border: 1px solid #1F2937 !important;
        border-radius: 16px !important;
        padding: 0.4rem;
    }

    div[data-testid="stMetricValue"] { color: #F9FAFB !important; font-weight: 700; }
    div[data-testid="stMetricLabel"] { color: #9CA3AF !important; }

    .stButton button {
        background-color: #1B2138;
        color: #E5E7EB;
        border: 1px solid #2A3350;
        border-radius: 10px;
    }
    .stButton button:hover { border-color: #6366F1; color: #fff; }

    .stProgress > div > div > div > div { border-radius: 6px; }
    .stProgress > div > div { background-color: #1F2937; border-radius: 6px; }

    div[role="radiogroup"] label { color: #D1D5DB !important; }

    .icon-badge {
        width: 44px; height: 44px; border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.3rem; margin-bottom: 0.4rem;
    }
    .status-pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600;
    }
    .completion-vdivider {
        width: 1px;
        height: 100%;
        min-height: 220px;
        background-color: #1F2937;
        margin: 0 auto;
    }
    .completion-hdivider {
        border: none;
        border-top: 1px solid #1F2937;
        margin: 0.75rem 0;
    }
    </style>
    """, unsafe_allow_html=True)


def _pill(text, color):
    st.markdown(
        f'<span class="status-pill" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55;">{text}</span>',
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
        marker=dict(colors=[color, "#1F2937"]),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(text=f"<b style='font-size:16px;color:#F9FAFB'>{pct}%</b>",
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

    # New employee with no projects yet — short onboarding message instead
    # of a bare dashboard.
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
    documents = _safe_json_list(docs_resp)

    scoped_projects = (
        projects if active_project_id is None
        else [p for p in projects if str(p.get("id")) == str(active_project_id)]
    )

    done_n = sum(1 for t in tasks if (t.get("status") or "") == "done")
    open_n = len(tasks) - done_n
    total_n = len(tasks) or 1
    completion_pct = round(100 * done_n / total_n)

    st.write("")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        with st.container(border=True):
            st.caption("📁 My Projects")
            st.metric(label="My Projects", value=len(scoped_projects), label_visibility="collapsed")
    with c2:
        with st.container(border=True):
            st.caption("✅ Assigned Tasks")
            st.metric(label="Assigned Tasks", value=len(tasks), label_visibility="collapsed")
    with c3:
        with st.container(border=True):
            st.caption("🔵 Open Tasks")
            st.metric(label="Open Tasks", value=open_n, label_visibility="collapsed")
    with c4:
        with st.container(border=True):
            st.caption("📄 Documents")
            st.metric(label="Documents", value=len(documents), label_visibility="collapsed")

    st.write("")

    # --- My Completion:
    #   1) Phase legend (To Do / In Progress / Testing / Done)
    #   2) --- horizontal divider line ---
    #   3) Two boxes split by a static vertical divider line:
    #        LEFT  = compact rings (graph), one per task, colored/percented
    #                by phase. New tasks automatically get their own ring
    #                since this loops over the live `tasks` list.
    #        RIGHT = plain list of every task with its name and % done.
    # Each ring chart gets a unique `key` (based on the task id) — without
    # it, two tasks sharing the same status/phase produce visually
    # identical charts with no distinguishing args, which Streamlit can't
    # tell apart and raises StreamlitDuplicateElementId.
    # (Needs Attention card removed; bell stays in the header as before.) ---
    with st.container(border=True):
        st.subheader("My Completion")
        if not tasks:
            st.info("No tasks assigned yet for this selection.")
        else:
            st.caption("Each ring shows how far along that task is in the workflow.")

            legend_cols = st.columns(len(STATUS_META))
            for col, key in zip(legend_cols, STATUS_META):
                meta = STATUS_META[key]
                with col:
                    st.markdown(
                        f"{meta['icon']} **{meta['label']}** — {PHASE_PERCENT[key]}%"
                    )

            # Horizontal line separating the phase legend from the
            # graph/list section below it, so it's clear the legend is
            # separate from the per-task data underneath.
            _horizontal_divider()

            graph_box, divider_box, list_box = st.columns([2.2, 0.15, 1.4])

            with graph_box:
                per_row = 3
                for i in range(0, len(tasks), per_row):
                    row_tasks = tasks[i:i + per_row]
                    cols = st.columns(per_row)
                    for j, (col, t) in enumerate(zip(cols, row_tasks)):
                        sk = t.get("status") or "todo"
                        sk = sk if sk in STATUS_META else "todo"
                        meta = STATUS_META[sk]
                        pct = PHASE_PERCENT[sk]
                        with col:
                            # Unique key: task id if present, else the
                            # absolute index in the tasks list as a
                            # fallback (guards against missing/duplicate
                            # ids in the API response).
                            ring_key = f"employee_completion_ring_{t.get('id', i + j)}"
                            st.plotly_chart(
                                _ring(pct, meta["color"], height=100),
                                use_container_width=True,
                                config={"displayModeBar": False},
                                key=ring_key,
                            )
                            st.caption(f"**{t.get('title', '—')}** · {meta['icon']} {meta['label']}")

            with divider_box:
                _vertical_divider()

            with list_box:
                st.markdown("**Task list**")
                for t in tasks:
                    sk = t.get("status") or "todo"
                    sk = sk if sk in STATUS_META else "todo"
                    meta = STATUS_META[sk]
                    pct = PHASE_PERCENT[sk]
                    st.markdown(
                        f"{meta['icon']} **{t.get('title', '—')}** — {pct}%"
                    )

            st.caption(f"{done_n} of {len(tasks)} tasks fully done ({completion_pct}% overall)")

    st.write("")

    dl_col, doc_col = st.columns(2)
    with dl_col:
        with st.container(border=True):
            st.subheader("⏳ Deadlines")
            dated = [
                (p["name"], p.get("deadline"), _days_left(p.get("deadline")))
                for p in scoped_projects if p.get("deadline")
            ]
            dated = [d for d in dated if d[2] is not None]
            dated.sort(key=lambda d: d[2])
            if not dated:
                st.caption("No deadlines to show.")
            else:
                for name, deadline, days in dated[:5]:
                    tag = "🔴 overdue" if days < 0 else ("🟠 soon" if days <= 3 else "🟢 on track")
                    st.markdown(f"**{name}** — {deadline} ({days}d) — {tag}")

    with doc_col:
        with st.container(border=True):
            st.subheader("📄 Recent Documents")
            if not documents:
                st.caption("No documents yet.")
            else:
                for doc in documents[:5]:
                    st.write(f"- {doc.get('filename', '—')}")


# --------------------------------------------------------------------------
# MY TASKS — kanban with status move (assignee can update own tasks)
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

    status_keys = list(STATUS_META.keys())
    cols = st.columns(len(status_keys))
    for col, key in zip(cols, status_keys):
        meta = STATUS_META[key]
        with col:
            st.markdown(f"**{meta['icon']} {meta['label']}** · {len(grouped[key])}")
            if not grouped[key]:
                st.caption("—")
            for t in grouped[key]:
                with st.container(border=True):
                    st.markdown(f"**{t.get('title', '—')}**")
                    pid = t.get("project_id")
                    if pid:
                        st.caption(f"📁 {name_by_id.get(str(pid), 'Project')}")
                    if t.get("description"):
                        st.caption(t["description"])
                    days = _task_due_days(t)
                    if days is not None and key != "done":
                        tag = "🔴 overdue" if days < 0 else ("🟠 due soon" if days <= 3 else "🟢 on track")
                        st.caption(f"{tag} · {abs(days)}d")
                    if key != "done":
                        keys_order = list(STATUS_META.keys())
                        idx = keys_order.index(key)
                        next_key = keys_order[idx + 1]
                        if st.button(
                            f"Move to {STATUS_META[next_key]['label']} →",
                            key=f"emp_move_{t['id']}",
                            use_container_width=True,
                        ):
                            resp = patch_task_status(
                                token, str(t["id"]), {"status": next_key}
                            )
                            if resp.status_code == 200:
                                st.success("Status updated.")
                                st.rerun()
                            else:
                                show_api_error(resp)


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
# --------------------------------------------------------------------------
def _render_employee_documents(projects, token):
    st.title("📄 Documents")
    st.caption("View and download project documents. Upload files to projects you're on.")

    active_project_id, project_label = _choose_active_project(projects)
    st.caption(f"Showing: **{project_label}**")
    st.write("")

    with st.container(border=True):
        st.subheader("⬆️ Upload a document")
        if not projects:
            st.info("You're not on any projects yet — nothing to upload into.")
        else:
            if "employee_doc_uploader_key" not in st.session_state:
                st.session_state["employee_doc_uploader_key"] = 0

            with st.form("employee_upload_document_form", clear_on_submit=True):
                project_names = [p["name"] for p in projects]
                default_index = 0
                if active_project_id is not None:
                    matching = [
                        p["name"] for p in projects
                        if str(p.get("id")) == str(active_project_id)
                    ]
                    if matching:
                        default_index = project_names.index(matching[0])

                upload_project_label = st.selectbox(
                    "Project",
                    project_names,
                    index=default_index,
                    key="employee_upload_project_select",
                )
                uploaded_file = st.file_uploader(
                    "Choose a file",
                    type=None,
                    key=f"employee_doc_uploader_{st.session_state['employee_doc_uploader_key']}",
                )
                if st.form_submit_button("Upload", type="primary"):
                    if uploaded_file is None:
                        st.warning("Please choose a file first.")
                    else:
                        upload_project_id = next(
                            (p["id"] for p in projects if p["name"] == upload_project_label),
                            None,
                        )
                        resp = upload_document(
                            token, uploaded_file, project_id=str(upload_project_id)
                        )
                        if resp.status_code in (200, 201):
                            st.session_state["employee_doc_uploader_key"] += 1
                            data = resp.json() if resp.content else {}
                            chunks = int(data.get("chunk_count") or 0)
                            if chunks > 0:
                                st.success(
                                    f"Uploaded to **{upload_project_label}** and indexed "
                                    f"for AI Chat ({chunks} chunk(s))."
                                )
                            else:
                                st.success(
                                    f"Uploaded to **{upload_project_label}**. "
                                    "No text for RAG yet — click Reindex if needed."
                                )
                            st.rerun()
                        else:
                            show_api_error(resp)

    st.write("")
    st.caption(
        "Indexed documents can be selected in the sidebar **AI Chat Assistant** for RAG Q&A."
    )

    docs_resp = list_documents(token, project_id=active_project_id)
    documents = _safe_json_list(docs_resp)
    if docs_resp.status_code != 200:
        return

    if not documents:
        st.info("No documents to show for this selection.")
        return

    name_by_id = _project_name_map(projects)
    with st.container(border=True):
        st.subheader(f"Documents — {project_label}")
        for doc in documents:
            row = st.columns([3, 1, 1, 1])
            with row[0]:
                st.markdown(f"📄 **{doc.get('filename', '—')}**")
                st.caption(rag_status_label(doc))
                pid = doc.get("project_id")
                if pid:
                    st.caption(f"📁 {name_by_id.get(str(pid), 'Project')}")
            with row[1]:
                # Lazy download: fetch the file only when the user asks for
                # it, instead of downloading every document on every rerun.
                dl_state_key = f"employee_dl_ready_{doc['id']}"
                if st.session_state.get(dl_state_key):
                    ready = st.session_state[dl_state_key]
                    st.download_button(
                        "Save file",
                        data=ready["content"],
                        file_name=ready["filename"],
                        mime="application/octet-stream",
                        key=f"employee_dl_save_{doc['id']}",
                        use_container_width=True,
                    )
                else:
                    if st.button(
                        "Download",
                        key=f"employee_dl_prep_{doc['id']}",
                        use_container_width=True,
                    ):
                        resp = download_document(token, str(doc["id"]))
                        if resp.status_code == 200:
                            st.session_state[dl_state_key] = {
                                "content": resp.content,
                                "filename": doc.get("filename", "file"),
                            }
                            st.rerun()
                        else:
                            show_api_error(resp)
            with row[2]:
                if st.button(
                    "Preview",
                    key=f"employee_view_{doc['id']}",
                    use_container_width=True,
                ):
                    show_document_preview(token, doc)
            with row[3]:
                trigger_reindex(token, doc, key=f"employee_reindex_{doc['id']}")
            st.divider()


# --------------------------------------------------------------------------
# APP ENTRY
# --------------------------------------------------------------------------
def render_employee_app():
    _inject_dark_theme()

    token = session_token()
    if not token:
        st.error("Your session expired. Please log in again.")
        if st.button("Back to login"):
            st.session_state.clear()
            st.rerun()
        return

    projects_resp = get_projects(token)
    projects = _safe_json_list(projects_resp)

    with st.sidebar:
        render_sidebar_header()
        st.subheader("Employee menu")
        page = st.radio(
            "Go to",
            ["Dashboard", "My Tasks", "My Projects", "Documents"],
        )

    if page == "Dashboard":
        _render_employee_dashboard(projects, token)
    elif page == "My Tasks":
        _render_employee_tasks(projects, token)
    elif page == "My Projects":
        _render_employee_projects(projects, token)
    elif page == "Documents":
        _render_employee_documents(projects, token)