from __future__ import annotations

from typing import Literal
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_role
from models import Task, User
from schemas import TaskCreate, TaskOut, TaskStatusUpdate, TaskUpdate

from project_access import (
    assert_manager_can_access_project,
    ensure_project_member,
    get_org_project_or_404,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


def serialize_task(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        organization_id=task.organization_id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        status=task.status,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        created_at=task.created_at,
    )


@router.get("", response_model=list[TaskOut])
def list_tasks(
    project_id: Optional[UUID] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Task).filter(Task.organization_id == current_user.organization_id)

    if current_user.role == "admin":
        if project_id is not None:
            query = query.filter(Task.project_id == project_id)
    elif current_user.role == "manager":
        # Managers see all org project tasks; optional dropdown filter by project_id
        if project_id is not None:
            assert_manager_can_access_project(db, current_user, project_id)
            query = query.filter(Task.project_id == project_id)
    else:
        # Employee: only tasks assigned to them
        query = query.filter(Task.assigned_to == current_user.id)
        if project_id is not None:
            query = query.filter(Task.project_id == project_id)

    tasks = query.order_by(Task.created_at.desc()).all()
    return [serialize_task(task) for task in tasks]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(require_role(["admin", "manager"])),
):
    if payload.project_id is None:
        if current_user.role == "manager":
            raise HTTPException(
                status_code=400,
                detail="Managers must create tasks under a project.",
            )
    else:
        get_org_project_or_404(db, payload.project_id, current_user.organization_id)
        assert_manager_can_access_project(db, current_user, payload.project_id)

    if payload.assigned_to:
        assigned_user = (
            db.query(User)
            .filter(
                User.id == payload.assigned_to,
                User.organization_id == current_user.organization_id,
            )
            .first()
        )
        if not assigned_user:
            raise HTTPException(status_code=404, detail="Assigned user not found in this organization")
        if assigned_user.role not in {"employee", "manager", "admin"}:
            raise HTTPException(status_code=400, detail="Tasks can only be assigned to staff users")

        # Connect employee to the project team so they get project docs/context
        if payload.project_id is not None:
            ensure_project_member(db, payload.project_id, assigned_user.id)

    task = Task(
        organization_id=current_user.organization_id,
        project_id=payload.project_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        assigned_to=payload.assigned_to,
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return serialize_task(task)


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_task_status(
    task_id: UUID,
    payload: TaskStatusUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current_user.role == "manager":
        if task.project_id is None:
            raise HTTPException(status_code=403, detail="Not authorized for this task")
        assert_manager_can_access_project(db, current_user, task.project_id)
    elif current_user.role not in {"admin"} and task.assigned_to != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the assignee or admin/manager can change task status",
        )

    task.status = payload.status
    db.commit()
    db.refresh(task)
    return serialize_task(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(require_role(["admin", "manager"])),
):
    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current_user.role == "manager":
        if task.project_id is None:
            raise HTTPException(status_code=403, detail="Not authorized for this task")
        assert_manager_can_access_project(db, current_user, task.project_id)

    db.delete(task)
    db.commit()
    return None