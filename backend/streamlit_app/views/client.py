"""
client.py
Client portal: project progress + documents shared on those projects.

DATA POLICY: every value shown is either returned directly by
get_client_dashboard() (project_name, project_id, status, deadline,
progress_percent, milestone_info, documents) or computed FROM those real
fields. Nothing is invented. There is NO Recent Updates feed, NO Project
Timeline stepper, and NO Storage Used meter, because the API does not
return that data.

Streamlit 1.37.1 does not support key= on st.container(border=True), so
per-card styling uses an invisible "card-anchor" marker + CSS :has()
selector to target the right bordered wrapper.
"""

import datetime as dt

import streamlit as st
import plotly.graph_objects as go

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
    rag_index_caption,
)

SHOW_DEMO_DASHBOARD = True

CLIENT_NAV_KEY = "client_nav_radio"
NAV_PAGES = ["My Projects", "Documents"]
ALL_PROJECTS_LABEL = "All Projects"

STATUS_META = {
    "in progress": {"icon": "🔵", "color": "blue", "hex": "#3B82F6"},
    "in_progress": {"icon": "🔵", "color": "blue", "hex": "#3B82F6"},
    "planning": {"icon": "🟣", "color": "violet", "hex": "#8B5CF6"},
    "active": {"icon": "🟢", "color": "green", "hex": "#22C55E"},
    "on_hold": {"icon": "🟠", "color": "orange", "hex": "#F59E0B"},
    "completed": {"icon": "🟢", "color": "green", "hex": "#22C55E"},
}

DOC_ICON = {
    "pdf": "📕", "doc": "📘", "docx": "📘", "xls": "📗", "xlsx": "📗",
    "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "zip": "🗜️",
}

DOC_TYPE_PILL = {
    "pdf": ("PDF", "pill-red"),
    "doc": ("DOC", "pill-blue"), "docx": ("DOCX", "pill-blue"),
    "xls": ("XLS", "pill-green"), "xlsx": ("XLSX", "pill-green"),
    "png": ("IMG", "pill-gray"), "jpg": ("IMG", "pill-gray"), "jpeg": ("IMG", "pill-gray"),
    "zip": ("ZIP", "pill-gray"),
}

CHART_COLORS = {
    "indigo": "#6366F1", "green": "#22C55E", "amber": "#F59E0B",
    "red": "#EF4444", "pink": "#EC4899", "teal": "#14B8A6", "violet": "#8B5CF6",
    "blue": "#2563EB", "grid": "#E5E7EB", "text": "#111827",
}

DEMO_DASHBOARDS = [
    {
        "project_id": "demo-1",
        "project_name": "AI Project OS",
        "status": "in_progress",
        "deadline": (dt.date.today() + dt.timedelta(days=39)).strftime("%Y-%m-%d"),
        "progress_percent": 70,
        "milestone_info": "Testing Dashboard UI",
        "documents": [],
    }
]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _status_meta(status_text):
    return STATUS_META.get(
        (status_text or "").strip().lower(),
        {"icon": "⚪", "color": "gray", "hex": "#6B7280"},
    )


def _effective_progress(dashboard):
    """Completed projects always read 100%, regardless of a stale stored
    progress_percent value. Every other status uses the real stored value."""
    if (dashboard.get("status") or "").strip().lower() == "completed":
        return 100
    return dashboard.get("progress_percent", 0)


def _initials(text, max_letters=2):
    parts = [p for p in text.replace("_", " ").split() if p]
    return "".join(p[0] for p in parts[:max_letters]).upper() or "?"


def _doc_ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _doc_icon(filename):
    return DOC_ICON.get(_doc_ext(filename), "📄")


def _pill_html(text, cls):
    return "<span class='pill " + cls + "'>" + text + "</span>"


def _doc_type_pill_html(filename):
    ext = _doc_ext(filename)
    label, cls = DOC_TYPE_PILL.get(ext, (ext.upper() or "FILE", "pill-gray"))
    return _pill_html(label, cls)


def _days_left(deadline_str):
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            deadline_date = dt.datetime.strptime(str(deadline_str)[:10], fmt).date()
            return (deadline_date - dt.date.today()).days
        except (ValueError, TypeError):
            continue
    return None


def _deadline_pill(days):
    if days is None:
        return "No deadline", "pill-gray"
    if days < 0:
        return "Overdue", "pill-red"
    if days <= 3:
        return "Soon", "pill-orange"
    return "On track", "pill-green"


def _card_anchor(name):
    st.markdown(
        "<span class='card-anchor card-anchor-" + name + "'></span>",
        unsafe_allow_html=True,
    )


def _icon_badge(icon, bg, fg="#111827"):
    st.markdown(
        "<div class='icon-badge' style='background:" + bg + ";'>"
        "<span style='color:" + fg + ";'>" + icon + "</span></div>",
        unsafe_allow_html=True,
    )


def _section_heading(icon, title):
    st.markdown(
        "<div class='section-heading'><div class='bar'></div>" + icon + " " + title + "</div>",
        unsafe_allow_html=True,
    )


def _go_to_documents():
    st.session_state[CLIENT_NAV_KEY] = "Documents"


# --------------------------------------------------------------------------
# THEME
# --------------------------------------------------------------------------
def _inject_client_light_theme():
    # Base palette is set in .streamlit/config.toml (base=light). This CSS
    # keeps client-specific card gradients, pills, and section chrome.
    css_lines = [
        "<style>",
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');",
        "html, body, [class*='css'] { font-family: 'Inter', sans-serif; }",
        "",
        ".stApp { background: linear-gradient(180deg, #F8F9FF 0%, #F5F6FA 100%); }",
        ".block-container { padding-top: 1.5rem; padding-bottom: 3rem; }",
        "",
        "header[data-testid='stHeader'] { background: #F8F9FF !important; }",
        "header[data-testid='stHeader'] * { color: #111827 !important; }",
        "",
        "h1, h2, h3, h4, h5, h6, p, span, label, li, div, .stMarkdown { color: #111827 !important; }",
        "[data-testid='stMarkdownContainer'], [data-testid='stMarkdownContainer'] * { color: #111827 !important; }",
        "[data-testid='stCaptionContainer'], [data-testid='stCaptionContainer'] * { color: #6B7280 !important; }",
        "",
        "section[data-testid='stSidebar'] { background: #FFFFFF; border-right: 1px solid #EEF0F3; }",
        "section[data-testid='stSidebar'] * { color: #374151 !important; }",
        "section[data-testid='stSidebar'] code {",
        "    background: #E0E7FF !important; color: #312E81 !important;",
        "    border: 1px solid #C7D2FE !important; border-radius: 5px !important; padding: 2px 6px !important;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] { display: flex; flex-direction: column; gap: 2px; }",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label {",
        "    border-radius: 8px; padding: 9px 12px !important; margin: 0 !important; cursor: pointer;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:hover { background-color: #F3F4F6; }",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) {",
        "    background-color: #EEF2FF !important; border-left: 3px solid #4F46E5 !important;",
        "}",
        "section[data-testid='stSidebar'] div[role='radiogroup'] label:has(input:checked) * {",
        "    color: #4338CA !important; font-weight: 600;",
        "}",
        "",
        "div[data-testid='stVerticalBlockBorderWrapper'] {",
        "    background-color: #FFFFFF !important;",
        "    border: 1px solid #EEF0F3 !important;",
        "    border-radius: 18px !important;",
        "    box-shadow: 0 2px 8px rgba(17,24,39,0.06) !important;",
        "    transition: transform 0.2s ease, box-shadow 0.2s ease !important;",
        "    padding: 0.35rem;",
        "}",
        "div[data-testid='stVerticalBlockBorderWrapper']:hover {",
        "    box-shadow: 0 12px 24px rgba(17,24,39,0.12) !important;",
        "}",
        "",
        ".card-anchor { display: none; }",
        "",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-welcome_header) {",
        "    background: linear-gradient(135deg, #EEF2FF 0%, #FDF2F8 100%) !important;",
        "    border: none !important; padding: 1.5rem !important;",
        "}",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-stat_total_projects) {",
        "    background: linear-gradient(135deg,#FFFFFF 0%,#EEF2FF 100%) !important; border-left: 4px solid #6366F1 !important;",
        "}",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-stat_avg_progress) {",
        "    background: linear-gradient(135deg,#FFFFFF 0%,#ECFDF5 100%) !important; border-left: 4px solid #22C55E !important;",
        "}",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-stat_documents) {",
        "    background: linear-gradient(135deg,#FFFFFF 0%,#EFF6FF 100%) !important; border-left: 4px solid #3B82F6 !important;",
        "}",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-stat_deadline) {",
        "    background: linear-gradient(135deg,#FFFFFF 0%,#FEF3C7 100%) !important; border-left: 4px solid #F59E0B !important;",
        "}",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-hero) { border-left: 4px solid #6366F1 !important; }",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-chart_bar) { border-left: 4px solid #2563EB !important; }",
        "div[data-testid='stVerticalBlockBorderWrapper']:has(.card-anchor-chart_deadline) { border-left: 4px solid #EC4899 !important; }",
        "",
        ".icon-badge {",
        "    width: 48px; height: 48px; border-radius: 14px;",
        "    display: flex; align-items: center; justify-content: center;",
        "    font-size: 1.4rem;",
        "    box-shadow: inset 0 1px 2px rgba(255,255,255,0.6), 0 2px 4px rgba(17,24,39,0.06);",
        "}",
        "",
        ".pill {",
        "    display: inline-block; padding: 3px 10px; border-radius: 999px;",
        "    font-size: 0.75rem; font-weight: 600; white-space: nowrap;",
        "    box-shadow: 0 1px 2px rgba(0,0,0,0.04); letter-spacing: 0.2px;",
        "}",
        ".pill-red    { background:#FEE2E2; color:#B91C1C; }",
        ".pill-orange { background:#FEF3C7; color:#B45309; }",
        ".pill-green  { background:#DCFCE7; color:#15803D; }",
        ".pill-blue   { background:#DBEAFE; color:#1D4ED8; }",
        ".pill-gray   { background:#F3F4F6; color:#374151; }",
        "",
        ".section-heading {",
        "    font-size: 1.4rem; font-weight: 800; color: #111827;",
        "    margin: 1.2rem 0 0.8rem 0; display:flex; align-items:center; gap:10px;",
        "}",
        ".section-heading .bar { width: 5px; height: 24px; border-radius: 3px; background: linear-gradient(180deg,#6366F1,#EC4899); }",
        "",
        ".meta-row {",
        "    display: flex; align-items: center; gap: 10px;",
        "    background: #F9FAFB; border-radius: 10px; padding: 10px 14px;",
        "    margin-top: 8px; font-size: 13px; color: #374151;",
        "    border: 1px solid #F3F4F6;",
        "}",
        ".meta-row b { color: #111827; }",
        "",
        ".stat-label { font-size: 0.85rem; color: #6B7280; margin-top: 8px; }",
        ".stat-value { font-size: 1.9rem; font-weight: 800; }",
        "",
        ".demo-banner {",
        "    background: linear-gradient(90deg, #EEF2FF 0%, #F5F3FF 100%);",
        "    border: 1px solid #C7D2FE; border-left: 4px solid #6366F1;",
        "    border-radius: 12px; padding: 14px 18px; color: #4338CA;",
        "    font-weight: 500; margin-bottom: 1rem; user-select: none;",
        "}",
        "",
        ".stButton button {",
        "    background-color: #FFFFFF; color: #374151;",
        "    border: 1px solid #E5E7EB; border-radius: 8px;",
        "}",
        ".stButton button:hover { border-color: #4F46E5; color: #4338CA; }",
        ".stButton button[kind='primary'] { background-color: #4F46E5; color: #FFFFFF !important; border: 1px solid #4F46E5; }",
        ".stButton button[kind='primary']:hover { background-color: #4338CA; border-color: #4338CA; }",
        "",
        ".stProgress > div > div > div > div { border-radius: 6px; background-color: #6366F1; }",
        ".stProgress > div > div { background-color: #F3F4F6; border-radius: 6px; }",
        "",
        "[data-testid='stFileUploaderDropzone'] {",
        "    background-color: #F9FAFB !important;",
        "    border: 1.5px dashed #D1D5DB !important;",
        "    border-radius: 12px !important;",
        "}",
        "[data-testid='stFileUploaderDropzone'] * { color: #374151 !important; }",
        "[data-testid='stFileUploaderDropzone'] button {",
        "    background-color: #FFFFFF !important;",
        "    border: 1px solid #E5E7EB !important;",
        "    color: #374151 !important;",
        "}",
        "[data-testid='stFileUploaderDropzone'] svg { fill: #6B7280 !important; }",
        "</style>",
    ]
    st.markdown("\n".join(css_lines), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# CHARTS
# --------------------------------------------------------------------------
def _ring_chart(pct, color=None, height=170):
    ring_color = color or CHART_COLORS["teal"]
    fig = go.Figure(data=[go.Pie(
        values=[pct, 100 - pct], hole=0.70,
        marker=dict(colors=[ring_color, "#F1F5F9"], line=dict(color="#FFFFFF", width=3)),
        textinfo="none", sort=False, direction="clockwise",
    )])
    fig.update_layout(
        showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text="<b style='font-size:24px;color:" + ring_color + "'>" + str(pct) + "%</b>",
            x=0.5, y=0.5, showarrow=False,
        )],
    )
    return fig


def _progress_bar_chart(dashboards):
    """'Project Progress' -- a clean line chart (no fill), with a
    synthetic 'Start' anchor point only when there's exactly 1 project,
    so a real line is visible instead of a single floating dot."""
    names = [d["project_name"] for d in dashboards]
    values = [_effective_progress(d) for d in dashboards]
    colors = [_status_meta(d["status"])["hex"] for d in dashboards]

    if len(dashboards) == 1:
        names = ["Start"] + names
        values = [0] + values
        colors = ["#E5E7EB"] + colors

    textposition = ["bottom center" if v >= 90 else "top center" for v in values]
    text_labels = [f"{v}%" for v in values]
    if len(dashboards) == 1:
        text_labels[0] = ""  # don't label the synthetic "Start" point

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=names, y=values, mode="lines+markers+text",
        line=dict(color=CHART_COLORS["blue"], width=4, shape="spline"),
        marker=dict(size=16, color=colors, line=dict(color="#FFFFFF", width=3)),
        text=text_labels,
        textposition=textposition,
        textfont=dict(color=CHART_COLORS["text"], size=13, family="Inter"),
    ))
    fig.update_layout(
        margin=dict(t=50, b=10, l=10, r=10),
        height=max(240, 70 * len(dashboards)),
        xaxis=dict(color="#374151", tickfont=dict(color="#374151", size=13), showgrid=False),
        yaxis=dict(range=[0, 115], autorange=False, color="#374151",
                   tickfont=dict(color="#374151", size=13), showgrid=True,
                   gridcolor=CHART_COLORS["grid"], griddash="dash", title="Progress %"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#374151"),
    )
    fig.update_yaxes(range=[0, 115], autorange=False)
    return fig


def _deadline_urgency_chart(dashboards):
    """'Deadline Urgency' -- vertical bars growing from a 0 baseline,
    color-coded red (overdue) / amber (due soon) / green (comfortable)."""
    names = [d["project_name"] for d in dashboards]
    days_values = []
    for d in dashboards:
        days = _days_left(d.get("deadline"))
        days_values.append(days if days is not None else 0)

    colors = []
    for days in days_values:
        if days < 0:
            colors.append(CHART_COLORS["red"])
        elif days <= 7:
            colors.append(CHART_COLORS["amber"])
        else:
            colors.append(CHART_COLORS["green"])

    labels = [(f"{d}d overdue" if d < 0 else f"{d}d left") for d in days_values]

    fig = go.Figure(go.Bar(
        x=names, y=days_values, orientation="v",
        marker=dict(color=colors, line=dict(color="#FFFFFF", width=1)),
        text=labels, textposition="outside",
        textfont=dict(color="#374151", size=13),
        width=0.45,
    ))

    min_val = min(days_values + [0])
    max_val = max(days_values + [1])
    padding = max(3, int((max_val - min_val) * 0.3))

    fig.update_layout(
        margin=dict(t=30, b=10, l=10, r=10),
        height=280,
        yaxis=dict(
            range=[min_val - padding, max_val + padding],
            color="#374151", tickfont=dict(color="#374151", size=13),
            showgrid=True, gridcolor=CHART_COLORS["grid"], griddash="dash",
            title="Days left", zeroline=True, zerolinecolor="#9CA3AF",
            zerolinewidth=2, autorange=False,
        ),
        xaxis=dict(color="#374151", tickfont=dict(color="#374151", size=13)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#374151"),
    )
    return fig


def _doc_type_pie(dashboards):
    ext_counts = {}
    for d in dashboards:
        for doc in (d.get("documents") or []):
            ext = _doc_ext(doc["filename"]).upper() or "OTHER"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    if not ext_counts:
        return None
    palette = [CHART_COLORS["indigo"], CHART_COLORS["teal"], CHART_COLORS["amber"],
               CHART_COLORS["pink"], CHART_COLORS["violet"], "#06B6D4"]
    total = sum(ext_counts.values())
    fig = go.Figure(go.Pie(
        labels=list(ext_counts.keys()), values=list(ext_counts.values()),
        hole=0.6, textinfo="percent", textfont=dict(size=12, color="#FFFFFF"),
        marker=dict(colors=palette, line=dict(color="#FFFFFF", width=3)),
    ))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10), height=260,
        paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5,
                    font=dict(color=CHART_COLORS["text"], size=11)),
        font=dict(color=CHART_COLORS["text"]),
        annotations=[dict(
            text="<b style='font-size:20px;color:#111827'>" + str(total) + "</b>"
                 "<br><span style='font-size:11px;color:#6B7280'>Total Docs</span>",
            x=0.5, y=0.5, showarrow=False,
        )],
    )
    return fig


# --------------------------------------------------------------------------
# DOCUMENT ROW (Reindex button removed — only Download / Preview / Delete)
# --------------------------------------------------------------------------
def _render_doc_row(token, doc, key_prefix, can_delete=True):
    cols = st.columns([3, 1, 1, 1] if can_delete else [3, 1, 1])
    with cols[0]:
        st.markdown(
            "<span style='display:inline-flex; align-items:center; justify-content:center; "
            "width:28px; height:28px; border-radius:8px; background:#F3F4F6; "
            "margin-right:6px;'>" + _doc_icon(doc["filename"]) + "</span>" + doc["filename"],
            unsafe_allow_html=True,
        )
        st.caption(rag_index_caption(doc))
    with cols[1]:
        resp = download_document(token, str(doc["id"]))
        if resp.status_code == 200:
            st.download_button(
                label="Download", data=resp.content, file_name=doc["filename"],
                mime="application/octet-stream", key=key_prefix + "_dl_" + str(doc["id"]),
                width="stretch",
            )
        else:
            show_api_error(resp)
    with cols[2]:
        if st.button("Preview", key=key_prefix + "_view_" + str(doc["id"]), width="stretch"):
            show_document_preview(token, doc)
    if can_delete:
        with cols[3]:
            if st.button("Delete", key=key_prefix + "_del_" + str(doc["id"]), width="stretch"):
                delete_resp = delete_document(token, str(doc["id"]))
                if delete_resp.status_code == 204:
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

    with st.container(border=True):
        _card_anchor("welcome_header")
        header_col, avatar_col = st.columns([6, 1])
        with header_col:
            st.title("👋 Welcome back, " + user["name"] + "!")
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
    using_demo = False

    if not dashboards:
        if SHOW_DEMO_DASHBOARD:
            using_demo = True
            dashboards = DEMO_DASHBOARDS
            st.markdown(
                "<div class='demo-banner'>ℹ️ No projects assigned yet — showing a "
                "demo dashboard so you can preview the layout.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No projects found for your account yet.")
            return

    # ---- Project selector dropdown ----
    project_names = [ALL_PROJECTS_LABEL] + [d["project_name"] for d in dashboards]
    selected_project_name = st.selectbox(
        "📁 Project", project_names, key="client_project_selector",
    )

    if selected_project_name == ALL_PROJECTS_LABEL:
        active_dashboards = dashboards
        show_remaining_list = True
    else:
        active_dashboards = [d for d in dashboards if d["project_name"] == selected_project_name]
        show_remaining_list = False

    st.caption("Showing data for: **" + selected_project_name + "**")
    st.write("")

    total_projects = len(active_dashboards)
    avg_progress = round(sum(_effective_progress(d) for d in active_dashboards) / total_projects)
    total_documents = sum(len(d.get("documents") or []) for d in active_dashboards)

    soonest_days = None
    for d in active_dashboards:
        days = _days_left(d.get("deadline"))
        if days is not None and (soonest_days is None or days < soonest_days):
            soonest_days = days

    def _stat_card(icon, label, value, sublabel, accent, anchor):
        with st.container(border=True):
            _card_anchor(anchor)
            _icon_badge(icon, "#FFFFFF", fg=accent)
            st.markdown("<div class='stat-label'>" + label + "</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='stat-value' style='color:" + accent + " !important;'>" + str(value) + "</div>",
                unsafe_allow_html=True,
            )
            st.caption(sublabel)
            st.markdown(
                "<svg width='100%' height='24' viewBox='0 0 100 24' preserveAspectRatio='none'>"
                "<path d='M0,18 Q15,6 30,14 T60,10 T100,4' stroke='" + accent + "' "
                "stroke-width='2' fill='none' opacity='0.5'/></svg>",
                unsafe_allow_html=True,
            )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("📁", "Total Projects", total_projects, "All ongoing projects",
                    CHART_COLORS["indigo"], "stat_total_projects")
    with c2:
        _stat_card("✅", "Average Progress", str(avg_progress) + "%", "Across all projects",
                    CHART_COLORS["green"], "stat_avg_progress")
    with c3:
        _stat_card("📄", "Documents", total_documents, "Total documents",
                    "#3B82F6", "stat_documents")
    with c4:
        _stat_card(
            "⏳", "Nearest Deadline",
            (str(soonest_days) + "d") if soonest_days is not None else "—", "Upcoming",
            CHART_COLORS["amber"], "stat_deadline",
        )

    st.write("")

    def _sort_key(d):
        days = _days_left(d.get("deadline"))
        return days if days is not None else 9999

    ordered_dashboards = sorted(active_dashboards, key=_sort_key)
    hero = ordered_dashboards[0]
    rest = ordered_dashboards[1:]

    _section_heading("📌", "Project Overview")
    with st.container(border=True):
        _card_anchor("hero")
        meta = _status_meta(hero["status"])
        hero_days = _days_left(hero.get("deadline"))
        hero_progress = _effective_progress(hero)

        ring_col, info_col = st.columns([1, 2])
        with ring_col:
            st.plotly_chart(
                _ring_chart(hero_progress, meta["hex"], height=190),
                width="stretch", config={"displayModeBar": False}, key="hero_ring",
            )
            st.caption("Completed")
        with info_col:
            status_label = meta["icon"] + " " + hero["status"].replace("_", " ").title()
            st.markdown(_pill_html(status_label, "pill-blue"), unsafe_allow_html=True)
            st.markdown("### " + hero["project_name"])

            deadline_line = "<div class='meta-row'>📅 Deadline &nbsp; <b>" + str(hero.get("deadline", "—")) + "</b>"
            if hero_days is not None:
                deadline_line += " &nbsp;·&nbsp; " + str(hero_days) + " day(s) remaining"
            deadline_line += "</div>"
            st.markdown(deadline_line, unsafe_allow_html=True)

            if hero.get("milestone_info"):
                st.markdown(
                    "<div class='meta-row'>🎯 Current Milestone &nbsp; <b>" + hero["milestone_info"] + "</b></div>",
                    unsafe_allow_html=True,
                )

            pill_text, pill_cls = _deadline_pill(hero_days)
            st.markdown(_pill_html(pill_text, pill_cls), unsafe_allow_html=True)

        hero_docs = hero.get("documents") or []
        with st.expander("📄 Documents (" + str(len(hero_docs)) + ")"):
            if not hero_docs:
                st.caption("No documents on this project yet.")
            elif not using_demo:
                for doc in hero_docs:
                    _render_doc_row(token, doc, key_prefix="hero_" + str(hero["project_id"]), can_delete=False)

    st.write("")

    if rest and not using_demo and show_remaining_list:
        _section_heading("📁", "My Projects")
        for dashboard in rest:
            meta = _status_meta(dashboard["status"])
            days_left = _days_left(dashboard.get("deadline"))
            progress = _effective_progress(dashboard)

            with st.container(border=True):
                _card_anchor("proj_" + str(dashboard["project_id"]))
                st.markdown(
                    "<div style='height:4px; border-radius:2px; background:" + meta["hex"] + "; "
                    "margin-bottom:10px;'></div>",
                    unsafe_allow_html=True,
                )
                title_col, badge_col = st.columns([3, 1.4])
                with title_col:
                    st.markdown("📁 **" + dashboard["project_name"] + "**")
                with badge_col:
                    status_label = meta["icon"] + " " + dashboard["status"].replace("_", " ").title()
                    st.markdown(_pill_html(status_label, "pill-blue"), unsafe_allow_html=True)

                dl_col, dr_col, pr_col = st.columns(3)
                with dl_col:
                    st.caption("DEADLINE")
                    st.markdown("**" + str(dashboard.get("deadline", "—")) + "**")
                with dr_col:
                    st.caption("DAYS REMAINING")
                    st.markdown(("**" + str(days_left) + " day(s)**") if days_left is not None else "**—**")
                with pr_col:
                    st.caption("PROGRESS")
                    st.markdown("**" + str(progress) + "%**")

                pill_text, pill_cls = _deadline_pill(days_left)
                st.markdown(_pill_html(pill_text, pill_cls), unsafe_allow_html=True)
                st.write("")
                st.progress(progress / 100)

                if dashboard.get("milestone_info"):
                    st.caption(dashboard["milestone_info"])

                documents = dashboard.get("documents") or []
                with st.expander("📄 Documents (" + str(len(documents)) + ")"):
                    if not documents:
                        st.caption("No documents on this project yet.")
                    else:
                        for doc in documents:
                            _render_doc_row(
                                token, doc,
                                key_prefix="dash_" + str(dashboard["project_id"]),
                                can_delete=False,
                            )
            st.write("")

    _section_heading("📊", "Analytics")

    subtitle_suffix = (
        "across all projects" if selected_project_name == ALL_PROJECTS_LABEL
        else "for " + selected_project_name
    )

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            _card_anchor("chart_bar")
            st.markdown("#### Project Progress")
            st.caption("Progress trend " + subtitle_suffix)
            st.plotly_chart(_progress_bar_chart(active_dashboards), width="stretch",
                             config={"displayModeBar": False}, key="chart_bar")

    with col2:
        with st.container(border=True):
            _card_anchor("chart_deadline")
            st.markdown("#### Deadline Urgency")
            st.caption("Days remaining " + subtitle_suffix)
            st.plotly_chart(_deadline_urgency_chart(active_dashboards), width="stretch",
                             config={"displayModeBar": False}, key="chart_deadline")


# --------------------------------------------------------------------------
# DOCUMENTS PAGE
# --------------------------------------------------------------------------
def _render_client_documents():
    token = session_token()

    st.title("📄 Documents")
    st.caption("Upload to a project, or preview files shared by your team.")
    st.write("")

    dashboard_resp = get_client_dashboard(token)
    if dashboard_resp.status_code != 200:
        show_api_error(dashboard_resp)
        return
    dashboards = dashboard_resp.json()

    project_options = {d["project_name"]: d["project_id"] for d in dashboards}

    # ---- Upload ---------------------------------------------------------
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
                    key="client_doc_uploader_" + str(st.session_state["client_doc_uploader_key"]),
                )
                if st.form_submit_button("Upload", type="primary"):
                    if uploaded is None:
                        st.warning("Please choose a file first.")
                    else:
                        project_id = str(project_options[project_label])
                        resp = upload_document(token, uploaded, project_id=project_id)
                        if resp.status_code in (200, 201):
                            st.session_state["client_doc_uploader_key"] += 1
                            st.success("Uploaded to **" + project_label + "**. Your team can see it now.")
                            st.rerun()
                        else:
                            show_api_error(resp)

    st.write("")

    if not dashboards:
        st.info("No projects found for your account yet.")
        return

    # ---- Flatten all documents across projects ---------------------------
    all_documents = []
    for d in dashboards:
        for doc in d.get("documents", []):
            doc = dict(doc)
            doc["_project_id"] = d["project_id"]
            doc["_project_name"] = d["project_name"]
            all_documents.append(doc)

    if not all_documents:
        st.info("No documents on your projects yet. Upload one above, or wait for your team to share files.")
        return

    # ---- All Documents — filterable by project ---------------------------
    with st.container(border=True):
        st.subheader("All Documents")

        doc_filter_options = ["All Documents"] + [d["project_name"] for d in dashboards if d.get("documents")]
        selected_doc_filter = st.selectbox(
            "📁 Filter by project", doc_filter_options,
            key="client_documents_project_filter",
        )

        if selected_doc_filter == "All Documents":
            filtered_documents = all_documents
        else:
            filtered_documents = [
                doc for doc in all_documents if doc["_project_name"] == selected_doc_filter
            ]

        if not filtered_documents:
            st.info("No documents for this selection.")

        for doc in filtered_documents:
            st.caption(f"📁 {doc['_project_name']}")
            _render_doc_row(
                token, doc,
                key_prefix="docs_" + str(doc["_project_id"]),
                can_delete=True,
            )

# --------------------------------------------------------------------------
# APP ENTRY
# --------------------------------------------------------------------------
def render_client_app():
    _inject_client_light_theme()

    if CLIENT_NAV_KEY not in st.session_state:
        st.session_state[CLIENT_NAV_KEY] = NAV_PAGES[0]

    with st.sidebar:
        render_sidebar_header()
        st.subheader("Client menu")
        page = st.radio("Go to", NAV_PAGES, key=CLIENT_NAV_KEY)

    if page == "My Projects":
        _render_client_dashboard()
    elif page == "Documents":
        _render_client_documents()