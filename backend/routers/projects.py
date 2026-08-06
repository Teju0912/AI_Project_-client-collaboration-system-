import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_role, get_current_user
from project_access import (
    assert_manager_can_access_project,
    ensure_project_member,
    is_project_member,
    manager_or_employee_project_ids,
    resolve_team_user_ids,
)
import models
import schemas

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectOut)
def create_project(
    payload: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    client = (
        db.query(models.Client)
        .filter(
            models.Client.id == payload.client_id,
            models.Client.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Managers may only create projects they will own — they are always on the team
    team_ids = resolve_team_user_ids(
        db,
        current_user.organization_id,
        list(payload.team_user_ids or []),
    )

    if current_user.role == "manager" and not team_ids:
        # Manager creating alone is fine — they become the only member
        pass

    project = models.Project(
        organization_id=current_user.organization_id,
        client_id=payload.client_id,
        name=payload.name,
        description=payload.description,
        budget=payload.budget,
        deadline=payload.deadline,
        status=payload.status,
        created_by=current_user.id,
    )
    db.add(project)
    db.flush()

    # Creator is always on the team (admin or manager)
    ensure_project_member(db, project.id, current_user.id)

    for user_id in team_ids:
        ensure_project_member(db, project.id, user_id)

    # Admin-created projects with no manager selected → assign all org managers
    # so project managers can see and work on them.
    if current_user.role == "admin":
        has_manager = False
        if team_ids:
            has_manager = (
                db.query(models.User)
                .filter(
                    models.User.id.in_(team_ids),
                    models.User.role == "manager",
                )
                .first()
                is not None
            )
        if not has_manager:
            org_managers = (
                db.query(models.User)
                .filter(
                    models.User.organization_id == current_user.organization_id,
                    models.User.role == "manager",
                    models.User.is_active.is_(True),
                )
                .all()
            )
            for manager in org_managers:
                ensure_project_member(db, project.id, manager.id)

    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Project).filter(
        models.Project.organization_id == current_user.organization_id
    )

    if current_user.role in {"admin", "manager"}:
        # Admin and managers see all org projects (managers pick one in the UI dropdown)
        pass
    elif current_user.role == "employee":
        allowed = manager_or_employee_project_ids(db, current_user.id)
        if not allowed:
            return []
        query = query.filter(models.Project.id.in_(allowed))
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    return query.order_by(models.Project.created_at.desc()).all()


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update_project(
    project_id: uuid.UUID,
    payload: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assert_manager_can_access_project(db, current_user, project_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}/team", response_model=list[uuid.UUID])
def assign_team(
    project_id: uuid.UUID,
    payload: schemas.ProjectTeamUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assert_manager_can_access_project(db, current_user, project_id)

    team_ids = resolve_team_user_ids(
        db,
        current_user.organization_id,
        list(payload.user_ids or []),
    )

    # Keep current editor on the team so they don't lock themselves out
    all_user_ids = set(team_ids)
    if current_user.role in {"admin", "manager"}:
        all_user_ids.add(current_user.id)

    # Keep original creator if they are still an active staff user
    creator = (
        db.query(models.User)
        .filter(
            models.User.id == project.created_by,
            models.User.organization_id == current_user.organization_id,
            models.User.role.in_(["admin", "manager", "employee"]),
        )
        .first()
    )
    if creator:
        all_user_ids.add(creator.id)

    db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id
    ).delete()

    for user_id in all_user_ids:
        db.add(models.ProjectMember(project_id=project_id, user_id=user_id))

    db.commit()
    return list(all_user_ids)


@router.get("/{project_id}/team", response_model=list[schemas.UserOut])
def get_team(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if current_user.role == "employee":
        if not is_project_member(db, project_id, current_user.id):
            raise HTTPException(status_code=403, detail="Not assigned to this project")
    elif current_user.role not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Not authorized")

    return (
        db.query(models.User)
        .join(models.ProjectMember, models.ProjectMember.user_id == models.User.id)
        .filter(models.ProjectMember.project_id == project_id)
        .all()
    )