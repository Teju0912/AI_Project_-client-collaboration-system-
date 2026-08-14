"""
models.py
SQLAlchemy table definitions. Every table (except organizations itself)
carries organization_id — this is what makes multi-tenant SaaS possible
later without a schema rewrite. Add new tables here following this same
pattern (Project, Task, Document, etc.) as you build later modules.

CHANGE LOG (Jira-style Tasks tab):
  - Task: added priority, story_points, labels, parent_task_id (sub-tasks)
  - NEW:  TaskComment  (activity / comment feed on an issue)
  - NEW:  TaskLink     (linked issues: "blocks", "relates to", etc.)

After merging these changes into your real models.py, run:
    alembic revision --autogenerate -m "jira-style task fields"
    alembic upgrade head
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, JSON, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base, DATABASE_URL

# pgvector Vector on Postgres; JSON elsewhere (SQLite / missing package)
# so local dev still works and RAG can rank in Python.
def _embedding_column():
    if (DATABASE_URL or "").startswith("sqlite"):
        return Column(JSON)
    try:
        from pgvector.sqlalchemy import Vector as _PgVector

        return Column(_PgVector(768))
    except ImportError:  # pragma: no cover
        return Column(JSON)

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="organization")
    clients = relationship("Client", back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    # role is one of: "admin", "manager", "employee", "client"
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    company_name = Column(String(255), nullable=False)
    contact_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="clients")

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    budget = Column(Numeric(10, 2), nullable=True)
    deadline = Column(Date, nullable=True)
    status = Column(String(50), nullable=False, default="planning")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client")


class ProjectMember(Base):
    __tablename__ = "project_team_members"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)



class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    # Optional workflow module within the project that owns this task.
    module_id = Column(UUID(as_uuid=True), ForeignKey("project_modules.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    epic = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="todo")
    # Set when work enters Done; used to keep the active board uncluttered.
    completed_at = Column(DateTime, nullable=True)
    start_date = Column(Date, nullable=True)
    deadline = Column(Date, nullable=True)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ---- NEW: Jira-style fields ----
    # one of: "low", "medium", "high", "urgent"
    priority = Column(String(20), nullable=False, default="medium")
    # story point estimate (Jira uses fractional values e.g. 0.5, 1, 2, 3, 5, 8...)
    story_points = Column(Numeric(5, 1), nullable=True)
    # simple list of strings, e.g. ["frontend", "bug"]
    labels = Column(JSON, nullable=False, default=list)
    testing_assigned_to = Column(JSON, nullable=False, default=list)
    testing_status = Column(String(20), nullable=True)
    # self-referencing FK -> lets a Task be a sub-task of another Task
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True)


class TaskComment(Base):
    """Comment / activity feed entry on a task (Jira-style issue comments)."""
    __tablename__ = "task_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskLink(Base):
    """
    A directed link between two tasks, Jira-style ("blocks", "is blocked by",
    "relates to", "duplicates"). Stored as one row per link; the UI renders
    it from the perspective of `task_id`.
    """
    __tablename__ = "task_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    linked_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    link_type = Column(String(50), nullable=False, default="relates to")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    """
    RAG support table. Each row is one text chunk from a Document, plus its
    vector embedding. organization_id and project_id are duplicated here
    (rather than joined through Document every query) so retrieval queries
    can filter and scope directly without an extra join.
    """
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True)
    chunk_text = Column(Text, nullable=False)
    embedding = _embedding_column()  # all-MiniLM-L6-v2 = 384 dimensions
    created_at = Column(DateTime, default=datetime.utcnow)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )

    report_text = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    audio_file_url = Column(String(500), nullable=False)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    action_items = Column(Text, nullable=True)
    risks = Column(Text, nullable=True)
    deadlines = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)


class AIUsageLog(Base):
    """
    Audit log of every AI call made through call_llm wrappers. Each row is
    one LLM invocation (or a fallback when no API key is configured), tagged
    with feature="..." so we can report per-feature API usage.
    """
    __tablename__ = "ai_usage_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    feature = Column(String(100), nullable=False)
    model = Column(String(100), nullable=True)
    prompt_tokens = Column(String(50), nullable=True)
    completion_tokens = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)


class RequirementAnalysis(Base):
    
    """
    Stored result of an AI requirement analysis run. The LLM's structured
    Epics -> Stories -> Tasks breakdown is saved here in status
    "pending_review" until a human explicitly approves (creates real
    Project/Task rows) or rejects it. Nothing is written to the tasks table
    until that explicit Approve action.

    The source document is optional at the database level because an analysis
    may remain as project history even after its original uploaded document is
    deleted. When the document is removed, the FK should resolve to NULL so the
    analysis is preserved without blocking deletion.
    """
    __tablename__ = "requirement_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    raw_output = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False, default="pending_review")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProjectModule(Base):
    """
    Step-by-step workflow module for a project (e.g. "Auth", "Payments").
    Modules unlock in order: only one is "in_progress" at a time, everything
    after it is "locked" until the previous one is marked "completed".
    """
    __tablename__ = "project_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    icon = Column(String(10), nullable=False, default="🧩")
    description = Column(Text, nullable=True)
    # one of: "locked", "in_progress", "completed"
    status = Column(String(50), nullable=False, default="locked")
    order = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)    


# ---------------------------------------------------------------------------
# NEXT MODULES — add tables here as you build them, following the same
# pattern (organization_id on every table, a relationship back if useful):
#
#   class Project(Base): ...        (Module 3 — needs client_id too)          [DONE]
#   class ProjectMember(Base): ...  (many-to-many: project_id, user_id)       [DONE]
#   class Task(Base): ...           (Module 4 — needs project_id, assigned_to) [DONE]
#   class Document(Base): ...       (Module 5 — needs project_id, file_url)   [DONE]
#   class DocumentChunk(Base): ...  (RAG — chunk_text, embedding vector)      [DONE]
#   class TaskComment(Base): ...    (Jira-style issue comments)               [DONE]
#   class TaskLink(Base): ...       (Jira-style linked issues)                [DONE]
#   class TaskLink(Base): ...       (Jira-style linked issues)                [DONE]
#   class ProjectModule(Base): ...  (project workflow steps)                  [DONE]
# After adding a table, always run:
#   alembic revision --autogenerate -m "add <table> table"
#   alembic upgrade head
# ---------------------------------------------------------------------------