"""
app.py
Streamlit entry point. Handles login, then routes to the role-specific app:
  admin    → views/admin.py
  manager  → views/manager.py
  employee → views/employee.py
  client   → views/client.py

Also hosts a shared AI Chat Assistant sidebar panel for every logged-in role.
"""

import streamlit as st

from api_client import (
    API_BASE_URL,
    ask_ai_chat,
    check_api_health,
    list_documents,
)
from login import render_login

st.set_page_config(page_title="AI Project OS", layout="wide")

ROLE_RENDERERS = {
    "admin": "views.admin.render_admin_app",
    "manager": "views.manager.render_manager_app",
    "employee": "views.employee.render_employee_app",
    "client": "views.client.render_client_app",
}


def _is_logged_in() -> bool:
    return bool(st.session_state.get("access_token") and st.session_state.get("user"))


def _clear_session() -> None:
    st.session_state.clear()


def _load_role_app(role: str):
    """Import the role dashboard only when needed (faster login screen startup)."""
    target = ROLE_RENDERERS.get(role)
    if not target:
        return None
    module_name, func_name = target.rsplit(".", 1)
    module = __import__(module_name, fromlist=[func_name])
    return getattr(module, func_name)


def _load_chat_documents(token: str) -> list[dict]:
    """Fetch documents the current user can access for RAG selection."""
    try:
        resp = list_documents(token)
        if resp.status_code == 200:
            return resp.json() or []
    except Exception:
        pass
    return []


def _render_shared_chat():
    """Sidebar chat available to all roles, with optional document selection for RAG."""
    token = st.session_state.get("access_token")
    if not token:
        return

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_selected_doc_ids" not in st.session_state:
        st.session_state.chat_selected_doc_ids = []
    if "chat_expander_open" not in st.session_state:
        st.session_state.chat_expander_open = False

    # Keep the panel open after a message so the answer stays visible.
    keep_open = bool(
        st.session_state.chat_history or st.session_state.get("chat_expander_open")
    )

    with st.sidebar:
        st.divider()
        with st.expander("AI Chat Assistant", expanded=keep_open):
            st.caption(
                "Try: pending tasks · project status · or ask about selected documents"
            )

            documents = _load_chat_documents(token)
            # Indexed files first so users don't pick the 0-chunk duplicate.
            documents = sorted(
                documents,
                key=lambda d: (
                    0 if int(d.get("chunk_count") or 0) > 0 else 1,
                    (d.get("filename") or "").lower(),
                ),
            )
            doc_label_to_id = {}
            doc_id_to_chunks = {}
            indexed_count = 0
            for d in documents:
                if not d.get("id"):
                    continue
                doc_id = str(d["id"])
                chunks = int(d.get("chunk_count") or 0)
                doc_id_to_chunks[doc_id] = chunks
                if chunks > 0:
                    indexed_count += 1
                tag = f"{chunks} chunks" if chunks else "not indexed"
                # Include short id so duplicate filenames stay unique in the picker.
                label = f"{d.get('filename', 'file')} [{tag}] ({doc_id[:8]})"
                doc_label_to_id[label] = doc_id
            doc_labels = list(doc_label_to_id.keys())

            if doc_labels:
                st.caption(
                    f"Documents linked to chat: {indexed_count}/{len(doc_labels)} "
                    "RAG-ready (indexed)."
                )
                # Prefer session-state selection with a stable key (no fragile default=).
                prior_ids = set(st.session_state.chat_selected_doc_ids)
                default_labels = [
                    lbl for lbl, did in doc_label_to_id.items() if did in prior_ids
                ]
                if "chat_rag_multiselect" not in st.session_state:
                    st.session_state.chat_rag_multiselect = default_labels

                selected_labels = st.multiselect(
                    "Search in documents (RAG)",
                    options=doc_labels,
                    key="chat_rag_multiselect",
                    help=(
                        "Select indexed files (chunk count > 0). "
                        "Leave empty for tasks/projects chat. "
                        "Files marked 'not indexed' → Documents → Reindex first."
                    ),
                )
                selected_ids = [
                    doc_label_to_id[label]
                    for label in selected_labels
                    if label in doc_label_to_id
                ]
                # Drop labels that disappeared after reindex renamed the option text.
                valid_labels = [
                    lbl for lbl in selected_labels if lbl in doc_label_to_id
                ]
                if valid_labels != list(selected_labels):
                    st.session_state.chat_rag_multiselect = valid_labels
                st.session_state.chat_selected_doc_ids = selected_ids

                if selected_ids:
                    st.caption(f"RAG mode: {len(selected_ids)} document(s) selected")
                    unindexed = [
                        i for i in selected_ids if doc_id_to_chunks.get(i, 0) == 0
                    ]
                    if unindexed:
                        st.warning(
                            "Selected file(s) are not indexed (0 chunks). "
                            "Open Documents → Reindex, then select the copy that "
                            "shows a chunk count > 0."
                        )
                elif indexed_count == 0:
                    st.caption(
                        "No indexed files yet. Open Documents and click Reindex "
                        "on PDF/DOCX/PPTX/TXT uploads."
                    )
            else:
                st.caption(
                    "No documents available yet. Upload a PDF/DOCX/PPTX/TXT on the "
                    "Documents page to enable RAG."
                )
                selected_ids = []
                st.session_state.chat_selected_doc_ids = []

            for role, text in st.session_state.chat_history[-12:]:
                label = "You" if role == "user" else "Assistant"
                st.markdown(f"**{label}:** {text}")

            with st.form("shared_chat_form", clear_on_submit=True):
                prompt = st.text_input(
                    "Message",
                    placeholder="Ask about tasks, projects, or selected docs...",
                    label_visibility="collapsed",
                )
                sent = st.form_submit_button("Send", use_container_width=True)

            if sent and prompt.strip():
                message = prompt.strip()
                # Read selection from session at submit time (more reliable than local var).
                selected_ids = list(st.session_state.get("chat_selected_doc_ids") or [])
                # Prefer indexed docs if the user selected a mix / duplicate.
                indexed_selected = [
                    i for i in selected_ids if doc_id_to_chunks.get(i, 0) > 0
                ]
                doc_ids_arg = indexed_selected or (selected_ids if selected_ids else None)

                display_msg = message
                if doc_ids_arg:
                    display_msg = f"{message}  \n_({len(doc_ids_arg)} doc selected)_"
                st.session_state.chat_history.append(("user", display_msg))
                st.session_state.chat_expander_open = True

                with st.spinner(
                    "Searching documents and generating answer… "
                    "(first question after API start can take longer)"
                ):
                    try:
                        response = ask_ai_chat(
                            token,
                            message,
                            document_ids=doc_ids_arg,
                        )
                        if response.ok:
                            payload = response.json() if response.content else {}
                            answer = (
                                payload.get("answer")
                                or "No answer returned from the assistant."
                            )
                        else:
                            try:
                                detail = response.json().get("detail", response.text)
                            except Exception:
                                detail = response.text or "Unknown error"
                            answer = f"Error ({response.status_code}): {detail}"
                    except Exception as exc:
                        answer = (
                            f"Could not reach chat API: {exc}. "
                            "If this timed out, wait for the embedding model to load "
                            "and try again, or restart the API so it can warm up."
                        )

                st.session_state.chat_history.append(("assistant", answer))
                st.rerun()

            if st.session_state.chat_history and st.button(
                "Clear chat", use_container_width=True, key="clear_shared_chat"
            ):
                st.session_state.chat_history = []
                st.session_state.chat_expander_open = False
                st.rerun()


def main():
    api_ok, api_detail = check_api_health()
    if not api_ok:
        st.error(f"Backend API is not reachable: {api_detail}")
        st.info(
            "Start the API first, then reload this page:\n\n"
            f"`cd backend` → `python -m uvicorn main:app --port 8000 --host 127.0.0.1`\n\n"
            f"Expected URL: `{API_BASE_URL}`"
        )
        if st.button("Retry connection"):
            st.rerun()
        return

    if "RAG warning" in str(api_detail):
        st.warning(
            f"Backend is up, but document chat (RAG) may not work: {api_detail}. "
            "Install packages with `pip install -r backend/requirements-rag.txt` "
            "in the same Python that runs uvicorn, then restart the API."
        )

    if not _is_logged_in():
        if st.session_state.get("access_token") or st.session_state.get("user"):
            _clear_session()
        render_login()
        return

    user = st.session_state["user"]
    role = user.get("role")
    render = _load_role_app(role)

    if render is None:
        st.error(f"Unknown role: `{role}`. Contact your administrator.")
        if st.button("Log out"):
            _clear_session()
            st.rerun()
        return

    render()
    _render_shared_chat()


if __name__ == "__main__":
    main()
