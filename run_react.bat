@echo off
cd /d %~dp0
start "AI Project OS Backend" cmd /k "cd backend && uvicorn main:app --reload --port 8000"
start "AI Project OS React" cmd /k "cd frontend && npm install && npm run dev"
