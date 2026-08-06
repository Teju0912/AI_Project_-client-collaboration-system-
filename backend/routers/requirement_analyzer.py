from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json

from database import get_db
from dependencies import get_current_user, require_role
import models
import schemas
import schemas_requirement_analyzer as ra_schemas
from routers.tasks import create_task as create_task_endpoint
from schemas import TaskCreate

router = APIRouter(prefix="/ai", tags=["ai", "requirement_analyzer"])


@router.post("/analyze-requirement", response_model=ra_schemas.AnalyzeResponse)
def analyze_requirement(
    payload: ra_schemas.AnalyzeRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(require_role(["admin", "manager"])),
):
    # Validate inputs
    if not payload.document_id and not payload.project_id:
        raise HTTPException(status_code=400, detail="Provide document_id or project_id")

    document = None
    if payload.document_id:
        document = db.query(models.Document).filter(models.Document.id == payload.document_id).first()
        if not document or document.organization_id != current_user.organization_id:
            raise HTTPException(status_code=404, detail="Document not found")

        # Ensure project (if present) is within org
        if document.project_id and payload.project_id and str(document.project_id) != str(payload.project_id):
            raise HTTPException(status_code=400, detail="Document project_id mismatch")

    # If project_id provided, validate it's in org
    project_id = None
    if payload.project_id:
        proj = db.query(models.Project).filter(models.Project.id == payload.project_id, models.Project.organization_id == current_user.organization_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        project_id = payload.project_id
    elif document and document.project_id:
        project_id = document.project_id

    # Get document text
    if not document and payload.document_id:
        raise HTTPException(status_code=404, detail="Document not found")

    document_text = ""
    # Read file content from storage_path
    if document:
        try:
            with open(document.storage_path, "r", encoding="utf-8") as fh:
                document_text = fh.read()
        except Exception:
            # If file cannot be read, try empty
            document_text = ""

    # If no document_text but project_id present, build a tiny prompt
    if not document_text and project_id:
        document_text = f"Project {project_id} - no document text provided."

    # Call analyzer
    from ai.requirement_analyzer import analyze_requirement_document

    try:
        result = analyze_requirement_document(document_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Persist analysis
    raw = result.model_dump()
    analysis = models.RequirementAnalysis(
        organization_id=current_user.organization_id,
        project_id=project_id,
        document_id=payload.document_id,
        raw_output=raw,
        status="pending_review",
        created_by=current_user.id,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return ra_schemas.AnalyzeResponse(id=analysis.id, result=result)


@router.get("/requirement-analyses/{analysis_id}", response_model=ra_schemas.RequirementAnalysisDetail)
def get_analysis(analysis_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(models.RequirementAnalysis).filter(models.RequirementAnalysis.id == analysis_id).first()
    if not analysis or analysis.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    parsed = ra_schemas.RequirementAnalysisOut.model_validate(analysis.raw_output)

    return ra_schemas.RequirementAnalysisDetail(
        id=analysis.id,
        organization_id=analysis.organization_id,
        project_id=analysis.project_id,
        document_id=analysis.document_id,
        raw_output=analysis.raw_output,
        status=analysis.status,
        created_by=analysis.created_by,
        created_at=analysis.created_at,
        parsed=parsed,
    )


@router.post("/requirement-analyses/{analysis_id}/approve", response_model=ra_schemas.ApproveResponse)
def approve_analysis(analysis_id: str, payload: ra_schemas.ApproveRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db), _=Depends(require_role(["admin", "manager"]))):
    analysis = db.query(models.RequirementAnalysis).filter(models.RequirementAnalysis.id == analysis_id).first()
    if not analysis or analysis.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis.status != "pending_review":
        raise HTTPException(status_code=400, detail="Analysis already processed")

    if not analysis.project_id:
        raise HTTPException(status_code=400, detail="Analysis must be associated with a project to create tasks")

    created_ids = []

    # For each epic, create a parent epic task (optional) and then story tasks linking to epic by name
    for epic in payload.epics:
        epic_title = epic.title
        # Create an epic as a task (optional parent)
        epic_payload = TaskCreate(project_id=analysis.project_id, title=epic_title, description=None)
        epic_task = create_task_endpoint(epic_payload, current_user, db)
        # epic_task is a TaskOut Pydantic instance
        created_ids.append(epic_task.id)

        for story in epic.stories:
            story_title = story.title
            story_description = story.description
            story_payload = TaskCreate(project_id=analysis.project_id, title=story_title, description=story_description)
            # Create story task; set epic name in the Task.epic column via direct DB update after creation
            created_task = create_task_endpoint(story_payload, current_user, db)
            created_ids.append(created_task.id)
            # Patch epic name directly on the DB model (safe and minimal change)
            task_row = db.query(models.Task).filter(models.Task.id == created_task.id, models.Task.organization_id == current_user.organization_id).first()
            if task_row:
                task_row.epic = epic_title
                db.commit()

    analysis.status = "approved"
    db.commit()

    return ra_schemas.ApproveResponse(created_task_ids=created_ids)


@router.post("/requirement-analyses/{analysis_id}/reject", response_model=ra_schemas.RejectResponse)
def reject_analysis(analysis_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db), _=Depends(require_role(["admin", "manager"]))):
    analysis = db.query(models.RequirementAnalysis).filter(models.RequirementAnalysis.id == analysis_id).first()
    if not analysis or analysis.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis.status != "pending_review":
        raise HTTPException(status_code=400, detail="Analysis already processed")

    analysis.status = "rejected"
    db.commit()
    return ra_schemas.RejectResponse(id=analysis.id, status=analysis.status)