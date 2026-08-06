import json
import traceback
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai.llm_client import call_llm
from database import SessionLocal
import models
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


def analyze_requirement_document(document_text: str) -> ra_schemas.RequirementAnalysisOut:
    """
    Sends the full document text to the LLM and returns a validated RequirementAnalysisOut.
    Follows the same retry-once-then-fail pattern used by meeting_summarizer_service.
    Also writes an ai_usage_log entry with feature="requirement_analysis" for auditing.
    """
    prompt = _build_prompt(document_text)

    try:
        llm_response = call_llm(prompt)
        payload = _parse_llm_json(llm_response)
        validated = ra_schemas.RequirementAnalysisOut.model_validate(payload)

        # Log usage (additional row so feature is searchable independently)
        try:
            db = SessionLocal()
            db.add(models.AIUsageLog(feature="requirement_analysis", tokens_used=0, cost_estimate=0.0, latency_ms=0))
            db.commit()
        except Exception:
            traceback.print_exc()
        finally:
            try:
                db.close()
            except Exception:
                pass

        return validated
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        traceback.print_exc()
        retry_prompt = prompt + "\nReturn valid JSON only, no markdown formatting."
        try:
            llm_response = call_llm(retry_prompt)
            payload = _parse_llm_json(llm_response)
            validated = ra_schemas.RequirementAnalysisOut.model_validate(payload)

            try:
                db = SessionLocal()
                db.add(models.AIUsageLog(feature="requirement_analysis", tokens_used=0, cost_estimate=0.0, latency_ms=0))
                db.commit()
            except Exception:
                traceback.print_exc()
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            return validated
        except Exception as retry_exc:
            traceback.print_exc()
            raise RuntimeError(f"Requirement analysis failed after retry: {retry_exc}")
    except Exception as exc:
        traceback.print_exc()
        raise RuntimeError(f"LLM call failed: {exc}")
