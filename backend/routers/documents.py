import os
import re
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from supabase import Client, create_client

for _env_path in (
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parent / ".env",
):
    load_dotenv(_env_path, override=False)

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


# ============================================================
# SUPABASE STORAGE
# ============================================================

def _normalize_supabase_url(value: str | None) -> str:
    if not value:
        return ""

    normalized = value.strip().rstrip("/")
    if normalized.lower().endswith("/rest/v1"):
        normalized = normalized[: -len("/rest/v1")]

    return normalized


SUPABASE_URL = _normalize_supabase_url(os.getenv("SUPABASE_URL"))
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = "documents"

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured"
    )

print(
    "Supabase storage config loaded: "
    f"URL={bool(SUPABASE_URL)}, service_key={bool(SUPABASE_SERVICE_ROLE_KEY)}"
)

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)


def _ensure_documents_bucket() -> None:
    try:
        buckets = supabase.storage.list_buckets()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to inspect Supabase Storage buckets: {exc}",
        ) from exc

    bucket_names = []
    for bucket in buckets or []:
        name = bucket.get("name") if isinstance(bucket, dict) else getattr(bucket, "name", None)
        if name:
            bucket_names.append(name)

    if SUPABASE_BUCKET in bucket_names:
        return

    try:
        supabase.storage.create_bucket(
            id=SUPABASE_BUCKET,
            options={"public": False},
        )
    except Exception as exc:
        msg = str(exc)
        if "Duplicate" in msg or "already exists" in msg.lower():
            return
        raise HTTPException(
            status_code=500,
            detail=(
                f"Supabase bucket '{SUPABASE_BUCKET}' does not exist and "
                f"could not be created: {exc}"
            ),
        ) from exc


# ============================================================
# HELPERS
# ============================================================

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


def _client_profile(
    db: Session,
    current_user: models.User,
) -> Optional[models.Client]:

    return (
        db.query(models.Client)
        .filter(
            models.Client.email == current_user.email,
            models.Client.organization_id == current_user.organization_id,
        )
        .first()
    )


def _client_project_ids(
    db: Session,
    current_user: models.User,
) -> list[UUID]:

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


def _get_project_or_404(
    db: Session,
    project_id: UUID,
    organization_id: UUID,
) -> models.Project:

    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.organization_id == organization_id,
        )
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    return project


def _assert_can_use_project(
    db: Session,
    current_user: models.User,
    project: models.Project,
) -> None:

    if current_user.role == "client":

        client = _client_profile(db, current_user)

        if not client or project.client_id != client.id:
            raise HTTPException(
                status_code=403,
                detail="You can only upload documents to your own projects.",
            )

    elif current_user.role == "manager":

        assert_manager_can_access_project(
            db,
            current_user,
            project.id,
        )

    elif current_user.role == "employee":

        if not is_project_member(
            db,
            project.id,
            current_user.id,
        ):
            raise HTTPException(
                status_code=403,
                detail="You can only upload documents to projects you are assigned to.",
            )

    # admin: any project in org


def _assert_can_access_document(
    db: Session,
    current_user: models.User,
    document: models.Document,
) -> None:

    if document.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if current_user.role in {"admin", "manager"}:
        return

    if document.project_id is None:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this document",
        )

    if current_user.role == "client":

        allowed = _client_project_ids(
            db,
            current_user,
        )

        if document.project_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this document",
            )

        return

    if current_user.role == "employee":

        allowed = manager_or_employee_project_ids(
            db,
            current_user.id,
        )

        if document.project_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this document",
            )

        return

    raise HTTPException(
        status_code=403,
        detail="Not authorized to access this document",
    )


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@router.post(
    "/upload",
    response_model=schemas.DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    # --------------------------------------------------------
    # Parse project ID
    # --------------------------------------------------------

    parsed_project_id = None

    if project_id and project_id.strip():

        try:
            parsed_project_id = UUID(project_id)

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid project_id format",
            )

    # --------------------------------------------------------
    # Project permission checks
    # --------------------------------------------------------

    if current_user.role == "client":

        if parsed_project_id is None:
            raise HTTPException(
                status_code=400,
                detail="Please select a project when uploading a document.",
            )

        project = _get_project_or_404(
            db,
            parsed_project_id,
            current_user.organization_id,
        )

        _assert_can_use_project(
            db,
            current_user,
            project,
        )

    elif parsed_project_id is not None:

        project = _get_project_or_404(
            db,
            parsed_project_id,
            current_user.organization_id,
        )

        _assert_can_use_project(
            db,
            current_user,
            project,
        )

    # --------------------------------------------------------
    # Validate Supabase storage target before upload
    # --------------------------------------------------------

    _ensure_documents_bucket()

    # --------------------------------------------------------
    # Prepare file
    # --------------------------------------------------------

    clean_name = safe_filename(file.filename)

    unique_name = f"{uuid4()}_{clean_name}"

    # This is now a SUPABASE STORAGE path,
    # NOT a local filesystem path.
    storage_path = (
        f"{current_user.organization_id}/{unique_name}"
    )

    file_bytes = file.file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    # --------------------------------------------------------
    # Upload to Supabase Storage
    # --------------------------------------------------------

    try:

        supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,

        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file to storage: {exc}",
        )

    # --------------------------------------------------------
    # Save document metadata in PostgreSQL
    # --------------------------------------------------------

    document = models.Document(
        organization_id=current_user.organization_id,
        project_id=parsed_project_id,
        filename=clean_name,
        storage_path=storage_path,
        uploaded_by=current_user.id,
    )

    try:

        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:

        db.rollback()

        # If DB save fails, try to remove the uploaded file
        try:
            supabase.storage.from_(SUPABASE_BUCKET).remove(
                [storage_path]
            )
        except Exception:
            pass

        raise

    # --------------------------------------------------------
    # RAG indexing
    #
    # RAG currently expects a local file path.
    # So create a temporary local file only while indexing.
    # --------------------------------------------------------

    try:

        temp_suffix = Path(clean_name).suffix or ".bin"

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=temp_suffix,
        ) as temp_file:

            temp_file.write(file_bytes)
            temp_path = temp_file.name

        try:

            process_document_for_rag(
                db,
                document.id,
                temp_path,
                current_user.organization_id,
                project_id=parsed_project_id,
            )

        finally:

            Path(temp_path).unlink(
                missing_ok=True
            )

    except Exception as exc:

        print(
            f"RAG indexing failed for document "
            f"{document.id}: {exc}"
        )

    db.refresh(document)

    return serialize_document(
        document,
        db,
    )


# ============================================================
# LIST DOCUMENTS
# ============================================================

@router.get(
    "",
    response_model=list[schemas.DocumentOut],
)
def list_documents(
    project_id: Optional[UUID] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    query = (
        db.query(models.Document)
        .filter(
            models.Document.organization_id
            == current_user.organization_id
        )
    )

    # --------------------------------------------------------
    # Client
    # --------------------------------------------------------

    if current_user.role == "client":

        allowed = _client_project_ids(
            db,
            current_user,
        )

        if not allowed:
            return []

        if project_id is not None:

            if project_id not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized for this project",
                )

            query = query.filter(
                models.Document.project_id == project_id
            )

        else:

            query = query.filter(
                models.Document.project_id.in_(allowed)
            )

    # --------------------------------------------------------
    # Employee
    # --------------------------------------------------------

    elif current_user.role == "employee":

        allowed = manager_or_employee_project_ids(
            db,
            current_user.id,
        )

        if not allowed:
            return []

        if project_id is not None:

            if project_id not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized for this project",
                )

            query = query.filter(
                models.Document.project_id == project_id
            )

        else:

            query = query.filter(
                models.Document.project_id.in_(allowed)
            )

    # --------------------------------------------------------
    # Admin / Manager
    # --------------------------------------------------------

    elif current_user.role in {"admin", "manager"}:

        if project_id is not None:

            _get_project_or_404(
                db,
                project_id,
                current_user.organization_id,
            )

            query = query.filter(
                models.Document.project_id == project_id
            )

    else:

        raise HTTPException(
            status_code=403,
            detail="Not authorized",
        )

    documents = (
        query
        .order_by(
            models.Document.uploaded_at.desc()
        )
        .all()
    )

    return [
        serialize_document(doc, db)
        for doc in documents
    ]


# ============================================================
# DOWNLOAD DOCUMENT
# ============================================================

@router.get("/{document_id}/download")
def download_document(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    document = (
        db.query(models.Document)
        .filter(
            models.Document.id == document_id
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    _assert_can_access_document(
        db,
        current_user,
        document,
    )

    # --------------------------------------------------------
    # Download from Supabase Storage
    # --------------------------------------------------------

    try:

        file_bytes = (
            supabase
            .storage
            .from_(SUPABASE_BUCKET)
            .download(document.storage_path)
        )

    except Exception as exc:

        raise HTTPException(
            status_code=404,
            detail=f"Document file not found in storage: {exc}",
        )

    return StreamingResponse(
        iter([file_bytes]),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{document.filename}"'
            )
        },
    )


# ============================================================
# PREVIEW DOCUMENT (returns a temporary signed URL)
#
# We CANNOT let the frontend put the /download URL directly
# into an <img>/<iframe> src, because:
#   1) /download requires an Authorization header, which
#      <img>/<iframe> tags cannot send.
#   2) /download forces "attachment" disposition, which tells
#      the browser to download the file instead of rendering it.
#   3) Frontend (Streamlit Cloud) and backend (Render) are on
#      different domains in production, so cookies/auth don't
#      carry over the way they might locally.
#
# This endpoint is called normally (with auth, like any other
# API call) and returns a short-lived Supabase "signed URL".
# That signed URL already contains its own access token, so it
# can be used directly as an <img>/<iframe> src with no auth
# headers needed — and it will render inline, not download.
# ============================================================

@router.get("/{document_id}/preview-url")
def get_document_preview_url(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    document = (
        db.query(models.Document)
        .filter(
            models.Document.id == document_id
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    _assert_can_access_document(
        db,
        current_user,
        document,
    )

    try:

        signed = supabase.storage.from_(SUPABASE_BUCKET).create_signed_url(
            document.storage_path,
            300,  # URL valid for 5 minutes
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate preview URL: {exc}",
        )

    signed_url = (
        signed.get("signedURL")
        or signed.get("signed_url")
        or signed.get("signedUrl")
    )

    if not signed_url:
        raise HTTPException(
            status_code=500,
            detail="Could not generate a signed preview URL",
        )

    # Supabase sometimes returns a relative path — make it absolute.
    if signed_url.startswith("/"):
        signed_url = f"{SUPABASE_URL}{signed_url}"

    return {
        "url": signed_url,
        "filename": document.filename,
    }


# ============================================================
# REINDEX DOCUMENT
# ============================================================

@router.post(
    "/{document_id}/reindex",
    response_model=schemas.ReindexResult,
)
def reindex_document(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    document = (
        db.query(models.Document)
        .filter(
            models.Document.id == document_id
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    _assert_can_access_document(
        db,
        current_user,
        document,
    )

    # --------------------------------------------------------
    # Get file from Supabase Storage
    # --------------------------------------------------------

    try:

        file_bytes = (
            supabase
            .storage
            .from_(SUPABASE_BUCKET)
            .download(document.storage_path)
        )

    except Exception as exc:

        raise HTTPException(
            status_code=404,
            detail=f"Document file not found in storage: {exc}",
        )

    # --------------------------------------------------------
    # Temporary local file for RAG
    # --------------------------------------------------------

    temp_suffix = (
        Path(document.filename).suffix
        or ".bin"
    )

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=temp_suffix,
    ) as temp_file:

        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:

        delete_chunks_for_document(
            db,
            document.id,
            commit=False,
        )

        chunks_indexed = process_document_for_rag(
            db,
            document.id,
            temp_path,
            document.organization_id,
            project_id=document.project_id,
        )

    finally:

        Path(temp_path).unlink(
            missing_ok=True
        )

    db.refresh(document)

    return schemas.ReindexResult(
        document_id=document.id,
        filename=document.filename,
        chunks_indexed=chunks_indexed,
        status=(
            "indexed"
            if chunks_indexed > 0
            else "no_text"
        ),
    )


# ============================================================
# DELETE DOCUMENT
# ============================================================

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    document = (
        db.query(models.Document)
        .filter(
            models.Document.id == document_id
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    _assert_can_access_document(
        db,
        current_user,
        document,
    )

    # Admin / manager: any org doc.
    # Client: only docs on their projects.
    if current_user.role not in {
        "admin",
        "manager",
        "client",
    }:
        raise HTTPException(
            status_code=403,
            detail="Not permitted to delete documents",
        )

    delete_chunks_for_document(
        db,
        document.id,
        commit=False,
    )

    # Requirement analyses keep the document link as context for historical
    # auditability, but the source document may be deleted without destroying
    # the analysis. Null the FK explicitly so deletion is safe even before the
    # database-level ON DELETE SET NULL constraint is in place.
    db.query(models.RequirementAnalysis).filter(
        models.RequirementAnalysis.document_id == document.id,
    ).update({
        models.RequirementAnalysis.document_id: None,
    }, synchronize_session=False)

    # --------------------------------------------------------
    # Delete from Supabase Storage
    # --------------------------------------------------------

    try:

        supabase.storage.from_(SUPABASE_BUCKET).remove(
            [document.storage_path]
        )

    except Exception as exc:

        print(
            f"Storage delete failed for "
            f"{document.id}: {exc}"
        )

    # --------------------------------------------------------
    # Delete database record
    # --------------------------------------------------------

    db.delete(document)
    db.commit()

    return None