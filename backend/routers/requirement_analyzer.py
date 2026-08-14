from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List, Optional
import uuid

from database import get_db
from dependencies import get_current_user, require_role
import models
from routers.tasks import create_task as create_task_endpoint
from schemas import TaskCreate
import schemas_requirement_analyzer as ra_schemas

router = APIRouter(prefix="/ai", tags=["ai", "requirement_analyzer"])


def _epics_from_raw(raw) -> list:
    if not isinstance(raw, dict):
        return []
    if isinstance(raw.get("epics"), list):
        return raw["epics"]
    for key in ("result", "breakdown", "parsed"):
        nested = raw.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("epics"), list):
            return nested["epics"]
    return []


def _story_created_id(story: dict) -> Optional[str]:
    value = (story or {}).get("created_task_id")
    if value in (None, "", "null"):
        return None
    return str(value)


def _story_counts(epics: list) -> tuple[int, int, int]:
    total = 0
    created = 0
    for epic in epics or []:
        for story in (epic or {}).get("stories") or []:
            total += 1
            if _story_created_id(story):
                created += 1
    return total, created, total - created


def _parsed_from_raw(raw) -> ra_schemas.RequirementAnalysisOut:
    epics = _epics_from_raw(raw)
    try:
        return ra_schemas.RequirementAnalysisOut.model_validate({"epics": epics})
    except Exception:
        return ra_schemas.RequirementAnalysisOut(epics=[])


def _project_name(db: Session, project_id) -> Optional[str]:
    if not project_id:
        return None
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    return project.name if project else None


def _document_filename(db: Session, document_id) -> Optional[str]:
    if not document_id:
        return None
    document = db.query(models.Document).filter(models.Document.id == document_id).first()
    return document.filename if document else None


def _serialize_detail(db: Session, analysis: models.RequirementAnalysis) -> ra_schemas.RequirementAnalysisDetail:
    parsed = _parsed_from_raw(analysis.raw_output)
    total, created, pending = _story_counts(_epics_from_raw(analysis.raw_output))
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
        project_name=_project_name(db, analysis.project_id),
        document_filename=_document_filename(db, analysis.document_id),
        pending_story_count=pending,
        created_story_count=created,
    )


def _create_story_task(
    *,
    analysis: models.RequirementAnalysis,
    current_user,
    db: Session,
    title: str,
    description: Optional[str],
    epic_title: str,
    priority: str,
    module_id: uuid.UUID,
    assigned_to: uuid.UUID,
    deadline,
):
    if not analysis.project_id:
        raise HTTPException(status_code=400, detail="Analysis must be associated with a project to create tasks")
    if not module_id:
        raise HTTPException(status_code=400, detail="A project module is required before creating this task")
    if not assigned_to:
        raise HTTPException(status_code=400, detail="An employee must be assigned before creating this task")

    payload = TaskCreate(
        project_id=analysis.project_id,
        module_id=module_id,
        title=title,
        description=description,
        epic=epic_title,
        assigned_to=assigned_to,
        priority=priority if priority in {"low", "medium", "high", "urgent"} else "medium",
        deadline=deadline,
    )
    return create_task_endpoint(payload, current_user, db)


def _mark_story_created(analysis: models.RequirementAnalysis, epic_index: int, story_index: int, updates: dict) -> None:
    raw = dict(analysis.raw_output or {})
    epics = _epics_from_raw(raw)
    if epic_index < 0 or epic_index >= len(epics):
        raise HTTPException(status_code=400, detail="Invalid epic index")
    stories = epics[epic_index].get("stories") or []
    if story_index < 0 or story_index >= len(stories):
        raise HTTPException(status_code=400, detail="Invalid story index")
    story = dict(stories[story_index])
    story.update(updates)
    stories[story_index] = story
    epics[epic_index] = dict(epics[epic_index])
    epics[epic_index]["stories"] = stories
    raw["epics"] = epics
    analysis.raw_output = raw
    flag_modified(analysis, "raw_output")


def _refresh_analysis_status(analysis: models.RequirementAnalysis) -> None:
    _, _, pending = _story_counts(_epics_from_raw(analysis.raw_output))
    if pending == 0 and analysis.status == "pending_review":
        analysis.status = "approved"


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
        result = analyze_requirement_document(
            document_text,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Persist analysis as a draft only — no tasks until Review Drafts approval.
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

    return ra_schemas.AnalyzeResponse(id=analysis.id, status=analysis.status, result=result)


@router.get("/requirement-analyses", response_model=List[ra_schemas.RequirementAnalysisListItem])
def list_analyses(
    status: Optional[str] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(require_role(["admin", "manager"])),
):
    query = db.query(models.RequirementAnalysis).filter(
        models.RequirementAnalysis.organization_id == current_user.organization_id
    )
    if status:
        query = query.filter(models.RequirementAnalysis.status == status)
    if project_id:
        query = query.filter(models.RequirementAnalysis.project_id == project_id)

    rows = query.order_by(models.RequirementAnalysis.created_at.desc()).all()
    items = []
    for analysis in rows:
        parsed = _parsed_from_raw(analysis.raw_output)
        total, created, pending = _story_counts(_epics_from_raw(analysis.raw_output))
        items.append(
            ra_schemas.RequirementAnalysisListItem(
                id=analysis.id,
                organization_id=analysis.organization_id,
                project_id=analysis.project_id,
                document_id=analysis.document_id,
                status=analysis.status,
                created_by=analysis.created_by,
                created_at=analysis.created_at,
                project_name=_project_name(db, analysis.project_id),
                document_filename=_document_filename(db, analysis.document_id),
                epic_count=len(parsed.epics),
                story_count=total,
                pending_story_count=pending,
                created_story_count=created,
                parsed=parsed,
            )
        )
    return items


@router.get("/requirement-analyses/{analysis_id}", response_model=ra_schemas.RequirementAnalysisDetail)
def get_analysis(analysis_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = db.query(models.RequirementAnalysis).filter(models.RequirementAnalysis.id == analysis_id).first()
    if not analysis or analysis.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return _serialize_detail(db, analysis)


@router.post("/requirement-analyses/{analysis_id}/approve-story", response_model=ra_schemas.ApproveStoryResponse)
def approve_story(
    analysis_id: str,
    payload: ra_schemas.ApproveStoryRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_role(["admin", "manager"])),
):
    analysis = db.query(models.RequirementAnalysis).filter(models.RequirementAnalysis.id == analysis_id).first()
    if not analysis or analysis.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis.status != "pending_review":
        raise HTTPException(status_code=400, detail="Analysis already processed")

    epics = _epics_from_raw(analysis.raw_output)
    if payload.epic_index < 0 or payload.epic_index >= len(epics):
        raise HTTPException(status_code=400, detail="Invalid epic index")
    stories = epics[payload.epic_index].get("stories") or []
    if payload.story_index < 0 or payload.story_index >= len(stories):
        raise HTTPException(status_code=400, detail="Invalid story index")

    stored = stories[payload.story_index] or {}
    if _story_created_id(stored):
        raise HTTPException(status_code=400, detail="This story has already been created as a task")

    epic_title = (epics[payload.epic_index] or {}).get("title") or ""
    title = (payload.title or stored.get("title") or "").strip()
    description = payload.description if payload.description is not None else stored.get("description")
    if not title:
        raise HTTPException(status_code=400, detail="Story title is required")

    created_task = _create_story_task(
        analysis=analysis,
        current_user=current_user,
        db=db,
        title=title,
        description=description,
        epic_title=epic_title,
        priority=payload.priority,
        module_id=payload.module_id,
        assigned_to=payload.assigned_to,
        deadline=payload.deadline,
    )

    _mark_story_created(
        analysis,
        payload.epic_index,
        payload.story_index,
        {
            "title": title,
            "description": description,
            "priority": payload.priority,
            "module_id": str(payload.module_id),
            "assigned_to": str(payload.assigned_to),
            "deadline": payload.deadline.isoformat() if payload.deadline else None,
            "created_task_id": str(created_task.id),
        },
    )
    _refresh_analysis_status(analysis)
    db.commit()
    db.refresh(analysis)

    _, created_n, pending_n = _story_counts(_epics_from_raw(analysis.raw_output))
    return ra_schemas.ApproveStoryResponse(
        created_task_id=created_task.id,
        status=analysis.status,
        pending_story_count=pending_n,
        created_story_count=created_n,
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
    stored_epics = _epics_from_raw(analysis.raw_output)

    for ei, epic in enumerate(payload.epics):
        stored_stories = []
        if ei < len(stored_epics):
            stored_stories = stored_epics[ei].get("stories") or []
        for si, story in enumerate(epic.stories):
            stored = stored_stories[si] if si < len(stored_stories) else {}
            if _story_created_id(stored) or story.created_task_id:
                continue
            if not story.module_id or not story.assigned_to:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Each story needs a module and an assigned employee before "
                        "it can become a task. Open Review Drafts to assign them."
                    ),
                )
            created_task = _create_story_task(
                analysis=analysis,
                current_user=current_user,
                db=db,
                title=story.title,
                description=story.description,
                epic_title=epic.title,
                priority=story.priority,
                module_id=story.module_id,
                assigned_to=story.assigned_to,
                deadline=story.deadline,
            )
            created_ids.append(created_task.id)
            _mark_story_created(
                analysis,
                ei,
                si,
                {
                    "title": story.title,
                    "description": story.description,
                    "priority": story.priority,
                    "module_id": str(story.module_id),
                    "assigned_to": str(story.assigned_to),
                    "deadline": story.deadline.isoformat() if story.deadline else None,
                    "created_task_id": str(created_task.id),
                },
            )

    _refresh_analysis_status(analysis)
    db.commit()

    return ra_schemas.ApproveResponse(created_task_ids=created_ids, status=analysis.status)


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
