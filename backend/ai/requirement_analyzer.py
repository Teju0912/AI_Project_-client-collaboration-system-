import json
import traceback
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from pydantic import ValidationError

from ai.llm_client import call_llm
import schemas_requirement_analyzer as ra_schemas

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "prompts" / "requirement_analyzer.txt"


def _load_prompt_template() -> str:
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _parse_llm_json(content: str) -> Any:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):]
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def _build_prompt(document_text: str) -> str:
    template = _load_prompt_template()
    return template.replace("{document_text}", document_text)


def analyze_requirement_document(
    document_text: str,
    *,
    organization_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
) -> ra_schemas.RequirementAnalysisOut:
    """
    Sends the full document text to the LLM and returns a validated RequirementAnalysisOut.
    Follows the same retry-once-then-fail pattern used by meeting_summarizer_service.
    Usage is audited via call_llm(..., feature="requirement_analysis").
    """
    prompt = _build_prompt(document_text)

    try:
        llm_response = call_llm(
            prompt,
            feature="requirement_analysis",
            organization_id=organization_id,
            user_id=user_id,
        )
        payload = _parse_llm_json(llm_response)
        validated = ra_schemas.RequirementAnalysisOut.model_validate(payload)
        return validated
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        traceback.print_exc()
        retry_prompt = prompt + "\nReturn valid JSON only, no markdown formatting."
        try:
            llm_response = call_llm(
                retry_prompt,
                feature="requirement_analysis",
                organization_id=organization_id,
                user_id=user_id,
            )
            payload = _parse_llm_json(llm_response)
            validated = ra_schemas.RequirementAnalysisOut.model_validate(payload)
            return validated
        except Exception as retry_exc:
            traceback.print_exc()
            raise RuntimeError(f"Requirement analysis failed after retry: {retry_exc}")
    except Exception as exc:
        traceback.print_exc()
        raise RuntimeError(f"LLM call failed: {exc}")
