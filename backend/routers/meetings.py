import json
import re
import threading
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import database
from database import get_db
from dependencies import get_current_user, require_role
import models
import schemas
from project_access import is_project_member
from services import meeting_summarizer_service as meeting_service

router = APIRouter(prefix="/meetings", tags=["meetings"])

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploaded_files"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    name = name or "meeting"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _get_project_or_404(db: Session, project_id: UUID, organization_id: UUID) -> models.Project:
    project = (
        db.query(models.Project)
        .filter(models.Project.id == project_id, models.Project.organization_id == organization_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _assert_project_access(db: Session, current_user: models.User, project_id: UUID) -> None:
    if current_user.role == "admin":
        return
    if current_user.role in {"manager", "employee"}:
        if not is_project_member(db, project_id, current_user.id):
            raise HTTPException(status_code=403, detail="You do not have access to this project.")
        return
    raise HTTPException(status_code=403, detail="You do not have access to this project.")


def _serialize_meeting(meeting: models.Meeting) -> schemas.MeetingSummaryOut:
    def _load_json(value):
        if not value:
            return None
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None

    return schemas.MeetingSummaryOut(
        id=meeting.id,
        project_id=meeting.project_id,
        status=meeting.status,
        transcript=meeting.transcript,
        summary=meeting.summary,
        action_items=_load_json(meeting.action_items),
        risks=_load_json(meeting.risks),
        deadlines=_load_json(meeting.deadlines),
        created_at=meeting.created_at,
    )


@router.post("/upload", response_model=schemas.MeetingUploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_meeting(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    current_user: models.User = Depends(require_role(["admin", "manager", "employee"])),
    db: Session = Depends(get_db),
):
    try:
        parsed_project_id = UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project_id format") from exc

    project = _get_project_or_404(db, parsed_project_id, current_user.organization_id)
    _assert_project_access(db, current_user, project.id)

    clean_name = _safe_filename(file.filename)
    unique_name = f"{uuid4()}_{clean_name}"
    storage_path = UPLOAD_ROOT / unique_name
    storage_path.write_bytes(file.file.read())

    meeting = models.Meeting(
        organization_id=current_user.organization_id,
        project_id=project.id,
        uploaded_by=current_user.id,
        audio_file_url=str(storage_path),
        status="processing",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    def _run_processing() -> None:
        session = database.SessionLocal()
        try:
            print(f"[_run_processing] start meeting_id={meeting.id}")
            meeting_service.process_meeting(meeting.id, session)
            print(f"[_run_processing] completed meeting_id={meeting.id}")
        except Exception as exc:
            print(f"[_run_processing] unexpected error meeting_id={meeting.id}: {exc}")
            import traceback

            traceback.print_exc()
        finally:
            session.close()

    thread = threading.Thread(target=_run_processing, daemon=True)
    thread.start()

    return schemas.MeetingUploadResponse(id=meeting.id, status=meeting.status)


@router.get("/{meeting_id}", response_model=schemas.MeetingSummaryOut)
def get_meeting(
    meeting_id: UUID,
    current_user: models.User = Depends(require_role(["admin", "manager", "employee"])),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    _assert_project_access(db, current_user, meeting.project_id)
    return _serialize_meeting(meeting)


@router.get("/project/{project_id}", response_model=list[schemas.MeetingSummaryOut])
def list_meetings_for_project(
    project_id: UUID,
    current_user: models.User = Depends(require_role(["admin", "manager", "employee"])),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, project_id, current_user.organization_id)
    _assert_project_access(db, current_user, project.id)

    meetings = (
        db.query(models.Meeting)
        .filter(models.Meeting.organization_id == current_user.organization_id, models.Meeting.project_id == project_id)
        .order_by(models.Meeting.created_at.desc())
        .all()
    )
    return [_serialize_meeting(meeting) for meeting in meetings]
