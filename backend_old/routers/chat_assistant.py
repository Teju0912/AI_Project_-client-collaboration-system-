from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import ChatQuery, ChatResponse
from services.chat_assistant_service import get_chat_response
from dependencies import get_current_user

router = APIRouter(
    prefix="/chat",
    tags=["AI Chat Assistant"],
)


@router.post("/query", response_model=ChatResponse)
def chat_query(
    payload: ChatQuery,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # When the UI picks specific files, force RAG-only answers from those docs.
    use_rag_only = bool(payload.document_ids)
    try:
        answer = get_chat_response(
            payload.message,
            db,
            current_user.organization_id,
            user_id=current_user.id,
            project_id=payload.project_id,
            document_ids=payload.document_ids,
            use_rag_only=use_rag_only,
        )
    except Exception as exc:
        # Never return an empty body — surface a usable message in the chat UI.
        print(f"chat_query failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Chat failed ({exc.__class__.__name__}). "
                "If this is the first request after startup, wait for the "
                "embedding model to finish loading and try again."
            ),
        ) from exc

    if not answer or not str(answer).strip():
        answer = (
            "I could not generate an answer. Make sure the selected documents "
            "are indexed (Documents → Reindex) and GROQ_API_KEY is set."
        )
    return ChatResponse(answer=answer)
