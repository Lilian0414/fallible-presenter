from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models import PresentationSession
from ..services.error_injector import inject_errors
from ..services.llm import ProviderOutputError, get_provider
from ..services.presenter import create_verified_presentation
from ..store.memory_store import store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionInput(BaseModel):
    source_text: str = Field(min_length=40, max_length=50_000)


def public_segment(segment):
    return {"id": segment.id, "text": segment.text}


def require_session(session_id: str) -> PresentationSession:
    session = store.get(session_id)
    if not session: raise HTTPException(404, "Session not found")
    return session


@router.post("")
async def create_session(body: SessionInput):
    provider = get_provider()
    try:
        claims = await provider.extract_claims(body.source_text)
        errors = inject_errors(claims)
        segments = await create_verified_presentation(provider, claims, errors)
    except (ValueError, ProviderOutputError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session = PresentationSession(id=str(uuid4()), source_text=body.source_text, claims=claims, errors=errors, segments=segments)
    store.add(session)
    return {"session_id": session.id, "segment_count": len(segments), "first_segment": public_segment(segments[0])}


@router.get("/{session_id}/current")
async def current(session_id: str):
    session = require_session(session_id)
    if session.completed: return {"completed": True}
    return {"segment": public_segment(session.segments[session.current_segment_index]), "index": session.current_segment_index, "total": len(session.segments)}


@router.post("/{session_id}/continue")
async def continue_session(session_id: str):
    session = require_session(session_id)
    if session.completed: return {"completed": True}
    session.current_segment_index += 1
    if session.current_segment_index >= len(session.segments):
        session.completed = True
        return {"completed": True}
    return {"segment": public_segment(session.segments[session.current_segment_index]), "index": session.current_segment_index, "total": len(session.segments)}


@router.get("/{session_id}/result")
async def result(session_id: str):
    session = require_session(session_id)
    if not session.completed: raise HTTPException(409, "Results are available after the presentation is complete")
    caught_ids = {challenge.identified_error_id for challenge in session.challenges if challenge.valid}
    false_count = sum(not c.valid for c in session.challenges)
    items = []
    for error in session.errors:
        claim = next(c for c in session.claims if c.id == error.claim_id)
        items.append({"id": error.id, "presented_statement": error.modified_statement, "source_supported_statement": error.original_statement, "caught": error.id in caught_ids, "explanation": error.explanation, "source_evidence": claim.evidence})
    caught = sum(item["caught"] for item in items)
    return {"summary": {"total_errors": len(items), "caught": caught, "missed": len(items) - caught, "false_challenges": false_count}, "errors": items}
