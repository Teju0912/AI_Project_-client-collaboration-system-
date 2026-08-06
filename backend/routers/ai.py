"""
routers/ai.py
Lightweight AI health/status endpoint used by main.py.
"""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status():
    has_key = bool(
        (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    )
    return {
        "status": "ok",
        "llm_configured": has_key,
        "model": os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini",
        "mode": "api" if has_key else "local_fallback",
    }