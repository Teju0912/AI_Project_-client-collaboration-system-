'''tasks.py - Task management endpoints for the FastAPI backend.'''

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_role
from models import ProjectModule, Task, User
from project_access import (
    assert_manager_can_access_project,
    ensure_project_member,
    get_org_project_or_404,
)
from schemas import TaskCreate, TaskOut, TaskStatusUpdate, TaskUpdate


router = APIRouter(prefix="/tasks", tags=["tasks"])


def create_task_record(
    db: Session,
    *,
    organization_id,
    project_id,
    module_id=None,
    title: str,
    description: Optional[str],
    epic: Optional[str],
    status: str,
    assigned_to,
    created_by,
) -> Task:
    """
    Core Module 4 task-creation logic. Both the /tasks router endpoint and
    the AI Requirement Analyzer reuse this so there is a single path for
    writing Task rows (no second parallel implementation).
    """
    task = Task(
        organization_id=organization_id,
        project_id=project_id,
        module_id=module_id,
        title=title,
        description=description,
        epic=epic,
        status=status,
        assigned_to=assigned_to,
        created_by=created_by,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def serialize_task(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        organization_id=task.organization_id,
        project_id=task.project_id,
        module_id=task.module_id,
        title=task.title,
        description=task.description,
        epic=task.epic,
        status=task.status,
        completed_at=task.completed_at,
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
    elif current_user.role == "employee":
        # Employee: only tasks assigned to them
        query = query.filter(Task.assigned_to == current_user.id)
        if project_id is not None:
            query = query.filter(Task.project_id == project_id)
    elif current_user.role == "client":
        # Clients use /client-dashboard for progress; no direct task list
        return []
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

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

    _validate_task_module(
        db, payload.module_id, payload.project_id, current_user.organization_id
    )

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

    task = create_task_record(
        db,
        organization_id=current_user.organization_id,
        project_id=payload.project_id,
        module_id=payload.module_id,
        title=payload.title,
        description=payload.description,
        epic=payload.epic,
        status=payload.status,
        assigned_to=payload.assigned_to,
        created_by=current_user.id,
    )
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

    previous_status = task.status
    task.status = payload.status
    if payload.status != "done":
        task.completed_at = None
    elif previous_status != "done":
        task.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def _validate_task_module(db: Session, module_id, project_id, organization_id) -> None:
    """Ensure a task's selected module belongs to its project."""
    if module_id is None:
        return
    if project_id is None:
        raise HTTPException(status_code=400, detail="A module can only be used with a project")
    module = db.query(ProjectModule).filter(
        ProjectModule.id == module_id,
        ProjectModule.project_id == project_id,
        ProjectModule.organization_id == organization_id,
    ).first()
    if not module:
        raise HTTPException(status_code=400, detail="Module does not belong to this project")


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(require_role(["admin", "manager"])),
):
    """Edit task details while enforcing the same project access as deletion."""
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.organization_id == current_user.organization_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current_user.role == "manager":
        if task.project_id is None:
            raise HTTPException(status_code=403, detail="Not authorized for this task")
        assert_manager_can_access_project(db, current_user, task.project_id)

    changes = payload.model_dump(exclude_unset=True)
    if "project_id" in changes:
        project_id = changes["project_id"]
        if project_id is None and current_user.role == "manager":
            raise HTTPException(status_code=400, detail="Managers must keep tasks under a project")
        if project_id is not None:
            get_org_project_or_404(db, project_id, current_user.organization_id)
            assert_manager_can_access_project(db, current_user, project_id)

    target_project_id = changes.get("project_id", task.project_id)
    target_module_id = changes.get("module_id", task.module_id)
    _validate_task_module(
        db, target_module_id, target_project_id, current_user.organization_id
    )

    if "assigned_to" in changes and changes["assigned_to"] is not None:
        assigned_user = (
            db.query(User)
            .filter(
                User.id == changes["assigned_to"],
                User.organization_id == current_user.organization_id,
            )
            .first()
        )
        if not assigned_user:
            raise HTTPException(status_code=404, detail="Assigned user not found in this organization")
        if assigned_user.role not in {"employee", "manager", "admin"}:
            raise HTTPException(status_code=400, detail="Tasks can only be assigned to staff users")
        if target_project_id is not None:
            ensure_project_member(db, target_project_id, assigned_user.id)

    previous_status = task.status
    for field, value in changes.items():
        setattr(task, field, value)
    if "status" in changes:
        if task.status != "done":
            task.completed_at = None
        elif previous_status != "done":
            task.completed_at = datetime.utcnow()
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