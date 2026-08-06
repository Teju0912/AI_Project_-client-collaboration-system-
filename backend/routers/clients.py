"""
routers/clients.py
Module 2 — Client Management.
This file is the pattern to copy for every future module
(projects.py, tasks.py, documents.py): a router, protected by
require_role(...), that always filters by the current user's
organization_id — never returns another organization's data.

--------------------------------------------------------------------------
ADDED: client-portal endpoints (dashboard + document upload/download/delete)
needed by views/client.py (the Streamlit client GUI). These follow the exact
same conventions as the original code below:
  - APIRouter, Depends(get_db), require_role(...) / get_current_user
  - every query filtered by organization_id
  - 404 (not leak-y errors) when a record isn't found or isn't owned

ASSUMED MODELS (not shown in the original file, inferred from what
client.py's api_client functions need — adjust field names to match your
actual models.py):

    class Project(Base):
        id: UUID
        organization_id: UUID
        client_id: UUID            # FK -> Client.id, who this project is for
        project_name: str
        status: str                # "planning" | "active" | "in progress" | "on_hold" | "completed"
        deadline: str              # stored as string, parsed client-side
        progress_percent: int
        milestone_info: str | None

    class Document(Base):
        id: UUID
        organization_id: UUID
        project_id: UUID           # FK -> Project.id
        filename: str
        content_type: str
        data: bytes                # or storage_path: str if using object storage
        uploaded_by_user_id: UUID

ASSUMED SCHEMAS (add to schemas.py):

    class DocumentOut(BaseModel):
        id: uuid.UUID
        filename: str

    class ClientDashboardOut(BaseModel):
        project_id: uuid.UUID
        project_name: str
        status: str
        deadline: str
        progress_percent: int
        milestone_info: str | None
        documents: list[DocumentOut]
--------------------------------------------------------------------------
"""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_role
import models
import schemas
from rag_utils import process_document_for_rag, delete_chunks_for_document
from routers.documents import serialize_document
from security import hash_password

router = APIRouter(prefix="/clients", tags=["clients"])


# ============================================================================
# ORIGINAL ENDPOINTS — unchanged
# ============================================================================

@router.get("", response_model=list[schemas.ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    return (
        db.query(models.Client)
        .filter(models.Client.organization_id == current_user.organization_id)
        .all()
    )


@router.post("", response_model=schemas.ClientOut)
def create_client(
    payload: schemas.ClientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    # password is not a column on the Client model — handle it separately
    client_data = payload.model_dump(exclude={"password"})
    client = models.Client(
        organization_id=current_user.organization_id,
        **client_data,
    )
    db.add(client)

    # If a password was provided, also create a login account for this client
    if payload.password:
        password = payload.password.strip()
        if password:
            # Check if a user with this email already exists
            existing_user = db.query(models.User).filter(
                models.User.email == payload.email
            ).first()
            if not existing_user and payload.email:
                client_user = models.User(
                    organization_id=current_user.organization_id,
                    name=payload.contact_name or payload.company_name,
                    email=payload.email,
                    password_hash=hash_password(password),
                    role="client",
                )
                db.add(client_user)

    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}", response_model=schemas.ClientOut)
def get_client(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.organization_id == current_user.organization_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client


@router.put("/{client_id}", response_model=schemas.ClientOut)
def update_client(
    client_id: uuid.UUID,
    payload: schemas.ClientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.organization_id == current_user.organization_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    previous_email = client.email
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(client, field, value)

    linked_user = (
        db.query(models.User)
        .filter(
            models.User.organization_id == current_user.organization_id,
            models.User.role == "client",
            models.User.email == previous_email,
        )
        .first()
    )
    if linked_user:
        if "email" in update_data and update_data["email"]:
            linked_user.email = update_data["email"]
        if "contact_name" in update_data and update_data["contact_name"]:
            linked_user.name = update_data["contact_name"]
        elif "company_name" in update_data and update_data["company_name"]:
            linked_user.name = update_data["company_name"]

    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}")
def delete_client(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["admin", "manager"])),
):
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.organization_id == current_user.organization_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    db.delete(client)
    db.commit()
    return {"detail": "Client deleted."}


# ============================================================================
# NEW: helper — resolve the Client row that belongs to the logged-in
# "client"-role user, scoped to their organization. Every new endpoint below
# uses this so a client can never see another client's projects/documents.
# ============================================================================

def _get_own_client_record(db: Session, current_user: models.User) -> models.Client:
    client = (
        db.query(models.Client)
        .filter(
            models.Client.organization_id == current_user.organization_id,
            models.Client.email == current_user.email,
        )
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="No client record linked to this account.")
    return client


# ============================================================================
# NEW: GET /clients/dashboard
# Powers client.py's get_client_dashboard(token). One entry per project
# belonging to the logged-in client, each with its documents nested inline —
# matching exactly the shape client.py expects (project_name, project_id,
# status, deadline, progress_percent, milestone_info, documents).
# ============================================================================

@router.get("/dashboard", response_model=list[schemas.ClientDashboardOut])
def get_client_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["client"])),
):
    client = _get_own_client_record(db, current_user)

    projects = (
        db.query(models.Project)
        .filter(
            models.Project.organization_id == current_user.organization_id,
            models.Project.client_id == client.id,
        )
        .all()
    )

    dashboard = []
    for project in projects:
        documents = (
            db.query(models.Document)
            .filter(
                models.Document.organization_id == current_user.organization_id,
                models.Document.project_id == project.id,
            )
            .all()
        )
        dashboard.append({
            "project_id": project.id,
            "project_name": project.project_name,
            "status": project.status,
            "deadline": project.deadline,
            "progress_percent": project.progress_percent,
            "milestone_info": project.milestone_info,
            "documents": [{"id": doc.id, "filename": doc.filename} for doc in documents],
        })

    return dashboard


# ============================================================================
# NEW: document upload / download / delete
# Powers client.py's upload_document / download_document / delete_document.
# Admin/manager can act on any project in their org; a client can only
# touch documents on projects that belong to their own client record.
# ============================================================================

def _get_project_scoped(db: Session, current_user: models.User, project_id: uuid.UUID) -> models.Project:
    query = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.organization_id == current_user.organization_id,
    )
    if current_user.role == "client":
        client = _get_own_client_record(db, current_user)
        query = query.filter(models.Project.client_id == client.id)

    project = query.first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _get_document_scoped(db: Session, current_user: models.User, document_id: uuid.UUID) -> models.Document:
    document = (
        db.query(models.Document)
        .filter(
            models.Document.id == document_id,
            models.Document.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    if current_user.role == "client":
        # Confirm the document's project actually belongs to this client.
        _get_project_scoped(db, current_user, document.project_id)

    return document


@router.post("/documents", response_model=schemas.DocumentOut, status_code=201)
def upload_document(
    project_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Confirms the project exists, is in this org, and — if the caller is a
    # client — belongs to them. Admin/manager can upload to any org project.
    _get_project_scoped(db, current_user, project_id)

    upload_root = Path(__file__).resolve().parent.parent / "uploaded_files"
    upload_root.mkdir(parents=True, exist_ok=True)
    clean_name = file.filename or "upload"
    unique_name = f"{uuid.uuid4()}_{clean_name}"
    storage_path = upload_root / unique_name
    storage_path.write_bytes(file.file.read())

    document = models.Document(
        organization_id=current_user.organization_id,
        project_id=project_id,
        filename=clean_name,
        storage_path=str(storage_path),
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        process_document_for_rag(
            db,
            document.id,
            str(storage_path),
            current_user.organization_id,
            project_id=project_id,
        )
    except Exception as exc:
        print(f"RAG indexing failed for client-uploaded document {document.id}: {exc}")

    db.refresh(document)
    return serialize_document(document, db)


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    document = _get_document_scoped(db, current_user, document_id)
    return StreamingResponse(
        io.BytesIO(document.data),
        media_type=document.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    document = _get_document_scoped(db, current_user, document_id)
    delete_chunks_for_document(db, document.id, commit=False)
    db.delete(document)
    db.commit()
    return None