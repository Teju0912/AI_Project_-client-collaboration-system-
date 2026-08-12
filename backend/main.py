"""
main.py
FastAPI application entry point. Run with:
    uvicorn main:app --reload
Then open http://localhost:8000/docs to test every endpoint interactively.
"""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

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
from routers.requirement_analyzer import router as requirement_analyzer_router
from routers import chat_assistant
from tasks_jira_router import router as tasks_jira_router
from database import initialize_database
from rag_utils import check_rag_dependencies
from routers.project_modules import router as project_modules_router

initialize_database()

_rag_ok, _rag_detail = check_rag_dependencies()
if _rag_ok:
    print(f"RAG status: {_rag_detail}")
else:
    print(f"RAG WARNING: {_rag_detail}")

app = FastAPI(
    title="AI Project OS API",
    version="1.0.0"
)

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
app.include_router(tasks_jira_router)
app.include_router(documents_router)
app.include_router(projects_router)
app.include_router(client_dashboard_router)
app.include_router(ai_router)
app.include_router(weekly_reports_router)
app.include_router(meetings_router)
app.include_router(project_modules_router)
app.include_router(requirement_analyzer_router)
app.include_router(chat_assistant.router)

# As you build more modules, add one line each here:
# from routers import <new_module>
# app.include_router(<new_module>.router)


@app.get("/")
def health_check():
    rag_ok, rag_detail = check_rag_dependencies()
    return {
        "status": "ok",
        "message": "AI Project OS API is running.",
        "rag_ready": rag_ok,
        "rag_detail": rag_detail,
    }