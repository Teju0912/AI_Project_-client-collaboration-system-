"""
api_client.py
Every Streamlit page calls the backend through these functions instead of
using `requests` directly everywhere — keeps the base URL and auth header
handling in one place.
"""

import os
from typing import Optional

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def login(email: str, password: str):
    """Returns (data, error). data has access_token + user on success."""
    response = requests.post(
        f"{API_BASE_URL}/auth/login",
        data={"username": email, "password": password},  # OAuth2 form fields
    )
    if response.status_code != 200:
        return None, response.json().get("detail", "Login failed.")
    return response.json(), None


def api_request(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    json_body: Optional[dict] = None,
    files: Optional[dict] = None,
):
    """Call the FastAPI backend (which talks to Postgres via SQLAlchemy)."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    method_upper = method.upper()
    request_kwargs = {"headers": headers, "timeout": 30}
    if files is not None:
        request_kwargs["files"] = files
        if json_body:
            request_kwargs["data"] = json_body
    elif json_body is not None:
        request_kwargs["json"] = json_body
    elif method_upper not in {"GET", "DELETE", "HEAD"}:
        # Only send an empty JSON body for write methods that expect one.
        request_kwargs["json"] = {}
    return requests.request(
        method=method_upper,
        url=f"{API_BASE_URL}{path}",
        **request_kwargs,
    )


# ---------- Clients ----------
def get_clients(token: str):
    return api_request("GET", "/clients", token=token)


def create_client(token: str, payload: dict):
    return api_request("POST", "/clients", token=token, json_body=payload)


def update_client(token: str, client_id: str, payload: dict):
    return api_request("PUT", f"/clients/{client_id}", token=token, json_body=payload)


def delete_client(token: str, client_id: str):
    return api_request("DELETE", f"/clients/{client_id}", token=token)


# ---------- Tasks ----------
def get_tasks(token: str, project_id: Optional[str] = None):
    path = "/tasks"
    if project_id:
        path = f"/tasks?project_id={project_id}"
    return api_request("GET", path, token=token)


def create_task(token: str, payload: dict):
    return api_request("POST", "/tasks", token=token, json_body=payload)


def patch_task_status(token: str, task_id: str, payload: dict):
    return api_request("PATCH", f"/tasks/{task_id}/status", token=token, json_body=payload)


def delete_task(token: str, task_id: str):
    return api_request("DELETE", f"/tasks/{task_id}", token=token)


# ---------- Documents ----------
def list_documents(token: str, project_id: Optional[str] = None):
    path = "/documents"
    if project_id:
        path = f"/documents?project_id={project_id}"
    return api_request("GET", path, token=token)


def upload_document(token: str, file, project_id: Optional[str] = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = {}
    if project_id:
        data["project_id"] = project_id
    # Sync RAG indexing on upload can take a while on cold embedding load.
    return requests.post(
        f"{API_BASE_URL}/documents/upload",
        headers=headers,
        files={"file": (file.name, file.getvalue(), file.type)},
        data=data,
        timeout=180,
    )

def download_document(token: str, document_id: str):
    return api_request("GET", f"/documents/{document_id}/download", token=token)


def delete_document(token: str, document_id: str):
    return api_request("DELETE", f"/documents/{document_id}", token=token)


def reindex_document(token: str, document_id: str):
    """Re-run RAG indexing for an uploaded document (can take ~30–90s)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(
        f"{API_BASE_URL}/documents/{document_id}/reindex",
        headers=headers,
        timeout=120,
    )

def get_users(token):
    return api_request("GET", "/users", token=token)


def create_project(token, payload):
    return api_request("POST", "/projects", token=token, json_body=payload)


def get_projects(token):
    return api_request("GET", "/projects", token=token)


def update_project(token, project_id, payload):
    return api_request(
        "PATCH",
        f"/projects/{project_id}",
        token=token,
        json_body=payload,
    )


def assign_team(token, project_id, user_ids):
    return api_request(
        "PUT",
        f"/projects/{project_id}/team",
        token=token,
        json_body={"user_ids": user_ids},
    )


def get_team(token, project_id):
    return api_request("GET", f"/projects/{project_id}/team", token=token)


def get_client_dashboard(token):
    return api_request("GET", "/client-dashboard", token=token)


# ---------- AI ----------
def generate_ai_tasks(token: str, project_name: str, description: str):
    payload = {
        "project_name": project_name,
        "description": description,
    }
    return api_request(
        "POST",
        "/ai/generate-tasks",
        token=token,
        json_body=payload,
    )


# ---------- Requirement Analyzer ----------
def analyze_requirement(token: str, document_id: str | None = None, project_id: str | None = None):
    payload = {}
    if document_id:
        payload["document_id"] = document_id
    if project_id:
        payload["project_id"] = project_id
    return api_request("POST", "/ai/analyze-requirement", token=token, json_body=payload)


def get_requirement_analysis(token: str, analysis_id: str):
    return api_request("GET", f"/ai/requirement-analyses/{analysis_id}", token=token)


def approve_requirement_analysis(token: str, analysis_id: str, payload: dict):
    return api_request("POST", f"/ai/requirement-analyses/{analysis_id}/approve", token=token, json_body=payload)


def reject_requirement_analysis(token: str, analysis_id: str):
    return api_request("POST", f"/ai/requirement-analyses/{analysis_id}/reject", token=token)


# ---------- Weekly Reports ----------
def generate_weekly_report(token: str, project_id: str):
    return api_request("POST", f"/weekly-reports/{project_id}", token=token)


def get_weekly_reports(token: str, project_id: str):
    return api_request("GET", f"/weekly-reports/{project_id}", token=token)


# ---------- Meetings ----------
def upload_meeting(token: str, project_id: str, file):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(
        f"{API_BASE_URL}/meetings/upload",
        headers=headers,
        files={"file": (file.name, file.getvalue(), file.type or "application/octet-stream")},
        data={"project_id": project_id},
        timeout=180,
    )


def get_meeting(token: str, meeting_id: str):
    return api_request("GET", f"/meetings/{meeting_id}", token=token)


def list_project_meetings(token: str, project_id: str):
    return api_request("GET", f"/meetings/project/{project_id}", token=token)


# ---------- AI Chat Assistant ----------
def ask_ai_chat(
    token: str,
    message: str,
    *,
    document_ids: Optional[list] = None,
    project_id: Optional[str] = None,
):
    """
    Ask the chat assistant. Optionally scope RAG to selected document IDs
    and/or a project.
    """
    body: dict = {"message": message}
    if document_ids is not None:
        body["document_ids"] = document_ids
    if project_id:
        body["project_id"] = project_id
    # RAG + LLM can exceed the default 30s on cold embedding load.
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(
        f"{API_BASE_URL}/chat/query",
        headers=headers,
        json=body,
        timeout=180,
    )


def check_api_health() -> tuple[bool, str]:
    """Quick backend reachability check for the Streamlit entry screen."""
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        if response.status_code == 200:
            data = {}
            try:
                data = response.json() or {}
            except Exception:
                pass
            if data.get("rag_ready") is False:
                return True, f"{API_BASE_URL} (RAG warning: {data.get('rag_detail', 'not ready')})"
            return True, API_BASE_URL
        return False, f"{API_BASE_URL} returned HTTP {response.status_code}"
    except requests.RequestException as exc:
        return False, f"{API_BASE_URL} is unreachable ({exc.__class__.__name__})"