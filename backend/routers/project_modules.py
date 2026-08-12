""" project_modules.py"""

import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Client, ProjectModule, Project
from schemas import (
    ProjectModuleCreate,
    ProjectModuleUpdate,
    ProjectModuleReorder,
    ProjectModuleOut,
)
from dependencies import get_current_user, require_role
from project_access import is_project_member

router = APIRouter()


def _get_project_or_404(db: Session, project_id: str, org_id):
    project = db.query(Project).filter(
        Project.id == project_id, Project.organization_id == org_id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _assert_can_view_modules(db: Session, project, current_user):
    """Clients may only see modules for projects belonging to their client record."""
    if current_user.role in {"admin", "manager"}:
        return
    if current_user.role == "employee":
        if is_project_member(db, project.id, current_user.id):
            return
        raise HTTPException(status_code=403, detail="Not assigned to this project")
    if current_user.role != "client":
        raise HTTPException(status_code=403, detail="Not authorized for project modules")
    linked_client = (
        db.query(Client)
        .filter(
            Client.id == project.client_id,
            Client.organization_id == current_user.organization_id,
            func.lower(Client.email) == current_user.email.lower(),
        )
        .first()
    )
    if not linked_client:
        raise HTTPException(status_code=403, detail="Not authorized for this project's modules")


@router.get("/projects/{project_id}/modules", response_model=List[ProjectModuleOut])
def list_modules(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    project = _get_project_or_404(db, str(project_id), current_user.organization_id)
    _assert_can_view_modules(db, project, current_user)
    modules = (
        db.query(ProjectModule)
        .filter(ProjectModule.project_id == project_id)
        .order_by(ProjectModule.order)
        .all()
    )
    return modules


@router.post("/projects/{project_id}/modules", response_model=ProjectModuleOut, status_code=201)
def create_module(
    project_id: uuid.UUID,
    payload: ProjectModuleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "manager"])),
):
    _get_project_or_404(db, str(project_id), current_user.organization_id)
    max_order = (
        db.query(func.max(ProjectModule.order))
        .filter(ProjectModule.project_id == project_id)
        .scalar()
    ) or 0

    module = ProjectModule(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        project_id=project_id,
        name=payload.name,
        icon=payload.icon or "🧩",
        description=payload.description,
        status=payload.status or "locked",
        order=max_order + 1,
        created_by=current_user.id,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


@router.post(
    "/projects/{project_id}/modules/insert-at/{position}",
    response_model=ProjectModuleOut,
    status_code=201,
)
def insert_module_at(
    project_id: uuid.UUID,
    position: int,
    payload: ProjectModuleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "manager"])),
):
    """Insert a module at a specific 0-based order position, shifting later ones down."""
    _get_project_or_404(db, str(project_id), current_user.organization_id)
    modules = (
        db.query(ProjectModule)
        .filter(ProjectModule.project_id == project_id)
        .order_by(ProjectModule.order)
        .all()
    )
    for m in modules:
        if m.order >= position:
            m.order += 1

    module = ProjectModule(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        project_id=project_id,
        name=payload.name,
        icon=payload.icon or "🧩",
        description=payload.description,
        status=payload.status or "locked",
        order=position,
        created_by=current_user.id,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


@router.patch("/modules/{module_id}", response_model=ProjectModuleOut)
def update_module(
    module_id: uuid.UUID,
    payload: ProjectModuleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "manager"])),
):
    module = db.query(ProjectModule).filter(
        ProjectModule.id == module_id,
        ProjectModule.organization_id == current_user.organization_id,
    ).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(module, field, value)

    db.commit()
    db.refresh(module)
    return module


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(
    module_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "manager"])),
):
    module = db.query(ProjectModule).filter(
        ProjectModule.id == module_id,
        ProjectModule.organization_id == current_user.organization_id,
    ).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    db.delete(module)
    db.commit()


@router.post("/projects/{project_id}/modules/reorder")
def reorder_modules(
    project_id: uuid.UUID,
    payload: ProjectModuleReorder,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "manager"])),
):
    _get_project_or_404(db, str(project_id), current_user.organization_id)
    modules = {
        m.id: m
        for m in db.query(ProjectModule).filter(ProjectModule.project_id == project_id).all()
    }
    for idx, mod_id in enumerate(payload.ordered_ids):
        if mod_id in modules:
            modules[mod_id].order = idx
    db.commit()
    return {"ok": True}