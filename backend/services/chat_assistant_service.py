"""
chat_logic.py
Rule-based chat assistant. Keyword -> handler dispatch table instead of a
long if/elif chain, so adding a new intent later means adding one line to
INTENT_HANDLERS instead of another branch.

MODEL ASSUMPTIONS (check against your actual models.py and adjust if needed):
- Task: organization_id, project_id, title, status, assigned_to, deadline, created_at
- Project: organization_id, client_id, name, status, deadline, created_at
- Client: may or may not have organization_id — handled defensively below
- MeetingSummary: project_id, summary, created_at (import is optional/guarded
  in case that model isn't named exactly this in your codebase)
"""

from datetime import date, timedelta
from typing import Optional, Sequence
from uuid import UUID
import re

from sqlalchemy.orm import Session

from models import Task, Project, Client, User, Document, WeeklyReport, Meeting
from rag_utils import get_rag_response


def _matches_keywords(message: str, keywords: Sequence[str]) -> bool:
    """
    Match intent keywords without false positives from short tokens.
    - Short greetings/help: whole-word only ("hi" must not match inside "this")
    - Longer phrases: substring OK so "pending task" matches "pending tasks"
    """
    for kw in keywords:
        if " " not in kw and len(kw) <= 4:
            pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
            if re.search(pattern, message):
                return True
        elif kw in message:
            return True
    return False


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_task(task) -> str:
    due = f", due {task.deadline}" if getattr(task, "deadline", None) else ""
    return f"- {task.title} ({task.status}){due}"


def _fmt_project(p) -> str:
    due = f", due {p.deadline}" if getattr(p, "deadline", None) else ""
    return f"- {p.name}: {p.status}{due}"


def _project_progress(db: Session, project_id) -> float:
    total = db.query(Task).filter(Task.project_id == project_id).count()
    if total == 0:
        return 0.0
    done = (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.status == "done")
        .count()
    )
    return round((done / total) * 100, 1)


# ---------------------------------------------------------------------------
# Task intents
# ---------------------------------------------------------------------------

def handle_pending_tasks(db, organization_id, user_id=None):
    tasks = (
        db.query(Task)
        .filter(Task.organization_id == organization_id, Task.status != "done")
        .all()
    )
    if not tasks:
        return "No pending tasks found."
    return "\n".join(_fmt_task(t) for t in tasks)


def handle_overdue_tasks(db, organization_id, user_id=None):
    today = date.today()
    tasks = (
        db.query(Task)
        .filter(
            Task.organization_id == organization_id,
            Task.status != "done",
            Task.deadline.isnot(None),
            Task.deadline < today,
        )
        .all()
    )
    if not tasks:
        return "No overdue tasks. Nice work!"
    return "Overdue tasks:\n" + "\n".join(_fmt_task(t) for t in tasks)


def handle_tasks_due_this_week(db, organization_id, user_id=None):
    today = date.today()
    week_end = today + timedelta(days=7)
    tasks = (
        db.query(Task)
        .filter(
            Task.organization_id == organization_id,
            Task.status != "done",
            Task.deadline.isnot(None),
            Task.deadline >= today,
            Task.deadline <= week_end,
        )
        .all()
    )
    if not tasks:
        return "No tasks due in the next 7 days."
    return "Tasks due this week:\n" + "\n".join(_fmt_task(t) for t in tasks)


def handle_my_tasks(db, organization_id, user_id=None):
    if not user_id:
        return "I can't tell who you are in this session, so I can't filter to 'my tasks'."
    tasks = (
        db.query(Task)
        .filter(
            Task.organization_id == organization_id,
            Task.assigned_to == user_id,
            Task.status != "done",
        )
        .all()
    )
    if not tasks:
        return "You have no open tasks assigned to you."
    return "Your open tasks:\n" + "\n".join(_fmt_task(t) for t in tasks)


def handle_unassigned_tasks(db, organization_id, user_id=None):
    tasks = (
        db.query(Task)
        .filter(
            Task.organization_id == organization_id,
            Task.assigned_to.is_(None),
            Task.status != "done",
        )
        .all()
    )
    if not tasks:
        return "Every open task is assigned to someone."
    return "Unassigned tasks:\n" + "\n".join(_fmt_task(t) for t in tasks)


def handle_task_status_breakdown(db, organization_id, user_id=None):
    statuses = ["todo", "in_progress", "testing", "done"]
    lines = []
    for s in statuses:
        count = (
            db.query(Task)
            .filter(Task.organization_id == organization_id, Task.status == s)
            .count()
        )
        lines.append(f"- {s}: {count}")
    return "Task breakdown by status:\n" + "\n".join(lines)


def handle_total_tasks(db, organization_id, user_id=None):
    count = db.query(Task).filter(Task.organization_id == organization_id).count()
    return f"Total Tasks: {count}"


# ---------------------------------------------------------------------------
# Project intents
# ---------------------------------------------------------------------------

def handle_project_status(db, organization_id, user_id=None):
    projects = db.query(Project).filter(Project.organization_id == organization_id).all()
    if not projects:
        return "No projects found."
    return "\n".join(_fmt_project(p) for p in projects)


def handle_active_projects(db, organization_id, user_id=None):
    projects = (
        db.query(Project)
        .filter(Project.organization_id == organization_id, Project.status == "active")
        .all()
    )
    if not projects:
        return "No active projects."
    return "Active projects:\n" + "\n".join(_fmt_project(p) for p in projects)


def handle_onhold_projects(db, organization_id, user_id=None):
    projects = (
        db.query(Project)
        .filter(Project.organization_id == organization_id, Project.status == "on_hold")
        .all()
    )
    if not projects:
        return "No projects are on hold."
    return "Projects on hold:\n" + "\n".join(_fmt_project(p) for p in projects)


def handle_completed_projects(db, organization_id, user_id=None):
    projects = (
        db.query(Project)
        .filter(Project.organization_id == organization_id, Project.status == "completed")
        .all()
    )
    if not projects:
        return "No completed projects yet."
    return "Completed projects:\n" + "\n".join(_fmt_project(p) for p in projects)


def handle_upcoming_deadlines(db, organization_id, user_id=None):
    today = date.today()
    projects = (
        db.query(Project)
        .filter(
            Project.organization_id == organization_id,
            Project.deadline.isnot(None),
            Project.deadline >= today,
        )
        .order_by(Project.deadline.asc())
        .limit(10)
        .all()
    )
    if not projects:
        return "No upcoming project deadlines."
    return "Upcoming deadlines:\n" + "\n".join(_fmt_project(p) for p in projects)


def handle_project_progress(db, organization_id, user_id=None):
    projects = db.query(Project).filter(Project.organization_id == organization_id).all()
    if not projects:
        return "No projects found."
    lines = [f"- {p.name}: {_project_progress(db, p.id)}% tasks complete" for p in projects]
    return "Project progress:\n" + "\n".join(lines)


def handle_total_projects(db, organization_id, user_id=None):
    count = db.query(Project).filter(Project.organization_id == organization_id).count()
    return f"Total Projects: {count}"


# ---------------------------------------------------------------------------
# Client intents
# ---------------------------------------------------------------------------

def handle_client_list(db, organization_id, user_id=None):
    query = db.query(Client)
    if hasattr(Client, "organization_id"):
        query = query.filter(Client.organization_id == organization_id)
    clients = query.all()
    if not clients:
        return "No clients found."
    return "Clients:\n" + "\n".join(f"- {c.company_name} ({c.status})" for c in clients)


def handle_inactive_clients(db, organization_id, user_id=None):
    query = db.query(Client).filter(Client.status != "active")
    if hasattr(Client, "organization_id"):
        query = query.filter(Client.organization_id == organization_id)
    clients = query.all()
    if not clients:
        return "No inactive clients."
    return "Inactive clients:\n" + "\n".join(f"- {c.company_name}" for c in clients)


# ---------------------------------------------------------------------------
# Team / workload intents
# ---------------------------------------------------------------------------

def handle_team_workload(db, organization_id, user_id=None):
    users = db.query(User).filter(User.organization_id == organization_id).all()
    if not users:
        return "No team members found."
    lines = []
    for u in users:
        open_count = (
            db.query(Task)
            .filter(
                Task.organization_id == organization_id,
                Task.assigned_to == u.id,
                Task.status != "done",
            )
            .count()
        )
        lines.append(f"- {u.name}: {open_count} open task(s)")
    return "Team workload:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Documents / meetings / reports
# ---------------------------------------------------------------------------

def handle_recent_documents(db, organization_id, user_id=None):
    docs = (
        db.query(Document)
        .filter(Document.organization_id == organization_id)
        .order_by(Document.uploaded_at.desc())
        .limit(5)
        .all()
    )
    if not docs:
        return "No documents uploaded yet."
    return "Recent documents:\n" + "\n".join(f"- {d.filename}" for d in docs)


def handle_latest_meeting_summary(db, organization_id, user_id=None):
    meeting = (
        db.query(Meeting)
        .filter(Meeting.organization_id == organization_id)
        .order_by(Meeting.created_at.desc())
        .first()
    )
    if not meeting or not meeting.summary:
        return "No meeting summaries found."
    return f"Latest meeting summary:\n{meeting.summary}"


def handle_latest_weekly_report(db, organization_id, user_id=None):
    report = (
        db.query(WeeklyReport)
        .filter(WeeklyReport.organization_id == organization_id)
        .order_by(WeeklyReport.created_at.desc())
        .first()
    )
    if not report:
        return "No weekly reports found yet."
    return f"Latest weekly report:\n{report.report_text}"


# ---------------------------------------------------------------------------
# Conversational
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "I can answer things like:\n"
    "- pending tasks / overdue tasks / tasks due this week\n"
    "- my tasks / unassigned tasks / task breakdown\n"
    "- project status / active projects / projects on hold / completed projects\n"
    "- upcoming deadlines / project progress\n"
    "- total projects / total tasks\n"
    "- client list / inactive clients\n"
    "- team workload\n"
    "- recent documents\n"
    "- latest meeting summary\n"
    "- latest weekly report\n"
    "- or ask about your uploaded documents (select files in the chat RAG picker "
    "for best results)"
)


def handle_greeting(db, organization_id, user_id=None):
    return "Hi! Ask me about your tasks, projects, clients, reports, or uploaded documents. Type 'help' to see everything I can do."


def handle_help(db, organization_id, user_id=None):
    return HELP_TEXT


# ---------------------------------------------------------------------------
# Dispatch table — order matters: put more specific phrases before shorter
# ones that could also match the same substring (e.g. "total tasks" before
# the generic "pending tasks" family).
# ---------------------------------------------------------------------------

INTENT_HANDLERS = [
    (["hi", "hello", "hey"], handle_greeting),
    (["help", "what can you do"], handle_help),

    (["overdue task"], handle_overdue_tasks),
    (["due this week"], handle_tasks_due_this_week),
    (["my task", "tasks assigned to me"], handle_my_tasks),
    (["unassigned task"], handle_unassigned_tasks),
    (["task breakdown", "tasks by status"], handle_task_status_breakdown),
    (["total task"], handle_total_tasks),
    (["pending task"], handle_pending_tasks),

    (["upcoming deadline"], handle_upcoming_deadlines),
    (["project progress", "progress of project"], handle_project_progress),
    (["active project"], handle_active_projects),
    (["on hold project", "on-hold project", "projects on hold"], handle_onhold_projects),
    (["completed project"], handle_completed_projects),
    (["total project"], handle_total_projects),
    (["project status", "projects status"], handle_project_status),

    (["inactive client"], handle_inactive_clients),
    (["client list", "list clients", "all clients"], handle_client_list),

    (["team workload", "who's overloaded", "who is overloaded", "workload"], handle_team_workload),

    (["recent document", "recent uploads"], handle_recent_documents),
    (["meeting summary", "meeting action items", "latest meeting"], handle_latest_meeting_summary),
    (["weekly report"], handle_latest_weekly_report),
]


# Phrases that mean the user is asking about uploaded file *content*.
# Keep specific — broad tokens like "summarize the" would steal task intents.
_DOC_QUESTION_MARKERS = (
    "document",
    "documents",
    "uploaded file",
    "uploaded files",
    "pdf",
    "docx",
    "proposal",
    "from the file",
    "in the file",
    "this file",
    "the file",
    "in the doc",
    "this doc",
    "the doc",
    "based on the document",
    "according to the document",
    "in our documents",
    "knowledge base",
    "selected document",
    "search documents",
    "what does the file",
    "summarize the document",
    "summarise the document",
    "summarize this document",
    "summarise this document",
    "summarize the file",
    "summarise the file",
)


def _looks_like_document_question(msg: str) -> bool:
    """True when the message is clearly about uploaded document content."""
    return any(marker in msg for marker in _DOC_QUESTION_MARKERS)


def get_chat_response(
    message: str,
    db: Session,
    organization_id,
    user_id: Optional[str] = None,
    project_id=None,
    document_ids: Optional[Sequence[UUID]] = None,
    use_rag_only: bool = False,
) -> str:
    """
    Rule-based intent matcher first; if no keyword matches, falls back to
    RAG search over uploaded documents.

    `document_ids` is the RAG allow-list (role-scoped and/or user-selected).
    `use_rag_only=True` when the user explicitly picked documents in the UI —
    then we always answer from those files, even if the question looks like
    a keyword intent (e.g. "pending tasks" inside a selected PDF).

    Document-oriented questions (mentions PDF/file/document, etc.) always
    go through RAG so keyword intents like "project status" cannot steal them.
    """
    msg = message.lower().strip()

    if use_rag_only:
        return get_rag_response(
            db,
            message,
            organization_id,
            project_id=project_id,
            document_ids=document_ids if document_ids is not None else [],
        )

    # Meta intents about documents (list uploads) must win over RAG content search.
    if _matches_keywords(msg, ["recent document", "recent uploads"]):
        return handle_recent_documents(db, organization_id, user_id)

    # Content questions about uploaded files → RAG (don't let "project status"
    # style keywords steal them).
    if _looks_like_document_question(msg):
        return get_rag_response(
            db,
            message,
            organization_id,
            project_id=project_id,
            document_ids=document_ids,
        )

    for keywords, handler in INTENT_HANDLERS:
        if _matches_keywords(msg, keywords):
            return handler(db, organization_id, user_id)

    # No keyword matched — answer from uploaded documents.
    return get_rag_response(
        db,
        message,
        organization_id,
        project_id=project_id,
        document_ids=document_ids,
    )