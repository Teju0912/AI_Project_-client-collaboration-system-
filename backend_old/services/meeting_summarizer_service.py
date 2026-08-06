import json
import os
import traceback
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ai.llm_client import call_llm
from ai.transcription import transcribe_audio
from database import SessionLocal
import models
import schemas

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "ai" / "prompts" / "meeting_summary.txt"


class MeetingSummaryPayload(BaseModel):
    summary: str
    action_items: list[str]
    risks: list[str]
    deadlines: list[str]


def _load_prompt_template() -> str:
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _parse_llm_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):]
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def _build_prompt(transcript: str) -> str:
    template = _load_prompt_template()
    return template.replace("{transcript}", transcript)


def _persist_meeting_failure(meeting_id, message: str, db: Session) -> None:
    try:
        try:
            db.rollback()
        except Exception:
            pass

        meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
        if meeting:
            meeting.status = "failed"
            meeting.summary = message
            db.commit()
            return
    except Exception:
        print(f"[process_meeting] failed to persist failure status in existing session meeting_id={meeting_id}: {message}")
        traceback.print_exc()

    try:
        fallback_db = SessionLocal()
        meeting = fallback_db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
        if meeting:
            meeting.status = "failed"
            meeting.summary = message
            fallback_db.commit()
    except Exception:
        print(f"[process_meeting] fallback failed to persist failure status meeting_id={meeting_id}: {message}")
        traceback.print_exc()
    finally:
        try:
            fallback_db.close()
        except Exception:
            pass


def process_meeting(meeting_id, db: Session) -> None:
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        return

    print(f"[process_meeting] start meeting_id={meeting_id}")
    try:
        try:
            print(f"[process_meeting] transcribe_audio start meeting_id={meeting_id} file={meeting.audio_file_url}")
            transcript = transcribe_audio(meeting.audio_file_url)
            print(f"[process_meeting] transcribe_audio complete meeting_id={meeting_id}")
        except Exception as exc:
            print(f"[process_meeting] transcription failed meeting_id={meeting_id}: {exc}")
            traceback.print_exc()
            _persist_meeting_failure(meeting_id, f"Transcription failed: {exc}", db)
            return

        prompt = _build_prompt(transcript)
        try:
            print(f"[process_meeting] call_llm start meeting_id={meeting_id}")
            llm_response = call_llm(prompt)
            print(f"[process_meeting] call_llm complete meeting_id={meeting_id}")
            payload = _parse_llm_json(llm_response)
            validated = MeetingSummaryPayload.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            print(f"[process_meeting] LLM response parse/validation failed meeting_id={meeting_id}: {exc}")
            traceback.print_exc()
            retry_prompt = prompt + "\nReturn valid JSON only, no markdown formatting."
            try:
                print(f"[process_meeting] retry call_llm start meeting_id={meeting_id}")
                llm_response = call_llm(retry_prompt)
                print(f"[process_meeting] retry call_llm complete meeting_id={meeting_id}")
                payload = _parse_llm_json(llm_response)
                validated = MeetingSummaryPayload.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, TypeError, Exception) as retry_exc:
                print(f"[process_meeting] retry failed meeting_id={meeting_id}: {retry_exc}")
                traceback.print_exc()
                _persist_meeting_failure(meeting_id, f"Summary generation failed: {exc}", db)
                return
        except Exception as exc:
            print(f"[process_meeting] LLM call failed meeting_id={meeting_id}: {exc}")
            traceback.print_exc()
            _persist_meeting_failure(meeting_id, f"Summary generation failed: {exc}", db)
            return

        meeting.transcript = transcript
        meeting.summary = validated.summary
        meeting.action_items = json.dumps(validated.action_items)
        meeting.risks = json.dumps(validated.risks)
        meeting.deadlines = json.dumps(validated.deadlines)
        meeting.status = "done"
        db.commit()
        print(f"[process_meeting] finished meeting_id={meeting_id} status=done")
    except Exception as exc:
        print(f"[process_meeting] unexpected error meeting_id={meeting_id}: {exc}")
        traceback.print_exc()
        _persist_meeting_failure(meeting_id, f"Processing failed: {exc}", db)
