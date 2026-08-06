from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_role
import models
import schemas
from routers.documents import serialize_document

router = APIRouter(prefix="/client-dashboard", tags=["client-dashboard"])


@router.get("", response_model=list[schemas.ClientDashboardOut])
def get_client_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["client"])),
):
    # Client user ka email uske Client record se match hota hai (assumption:
    # client login karte waqt Client.email == User.email)
    client = (
        db.query(models.Client)
        .filter(
            models.Client.email == current_user.email,
            models.Client.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="No client profile linked to this account")

    projects = (
        db.query(models.Project)
        .filter(
            models.Project.client_id == client.id,
            models.Project.organization_id == current_user.organization_id,
        )
        .all()
    )

    result = []
    for project in projects:
        tasks = db.query(models.Task).filter(models.Task.project_id == project.id).all()
        total = len(tasks)
        done = len([t for t in tasks if t.status == "done"])
        progress = round((done / total) * 100, 1) if total > 0 else 0.0

        documents = (
            db.query(models.Document)
            .filter(models.Document.project_id == project.id)
            .all()
        )

        result.append(
            schemas.ClientDashboardOut(
                project_id=project.id,
                project_name=project.name,
                status=project.status,
                deadline=project.deadline,
                progress_percent=progress,
                milestone_info=f"{done}/{total} tasks completed",
                documents=[serialize_document(doc, db) for doc in documents],
            )
        )

    return result