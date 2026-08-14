from __future__ import annotations

from pydantic import BaseModel
from typing import List, Literal, Optional
import uuid
from datetime import date, datetime


class StoryOut(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"]
    # Filled in during Review Drafts; ignored by the LLM analyzer.
    module_id: Optional[uuid.UUID] = None
    assigned_to: Optional[uuid.UUID] = None
    deadline: Optional[date] = None
    created_task_id: Optional[uuid.UUID] = None


class EpicOut(BaseModel):
    title: str
    stories: List[StoryOut]


class RequirementAnalysisOut(BaseModel):
    epics: List[EpicOut]


# API request to start analysis
class AnalyzeRequest(BaseModel):
    document_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None


# Response for analyze endpoint
class AnalyzeResponse(BaseModel):
    id: uuid.UUID
    status: str = "pending_review"
    result: RequirementAnalysisOut


# Fetch/Review response
class RequirementAnalysisDetail(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    document_id: Optional[uuid.UUID]
    raw_output: dict
    status: str
    created_by: uuid.UUID
    created_at: datetime
    parsed: RequirementAnalysisOut
    project_name: Optional[str] = None
    document_filename: Optional[str] = None
    pending_story_count: int = 0
    created_story_count: int = 0


class RequirementAnalysisListItem(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    document_id: Optional[uuid.UUID]
    status: str
    created_by: uuid.UUID
    created_at: datetime
    project_name: Optional[str] = None
    document_filename: Optional[str] = None
    epic_count: int = 0
    story_count: int = 0
    pending_story_count: int = 0
    created_story_count: int = 0
    parsed: RequirementAnalysisOut


# Approve payload (user-edited final list)
class ApproveRequest(BaseModel):
    epics: List[EpicOut]


# Approve a single draft story as a real task
class ApproveStoryRequest(BaseModel):
    epic_index: int
    story_index: int
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Literal["low", "medium", "high"] = "medium"
    module_id: uuid.UUID
    assigned_to: uuid.UUID
    deadline: Optional[date] = None


# Approve response — returns created task IDs
class ApproveResponse(BaseModel):
    created_task_ids: List[uuid.UUID]
    status: str = "pending_review"


class ApproveStoryResponse(BaseModel):
    created_task_id: uuid.UUID
    status: str
    pending_story_count: int
    created_story_count: int


# Reject response — just confirmation
class RejectResponse(BaseModel):
    id: uuid.UUID
    status: str
