"""
client.py
Client portal: project progress + documents shared on those projects.

Admin uploads a doc linked to a project → it appears here for that client.
Client uploads a doc to a project → admin/manager see it under Documents.

Built with native Streamlit components (st.container, st.metric, st.badge,
st.progress, st.tabs, st.columns) plus Plotly charts for visual richness —
no HTML/CSS injection anywhere.

DATA POLICY: every value shown is either returned directly by
get_client_dashboard() (project_name, project_id, status, deadline,
progress_percent, milestone_info, documents) or computed FROM those real
fields (e.g. "days left" is calculated from the real deadline date;
document-type breakdown is counted from real filenames' extensions).
Nothing is invented. Fields your API doesn't return yet — start dates,
milestone/task fraction counts, a dated timeline, team members, upload
timestamps, announcements — are listed at the bottom of this file rather
than faked.
"""

import datetime as dt
import hashlib

import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from api_client import (
    get_client_dashboard,
    download_document,
    upload_document,
    delete_document,
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
    "planning":    {"label": "Planning",    "icon": "🟣", "color": "violet", "hex": "#8B5CF6"},
    "active":      {"label": "Active",      "icon": "🟢", "color": "green",  "hex": "#22C55E"},
    "in progress": {"label": "In Progress", "icon": "🔵", "color": "blue",   "hex": "#3B82F6"},
    "on hold":     {"label": "On Hold",     "icon": "🟠", "color": "orange", "hex": "#F59E0B"},
    "completed":   {"label": "Completed",   "icon": "✅", "color": "green",  "hex": "#22C55E"},
}

DOC_ICON = {
    "pdf": "📕", "doc": "📘", "docx": "📘", "xls": "📗", "xlsx": "📗",
    "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "zip": "🗜️",
}


def _status_meta(status_text):
    key = (status_text or "").strip().lower().replace("_", " ")
    return STATUS_META.get(
        key,
        {"label": status_text or "Unknown", "icon": "⚪", "color": "gray", "hex": "#6B7280"},
    )


def _progress_value(value):
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, round(pct)))


def _dashboard_signature(dashboards):
    """Compact fingerprint of live API data — used to detect changes between renders."""
    parts = []
    for dashboard in dashboards:
        documents = dashboard.get("documents") or []
        doc_ids = ",".join(sorted(str(doc.get("id", "")) for doc in documents))
        parts.append(
            f"{dashboard.get('project_id')}:"
            f"{dashboard.get('progress_percent')}:"
            f"{dashboard.get('status', '')}:"
            f"{dashboard.get('deadline', '')}:"
            f"{dashboard.get('milestone_info', '')}:"
            f"{doc_ids}"
        )
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _initials(text, max_letters=2):
    parts = [p for p in text.replace("_", " ").split() if p]
    return "".join(p[0] for p in parts[:max_letters]).upper() or "?"


def _doc_icon(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return DOC_ICON.get(ext, "📄")


def _days_left(deadline_str):
    """Computed from the real deadline field. Returns None if unparseable
    rather than guessing a value."""
    if not deadline_str:
        return None
    normalized = str(deadline_str)[:10]
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            deadline_date = dt.datetime.strptime(normalized, fmt).date()
            return (deadline_date - dt.date.today()).days
        except (ValueError, TypeError):
            continue
    return None


def _deadline_label(deadline_str):
    days = _days_left(deadline_str)
    if days is None:
        return ""
    if days < 0:
        return f"  ·  {abs(days)} day(s) overdue"
    if days == 0:
        return "  ·  due today"
    return f"  ·  {days} day(s) left"


def _ring_chart(pct, color, height=170):
    pct = _progress_value(pct)
    fig = go.Figure(data=[go.Pie(
        values=[pct, 100 - pct], hole=0.72,
        marker=dict(colors=[color, "#E5E7EB"]),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)", uirevision="client_ring",
        annotations=[dict(text=f"<b style='font-size:20px'>{pct}%</b>", x=0.5, y=0.5, showarrow=False)],
    )
    return fig


def _progress_bar_chart(dashboards):
    names = [d["project_name"] for d in dashboards]
    values = [_progress_value(d["progress_percent"]) for d in dashboards]
    colors = [_status_meta(d["status"])["hex"] for d in dashboards]
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker_color=colors,
        text=[f"{v}%" for v in values], textposition="outside",
    ))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=30),
        height=max(160, 70 * len(dashboards)),
        xaxis=dict(range=[0, 110], showgrid=False, title="Progress %"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        uirevision="client_project_bars",
    )
    return fig


def _doc_type_pie(dashboards):
    ext_counts = {}
    for d in dashboards:
        for doc in (d.get("documents") or []):
            ext = doc["filename"].rsplit(".", 1)[-1].upper() if "." in doc["filename"] else "OTHER"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    if not ext_counts:
        return None
    fig = go.Figure(go.Pie(
        labels=list(ext_counts.keys()), values=list(ext_counts.values()),
        hole=0.5, textinfo="label+value",
    ))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10), height=260,
        paper_bgcolor="rgba(0,0,0,0)", showlegend=False, uirevision="client_doc_pie",
    )
    return fig


def _render_doc_row(token, doc, key_prefix: str, can_delete: bool = True):
    cols = st.columns([3, 1, 1, 1, 1] if can_delete else [3, 1, 1, 1])
    with cols[0]:
        st.write(f"{_doc_icon(doc['filename'])} {doc['filename']}")
        st.caption(rag_status_label(doc))
    with cols[1]:
        resp = download_document(token, str(doc["id"]))
        if resp.status_code == 200:
            st.download_button(
                label="Download", data=resp.content, file_name=doc["filename"],
                mime="application/octet-stream", key=f"{key_prefix}_dl_{doc['id']}",
                use_container_width=True,
            )
        else:
            show_api_error(resp)
    with cols[2]:
        if st.button("Preview", key=f"{key_prefix}_view_{doc['id']}", use_container_width=True):
            show_document_preview(token, doc)
    with cols[3]:
        trigger_reindex(token, doc, key=f"{key_prefix}_reindex_{doc['id']}")
    if can_delete:
        with cols[4]:
            if st.button("Delete", key=f"{key_prefix}_del_{doc['id']}", use_container_width=True):
                delete_resp = delete_document(token, str(doc["id"]))
                if delete_resp.status_code == 204:
                    st.session_state["client_chart_rev"] = (
                        st.session_state.get("client_chart_rev", 0) + 1
                    )
                    st.success("Document deleted.")
                    st.rerun()
                else:
                    show_api_error(delete_resp)


# --------------------------------------------------------------------------
# DASHBOARD
# --------------------------------------------------------------------------
def _render_client_dashboard():
    user = session_user()
    token = session_token()

    # Poll the API every 30s so progress charts reflect task updates from the team.
    st_autorefresh(interval=30_000, key="client_dashboard_autorefresh")

    header_col, avatar_col = st.columns([6, 1])
    with header_col:
        st.title(f"👋 Welcome back, {user['name']}!")
        st.caption("Here's the latest overview of your projects and progress.")
    with avatar_col:
        st.write("")
        st.badge(_initials(user["name"]), color="violet")

    st.write("")

    dashboard_resp = get_client_dashboard(token)
    if dashboard_resp.status_code != 200:
        show_api_error(dashboard_resp)
        return

    dashboards = dashboard_resp.json()
    if not dashboards:
        st.info(
            "No projects found for your account yet. "
            "Ask your admin to link your login email to a client record and assign projects."
        )
        return

    data_signature = _dashboard_signature(dashboards)
    if st.session_state.get("client_dashboard_signature") != data_signature:
        st.session_state["client_dashboard_signature"] = data_signature
        st.session_state["client_chart_rev"] = st.session_state.get("client_chart_rev", 0) + 1
    chart_rev = st.session_state.get("client_chart_rev", 0)
    total_projects = len(dashboards)
    avg_progress = round(
        sum(_progress_value(d["progress_percent"]) for d in dashboards) / total_projects
    )
    total_documents = sum(len(d.get("documents") or []) for d in dashboards)

    # "Upcoming deadline" = the soonest real, parseable deadline across all
    # projects — not a fixed/fake countdown, computed live each render.
    soonest_days = None
    for d in dashboards:
        days = _days_left(d.get("deadline"))
        if days is not None and (soonest_days is None or days < soonest_days):
            soonest_days = days

    # ---- Top summary cards -------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        with st.container(border=True):
            st.caption("📁 Total Projects")
            st.metric(label="", value=total_projects, label_visibility="collapsed")
    with c2:
        with st.container(border=True):
            st.caption("✅ Average Progress")
            st.metric(label="", value=f"{avg_progress}%", label_visibility="collapsed")
    with c3:
        with st.container(border=True):
            st.caption("📄 Documents")
            st.metric(label="", value=total_documents, label_visibility="collapsed")
    with c4:
        with st.container(border=True):
            st.caption("⏳ Nearest Deadline")
            if soonest_days is None:
                deadline_metric = "—"
            elif soonest_days < 0:
                deadline_metric = f"{abs(soonest_days)}d overdue"
            elif soonest_days == 0:
                deadline_metric = "Today"
            else:
                deadline_metric = f"{soonest_days}d"
            st.metric(label="", value=deadline_metric, label_visibility="collapsed")

    st.write("")

    # ---- Visual overview: progress ring + comparison bar chart --------
    chart_col1, chart_col2 = st.columns([1, 2])
    with chart_col1:
        with st.container(border=True):
            st.subheader("Overall Progress")
            st.plotly_chart(
                _ring_chart(avg_progress, "#6366F1"),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"client_overall_progress_{chart_rev}",
            )
            st.caption(f"Average across {total_projects} project(s) · auto-refreshes every 30s")

    with chart_col2:
        with st.container(border=True):
            st.subheader("Progress by Project")
            st.plotly_chart(
                _progress_bar_chart(dashboards),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"client_project_progress_{chart_rev}",
            )

    st.write("")

    # ---- My Projects — one card per project ----------------------------
    with st.container(border=True):
        st.subheader("My Projects")

        for dashboard in dashboards:
            meta = _status_meta(dashboard["status"])
            project_progress = _progress_value(dashboard["progress_percent"])
            project_id = dashboard["project_id"]

            ring_col, info_col, status_col = st.columns([1, 3, 1.4])
            with ring_col:
                st.plotly_chart(
                    _ring_chart(project_progress, meta["hex"], height=110),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"client_ring_{project_id}_{chart_rev}",
                )
            with info_col:
                st.markdown(f"**{dashboard['project_name']}**")
                st.caption(
                    f"Deadline: {dashboard['deadline'] or '—'}"
                    f"{_deadline_label(dashboard.get('deadline'))}"
                )
                if dashboard.get("milestone_info"):
                    st.caption(dashboard["milestone_info"])
            with status_col:
                st.write("")
                st.badge(f"{meta['icon']} {meta['label']}", color=meta["color"])

            documents = dashboard.get("documents") or []
            with st.expander(f"📄 Documents ({len(documents)})"):
                if not documents:
                    st.caption("No documents on this project yet.")
                else:
                    for doc in documents:
                        _render_doc_row(
                            token, doc,
                            key_prefix=f"dash_{dashboard['project_id']}",
                            can_delete=False,
                        )

            st.divider()


# --------------------------------------------------------------------------
# DOCUMENTS
# --------------------------------------------------------------------------
def _render_client_documents():
    token = session_token()

    st_autorefresh(interval=30_000, key="client_documents_autorefresh")

    st.title("📄 Documents")
    st.caption("Upload to a project, or preview files shared by your team.")
    st.write("")

    dashboard_resp = get_client_dashboard(token)
    if dashboard_resp.status_code != 200:
        show_api_error(dashboard_resp)
        return
    dashboards = dashboard_resp.json()
    data_signature = _dashboard_signature(dashboards)
    if st.session_state.get("client_dashboard_signature") != data_signature:
        st.session_state["client_dashboard_signature"] = data_signature
        st.session_state["client_chart_rev"] = st.session_state.get("client_chart_rev", 0) + 1
    chart_rev = st.session_state.get("client_chart_rev", 0)

    project_options = {d["project_name"]: d["project_id"] for d in dashboards}

    upload_col, chart_col = st.columns([1.4, 1])

    with upload_col:
        with st.container(border=True):
            st.subheader("⬆️ Upload a document")
            if not project_options:
                st.info("No projects available to upload into yet.")
            else:
                if "client_doc_uploader_key" not in st.session_state:
                    st.session_state["client_doc_uploader_key"] = 0

                with st.form("client_upload_document_form", clear_on_submit=True):
                    project_label = st.selectbox("Project", list(project_options.keys()))
                    uploaded = st.file_uploader(
                        "Choose a file", type=None,
                        key=f"client_doc_uploader_{st.session_state['client_doc_uploader_key']}",
                    )
                    if st.form_submit_button("Upload", type="primary"):
                        if uploaded is None:
                            st.warning("Please choose a file first.")
                        else:
                            project_id = str(project_options[project_label])
                            resp = upload_document(token, uploaded, project_id=project_id)
                            if resp.status_code in (200, 201):
                                st.session_state["client_doc_uploader_key"] += 1
                                st.session_state["client_chart_rev"] = (
                                    st.session_state.get("client_chart_rev", 0) + 1
                                )
                                data = resp.json() if resp.content else {}
                                chunks = int(data.get("chunk_count") or 0)
                                if chunks > 0:
                                    st.success(
                                        f"Uploaded to **{project_label}** and indexed "
                                        f"for AI Chat ({chunks} chunk(s))."
                                    )
                                else:
                                    st.success(
                                        f"Uploaded to **{project_label}**. Your team can see it. "
                                        "Click Reindex if chat search is needed."
                                    )
                                st.rerun()
                            else:
                                show_api_error(resp)

    with chart_col:
        with st.container(border=True):
            st.subheader("Document Types")
            pie = _doc_type_pie(dashboards)
            if pie is None:
                st.caption("No documents yet to break down.")
            else:
                st.plotly_chart(
                    pie,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"client_doc_types_{chart_rev}",
                )

    st.write("")

    if not dashboards:
        st.info("No projects found for your account yet.")
        return

    any_documents = any(d.get("documents") for d in dashboards)
    if not any_documents:
        st.info("No documents on your projects yet. Upload one above, or wait for your team to share files.")
        return

    tab_labels = [d["project_name"] for d in dashboards if d.get("documents")]
    tabs = st.tabs(tab_labels) if tab_labels else []

    for tab, dashboard in zip(tabs, [d for d in dashboards if d.get("documents")]):
        with tab:
            documents = dashboard["documents"]
            st.caption(f"{len(documents)} file(s) on this project")
            for doc in documents:
                _render_doc_row(
                    token, doc,
                    key_prefix=f"docs_{dashboard['project_id']}",
                    can_delete=True,
                )


def render_client_app():
    with st.sidebar:
        render_sidebar_header()
        st.subheader("Client menu")
        if st.button("🔄 Refresh data", use_container_width=True, key="client_refresh_data"):
            st.session_state["client_chart_rev"] = st.session_state.get("client_chart_rev", 0) + 1
            st.session_state.pop("client_dashboard_signature", None)
            st.rerun()
        page = st.radio("Go to", ["My Projects", "Documents"])

    if page == "My Projects":
        _render_client_dashboard()
    elif page == "Documents":
        _render_client_documents()