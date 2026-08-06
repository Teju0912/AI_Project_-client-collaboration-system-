"""
admin.py
Full admin interface styled to match the "AI Project OS" dark dashboard
design. Every number, chart, and list is computed from live API responses
(get_clients, get_projects, get_tasks, list_documents, get_users) —
nothing is fabricated. Trend deltas, relative timestamps ("2 hours ago"),
and countdowns are NOT shown because your API doesn't return that data —
adding them would mean making them up.

Clients / Projects / Tasks / Documents are rendered directly in this file
(richer Streamlit UI: donut charts, kanban board, upload/preview/delete,
team assignment) instead of delegating to opaque shared page functions.
Admin has full permissions everywhere (create/edit/delete clients,
create/edit projects + assign teams, create/move tasks, upload/preview/
download/delete documents).

Dashboard:
- Task Overview card removed; Projects Overview takes the wider column.
  Its legend shows: status label -> percentage -> colour dot (dot colour
  matches the donut slice). The dot's inline color uses !important so it
  overrides the global dark-theme `span { color: ... !important }` rule.
- "Team by Role" excludes Admin, shows a real "Total Members" count, and
  lets the admin pick a role to see the actual names in that role.
- "Project Details" lives inside the Projects tab as a dropdown.

Clients tab:
- "Client Directory" list removed (redundant with the "Client Details"
  dropdown below it) — the donut chart now occupies that space, with the
  same label -> percentage -> colour-dot legend pattern.

Projects tab:
- "All Projects" list removed (redundant with the "Project Details"
  dropdown) — stats cards, the dropdown, create/edit, and team assignment
  remain.

Tasks tab:
- Create task form field order: Project -> Assign to (employee) -> Title
  -> Description -> Status.

Meetings:
- A read-only "🎙️ Meeting Summaries" page (via render_meeting_panel)
  shows meeting summaries across every project in the organization.
"""

import datetime as dt

import streamlit as st
import plotly.graph_objects as go

from api_client import (
    get_clients, get_projects, get_tasks, list_documents, get_users,
    get_team, create_project, update_project, assign_team,
    create_client, update_client, delete_client,
    patch_task_status, create_task,
    upload_document, download_document, delete_document,
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
PROJECT_STATUS_OPTIONS = ["planning", "active", "on_hold", "completed"]

CLIENT_STATUS_META = {
    "active":   {"icon": "🟢", "color": "#22C55E"},
    "pending":  {"icon": "🟡", "color": "#EAB308"},
    "inactive": {"icon": "⚪", "color": "#6B7280"},
}
CLIENT_STATUS_OPTIONS = ["active", "pending", "inactive"]


# --------------------------------------------------------------------------
# DARK THEME (needed to match the screenshot — layout/logic still Streamlit)
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
    .stButton button[kind="primary"] {
        background-color: #4F46E5;
        border: 1px solid #4F46E5;
        color: #fff;
    }
    .stButton button[kind="primary"]:hover { background-color: #4338CA; }

    .stProgress > div > div > div > div { border-radius: 6px; }
    .stProgress > div > div { background-color: #1F2937; border-radius: 6px; }

    div[role="radiogroup"] label { color: #D1D5DB !important; }

    div[data-testid="stExpander"] {
        border: 1px solid #1F2937 !important;
        border-radius: 14px !important;
        background-color: #10152A !important;
    }

    hr { border-color: #1F2937 !important; }

    .icon-badge {
        width: 44px; height: 44px; border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.3rem; margin-bottom: 0.4rem;
    }
    .status-pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)


def _icon_badge(icon, bg):
    st.markdown(f'<div class="icon-badge" style="background:{bg};">{icon}</div>', unsafe_allow_html=True)


def _pill(text, color):
    st.markdown(
        f'<span class="status-pill" style="background:{color}22;color:{color} !important;'
        f'border:1px solid {color}55;">{text}</span>',
        unsafe_allow_html=True,
    )


def _donut(labels, values, colors, center_line1, center_line2, height=230):
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.68,
        marker=dict(colors=colors, line=dict(color="#131A2E", width=3)),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=f"<b style='font-size:26px;color:#F9FAFB'>{center_line1}</b><br>"
                 f"<span style='font-size:12px;color:#9CA3AF'>{center_line2}</span>",
            x=0.5, y=0.5, showarrow=False,
        )],
    )
    return fig


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


def _project_task_progress(project_id, tasks):
    linked = [t for t in tasks if str(t.get("project_id")) == str(project_id)]
    if not linked:
        return None, 0, 0
    done = sum(1 for t in linked if (t.get("status") or "") == "done")
    return round(100 * done / len(linked)), done, len(linked)


# --------------------------------------------------------------------------
# PROJECT DETAILS — project picker + scoped data (used inside Projects tab)
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

    # ---- Top bar: avatar only (search bar removed — it wasn't wired to
    # anything and gave the impression of a working search that didn't
    # exist) --------------------------------------------------------------
    title_col, avatar_col = st.columns([9, 1])
    with title_col:
        hour = dt.datetime.now().hour
        salutation = "Morning" if hour < 12 else ("Afternoon" if hour < 18 else "Evening")
        st.title(f"Good {salutation}, {user['name'].split()[0]}! 👋")
        st.caption("Here's what's happening with your organization today.")
    with avatar_col:
        st.write("")
        initials = "".join(p[0] for p in user["name"].split()[:2]).upper()
        st.badge(initials, color="violet")

    st.write("")

    # ---- Live fetches ---------------------------------------------------
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

    clients_n = len(clients) if clients_resp.status_code == 200 else "—"
    active_projects_n = (
        sum(1 for p in projects if (p.get("status") or "").lower() == "active")
        if projects_resp.status_code == 200 else "—"
    )
    tasks_n = len(tasks) if tasks_resp.status_code == 200 else "—"
    docs_n = len(documents) if docs_resp.status_code == 200 else "—"
    users_n = len(users) if users_resp.status_code == 200 else "—"

    stat_cards = [
        ("👥", "#4C1D95", "Total Clients", clients_n),
        ("📁", "#1E40AF", "Active Projects", active_projects_n),
        ("✅", "#065F46", "Tasks", tasks_n),
        ("📄", "#92400E", "Documents", docs_n),
        ("👤", "#5B21B6", "Users", users_n),
    ]
    cols = st.columns(5)
    for col, (icon, bg, label, value) in zip(cols, stat_cards):
        with col:
            with st.container(border=True):
                _icon_badge(icon, bg)
                st.caption(label)
                st.metric(label=label, value=value, label_visibility="collapsed")

    st.write("")

    # Task Overview card removed — Projects Overview takes the wider
    # column and Team by Role fills the rest.
    c1, c2 = st.columns([2, 1])

    with c1:
        with st.container(border=True):
            st.subheader("Projects Overview")
            if projects_resp.status_code != 200:
                show_api_error(projects_resp)
            elif not projects:
                st.info("No projects yet.")
            else:
                status_counts = {k: 0 for k in PROJECT_STATUS_META}
                for p in projects:
                    sk = (p.get("status") or "active").lower()
                    status_counts[sk if sk in status_counts else "active"] += 1
                total = len(projects)
                active_like = status_counts.get("active", 0)

                shown = [k for k in PROJECT_STATUS_META if status_counts[k] > 0]
                labels = [PROJECT_STATUS_META[k]["label"] for k in shown]
                values = [status_counts[k] for k in shown]
                colors = [PROJECT_STATUS_META[k]["color"] for k in shown]
                active_pct = round(100 * active_like / total) if total else 0

                donut_col, legend_col = st.columns([1, 1])
                with donut_col:
                    st.plotly_chart(
                        _donut(labels, values, colors, f"{active_pct}%", "Active", height=300),
                        use_container_width=True, config={"displayModeBar": False},
                    )
                with legend_col:
                    st.write("")
                    for key in shown:
                        meta = PROJECT_STATUS_META[key]
                        val = status_counts[key]
                        pct = round(100 * val / total) if total else 0
                        # Order: status label -> percentage -> colour dot.
                        # !important on the dot's color is required because
                        # the global dark-theme CSS rule
                        # `span { color: #E5E7EB !important; }` would
                        # otherwise override this inline colour and every
                        # dot would render grey/white instead of its
                        # status colour.
                        st.markdown(
                            f"**{meta['label']}** &nbsp; **{pct}%** &nbsp; "
                            f"<span style='color:{meta['color']} !important;font-size:1.1rem;'>●</span>"
                            f"&nbsp; <span style='color:#9CA3AF !important;font-size:0.8rem;'>({val})</span>",
                            unsafe_allow_html=True,
                        )
                        st.write("")

                st.write("")
                if st.button("View all projects →", key="view_all_projects", use_container_width=True):
                    st.session_state["admin_nav_override"] = "Projects"
                    st.rerun()

    with c2:
        with st.container(border=True):
            st.subheader("Team by Role")
            if users_resp.status_code != 200:
                show_api_error(users_resp)
            elif not users:
                st.info("No users found.")
            else:
                # Admin is the viewer of this dashboard, not a staffable
                # team member — exclude it so the breakdown reflects the
                # actual team (managers, employees, clients).
                team_users = [u for u in users if (u.get("role") or "").lower() != "admin"]

                st.metric("Total Members", len(team_users))
                st.write("")

                if not team_users:
                    st.caption("No non-admin team members yet.")
                else:
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
                        key="admin_team_role_filter",
                    )
                    st.caption(f"**{selected_role.title()}** ({role_counts[selected_role]}):")
                    for u in team_users:
                        if (u.get("role") or "") == selected_role:
                            st.markdown(f"- {u.get('name', '—')} · {u.get('email', '—')}")

    st.write("")

    left, right = st.columns([2, 1])

    with left:
        with st.container(border=True):
            st.subheader("Recent Activity")
            activity_items = []
            for t in sorted(tasks, key=lambda t: t.get("id", 0), reverse=True)[:4]:
                meta = STATUS_META.get(t.get("status") or "todo", STATUS_META["todo"])
                activity_items.append(
                    f"<span style='color:{meta['color']} !important;'>●</span> Task **{t['title']}** — {meta['label']}"
                )
            for d in documents[-2:]:
                activity_items.append(f"📄 Document **{d['filename']}** uploaded")
            if not activity_items:
                st.caption("No recent activity yet.")
            else:
                for item in reversed(activity_items):
                    st.markdown(item, unsafe_allow_html=True)
            st.caption("Built from live task/document data — add timestamps to your API for exact times.")

    with right:
        with st.container(border=True):
            st.subheader("Quick Actions")
            qa1, qa2 = st.columns(2)
            with qa1:
                if st.button("➕ Add Client", use_container_width=True):
                    st.session_state["admin_nav_override"] = "Clients"
                    st.rerun()
                if st.button("✅ Add Task", use_container_width=True):
                    st.session_state["admin_nav_override"] = "Tasks"
                    st.rerun()
            with qa2:
                if st.button("📁 Add Project", use_container_width=True):
                    st.session_state["admin_nav_override"] = "Projects"
                    st.rerun()
                if st.button("⬆️ Upload Doc", use_container_width=True):
                    st.session_state["admin_nav_override"] = "Documents"
                    st.rerun()


# --------------------------------------------------------------------------
# CLIENTS — view, add, edit, delete (admin: full control)
# --------------------------------------------------------------------------
def _client_status_meta(status_text):
    return CLIENT_STATUS_META.get((status_text or "").strip().lower(),
                                   {"icon": "⚪", "color": "#6B7280"})


def _client_status_donut(clients, height=320):
    counts = {}
    for c in clients:
        s = (c.get("status") or "unknown").lower()
        counts[s] = counts.get(s, 0) + 1
    labels = [s.title() for s in counts]
    values = list(counts.values())
    colors = [_client_status_meta(s)["color"] for s in counts]
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.68,
        marker=dict(colors=colors, line=dict(color="#131A2E", width=2)),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=f"<b style='font-size:28px;color:#F9FAFB'>{len(clients)}</b>"
                 f"<br><span style='font-size:12px;color:#9CA3AF'>Total Clients</span>",
            x=0.5, y=0.5, showarrow=False,
        )],
    )
    return fig, counts


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

    # Client Directory list removed — the "Client Details" dropdown below
    # already lets the admin look up any client. The donut chart now takes
    # the full-width space that used to be shared with the list.
    if not clients:
        st.info("No clients found for your organization yet. Add one below.")
    else:
        with st.container(border=True):
            st.subheader("By Status")
            fig, counts = _client_status_donut(clients)
            chart_col, legend_col = st.columns([1.3, 1])
            with chart_col:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            with legend_col:
                st.write("")
                for status, count in counts.items():
                    meta = _client_status_meta(status)
                    pct = round(100 * count / len(clients))
                    # Same label -> percentage -> colour-dot pattern as
                    # Projects Overview, with !important so the dot colour
                    # isn't overridden by the global span colour rule.
                    st.markdown(
                        f"**{status.title()}** &nbsp; **{pct}%** &nbsp; "
                        f"<span style='color:{meta['color']} !important;font-size:1.1rem;'>●</span>"
                        f"&nbsp; <span style='color:#9CA3AF !important;font-size:0.8rem;'>({count})</span>",
                        unsafe_allow_html=True,
                    )
                    st.write("")

    st.write("")

    # 🔎 Client Details — dropdown to pick any client and see its details.
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

    # "All Projects" list removed — the "Project Details" dropdown below
    # already lets the admin pick any project and see its full status,
    # deadline, task progress, documents, and team.
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
            # 1) Project
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

            # 2) Assign to (employee)
            assignee_labels = [label for label, _ in assignee_options]
            assignee_label = st.selectbox(
                "Assign to (employee)",
                assignee_labels,
                key="admin_create_task_assignee",
            )
            if not users_ok:
                st.caption("Could not load employees for assignment.")

            # 3) Title
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
                        key=f"admin_dl_{doc['id']}", use_container_width=True,
                    )
                else:
                    show_api_error(resp)
            with row[2]:
                if st.button("Preview", key=f"admin_view_{doc['id']}", use_container_width=True):
                    show_document_preview(token, doc)
            with row[3]:
                trigger_reindex(token, doc, key=f"admin_reindex_{doc['id']}")
            with row[4]:
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
# APP ENTRY
# --------------------------------------------------------------------------
def render_admin_app():
    _inject_dark_theme()

    with st.sidebar:
        render_sidebar_header()
        st.caption("MANAGEMENT")
        default_page = st.session_state.pop("admin_nav_override", "Dashboard")
        nav_options = ["Dashboard", "Clients", "Projects", "Tasks", "Documents", "Meetings"]
        page = st.radio(
            "Go to",
            nav_options,
            index=nav_options.index(default_page) if default_page in nav_options else 0,
            label_visibility="collapsed",
        )

    if page == "Dashboard":
        _render_admin_dashboard()
    elif page == "Clients":
        _render_admin_clients()
    elif page == "Projects":
        _render_admin_projects()
    elif page == "Tasks":
        _render_admin_tasks()
    elif page == "Documents":
        _render_admin_documents()
    elif page == "Meetings":
        _render_admin_meetings()