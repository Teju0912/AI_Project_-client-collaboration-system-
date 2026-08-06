"""
main.py
FastAPI application entry point. Run with:
    uvicorn main:app --reload
Then open http://localhost:8000/docs to test every endpoint interactively.
"""
from pathlib import Path
import threading

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BACKEND_DIR.parent
load_dotenv(dotenv_path=_BACKEND_DIR / ".env")
load_dotenv(dotenv_path=_ROOT_DIR / ".env", override=False)

from routers.auth import router as auth_router
from routers.clients import router as clients_router
from routers.tasks import router as tasks_router
from routers.documents import router as documents_router
from routers.users import router as users_router
from routers.projects import router as projects_router
from routers.client_dashboard import router as client_dashboard_router
from routers.ai import router as ai_router
from routers.weekly_reports import router as weekly_reports_router
from routers.meetings import router as meetings_router
from routers import chat_assistant
from routers.requirement_analyzer import router as requirement_analyzer_router
from database import initialize_database

initialize_database()

app = FastAPI(
    title="AI Project OS API",
    version="1.0.0"
)


@app.on_event("startup")
def _warmup_rag_on_startup() -> None:
    """Preload sentence-transformers in a daemon thread so first chat is fast."""

    def _run():
        try:
            from rag_utils import warmup_embedding_model

            warmup_embedding_model()
        except Exception as exc:  # pragma: no cover
            print(f"RAG startup warmup failed: {exc}")

    threading.Thread(target=_run, daemon=True, name="rag-warmup").start()

# Allows the Streamlit app (running on a different port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your real Streamlit URL before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(clients_router)
app.include_router(tasks_router)
app.include_router(documents_router)
app.include_router(projects_router)
app.include_router(client_dashboard_router)
app.include_router(ai_router)
app.include_router(requirement_analyzer_router)
app.include_router(weekly_reports_router)
app.include_router(meetings_router)
app.include_router(chat_assistant.router)

# As you build more modules, add one line each here:
# from routers import <new_module>
# app.include_router(<new_module>.router)


@app.get("/")
def health_check():
    from rag_utils import check_rag_dependencies

    rag_ready, rag_detail = check_rag_dependencies()
    return {
        "status": "ok",
        "message": "AI Project OS API is running.",
        "rag_ready": rag_ready,
        "rag_detail": rag_detail,
    }