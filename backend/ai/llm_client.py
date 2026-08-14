import os
import time
import traceback
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

import database
from models import AIUsageLog

engine = database.engine

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - fallback for environments without the package
    genai = None


def _usage_int(usage: Any, *names: str) -> Optional[int]:
    """Read the first present token-count field from Gemini/OpenAI-style usage objects."""
    if usage is None:
        return None
    for name in names:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


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
    # Attach resolved model name so call_llm can log it without re-reading env.
    try:
        response._ai_project_os_model = model_name  # noqa: SLF001
    except Exception:
        pass
    return response


def call_llm(
    prompt: str,
    *,
    feature: str = "llm",
    organization_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
) -> str:
    start = time.perf_counter()
    temperature = 0.2
    print(f"[call_llm] start feature={feature} prompt_length={len(prompt)}")
    response = _run_provider(prompt, temperature)
    latency_ms = int((time.perf_counter() - start) * 1000)
    print(f"[call_llm] complete feature={feature} latency_ms={latency_ms}")

    content = ""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        usage = getattr(response, "usage", None)

    # Gemini: prompt_token_count / candidates_token_count / total_token_count
    # OpenAI-style: prompt_tokens / completion_tokens / total_tokens
    prompt_tokens = _usage_int(
        usage, "prompt_token_count", "prompt_tokens", "input_tokens"
    )
    completion_tokens = _usage_int(
        usage, "candidates_token_count", "completion_tokens", "output_tokens"
    )
    total_tokens = _usage_int(usage, "total_token_count", "total_tokens")
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    if hasattr(response, "text"):
        content = response.text
    elif hasattr(response, "output") and response.output:
        first = response.output[0]
        if hasattr(first, "content"):
            content = "".join(
                getattr(item, "text", "")
                for item in first.content
                if getattr(item, "text", None)
            )
    elif hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content
    else:
        content = getattr(response, "text", "") or ""

    model_name = getattr(response, "_ai_project_os_model", None) or os.getenv(
        "GEMINI_MODEL", "gemini-1.5-flash"
    )

    # Usage logging must never break the LLM response path.
    # AIUsageLog columns: organization_id, user_id, feature, model,
    # prompt_tokens, completion_tokens, status (no tokens_used/cost_estimate/latency_ms).
    db: Session = database.SessionLocal()
    try:
        if organization_id is None:
            print(
                f"[call_llm] skip AIUsageLog (no organization_id) "
                f"feature={feature} prompt_tokens={prompt_tokens} "
                f"completion_tokens={completion_tokens} total={total_tokens}"
            )
        else:
            db.add(
                AIUsageLog(
                    organization_id=organization_id,
                    user_id=user_id,
                    feature=feature,
                    model=model_name,
                    prompt_tokens=str(prompt_tokens) if prompt_tokens is not None else None,
                    completion_tokens=(
                        str(completion_tokens) if completion_tokens is not None else None
                    ),
                    status="success",
                )
            )
            db.commit()
    except Exception as exc:
        print(f"[call_llm] AIUsageLog write failed: {exc}")
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

    return content
