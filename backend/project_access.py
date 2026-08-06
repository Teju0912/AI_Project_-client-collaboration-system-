"""
project_access.py
Shared helpers for role ↔ project connections.

Membership in project_team_members is the link that lets:
  admin   → create projects and assign managers/employees
  manager → see/work on all org projects (pick one in UI dropdown)
  employee→ see tasks assigned to them + docs on projects they belong to
  client  → see projects where clients.email matches their login
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models

STAFF_ROLES = {"admin", "manager", "employee"}
TEAM_ROLES = {"manager", "employee"}  # who can be placed on a project team


def manager_or_employee_project_ids(db: Session, user_id: UUID) -> list[UUID]:
    rows = (
        db.query(models.ProjectMember.project_id)
        .filter(models.ProjectMember.user_id == user_id)
        .all()
    )
    return [row[0] for row in rows]


def is_project_member(db: Session, project_id: UUID, user_id: UUID) -> bool:
    return (
        db.query(models.ProjectMember)
        .filter(
            models.ProjectMember.project_id == project_id,
            models.ProjectMember.user_id == user_id,
        )
        .first()
        is not None
    )


def ensure_project_member(db: Session, project_id: UUID, user_id: UUID) -> None:
    if not is_project_member(db, project_id, user_id):
        db.add(models.ProjectMember(project_id=project_id, user_id=user_id))


def get_org_project_or_404(db: Session, project_id: UUID, organization_id: UUID) -> models.Project:
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.organization_id == organization_id,
        )
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def assert_manager_can_access_project(db: Session, user: models.User, project_id: UUID) -> None:
    """Managers may work on any project in their organization."""
    if user.role != "manager":
        return
    get_org_project_or_404(db, project_id, user.organization_id)


def resolve_team_user_ids(
    db: Session,
    organization_id: UUID,
    user_ids: list[UUID],
    *,
    allowed_roles: set[str] = TEAM_ROLES,
) -> list[UUID]:
    """Validate users belong to the org and have assignable roles."""
    if not user_ids:
        return []

    users = (
        db.query(models.User)
        .filter(
            models.User.id.in_(user_ids),
            models.User.organization_id == organization_id,
            models.User.is_active.is_(True),
        )
        .all()
    )
    found = {u.id: u for u in users}
    missing = [uid for uid in user_ids if uid not in found]
    if missing:
        raise HTTPException(status_code=404, detail="One or more team users were not found in this organization")

    bad_roles = [u.email for u in users if u.role not in allowed_roles]
    if bad_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Only managers and employees can be assigned to a project team. Invalid: {', '.join(bad_roles)}",
        )
    return list(found.keys())