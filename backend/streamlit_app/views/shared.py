"""
shared.py
Helpers and reusable page bodies used by admin / manager / employee / client
role apps. Data still flows through api_client + the FastAPI backend —
these are UI only.
"""

import pandas as pd
import streamlit as st

from api_client import (
    get_clients, create_client, update_client, delete_client,
    get_tasks, create_task, patch_task_status,
    list_documents, upload_document, download_document, delete_document,
    reindex_document,
    get_users,
    get_projects, create_project, assign_team, get_team,
    upload_meeting, list_project_meetings,
)


def show_api_error(response):
    try:
        payload = response.json()
        detail = payload.get("detail", payload)
    except Exception:
        detail = response.text

    if response.status_code == 403:
        st.error(f"Forbidden: {detail}")
    elif response.status_code == 404:
        st.error(f"Not found: {detail}")
    else:
        st.error(f"Request failed ({response.status_code}): {detail}")


def render_sidebar_header():
    """User info + logout — shared across all role sidebars."""
    user = st.session_state["user"]
    st.write(f"**{user['name']}**")
    st.write(f"Role: `{user['role']}`")
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()


def session_token():
    return st.session_state.get("access_token")


def session_user():
    return st.session_state.get("user")


_RAG_SUPPORTED_EXTS = (".pdf", ".docx", ".pptx", ".txt", ".csv", ".md", ".log")



#------------Avi add ------------------------------


def rag_index_caption(doc: dict) -> str:
    """Human-readable RAG indexing status for a document row."""
    chunks = int(doc.get("chunk_count") or 0)
    if chunks > 0:
        return f"RAG indexed · {chunks} chunk{'s' if chunks != 1 else ''}"
    return "Not indexed for chat — use Reindex (PDF/DOCX/PPTX/TXT)"


def render_reindex_button(token: str, doc: dict, *, key: str) -> None:
    """Button that re-runs RAG extraction + embedding for one document."""
    if not st.button("Reindex", key=key, use_container_width=True):
        return
    with st.spinner(f"Indexing {doc.get('filename', 'document')}…"):
        resp = reindex_document(token, str(doc["id"]))
    if resp.status_code == 200:
        data = resp.json()
        chunks = data.get("chunks_indexed", 0)
        if chunks:
            st.success(f"Indexed {chunks} chunk(s). Available in AI Chat.")
        else:
            st.warning(
                "No text extracted. Use PDF, DOCX, PPTX, TXT, CSV, or MD."
            )
        st.rerun()
    else:
        show_api_error(resp)







def rag_status_label(doc: dict) -> str:
    """Human-readable RAG indexing status for a document list row."""
    chunks = int(doc.get("chunk_count") or 0)
    if chunks > 0:
        return f"RAG ready · {chunks} chunk(s)"
    name = (doc.get("filename") or "").lower()
    if name.endswith(_RAG_SUPPORTED_EXTS):
        return "Not indexed for chat — click Reindex"
    return "Unsupported for RAG (use PDF/DOCX/PPTX/TXT/CSV/MD)"


def trigger_reindex(token: str, doc: dict, *, key: str) -> None:
    """Render a Reindex button that rebuilds vector chunks for a document."""
    if st.button("Reindex", key=key, use_container_width=True):
        with st.spinner(f"Indexing {doc.get('filename', 'document')}…"):
            resp = reindex_document(token, str(doc["id"]))
        if resp.status_code == 200:
            data = resp.json() if resp.content else {}
            n = data.get("chunks_indexed", 0)
            if n > 0:
                st.success(f"Indexed {n} chunk(s) — available in AI Chat.")
            else:
                st.warning(
                    "No text extracted. Use PDF, DOCX, PPTX, TXT, CSV, or MD, "
                    "or check that the file is not image-only."
                )
            st.rerun()
        else:
            show_api_error(resp)


# ---------- Reusable pages (capabilities differ by role) ----------

def render_clients_page(*, can_manage: bool):
    """can_manage=True → admin create/edit/delete. Managers get read-only list."""
    st.title("Clients")
    token = session_token()

    clients_resp = get_clients(token)
    if clients_resp.status_code != 200:
        show_api_error(clients_resp)
        return

    clients = clients_resp.json()
    if not clients:
        st.info("No clients found for your organization.")
        if not can_manage:
            return
    else:
        df = pd.DataFrame(clients)
        st.subheader("Client list")
        st.dataframe(
            df[["company_name", "contact_name", "email", "phone", "status"]],
            use_container_width=True,
            hide_index=True,
        )

    if not can_manage:
        return

    st.subheader("Add client")
    with st.form("add_client_form", clear_on_submit=True):
        company_name = st.text_input("Company name")
        contact_name = st.text_input("Contact name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        status = st.selectbox("Status", ["active", "pending", "inactive"])
        password = st.text_input("Client login password (optional)", type="password")
        submitted = st.form_submit_button("Add client")
        if submitted:
            payload = {
                "company_name": company_name,
                "contact_name": contact_name or None,
                "email": email or None,
                "phone": phone or None,
                "status": status,
                "password": password or None,
            }
            resp = create_client(token, payload)
            if resp.status_code in {200, 201}:
                st.success("Client created.")
                if password:
                    st.info(f"Client login created — email: {email}")
                st.rerun()
            else:
                show_api_error(resp)

    if not clients:
        return

    st.subheader("Edit client")
    client_options = {f"{c['company_name']} ({c['id']})": c for c in clients}
    selected_label = st.selectbox("Select client to edit", list(client_options.keys()))
    selected_client = client_options[selected_label]

    with st.form("edit_client_form"):
        company_name = st.text_input("Company name", value=selected_client["company_name"])
        contact_name = st.text_input("Contact name", value=selected_client["contact_name"])
        email = st.text_input("Email", value=selected_client["email"])
        phone = st.text_input("Phone", value=selected_client["phone"])
        status = st.selectbox(
            "Status", ["active", "pending", "inactive"],
            index=["active", "pending", "inactive"].index(selected_client["status"]),
        )
        submitted = st.form_submit_button("Update client")
        if submitted:
            payload = {
                "company_name": company_name,
                "contact_name": contact_name,
                "email": email,
                "phone": phone,
                "status": status,
            }
            resp = update_client(token, selected_client["id"], payload)
            if resp.status_code == 200:
                st.success("Client updated.")
                st.rerun()
            else:
                show_api_error(resp)

    st.subheader("Delete client")
    delete_client_id = st.selectbox("Select client to delete", [c["id"] for c in clients])
    confirm_delete = st.checkbox("I confirm deletion")
    if confirm_delete and st.button("Delete client", type="primary"):
        resp = delete_client(token, delete_client_id)
        if resp.status_code == 200:
            st.success("Client deleted.")
            st.rerun()
        else:
            show_api_error(resp)


def render_projects_page(*, can_create: bool, can_assign_team: bool):
    """
    Role connection hub for projects:
      Admin creates project → picks managers (+ employees) → they see it
      Manager can also create / update team on their projects
      Client linked via client_id sees it on client portal
    """
    st.title("Projects")
    token = session_token()
    user = session_user() or {}

    projects_resp = get_projects(token)
    if projects_resp.status_code != 200:
        show_api_error(projects_resp)
        return

    projects = projects_resp.json()
    if not projects:
        st.info("No projects found.")
    else:
        clients_resp = get_clients(token)
        client_name_map = {}
        if clients_resp.status_code == 200:
            for c in clients_resp.json():
                client_name_map[c["id"]] = c["company_name"]

        df = pd.DataFrame(projects)
        df["client_name"] = df["client_id"].apply(lambda x: client_name_map.get(x, str(x)[:8]))
        st.subheader("Project list")
        st.dataframe(
            df[["name", "client_name", "status", "deadline", "budget"]],
            use_container_width=True,
            hide_index=True,
        )

    # Load staff for team assignment
    users_resp = get_users(token)
    managers = []
    employees = []
    if users_resp.status_code == 200:
        for u in users_resp.json():
            if u.get("role") == "manager":
                managers.append(u)
            elif u.get("role") == "employee":
                employees.append(u)
    elif can_create or can_assign_team:
        st.warning("Could not load users for team assignment.")

    def _label(u):
        return f"{u['name']} · {u['email']} ({u['role']})"

    if can_create:
        st.subheader("Create project")
        st.caption(
            "Link a client, then assign project managers (and optional employees). "
            "Assigned managers will see this project in their workspace."
        )
        clients_resp = get_clients(token)
        client_options = {}
        if clients_resp.status_code == 200:
            for c in clients_resp.json():
                client_options[c["company_name"]] = c["id"]
        else:
            show_api_error(clients_resp)

        with st.form("create_project_form", clear_on_submit=True):
            client_name = st.selectbox("Client", list(client_options.keys()) or ["(no clients)"])
            name = st.text_input("Project name")
            description = st.text_area("Description")
            budget = st.number_input("Budget", min_value=0.0, step=100.0)
            deadline = st.date_input("Deadline")
            status = st.selectbox("Status", ["planning", "active", "on_hold", "completed"])

            manager_labels = [_label(u) for u in managers]
            employee_labels = [_label(u) for u in employees]
            selected_managers = st.multiselect(
                "Project managers",
                manager_labels,
                help="These managers will see and work on this project.",
            )
            selected_employees = st.multiselect(
                "Employees (optional)",
                employee_labels,
                help="Optional. Employees are also added automatically when you assign them a task.",
            )
            if user.get("role") == "admin" and not managers:
                st.info("No managers in this organization yet. Create manager users first.")
            elif user.get("role") == "admin" and not selected_managers:
                st.caption("Tip: if you leave managers empty, all org managers are auto-assigned.")

            submitted = st.form_submit_button("Create project")
            if submitted:
                if not client_options:
                    st.error("Create a client first.")
                elif not name.strip():
                    st.error("Project name is required.")
                else:
                    label_to_id = {_label(u): u["id"] for u in managers + employees}
                    team_user_ids = [label_to_id[l] for l in selected_managers + selected_employees]
                    payload = {
                        "client_id": client_options[client_name],
                        "name": name.strip(),
                        "description": description,
                        "budget": float(budget),
                        "deadline": str(deadline),
                        "status": status,
                        "team_user_ids": team_user_ids,
                    }
                    resp = create_project(token, payload)
                    if resp.status_code in {200, 201}:
                        st.success(
                            "Project created and connected to the selected team. "
                            "Managers can open it in their project switcher."
                        )
                        st.rerun()
                    else:
                        show_api_error(resp)

    if can_assign_team and projects:
        st.subheader("Assign / update project team")
        st.caption("Connect managers and employees to a project so they share its tasks and documents.")

        project_select = st.selectbox("Project", [p["name"] for p in projects], key="assign_team_project")
        selected_project = next((p for p in projects if p["name"] == project_select), None)
        if selected_project is not None:
            team_resp = get_team(token, str(selected_project["id"]))
            current_ids = set()
            if team_resp.status_code == 200:
                current_ids = {str(m["id"]) for m in team_resp.json()}
            else:
                show_api_error(team_resp)

            staff = managers + employees
            label_to_id = {_label(u): str(u["id"]) for u in staff}
            defaults = [_label(u) for u in staff if str(u["id"]) in current_ids]

            selected_members = st.multiselect(
                "Project team (managers + employees)",
                list(label_to_id.keys()),
                default=defaults,
                key=f"team_multi_{selected_project['id']}",
            )
            if st.button("Save team members", type="primary"):
                user_ids = [label_to_id[label] for label in selected_members]
                resp = assign_team(token, str(selected_project["id"]), user_ids)
                if resp.status_code in {200, 201}:
                    st.success("Team updated. Assigned managers/employees can now see this project's data.")
                    st.rerun()
                else:
                    show_api_error(resp)


def render_tasks_page(*, can_create: bool, employee_mode: bool = False):
    """
    Backend already filters: admin/manager see all org tasks;
    employee sees only assigned tasks.
    """
    st.title("My Tasks" if employee_mode else "Tasks")
    token = session_token()

    tasks_resp = get_tasks(token)
    if tasks_resp.status_code != 200:
        show_api_error(tasks_resp)
        return

    tasks = tasks_resp.json()
    if not tasks:
        st.info("No tasks found." if not employee_mode else "No tasks assigned to you yet.")
        if not can_create:
            return

    status_order = {
        "todo": "To do",
        "in_progress": "In progress",
        "testing": "Testing",
        "done": "Done",
    }

    user_name_map = {}
    if not employee_mode:
        users_resp_for_lookup = get_users(token)
        if users_resp_for_lookup.status_code == 200:
            for u in users_resp_for_lookup.json():
                user_name_map[u["id"]] = u["name"]

    if tasks:
        status_columns = st.columns(4)
        grouped = {key: [] for key in status_order}
        for task in tasks:
            grouped[task["status"]].append(task)

        for idx, (status_key, status_label) in enumerate(status_order.items()):
            with status_columns[idx]:
                st.subheader(status_label)
                for task in grouped[status_key]:
                    assignee_id = task.get("assigned_to")
                    assignee_name = user_name_map.get(assignee_id, "Unassigned") if assignee_id else "Unassigned"
                    st.markdown(f"### {task['title']}")
                    if not employee_mode:
                        st.caption(f"Assignee: {assignee_name}")
                    if status_key != "done":
                        next_status = list(status_order.keys())[list(status_order.keys()).index(status_key) + 1]
                        if st.button(f"Move to {status_order[next_status]}", key=f"move_{task['id']}"):
                            payload = {"status": next_status}
                            resp = patch_task_status(token, str(task["id"]), payload)
                            if resp.status_code == 200:
                                st.success("Task status updated.")
                                st.rerun()
                            else:
                                show_api_error(resp)

    if can_create:
        st.subheader("Create task")
        users_resp = get_users(token)
        user_options = {"Unassigned": None}
        if users_resp.status_code == 200:
            for u in users_resp.json():
                if u.get("role") in {"employee", "manager"}:
                    user_options[f"{u['name']} ({u['email']}) · {u['role']}"] = u["id"]
        else:
            st.warning("Could not load users list for assignment.")

        projects_resp = get_projects(token)
        project_options = {}
        if projects_resp.status_code == 200:
            for p in projects_resp.json():
                project_options[p["name"]] = p["id"]
        else:
            show_api_error(projects_resp)

        with st.form("create_task_form", clear_on_submit=True):
            title = st.text_input("Title")
            description = st.text_area("Description")
            status = st.selectbox("Status", ["todo", "in_progress", "testing", "done"])
            project_label = st.selectbox(
                "Project",
                list(project_options.keys()) or ["(no projects)"],
            )
            assignee_label = st.selectbox("Assign to", list(user_options.keys()))
            submitted = st.form_submit_button("Create task")
            if submitted:
                if not project_options:
                    st.error("Create a project first, then create tasks under it.")
                elif not title.strip():
                    st.error("Title is required.")
                else:
                    payload = {
                        "title": title.strip(),
                        "description": description,
                        "status": status,
                        "project_id": project_options[project_label],
                        "assigned_to": user_options[assignee_label],
                    }
                    resp = create_task(token, payload)
                    if resp.status_code in {200, 201}:
                        st.success("Task created and linked to the project/assignee.")
                        st.rerun()
                    else:
                        show_api_error(resp)


def render_documents_page(*, can_delete: bool):
    st.title("Documents")
    token = session_token()

    if "doc_uploader_key" not in st.session_state:
        st.session_state["doc_uploader_key"] = 0

    projects_resp = get_projects(token)
    project_lookup = {"General (not linked to a project)": None}
    if projects_resp.status_code == 200:
        for p in projects_resp.json():
            project_lookup[p["name"]] = p["id"]

    st.subheader("Upload document")
    with st.form("upload_document_form", clear_on_submit=True):
        project_label = st.selectbox("Link to project", list(project_lookup.keys()))
        uploaded = st.file_uploader(
            "Choose a file",
            type=None,
            key=f"doc_uploader_{st.session_state['doc_uploader_key']}",
        )
        submit = st.form_submit_button("Upload")
        if submit:
            if uploaded is None:
                st.warning("Please choose a file first.")
            else:
                selected_project_id = project_lookup[project_label]
                resp = upload_document(
                    token, uploaded,
                    project_id=str(selected_project_id) if selected_project_id else None,
                )
                if resp.status_code in (200, 201):
                    st.session_state["doc_uploader_key"] += 1
                    data = resp.json() if resp.content else {}
                    chunks = int(data.get("chunk_count") or 0)
                    if chunks > 0:
                        st.success(
                            f"Uploaded and indexed for AI Chat ({chunks} chunk(s)). "
                            "Select this file in the sidebar chat to ask questions."
                        )
                    else:
                        st.success(
                            "Document uploaded. No text extracted for RAG — "
                            "use PDF/DOCX/PPTX/TXT/CSV/MD, or click Reindex."
                        )
                    st.rerun()
                else:
                    show_api_error(resp)

    documents_resp = list_documents(token)
    if documents_resp.status_code != 200:
        show_api_error(documents_resp)
        return

    documents = documents_resp.json()
    if not documents:
        st.info("No documents found for your organization.")
        return

    project_id_to_name = {str(v): k for k, v in project_lookup.items() if v is not None}

    grouped_docs = {}
    for doc in documents:
        pid = doc.get("project_id")
        group_name = (
            project_id_to_name.get(str(pid), "General (not linked to a project)")
            if pid else "General (not linked to a project)"
        )
        grouped_docs.setdefault(group_name, []).append(doc)

    for group_name, docs_in_group in grouped_docs.items():
        st.subheader(group_name)
        for doc in docs_in_group:
            col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
            with col1:
                st.write(doc["filename"])
                st.caption(rag_status_label(doc))
            with col2:
                resp = download_document(token, str(doc["id"]))
                if resp.status_code == 200:
                    st.download_button(
                        label="Download",
                        data=resp.content,
                        file_name=doc["filename"],
                        mime="application/octet-stream",
                        key=f"download_{doc['id']}",
                    )
                else:
                    show_api_error(resp)
            with col3:
                if st.button("Preview", key=f"preview_doc_{doc['id']}"):
                    show_document_preview(token, doc)
            with col4:
                trigger_reindex(token, doc, key=f"reindex_doc_{doc['id']}")
            with col5:
                if can_delete:
                    if st.button("Delete", key=f"delete_doc_{doc['id']}"):
                        delete_resp = delete_document(token, str(doc["id"]))
                        if delete_resp.status_code == 204:
                            st.success("Document deleted.")
                            st.rerun()
                        else:
                            show_api_error(delete_resp)
        st.divider()


@st.dialog("Document Preview", width="large")
def show_document_preview(token, doc):
    view_resp = download_document(token, str(doc["id"]))
    if view_resp.status_code != 200:
        show_api_error(view_resp)
        return

    filename_lower = doc["filename"].lower()
    if filename_lower.endswith((".png", ".jpg", ".jpeg", ".gif")):
        st.image(view_resp.content)
    elif filename_lower.endswith(".pdf"):
        import base64
        b64 = base64.b64encode(view_resp.content).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500"></iframe>',
            unsafe_allow_html=True,
        )
    elif filename_lower.endswith((".txt", ".csv", ".md")):
        st.text(view_resp.content.decode(errors="replace"))
    elif filename_lower.endswith(".docx"):
        import mammoth
        import io
        result = mammoth.convert_to_html(io.BytesIO(view_resp.content))
        styled_html = f"""
        <div style="background-color: white; color: black; padding: 20px; font-family: Arial, sans-serif; line-height: 1.6;">
            {result.value}
        </div>
        """
        st.components.v1.html(styled_html, height=500, scrolling=True)
    else:
        st.info("Preview not supported for this file type — please download instead.")


# ---------- Meeting Summarizer (shared across admin/manager/employee) ----------

MEETING_STATUS_META = {
    "processing": {"icon": "🟡", "color": "orange", "hex": "#F59E0B"},
    "done":       {"icon": "🟢", "color": "green",  "hex": "#22C55E"},
    "failed":     {"icon": "🔴", "color": "red",    "hex": "#EF4444"},
}


def _meeting_status_meta(status_text):
    return MEETING_STATUS_META.get(
        (status_text or "").strip().lower(),
        {"icon": "⚪", "color": "gray", "hex": "#6B7280"},
    )


def render_meeting_panel(
    *,
    token,
    projects,
    allow_upload: bool,
    key_prefix: str,
    selected_project_id=None,
    show_project_selector: bool = True,
):
    """
    Shared Meeting Summarizer panel.

    Used by:
      - admin.py    → allow_upload=False, projects = ALL org projects
      - manager.py  → allow_upload=True,  projects = this manager's projects
                      (passes selected_project_id + show_project_selector=False
                       so it shares the manager project dropdown)
      - employee.py → allow_upload=True,  projects = this employee's assigned projects

    The backend has already scoped `projects` by role before this function
    ever sees it — this function does no additional filtering, only display.

    `key_prefix` must be unique per calling page (same convention as
    `_choose_active_project`'s widget_key in manager.py) to avoid
    StreamlitDuplicateElementKey.

    When `show_project_selector` is False, `selected_project_id` controls
    the filter (None = all projects in `projects`).
    """
    if not projects:
        st.info("No projects available yet.")
        return

    project_by_id = {str(p["id"]): p["name"] for p in projects}
    ALL_LABEL = "All Projects"

    if show_project_selector:
        if len(projects) > 1:
            labels = [ALL_LABEL] + [p["name"] for p in projects]
        else:
            labels = [p["name"] for p in projects]

        selected_label = st.selectbox(
            "📁 Project", labels, key=f"{key_prefix}_meeting_project_select",
        )

        if selected_label == ALL_LABEL:
            selected_project_ids = [str(p["id"]) for p in projects]
            filter_project_id = None
        else:
            selected_project_ids = [
                str(p["id"]) for p in projects if p["name"] == selected_label
            ]
            filter_project_id = selected_project_ids[0] if selected_project_ids else None
    else:
        if selected_project_id is None:
            selected_project_ids = [str(p["id"]) for p in projects]
            filter_project_id = None
        else:
            filter_project_id = str(selected_project_id)
            selected_project_ids = [filter_project_id]

    # ---- Upload form (Manager / Employee only) ----
    if allow_upload:
        uploader_key_name = f"{key_prefix}_meeting_uploader_key"
        if uploader_key_name not in st.session_state:
            st.session_state[uploader_key_name] = 0

        with st.container(border=True):
            st.markdown("**⬆️ Upload a recording**")
            upload_project_names = [p["name"] for p in projects]
            default_index = 0
            if filter_project_id is not None:
                matching = [
                    p["name"] for p in projects if str(p.get("id")) == filter_project_id
                ]
                if matching:
                    default_index = upload_project_names.index(matching[0])

            with st.form(f"{key_prefix}_meeting_upload_form", clear_on_submit=True):
                upload_project_label = st.selectbox(
                    "Project",
                    upload_project_names,
                    index=default_index,
                    key=f"{key_prefix}_meeting_upload_project",
                )
                audio_file = st.file_uploader(
                    "Audio / notes (.mp3, .wav, .m4a, .ogg, .txt, .md)",
                    type=None,
                    key=(
                        f"{key_prefix}_meeting_audio_uploader_"
                        f"{st.session_state[uploader_key_name]}"
                    ),
                )
                if st.form_submit_button("Upload & Summarize", type="primary"):
                    if audio_file is None:
                        st.warning("Please choose a file first.")
                    else:
                        upload_project_id = next(
                            (
                                str(p["id"])
                                for p in projects
                                if p["name"] == upload_project_label
                            ),
                            None,
                        )
                        if not upload_project_id:
                            st.error("Select a valid project.")
                        else:
                            with st.spinner("Uploading and summarizing…"):
                                resp = upload_meeting(
                                    token, upload_project_id, audio_file
                                )
                            if resp.status_code in (200, 201, 202):
                                meeting = {}
                                try:
                                    meeting = resp.json()
                                except Exception:
                                    pass
                                status = (meeting.get("status") or "").lower()
                                st.session_state[uploader_key_name] += 1
                                if status == "done":
                                    st.success("Uploaded and summarized.")
                                elif status == "failed":
                                    st.error(
                                        meeting.get("summary")
                                        or "Upload saved but summarization failed."
                                    )
                                else:
                                    st.success(
                                        "Uploaded — processing started. "
                                        "Use Refresh below to check status."
                                    )
                                st.rerun()
                            else:
                                show_api_error(resp)

    st.write("")

    # ---- Manual refresh ----
    if st.button("🔄 Refresh status", key=f"{key_prefix}_meeting_refresh"):
        st.rerun()

    # ---- List meetings for the selected project(s) ----
    all_meetings = []
    for pid in selected_project_ids:
        resp = list_project_meetings(token, pid)
        if resp.status_code == 200:
            for m in resp.json():
                m["_project_name"] = project_by_id.get(pid, str(pid)[:8])
                all_meetings.append(m)
        elif resp.status_code == 403:
            # Skip projects the caller isn't allowed to open (e.g. employee
            # fan-out over a wider project list). Don't spam the page with errors.
            continue
        else:
            show_api_error(resp)

    if not all_meetings:
        st.info("No meetings uploaded yet for this selection.")
        return

    all_meetings.sort(key=lambda m: m.get("created_at", ""), reverse=True)

    for meeting in all_meetings:
        meeting_id = str(meeting.get("id", ""))
        meta = _meeting_status_meta(meeting.get("status"))
        with st.container(border=True):
            head_col, badge_col = st.columns([4, 1.2])
            with head_col:
                st.markdown(
                    f"**{meeting.get('_project_name')}** — "
                    f"{str(meeting.get('created_at', ''))[:10]}"
                )
            with badge_col:
                st.badge(
                    f"{meta['icon']} {meeting.get('status', 'unknown')}",
                    color=meta["color"],
                )

            status = (meeting.get("status") or "").lower()
            if status == "processing":
                st.caption("Still processing — check back in a moment.")
            elif status == "failed":
                st.error("Summarization failed — you can re-upload the recording.")
                if meeting.get("summary"):
                    st.caption(meeting["summary"])
            elif status == "done":
                with st.expander(
                    "View summary",
                    key=f"{key_prefix}_meeting_summary_{meeting_id}",
                ):
                    if meeting.get("summary"):
                        st.markdown("**Summary**")
                        st.write(meeting["summary"])
                    for label, field in (
                        ("Action items", "action_items"),
                        ("Risks", "risks"),
                        ("Deadlines", "deadlines"),
                    ):
                        items = meeting.get(field) or []
                        if items:
                            st.markdown(f"**{label}**")
                            for item in items:
                                st.write(f"- {item}")
                    if meeting.get("transcript"):
                        st.markdown("**Transcript**")
                        st.write(meeting["transcript"])
            else:
                st.caption("Status unknown.")