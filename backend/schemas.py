"""
schemas.py
Pydantic models define what a valid API request/response looks like.
These are NOT database tables (that's models.py) — they're the shape of
data going in and out over HTTP.
"""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

from typing import Literal
from datetime import date


# ---------- Chat Assistant ----------
class ChatQuery(BaseModel):
    message: str
    # Optional RAG scope: restrict retrieval to these uploaded documents.
    # When omitted / null, search all documents the user can access in the org
    # (optionally further limited by project_id).
    document_ids: Optional[list[uuid.UUID]] = None
    project_id: Optional[uuid.UUID] = None


class ChatResponse(BaseModel):
    answer: str


# ---------- Auth ----------
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str  # "admin" | "manager" | "employee" | "client"
    organization_id: uuid.UUID


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    organization_id: uuid.UUID

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Clients ----------
class ClientCreate(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = "active"
    password: Optional[str] = None   # client login banane ke liye


class ClientUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = None


class ClientOut(BaseModel):
    id: uuid.UUID
    company_name: str
    contact_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Tasks ----------
class TaskCreate(BaseModel):
    project_id: Optional[uuid.UUID] = None
    module_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    epic: Optional[str] = None
    status: Literal["todo", "in_progress", "testing", "done"] = "todo"
    assigned_to: Optional[uuid.UUID] = None


class TaskUpdate(BaseModel):
    project_id: Optional[uuid.UUID] = None
    module_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None
    epic: Optional[str] = None
    status: Optional[Literal["todo", "in_progress", "testing", "done"]] = None
    assigned_to: Optional[uuid.UUID] = None


class TaskStatusUpdate(BaseModel):
    status: Literal["todo", "in_progress", "testing", "done"]


class TaskOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    module_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    epic: Optional[str] = None
    status: str
    completed_at: Optional[datetime] = None
    assigned_to: Optional[uuid.UUID] = None
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Documents ----------
class DocumentOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    filename: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    # How many RAG chunks exist for this file (0 = not indexed / unsupported).
    chunk_count: int = 0

    class Config:
        from_attributes = True


class ReindexResult(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunks_indexed: int
    status: str


# ---------- Projects ----------
class ProjectCreate(BaseModel):
    client_id: uuid.UUID
    name: str
    description: Optional[str] = None
    budget: Optional[float] = None
    deadline: Optional[date] = None
    status: Literal["planning", "active", "on_hold", "completed"] = "planning"
    # Managers / employees linked so they can see and work on this project
    team_user_ids: list[uuid.UUID] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    budget: Optional[float] = None
    deadline: Optional[date] = None
    status: Optional[Literal["planning", "active", "on_hold", "completed"]] = None


class ProjectTeamUpdate(BaseModel):
    user_ids: list[uuid.UUID]


class ProjectOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    client_id: uuid.UUID
    name: str
    description: Optional[str] = None
    budget: Optional[float] = None
    deadline: Optional[date] = None
    status: str
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- AI Task Generator ----------
class AITaskGenerateRequest(BaseModel):
    project_name: str
    description: str


class AITaskOut(BaseModel):
    title: str
    description: str
    priority: str


# ---------- AI Requirement Analyzer ----------
class StoryOut(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"] = "medium"


class EpicOut(BaseModel):
    title: str
    stories: list[StoryOut] = []


class RequirementAnalysisOut(BaseModel):
    epics: list[EpicOut] = []


class RequirementAnalyzeRequest(BaseModel):
    document_id: uuid.UUID
    project_id: uuid.UUID


class RequirementAnalysisResult(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    document_id: Optional[uuid.UUID] = None
    status: str
    breakdown: RequirementAnalysisOut
    created_at: datetime


class RequirementReviewApproveRequest(BaseModel):
    epics: list[EpicOut] = []


class RequirementApproveResponse(BaseModel):
    analysis_id: uuid.UUID
    task_ids: list[uuid.UUID]


# ---------- Client Dashboard ----------
class ClientDashboardOut(BaseModel):
    project_id: uuid.UUID
    project_name: str
    status: str
    deadline: Optional[date] = None
    progress_percent: float
    milestone_info: str
    documents: list[DocumentOut]

    class Config:
        from_attributes = True


# ---------- Weekly Reports ----------
class WeeklyReportOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    report_text: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Meetings ----------
class MeetingUploadResponse(BaseModel):
    id: uuid.UUID
    status: str


class MeetingSummaryOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[list[str]] = None
    risks: Optional[list[str]] = None
    deadlines: Optional[list[str]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Kept for any older callers that expect the fuller payload shape.
class MeetingOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    uploaded_by: uuid.UUID
    audio_file_url: str
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: list[str] = []
    risks: list[str] = []
    deadlines: list[str] = []
    status: str
    created_at: datetime

# ---------- Project Modules ----------
class ProjectModuleCreate(BaseModel):
    name: str
    icon: Optional[str] = "🧩"
    description: Optional[str] = None
    status: Literal["locked", "in_progress", "completed"] = "locked"


class ProjectModuleUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["locked", "in_progress", "completed"]] = None


class ProjectModuleReorder(BaseModel):
    ordered_ids: list[uuid.UUID]


class ProjectModuleOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    icon: str
    description: Optional[str] = None
    status: str
    order: int
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True    

    class Config:
        from_attributes = True