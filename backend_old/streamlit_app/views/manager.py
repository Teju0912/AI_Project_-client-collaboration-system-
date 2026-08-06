"""
manager.py
Project manager interface: project-focused dashboard, clients (view/add/
edit/delete), projects (table/create/edit/assign team), tasks, documents
(upload/preview/download/delete, scoped by project), meeting summaries,
and AI-generated weekly reports — with a project selector so a PM
juggling multiple projects can filter Dashboard/Tasks/Documents/
Meetings/Weekly Reports.

Built entirely with native Streamlit components + Plotly charts, plus a
shared dark theme (matching the admin "AI Project OS" look) injected once
for all manager pages — no ad-hoc HTML/CSS scattered per page.

DATA POLICY: every number and chart is computed from live API responses.
Nothing is fabricated.

PERMISSIONS NOTE: managers can view/add/edit clients and fully manage
projects (create/update + assign team), tasks, documents, can
upload/view meeting summaries for projects they belong to, and can
generate/view AI-powered weekly reports per project. Client delete
remains available in this UI for managers as well.

KEY FIX: _choose_active_project() is called exactly ONCE per page, each
with its own unique widget key, to avoid StreamlitDuplicateElementKey.
"""

import datetime as dt

import streamlit as st
import plotly.graph_objects as go

from api_client import (
    get_projects, get_tasks, list_documents, get_clients, get_users,
    get_team, create_project, update_project, assign_team,
    create_client, update_client, delete_client,
    patch_task_status, download_document, create_task,
    upload_document, delete_document,
    generate_weekly_report, get_weekly_reports,
    analyze_requirement, get_requirement_analysis, approve_requirement_analysis, reject_requirement_analysis,
)
from views.shared import (
    render_sidebar_header,
    show_api_error,
    show_document_preview,
    session_token,
    session_user,
    render_meeting_panel,
    rag_status_label,
    trigger_reindex,
)

STATUS_META = {
    "todo":        {"label": "To Do",       "icon": "⚪", "color": "gray",   "hex": "#8B5CF6"},
    "in_progress": {"label": "In Progress", "icon": "🔵", "color": "blue",   "hex": "#3B82F6"},
    "testing":     {"label": "Testing",     "icon": "🟠", "color": "orange", "hex": "#F59E0B"},
    "done":        {"label": "Done",        "icon": "🟢", "color": "green",  "hex": "#22C55E"},
}
CLIENT_STATUS_META = {
    "active":   {"icon": "🟢", "color": "green",  "hex": "#22C55E"},
    "pending":  {"icon": "🟡", "color": "orange", "hex": "#EAB308"},
    "inactive": {"icon": "⚪", "color": "gray",   "hex": "#6B7280"},
}
CLIENT_STATUS_OPTIONS = ["active", "pending", "inactive"]

ALL_PROJECTS_LABEL = "All Projects"
ACTIVE_PROJECT_KEY = "manager_active_project_id"
PROJECT_STATUS_OPTIONS = ["planning", "active", "on_hold", "completed"]


# --------------------------------------------------------------------------
# DARK THEME (matches the admin "AI Project OS" look, applied to all tabs)
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
    </style>
    """, unsafe_allow_html=True)


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


def _ring(pct, color, height=170):
    fig = go.Figure(data=[go.Pie(
        values=[pct, 100 - pct], hole=0.72,
        marker=dict(colors=[color, "#1F2937"]),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(text=f"<b style='font-size:20px;color:#F9FAFB'>{pct}%</b>",
                           x=0.5, y=0.5, showarrow=False)],
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

    if current is None:
        current = str(projects[0]["id"])
        st.session_state[ACTIVE_PROJECT_KEY] = current

    default_index = labels.index(name_by_id[str(current)])

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


# --------------------------------------------------------------------------
# DASHBOARD
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
    total_n = len(tasks) or 1
    completion_pct = round(100 * completed_n / total_n)

    st.write("")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        with st.container(border=True):
            st.caption("📁 Projects in view")
            st.metric(label="Projects in view", value=len(scoped_projects), label_visibility="collapsed")
    with c2:
        with st.container(border=True):
            st.caption("✅ Tasks")
            st.metric(label="Tasks", value=len(tasks), label_visibility="collapsed")
    with c3:
        with st.container(border=True):
            st.caption("🎯 Completed")
            st.metric(label="Completed", value=completed_n, label_visibility="collapsed")
    with c4:
        with st.container(border=True):
            st.caption("👥 Team" if active_project_id else "🟢 Active projects")
            st.metric(
                label="Team or active projects",
                value=len(team) if active_project_id else active_n,
                label_visibility="collapsed",
            )

    st.write("")

    # ---- Overall Completion: ring graph + phase list, split by a divider --
    with st.container(border=True):
        st.subheader("Overall Completion")
        if tasks:
            status_counts = {k: 0 for k in STATUS_META}
            for t in tasks:
                sk = t.get("status") or "todo"
                status_counts[sk if sk in status_counts else "todo"] += 1

            graph_col, divider_col, list_col = st.columns([2, 0.15, 2])
            with graph_col:
                st.plotly_chart(_ring(completion_pct, "#22C55E"), use_container_width=True,
                                 config={"displayModeBar": False})
                st.caption(f"{completed_n} of {len(tasks)} tasks done")
            with divider_col:
                st.markdown(
                    "<div style='border-left:1px solid #1F2937; height:210px; "
                    "margin:0 auto;'></div>",
                    unsafe_allow_html=True,
                )
            with list_col:
                st.markdown("**Phases**")
                for k, meta in STATUS_META.items():
                    st.markdown(
                        f"<div style='display:flex; align-items:center; margin-bottom:10px;'>"
                        f"<span style='width:12px; height:12px; border-radius:3px; "
                        f"background-color:{meta['hex']}; display:inline-block; margin-right:10px;'></span>"
                        f"<span>{meta['icon']} {meta['label']} — {status_counts[k]}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No tasks in this view.")

    st.write("")

    dl_col, doc_col = st.columns(2)
    with dl_col:
        with st.container(border=True):
            st.subheader("⏳ Deadlines")
            dated = [(p["name"], p.get("deadline"), _days_left(p.get("deadline")))
                     for p in scoped_projects if p.get("deadline")]
            dated = [d for d in dated if d[2] is not None]
            dated.sort(key=lambda d: d[2])
            if not dated:
                st.caption("No deadlines in this view.")
            else:
                for name, deadline, days in dated[:5]:
                    tag = "🔴 overdue" if days < 0 else ("🟠 soon" if days <= 3 else "🟢 on track")
                    st.markdown(f"**{name}** — {deadline} ({days}d) — {tag}")

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

    if active_project_id and team:
        st.write("")
        with st.container(border=True):
            st.subheader("👥 Project Team")
            for member in team:
                st.write(f"**{member.get('name')}** · `{member.get('role')}` · {member.get('email')}")


# --------------------------------------------------------------------------
# TASKS
# --------------------------------------------------------------------------
def _render_manager_tasks(projects, token):
    st.title("✅ Tasks")

    active_project_id, project_label = _choose_active_project(
        projects, widget_key="manager_tasks_project_dropdown"
    )
    st.caption(f"Showing: **{project_label}**")
    st.write("")

    tasks_resp = get_tasks(token, project_id=active_project_id)
    if tasks_resp.status_code != 200:
        show_api_error(tasks_resp)
        return
    tasks = tasks_resp.json()

    if not tasks:
        st.info("No tasks to show for this selection.")
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
                                         key=f"move_{t['id']}", use_container_width=True):
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

        with st.form("manager_create_task_form", clear_on_submit=True):
            # 1) Select project
            project_for_task = None
            if projects:
                proj_label = st.selectbox(
                    "Project",
                    [p["name"] for p in projects],
                    key="create_task_project_select",
                )
                project_for_task = next(
                    (p.get("id") for p in projects if p["name"] == proj_label),
                    None,
                )
            else:
                st.caption("Create a project first — managers must attach tasks to a project.")

            # 2) Select employee
            assignee_labels = [label for label, _ in assignee_options]
            assignee_label = st.selectbox(
                "Assign to (employee)",
                assignee_labels,
                key="manager_create_task_assignee",
            )
            if not users_ok:
                st.caption("Could not load employees for assignment.")

            # 3) Task title
            title = st.text_input("Title")

            # 4) Description
            description = st.text_area("Description")

            # 5) Status
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


# --------------------------------------------------------------------------
# DOCUMENTS — upload (with project selection), view, preview, download, delete
# --------------------------------------------------------------------------
def _render_manager_documents(projects, token):
    st.title("📄 Documents")

    active_project_id, project_label = _choose_active_project(
        projects, widget_key="manager_documents_project_dropdown"
    )
    st.caption(f"Showing: **{project_label}**")
    st.write("")

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
                if active_project_id is not None:
                    matching = [p["name"] for p in projects if str(p.get("id")) == str(active_project_id)]
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
    if docs_resp.status_code != 200:
        show_api_error(docs_resp)
        return
    documents = docs_resp.json()

    if not documents:
        st.info("No documents to show for this selection.")
        return

    with st.container(border=True):
        st.subheader(f"Documents — {project_label}")
        for doc in documents:
            row = st.columns([3, 1, 1, 1, 1])
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
                trigger_reindex(token, doc, key=f"manager_reindex_{doc['id']}")
            with row[4]:
                if st.button("Delete", key=f"manager_del_{doc['id']}", use_container_width=True):
                    delete_resp = delete_document(token, str(doc["id"]))
                    if delete_resp.status_code == 204:
                        st.success("Document deleted.")
                        st.rerun()
                    else:
                        show_api_error(delete_resp)
            st.divider()


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
        with st.container(border=True):
            st.caption("📁 Total Projects")
            st.metric(label="Total Projects", value=len(projects), label_visibility="collapsed")
    with c2:
        with st.container(border=True):
            st.caption("🟢 Active")
            st.metric(label="Active", value=active_n, label_visibility="collapsed")
    with c3:
        with st.container(border=True):
            st.caption("✅ Completed")
            st.metric(label="Completed", value=completed_n, label_visibility="collapsed")

    st.write("")

    with st.container(border=True):
        st.subheader("All Projects")
        if not projects:
            st.info("No projects yet — create one below.")
        else:
            table_rows = []
            for p in projects:
                days_left = _days_left(p.get("deadline"))
                table_rows.append({
                    "Name": p.get("name", "—"),
                    "Status": p.get("status", "—"),
                    "Deadline": p.get("deadline", "—"),
                    "Days Left": days_left if days_left is not None else "—",
                })
            st.dataframe(table_rows, use_container_width=True, hide_index=True)

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

    # ---- Assign / update project team ------------------------------------
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
def _client_status_meta(status_text):
    return CLIENT_STATUS_META.get((status_text or "").strip().lower(),
                                   {"icon": "⚪", "color": "gray", "hex": "#6B7280"})


def _client_status_donut(clients, height=230):
    counts = {}
    for c in clients:
        s = (c.get("status") or "unknown").lower()
        counts[s] = counts.get(s, 0) + 1
    labels = [s.title() for s in counts]
    values = list(counts.values())
    colors = [_client_status_meta(s)["hex"] for s in counts]
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.68,
        marker=dict(colors=colors, line=dict(color="#131A2E", width=2)),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=f"<b style='font-size:24px;color:#F9FAFB'>{len(clients)}</b>"
                 f"<br><span style='font-size:11px;color:#9CA3AF'>Total Clients</span>",
            x=0.5, y=0.5, showarrow=False,
        )],
    )
    return fig, counts


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
        with st.container(border=True):
            st.caption("🏢 Total Clients")
            st.metric(label="Total Clients", value=len(clients), label_visibility="collapsed")
    with c2:
        with st.container(border=True):
            st.caption("🟢 Active")
            st.metric(label="Active", value=active_n, label_visibility="collapsed")
    with c3:
        with st.container(border=True):
            st.caption("🟡 Pending")
            st.metric(label="Pending", value=pending_n, label_visibility="collapsed")
    with c4:
        with st.container(border=True):
            st.caption("⚪ Inactive")
            st.metric(label="Inactive", value=inactive_n, label_visibility="collapsed")

    st.write("")

    if not clients:
        st.info("No clients found for your organization yet. Add one below.")
    else:
        chart_col, list_col = st.columns([1, 2])

        with chart_col:
            with st.container(border=True):
                st.subheader("By Status")
                fig, counts = _client_status_donut(clients)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                for status, count in counts.items():
                    meta = _client_status_meta(status)
                    pct = round(100 * count / len(clients))
                    st.caption(f"{meta['icon']} {status.title()} — {count} ({pct}%)")

        with list_col:
            with st.container(border=True):
                st.subheader("Client Directory")

                client_labels = [c.get("company_name", "—") for c in clients]
                selected_client_label = st.selectbox(
                    "Select client", client_labels, key="manager_client_select_dropdown"
                )
                selected_client = next(
                    (c for c in clients if c.get("company_name", "—") == selected_client_label),
                    None,
                )

                if selected_client:
                    meta = _client_status_meta(selected_client.get("status"))
                    badge_col, info_col, status_col = st.columns([0.6, 3, 1.2])
                    with badge_col:
                        st.badge(_initials(selected_client.get("company_name", "?")), color="violet")
                    with info_col:
                        st.markdown(f"**{selected_client.get('company_name', '—')}**")
                        st.caption(
                            f"{selected_client.get('contact_name', '—')} · "
                            f"{selected_client.get('email', '—')} · "
                            f"{selected_client.get('phone', '—')}"
                        )
                    with status_col:
                        st.write("")
                        st.badge(f"{meta['icon']} {selected_client.get('status', '—')}", color=meta["color"])

                    st.divider()
                    st.markdown("**Projects**")
                    client_projects = [
                        p for p in projects
                        if str(p.get("client_id")) == str(selected_client.get("id"))
                    ]
                    if not client_projects:
                        st.caption("No projects linked to this client.")
                    else:
                        project_labels = [p["name"] for p in client_projects]
                        selected_project_label = st.selectbox(
                            "Project", project_labels, key="manager_client_project_dropdown"
                        )
                        selected_proj = next(
                            (p for p in client_projects if p["name"] == selected_project_label),
                            None,
                        )
                        if selected_proj:
                            st.write(f"**{selected_proj['name']}**")
                            st.caption(
                                f"Status: {selected_proj.get('status', '—')} · "
                                f"Deadline: {selected_proj.get('deadline', '—')}"
                            )

    st.write("")

    # ---- Add client ------------------------------------------------------
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

    # ---- Edit client -------------------------------------------------------
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

    # ---- Delete client -----------------------------------------------------
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

    # --- Generate report ---
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

    # --- View past reports ---
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
# REQUIREMENT ANALYZER
# --------------------------------------------------------------------------
from views._requirement_helper import _epic_key, _story_key


def _render_manager_requirement_analyzer(projects, token):
    st.title("🧾 Requirement Analyzer")
    st.caption("Analyze a requirements document with AI, review/edit the generated Epics/Stories, then approve to create tasks.")
    st.write("")

    active_project_id, project_label = _choose_active_project(projects, widget_key="manager_req_project_dropdown")
    st.caption(f"Project context: **{project_label}**")

    # Document picker
    docs_resp = list_documents(token, project_id=active_project_id)
    if docs_resp.status_code != 200:
        show_api_error(docs_resp)
        return
    docs = docs_resp.json()

    doc_options = ["(select a document)"] + [f"{d['filename']} ({d['id']})" for d in docs]
    selected_doc_label = st.selectbox("Document to analyze", doc_options, key="req_doc_select")
    selected_doc_id = None
    if selected_doc_label != "(select a document)":
        selected_doc_id = selected_doc_label.split("(")[-1].strip(")")

    if st.button("Analyze", key="req_analyze_btn", type="primary"):
        if not selected_doc_id and not active_project_id:
            st.error("Select a document or specify a project context.")
        else:
            with st.spinner("Sending to AI and parsing result..."):
                resp = analyze_requirement(token, document_id=selected_doc_id, project_id=active_project_id)
            if resp.status_code != 200:
                show_api_error(resp)
                return
            data = resp.json()
            st.session_state["req_analysis_id"] = data.get("id")
            st.session_state["req_parsed"] = data.get("result")
            st.success("Analysis complete — review below.")

    # If existing analysis in session, or user can fetch by ID
    existing_id = st.session_state.get("req_analysis_id")
    if existing_id:
        if st.button("Refresh analysis from server", key="req_refresh"):
            fetch = get_requirement_analysis(token, existing_id)
            if fetch.status_code == 200:
                st.session_state["req_parsed"] = fetch.json().get("parsed")
            else:
                show_api_error(fetch)

    parsed = st.session_state.get("req_parsed")
    if not parsed:
        st.info("No analysis to review yet. Click Analyze after selecting a document.")
        return

    # Editable review UI
    edited_epics = []
    for i, epic in enumerate(parsed.get("epics", [])):
        with st.container(border=True):
            st.markdown(f"### Epic {i+1}")
            epic_title = st.text_input("Epic title", value=epic.get("title"), key=_epic_key(i))
            stories = epic.get("stories", [])
            edited_stories = []
            for j, story in enumerate(stories):
                st.markdown(f"#### Story {j+1}")
                s_title = st.text_input("Title", value=story.get("title"), key=_story_key(i, j))
                s_desc = st.text_area("Description", value=story.get("description"), key=f"{_story_key(i,j)}_desc")
                s_pri = st.selectbox("Priority", ["low", "medium", "high"], index={"low":0,"medium":1,"high":2}.get(story.get("priority","medium")), key=f"{_story_key(i,j)}_pri")
                if st.button("Delete this story", key=f"del_story_{i}_{j}"):
                    # mark for deletion by skipping append
                    st.experimental_rerun()
                edited_stories.append({"title": s_title, "description": s_desc, "priority": s_pri})
            if st.button("Delete this epic", key=f"del_epic_{i}"):
                st.experimental_rerun()
            edited_epics.append({"title": epic_title, "stories": edited_stories})

    # Approve / Reject actions
    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("Approve & Create Tasks", key="req_approve", type="primary"):
            if not st.session_state.get("req_analysis_id"):
                st.error("No analysis selected to approve.")
            else:
                payload = {"epics": edited_epics}
                with st.spinner("Creating tasks from approved analysis..."):
                    resp = approve_requirement_analysis(token, st.session_state["req_analysis_id"], payload)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    ids = data.get("created_task_ids", [])
                    st.success(f"Created {len(ids)} tasks.")
                    st.write("Created task IDs:")
                    for tid in ids:
                        st.write(f"- {tid}")
                    # Clear session state so user can't re-approve accidentally
                    del st.session_state["req_analysis_id"]
                    del st.session_state["req_parsed"]
                else:
                    show_api_error(resp)
    with cols[1]:
        if st.button("Reject Analysis", key="req_reject", type="secondary"):
            if not st.session_state.get("req_analysis_id"):
                st.error("No analysis selected to reject.")
            else:
                resp = reject_requirement_analysis(token, st.session_state["req_analysis_id"])
                if resp.status_code == 200:
                    st.success("Analysis rejected.")
                    try:
                        del st.session_state["req_analysis_id"]
                        del st.session_state["req_parsed"]
                    except Exception:
                        pass
                else:
                    show_api_error(resp)


# --------------------------------------------------------------------------
# APP ENTRY
# --------------------------------------------------------------------------
def render_manager_app():
    _inject_dark_theme()

    token = session_token()

    projects_resp = get_projects(token)
    projects = projects_resp.json() if projects_resp.status_code == 200 else []
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)

    with st.sidebar:
        render_sidebar_header()
        st.subheader("Manager menu")
        page = st.radio(
            "Go to",
                    ["Dashboard", "Clients", "Projects", "Tasks", "Documents", "Meetings", "Weekly Reports", "Requirement Analyzer"],
        )

    if page == "Dashboard":
        _render_manager_dashboard(projects, token)
    elif page == "Clients":
        _render_manager_clients(token, projects)
    elif page == "Projects":
        _render_manager_projects(projects, token)
    elif page == "Tasks":
        _render_manager_tasks(projects, token)
    elif page == "Documents":
        _render_manager_documents(projects, token)
    elif page == "Meetings":
        _render_manager_meetings(projects, token)
    elif page == "Weekly Reports":
        _render_weekly_reports(projects, token)
    elif page == "Requirement Analyzer":
            _render_manager_requirement_analyzer(projects, token)