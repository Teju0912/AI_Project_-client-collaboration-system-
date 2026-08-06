import os
import time
from typing import Any

from sqlalchemy.orm import Session

import database
from models import AIUsageLog, Base

engine = database.engine

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - fallback for environments without the package
    genai = None


def _estimate_cost(tokens_used: int) -> float:
    return round(tokens_used * 0.000015, 6)


def _run_provider(prompt: str, temperature: float) -> Any:
    if genai is None:
        raise RuntimeError("google-generativeai package is not installed")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing credentials. Please set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
        )

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(model_name)
    timeout_seconds = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
    response = model.generate_content(
        prompt,
        request_options={"timeout": timeout_seconds},
    )
    return response


def call_llm(prompt: str) -> str:
    start = time.perf_counter()
    temperature = 0.2
    print(f"[call_llm] start prompt_length={len(prompt)}")
    response = _run_provider(prompt, temperature)
    latency_ms = int((time.perf_counter() - start) * 1000)
    print(f"[call_llm] complete latency_ms={latency_ms}")

    content = ""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        usage = getattr(response, "usage", None)

    if hasattr(usage, "total_token_count"):
        total_tokens = usage.total_token_count or 0
    elif isinstance(usage, dict):
        total_tokens = usage.get("total_tokens") or usage.get("input_tokens") or 0
    elif usage is not None:
        total_tokens = getattr(usage, "total_tokens", None) or getattr(usage, "input_tokens", None) or 0
    else:
        total_tokens = 0

    if hasattr(response, "text"):
        content = response.text
    elif hasattr(response, "output") and response.output:
        first = response.output[0]
        if hasattr(first, "content"):
            content = "".join(getattr(item, "text", "") for item in first.content if getattr(item, "text", None))
    elif hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content
    else:
        content = getattr(response, "text", "") or ""

    tokens_used = int(total_tokens or 0)
    cost_estimate = _estimate_cost(tokens_used)

    db: Session = database.SessionLocal()
    try:
        db.add(AIUsageLog(feature="meeting_summarizer", tokens_used=tokens_used, cost_estimate=cost_estimate, latency_ms=latency_ms))
        db.commit()
    finally:
        db.close()

    return content
