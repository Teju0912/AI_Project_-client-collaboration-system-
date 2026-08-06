import os
import sys
import time
import importlib
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("WHISPER_MODEL_SIZE", "base")

import database
import dependencies
import models
from security import create_access_token
from main import app


@pytest.fixture()
def client_and_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    database.engine = engine
    database.SessionLocal = TestingSessionLocal
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[dependencies.get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal

    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_data(client_and_db):
    client, SessionLocal = client_and_db
    db = SessionLocal()
    try:
        org = models.Organization(name="Test Org")
        db.add(org)
        db.flush()

        admin = models.User(
            organization_id=org.id,
            name="Admin User",
            email="admin@example.com",
            password_hash="x",
            role="admin",
        )
        employee = models.User(
            organization_id=org.id,
            name="Employee User",
            email="employee@example.com",
            password_hash="x",
            role="employee",
        )
        client_user = models.User(
            organization_id=org.id,
            name="Client User",
            email="client@example.com",
            password_hash="x",
            role="client",
        )
        db.add_all([admin, employee, client_user])
        db.flush()

        project_client = models.Client(
            organization_id=org.id,
            company_name="Acme",
            contact_name="Jane",
            email="acme@example.com",
            phone="123",
        )
        db.add(project_client)
        db.flush()

        project = models.Project(
            organization_id=org.id,
            client_id=project_client.id,
            name="Project Alpha",
            description="Demo",
            created_by=admin.id,
        )
        db.add(project)
        db.flush()

        db.add(models.ProjectMember(project_id=project.id, user_id=employee.id))
        db.commit()

        yield {
            "org": org,
            "admin": admin,
            "employee": employee,
            "client": client_user,
            "project": project,
            "db": db,
        }
    finally:
        db.close()


def _auth_headers(user):
    token = create_access_token({"sub": str(user.id), "role": user.role, "organization_id": str(user.organization_id)})
    return {"Authorization": f"Bearer {token}"}


def test_happy_path_upload_and_get(client_and_db, seeded_data, monkeypatch):
    client, SessionLocal = client_and_db
    admin = seeded_data["admin"]
    project = seeded_data["project"]

    from services import meeting_summarizer_service as service_module

    monkeypatch.setattr(service_module, "transcribe_audio", lambda file_path: "hello world")

    def fake_call_llm(prompt: str) -> str:
        return '{"summary": "A good recap", "action_items": ["Follow up"], "risks": ["Delay"], "deadlines": ["2026-09-01"]}'

    monkeypatch.setattr(service_module, "call_llm", fake_call_llm)

    resp = client.post(
        "/meetings/upload",
        files={"file": ("demo.wav", b"fake audio", "audio/wav")},
        data={"project_id": str(project.id)},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 202
    payload = resp.json()
    meeting_id = payload["id"]

    for _ in range(20):
        get_resp = client.get(f"/meetings/{meeting_id}", headers=_auth_headers(admin))
        if get_resp.json()["status"] == "done":
            break
        time.sleep(0.1)

    get_resp = client.get(f"/meetings/{meeting_id}", headers=_auth_headers(admin))
    body = get_resp.json()
    assert body["status"] == "done"
    assert body["summary"] == "A good recap"
    assert body["action_items"] == ["Follow up"]
    assert body["risks"] == ["Delay"]
    assert body["deadlines"] == ["2026-09-01"]


def test_upload_returns_before_processing_finishes(client_and_db, seeded_data, monkeypatch):
    client, _ = client_and_db
    admin = seeded_data["admin"]
    project = seeded_data["project"]

    from services import meeting_summarizer_service as service_module

    def slow_process(meeting_id, db):
        time.sleep(0.5)

    monkeypatch.setattr(service_module, "process_meeting", slow_process)

    start = time.perf_counter()
    resp = client.post(
        "/meetings/upload",
        files={"file": ("demo.wav", b"fake audio", "audio/wav")},
        data={"project_id": str(project.id)},
        headers=_auth_headers(admin),
    )
    elapsed = time.perf_counter() - start

    assert resp.status_code == 202
    assert elapsed < 0.3


def test_auth_rejection(client_and_db, seeded_data):
    client, _ = client_and_db
    project = seeded_data["project"]
    resp = client.post(
        "/meetings/upload",
        files={"file": ("demo.wav", b"fake audio", "audio/wav")},
        data={"project_id": str(project.id)},
    )
    assert resp.status_code == 401


def test_role_rejection(client_and_db, seeded_data):
    client, _ = client_and_db
    client_user = seeded_data["client"]
    project = seeded_data["project"]
    resp = client.post(
        "/meetings/upload",
        files={"file": ("demo.wav", b"fake audio", "audio/wav")},
        data={"project_id": str(project.id)},
        headers=_auth_headers(client_user),
    )
    assert resp.status_code == 403


def test_project_membership_rejection(client_and_db, seeded_data):
    client, SessionLocal = client_and_db
    employee = seeded_data["employee"]
    project = seeded_data["project"]
    db_session = SessionLocal()
    try:
        other_project = models.Project(
            organization_id=project.organization_id,
            client_id=project.client_id,
            name="Project Beta",
            description="Other",
            created_by=employee.id,
        )
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)
    finally:
        db_session.close()

    resp = client.post(
        "/meetings/upload",
        files={"file": ("demo.wav", b"fake audio", "audio/wav")},
        data={"project_id": str(other_project.id)},
        headers=_auth_headers(employee),
    )
    assert resp.status_code == 403


def test_malformed_llm_output_marks_meeting_failed(client_and_db, seeded_data, monkeypatch):
    client, SessionLocal = client_and_db
    admin = seeded_data["admin"]
    project = seeded_data["project"]

    from services import meeting_summarizer_service as service_module

    monkeypatch.setattr(service_module, "transcribe_audio", lambda file_path: "hello")
    monkeypatch.setattr(service_module, "call_llm", lambda prompt: "not json")

    resp = client.post(
        "/meetings/upload",
        files={"file": ("demo.wav", b"fake audio", "audio/wav")},
        data={"project_id": str(project.id)},
        headers=_auth_headers(admin),
    )
    meeting_id = resp.json()["id"]

    for _ in range(20):
        get_resp = client.get(f"/meetings/{meeting_id}", headers=_auth_headers(admin))
        if get_resp.json()["status"] in {"done", "failed"}:
            break
        time.sleep(0.1)

    get_resp = client.get(f"/meetings/{meeting_id}", headers=_auth_headers(admin))
    assert get_resp.json()["status"] == "failed"


def test_ai_usage_log_is_written(monkeypatch):
    import ai.llm_client as llm_client

    monkeypatch.setattr(llm_client, "_run_provider", lambda prompt, temperature: type("Resp", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": '{"summary": "ok"}'} )()})()], "usage": {"total_tokens": 42}})())

    session = llm_client.database.SessionLocal()
    try:
        llm_client.Base.metadata.create_all(bind=llm_client.engine)
        result = llm_client.call_llm("prompt")
        assert result == '{"summary": "ok"}'
        row = session.query(models.AIUsageLog).order_by(models.AIUsageLog.created_at.desc()).first()
        assert row is not None
        assert row.tokens_used == 42
        assert row.cost_estimate is not None and row.cost_estimate > 0
        assert row.latency_ms is not None and row.latency_ms >= 0
    finally:
        session.close()
