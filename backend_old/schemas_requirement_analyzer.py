from __future__ import annotations

from pydantic import BaseModel
from typing import List, Literal, Optional
import uuid
from datetime import datetime


class StoryOut(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"]


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


# Approve payload (user-edited final list)
class ApproveRequest(BaseModel):
    epics: List[EpicOut]


# Approve response — returns created task IDs
class ApproveResponse(BaseModel):
    created_task_ids: List[uuid.UUID]


# Reject response — just confirmation
class RejectResponse(BaseModel):
    id: uuid.UUID
    status: str
