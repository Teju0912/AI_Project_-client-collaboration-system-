from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import WeeklyReport, Project
from schemas import WeeklyReportOut
from services.weekly_report_service import generate_report

router = APIRouter(
    prefix="/weekly-reports",
    tags=["Weekly Reports"]
)


@router.post("/generate/{project_id}",
             response_model=WeeklyReportOut)
def generate_weekly_report(
    project_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    project = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    report_text = generate_report(
        db,
        project_id
    )

    report = WeeklyReport(
        organization_id=current_user.organization_id,
        project_id=project_id,
        report_text=report_text
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return report


# NEW ENDPOINT
@router.get("/{project_id}",
            response_model=list[WeeklyReportOut])
def get_reports(
    project_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    reports = (
        db.query(WeeklyReport)
        .filter(
            WeeklyReport.project_id == project_id,
            WeeklyReport.organization_id == current_user.organization_id
        )
        .order_by(WeeklyReport.created_at.desc())
        .all()
    )

    return reports