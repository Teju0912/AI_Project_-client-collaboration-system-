"""
tasks_jira_router.py

NEW backend endpoints that power the Jira-style Tasks tab:
  - GET    /tasks/{task_id}                  full issue detail (subtasks, comments, links)
  - POST   /tasks/{task_id}/subtasks         create a sub-task under an issue
  - GET    /tasks/{task_id}/subtasks         list sub-tasks
  - POST   /tasks/{task_id}/comments         add a comment
  - GET    /tasks/{task_id}/comments         list comments
  - POST   /tasks/{task_id}/links            link this issue to another
  - GET    /tasks/{task_id}/links            list linked issues
  - DELETE /tasks/{task_id}/links/{link_id}  remove a link

HOW TO WIRE THIS IN
--------------------
1. This file assumes two dependencies exist somewhere in your project:
     - `get_db`            -> yields a SQLAlchemy Session
     - `get_current_user`  -> returns the authenticated User (from your JWT auth)
   Update the two imports right below to point at your real modules
   (e.g. `from database import get_db`, `from auth import get_current_user`).

2. In your main FastAPI app file:
     from tasks_jira_router import router as tasks_jira_router
     app.include_router(tasks_jira_router)

3. Your EXISTING `POST /tasks` and `PATCH /tasks/{id}` handlers (wherever
   they live today) must be extended to accept the new Task fields so
   create/edit forms can save them. Add these optional fields to whatever
   Pydantic schema those two routes already use:

     priority: Optional[str] = None        # "low" | "medium" | "high" | "urgent"
     story_points: Optional[float] = None
     labels: Optional[list[str]] = None
     parent_task_id: Optional[str] = None

   ...and in the handler body, set them on the ORM object same as the
   existing fields (title, description, status, etc.) when present.
   Nothing in THIS file duplicates those two routes, to avoid a
   "duplicate path operation" conflict with your existing router.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user

from models import Task, TaskComment, TaskLink, User

router = APIRouter(prefix="/tasks", tags=["tasks-jira"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SubtaskCreateIn(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    assigned_to: Optional[str] = None


class CommentCreateIn(BaseModel):
    body: str = Field(min_length=1)


class CommentOut(BaseModel):
    id: str
    body: str
    author_id: Optional[str]
    author_name: str
    created_at: str


class TaskLinkCreateIn(BaseModel):
    linked_task_id: str
    link_type: str = "relates to"


class TaskLinkOut(BaseModel):
    id: str
    link_type: str
    linked_task_id: str
    linked_task_title: str
    linked_task_status: str


class SubtaskOut(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    assigned_to: Optional[str]
    assigned_to_name: Optional[str]
    testing_assigned_to: List[str]
    testing_status: Optional[str]


class TaskDetailOut(BaseModel):
    id: str
    project_id: Optional[str]
    title: str
    description: Optional[str]
    epic: Optional[str]
    status: str
    priority: str
    story_points: Optional[float]
    labels: List[str]
    assigned_to: Optional[str]
    assigned_to_name: Optional[str]
    created_by: Optional[str]
    created_by_name: Optional[str]
    created_at: str
    parent_task_id: Optional[str]
    subtasks: List[SubtaskOut]
    comments: List[CommentOut]
    links: List[TaskLinkOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_org_task(db: Session, task_id: str, organization_id) -> Task:
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.organization_id == organization_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _user_name(db: Session, user_id) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    return u.name if u else None


def _serialize_detail(db: Session, task: Task) -> dict:
    subtasks = db.query(Task).filter(Task.parent_task_id == task.id).all()
    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task.id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )
    links = db.query(TaskLink).filter(TaskLink.task_id == task.id).all()

    linked_tasks_by_id = {}
    if links:
        linked_ids = [l.linked_task_id for l in links]
        for t in db.query(Task).filter(Task.id.in_(linked_ids)).all():
            linked_tasks_by_id[str(t.id)] = t

    return {
        "id": str(task.id),
        "project_id": str(task.project_id) if task.project_id else None,
        "module_id": str(task.module_id) if task.module_id else None,
        "title": task.title,
        "description": task.description,
        "epic": task.epic,
        "status": task.status,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "priority": task.priority or "medium",
        "story_points": float(task.story_points) if task.story_points is not None else None,
        "labels": task.labels or [],
        "assigned_to": str(task.assigned_to) if task.assigned_to else None,
        "assigned_to_name": _user_name(db, task.assigned_to),
        "testing_assigned_to": [str(tester_id) for tester_id in (task.testing_assigned_to or [])],
        "testing_status": task.testing_status,
        "created_by": str(task.created_by) if task.created_by else None,
        "created_by_name": _user_name(db, task.created_by),
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
        "subtasks": [
            {
                "id": str(st.id),
                "title": st.title,
                "status": st.status,
                "priority": st.priority or "medium",
                "assigned_to": str(st.assigned_to) if st.assigned_to else None,
                "assigned_to_name": _user_name(db, st.assigned_to),
            }
            for st in subtasks
        ],
        "comments": [
            {
                "id": str(c.id),
                "body": c.body,
                "author_id": str(c.user_id) if c.user_id else None,
                "author_name": _user_name(db, c.user_id) or "Unknown",
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in comments
        ],
        "links": [
            {
                "id": str(l.id),
                "link_type": l.link_type,
                "linked_task_id": str(l.linked_task_id),
                "linked_task_title": (
                    linked_tasks_by_id[str(l.linked_task_id)].title
                    if str(l.linked_task_id) in linked_tasks_by_id
                    else "(deleted task)"
                ),
                "linked_task_status": (
                    linked_tasks_by_id[str(l.linked_task_id)].status
                    if str(l.linked_task_id) in linked_tasks_by_id
                    else "unknown"
                ),
            }
            for l in links
        ],
    }


# ---------------------------------------------------------------------------
# Issue detail
# ---------------------------------------------------------------------------
@router.get("/{task_id}", response_model=TaskDetailOut)
def get_task_detail(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_org_task(db, task_id, current_user.organization_id)
    return _serialize_detail(db, task)


# ---------------------------------------------------------------------------
# Sub-tasks
# ---------------------------------------------------------------------------
@router.post("/{task_id}/subtasks", response_model=SubtaskOut, status_code=status.HTTP_201_CREATED)
def create_subtask(
    task_id: str,
    payload: SubtaskCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parent = _get_org_task(db, task_id, current_user.organization_id)

    subtask = Task(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        project_id=parent.project_id,
        parent_task_id=parent.id,
        title=payload.title.strip(),
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        assigned_to=payload.assigned_to,
        created_by=current_user.id,
    )
    db.add(subtask)
    db.commit()
    db.refresh(subtask)

    return {
        "id": str(subtask.id),
        "title": subtask.title,
        "status": subtask.status,
        "priority": subtask.priority or "medium",
        "assigned_to": str(subtask.assigned_to) if subtask.assigned_to else None,
        "assigned_to_name": _user_name(db, subtask.assigned_to),
    }


@router.get("/{task_id}/subtasks", response_model=List[SubtaskOut])
def list_subtasks(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_org_task(db, task_id, current_user.organization_id)
    subtasks = db.query(Task).filter(Task.parent_task_id == task_id).all()
    return [
        {
            "id": str(st.id),
            "title": st.title,
            "status": st.status,
            "priority": st.priority or "medium",
            "assigned_to": str(st.assigned_to) if st.assigned_to else None,
            "assigned_to_name": _user_name(db, st.assigned_to),
        }
        for st in subtasks
    ]


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
@router.post("/{task_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    task_id: str,
    payload: CommentCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_org_task(db, task_id, current_user.organization_id)

    comment = TaskComment(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        task_id=task_id,
        user_id=current_user.id,
        body=payload.body.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {
        "id": str(comment.id),
        "body": comment.body,
        "author_id": str(current_user.id),
        "author_name": current_user.name,
        "created_at": comment.created_at.isoformat() if comment.created_at else "",
    }


@router.get("/{task_id}/comments", response_model=List[CommentOut])
def list_comments(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_org_task(db, task_id, current_user.organization_id)
    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )
    return [
        {
            "id": str(c.id),
            "body": c.body,
            "author_id": str(c.user_id) if c.user_id else None,
            "author_name": _user_name(db, c.user_id) or "Unknown",
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }
        for c in comments
    ]


# ---------------------------------------------------------------------------
# Linked issues
# ---------------------------------------------------------------------------
@router.post("/{task_id}/links", response_model=TaskLinkOut, status_code=status.HTTP_201_CREATED)
def add_task_link(
    task_id: str,
    payload: TaskLinkCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_org_task(db, task_id, current_user.organization_id)
    linked_task = _get_org_task(db, payload.linked_task_id, current_user.organization_id)

    if str(linked_task.id) == str(task_id):
        raise HTTPException(status_code=400, detail="A task cannot be linked to itself.")

    link = TaskLink(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        task_id=task_id,
        linked_task_id=linked_task.id,
        link_type=payload.link_type,
        created_by=current_user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "id": str(link.id),
        "link_type": link.link_type,
        "linked_task_id": str(linked_task.id),
        "linked_task_title": linked_task.title,
        "linked_task_status": linked_task.status,
    }


@router.get("/{task_id}/links", response_model=List[TaskLinkOut])
def list_task_links(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_org_task(db, task_id, current_user.organization_id)
    links = db.query(TaskLink).filter(TaskLink.task_id == task_id).all()
    out = []
    for l in links:
        linked = db.query(Task).filter(Task.id == l.linked_task_id).first()
        out.append({
            "id": str(l.id),
            "link_type": l.link_type,
            "linked_task_id": str(l.linked_task_id),
            "linked_task_title": linked.title if linked else "(deleted task)",
            "linked_task_status": linked.status if linked else "unknown",
        })
    return out


@router.delete("/{task_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task_link(
    task_id: str,
    link_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_org_task(db, task_id, current_user.organization_id)
    link = (
        db.query(TaskLink)
        .filter(TaskLink.id == link_id, TaskLink.task_id == task_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return None