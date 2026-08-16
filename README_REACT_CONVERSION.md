# AI Project OS — React Conversion

The original Streamlit application is retained as `backend/streamlit_app` for reference, while the new production UI is in `frontend/`.

## Architecture

React/Vite frontend → existing FastAPI backend → PostgreSQL/pgvector → AI/RAG services.

No AI/data/backend logic was moved into the browser. The React UI calls the same FastAPI routes used by the Streamlit application.

## Start on Windows

Run `run_react.bat`, or manually:

### Backend
```powershell
cd backend
uvicorn main:app --reload --port 8000
```

### React
```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`).

## Important

The uploaded project contained `.env` files. They are intentionally not included in the conversion archive to avoid redistributing database/API credentials. Use the existing local `.env` values in your private environment and keep `frontend/.env` pointed at the backend.
