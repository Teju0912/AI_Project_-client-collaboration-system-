from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from project_access import (
    assert_manager_can_access_project,
    is_project_member,
    manager_or_employee_project_ids,
)
import models
import schemas
from rag_utils import (
    process_document_for_rag,
    delete_chunks_for_document,
    chunk_count_for_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploaded_files"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    name = name or "upload"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def serialize_document(
    document: models.Document,
    db: Session | None = None,
) -> schemas.DocumentOut:
    if db is not None:
        chunks = chunk_count_for_document(db, document.id)
    elif getattr(document, "chunks", None) is not None:
        chunks = len(document.chunks)
    else:
        chunks = 0
    return schemas.DocumentOut(
        id=document.id,
        organization_id=document.organization_id,
        project_id=document.project_id,
        filename=document.filename,
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
        chunk_count=chunks,
    )


def _client_profile(db: Session, current_user: models.User) -> Optional[models.Client]:
    return (
        db.query(models.Client)
        .filter(
            models.Client.email == current_user.email,
            models.Client.organization_id == current_user.organization_id,
        )
        .first()
    )


def _client_project_ids(db: Session, current_user: models.User) -> list[UUID]:
    client = _client_profile(db, current_user)
    if not client:
        return []
    rows = (
        db.query(models.Project.id)
        .filter(
            models.Project.client_id == client.id,
            models.Project.organization_id == current_user.organization_id,
        )
        .all()
    )
    return [row[0] for row in rows]


def _get_project_or_404(db: Session, project_id: UUID, organization_id: UUID) -> models.Project:
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


def _assert_can_use_project(db: Session, current_user: models.User, project: models.Project) -> None:
    if current_user.role == "client":
        client = _client_profile(db, current_user)
        if not client or project.client_id != client.id:
            raise HTTPException(
                status_code=403,
                detail="You can only upload documents to your own projects.",
            )
    elif current_user.role == "manager":
        assert_manager_can_access_project(db, current_user, project.id)
    elif current_user.role == "employee":
        if not is_project_member(db, project.id, current_user.id):
            raise HTTPException(
                status_code=403,
                detail="You can only upload documents to projects you are assigned to.",
            )
    # admin: any project in org


def _assert_can_access_document(db: Session, current_user: models.User, document: models.Document) -> None:
    if document.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")

    if current_user.role in {"admin", "manager"}:
        return

    if document.project_id is None:
        raise HTTPException(status_code=403, detail="Not authorized to access this document")

    if current_user.role == "client":
        allowed = _client_project_ids(db, current_user)
        if document.project_id not in allowed:
            raise HTTPException(status_code=403, detail="Not authorized to access this document")
        return

    if current_user.role == "employee":
        allowed = manager_or_employee_project_ids(db, current_user.id)
        if document.project_id not in allowed:
            raise HTTPException(status_code=403, detail="Not authorized to access this document")
        return

    raise HTTPException(status_code=403, detail="Not authorized to access this document")

@router.post("/upload", response_model=schemas.DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    parsed_project_id = None
    if project_id and project_id.strip():
        try:
            parsed_project_id = UUID(project_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid project_id format")

    # Clients must attach uploads to one of their projects
    if current_user.role == "client":
        if parsed_project_id is None:
            raise HTTPException(
                status_code=400,
                detail="Please select a project when uploading a document.",
            )
        project = _get_project_or_404(db, parsed_project_id, current_user.organization_id)
        _assert_can_use_project(db, current_user, project)
    elif parsed_project_id is not None:
        project = _get_project_or_404(db, parsed_project_id, current_user.organization_id)
        _assert_can_use_project(db, current_user, project)

    clean_name = safe_filename(file.filename)
    unique_name = f"{uuid4()}_{clean_name}"
    storage_path = UPLOAD_ROOT / unique_name

    file_bytes = file.file.read()
    storage_path.write_bytes(file_bytes)

    document = models.Document(
        organization_id=current_user.organization_id,
        project_id=parsed_project_id,
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
            project_id=parsed_project_id,
        )
    except Exception as exc:
        print(f"RAG indexing failed for document {document.id}: {exc}")

    db.refresh(document)
    return serialize_document(document, db)


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(
    project_id: Optional[UUID] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Document).filter(
        models.Document.organization_id == current_user.organization_id
    )

    if current_user.role == "client":
        allowed = _client_project_ids(db, current_user)
        if not allowed:
            return []
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Not authorized for this project")
            query = query.filter(models.Document.project_id == project_id)
        else:
            query = query.filter(models.Document.project_id.in_(allowed))
    elif current_user.role == "employee":
        allowed = manager_or_employee_project_ids(db, current_user.id)
        if not allowed:
            return []
        if project_id is not None:
            if project_id not in allowed:
                raise HTTPException(status_code=403, detail="Not authorized for this project")
            query = query.filter(models.Document.project_id == project_id)
        else:
            query = query.filter(models.Document.project_id.in_(allowed))
    elif current_user.role in {"admin", "manager"}:
        if project_id is not None:
            _get_project_or_404(db, project_id, current_user.organization_id)
            query = query.filter(models.Document.project_id == project_id)
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    documents = query.order_by(models.Document.uploaded_at.desc()).all()
    return [serialize_document(doc, db) for doc in documents]


@router.get("/{document_id}/download")
def download_document(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    _assert_can_access_document(db, current_user, document)

    return FileResponse(
        path=document.storage_path,
        filename=document.filename,
        media_type="application/octet-stream",
    )


@router.post("/{document_id}/reindex", response_model=schemas.ReindexResult)
def reindex_document(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    _assert_can_access_document(db, current_user, document)

    delete_chunks_for_document(db, document.id, commit=False)
    chunks_indexed = process_document_for_rag(
        db,
        document.id,
        document.storage_path,
        document.organization_id,
        project_id=document.project_id,
    )
    db.refresh(document)
    return schemas.ReindexResult(
        document_id=document.id,
        filename=document.filename,
        chunks_indexed=chunks_indexed,
        status="indexed" if chunks_indexed > 0 else "no_text",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    _assert_can_access_document(db, current_user, document)

    # Admin / manager: any org doc. Client: only docs on their projects (checked above).
    if current_user.role not in {"admin", "manager", "client"}:
        raise HTTPException(status_code=403, detail="Not permitted to delete documents")

    delete_chunks_for_document(db, document.id, commit=False)

    try:
        Path(document.storage_path).unlink(missing_ok=True)
    except Exception:
        pass

    db.delete(document)
    db.commit()
    return None




