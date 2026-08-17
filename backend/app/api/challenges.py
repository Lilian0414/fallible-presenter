from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models import Challenge
from ..services.llm import get_provider
from .sessions import require_session

router = APIRouter(prefix="/api/sessions", tags=["challenges"])


class ChallengeInput(BaseModel):
    segment_id: str
    reason: str = Field(min_length=3, max_length=2000)


@router.post("/{session_id}/challenge")
async def challenge(session_id: str, body: ChallengeInput):
    session = require_session(session_id)
    if session.completed: raise HTTPException(409, "Presentation is complete")
    segment = session.segments[session.current_segment_index]
    if body.segment_id != segment.id: raise HTTPException(409, "Challenge is not for the current segment")
    if any(c.segment_id == segment.id for c in session.challenges): raise HTTPException(409, "This segment has already been challenged")
    relevant = [error for error in session.errors if error.id in segment.error_ids]
    evaluation = await get_provider().evaluate_challenge(segment, body.reason, relevant)
    identified = relevant[0].id if evaluation["valid"] and relevant else None
    session.challenges.append(Challenge(id=str(uuid4()), segment_id=segment.id, user_reason=body.reason,
        valid=evaluation["valid"], identified_error_id=identified, reasoning_score=evaluation["reasoning_score"], feedback=evaluation["feedback"]))
    return {key: evaluation[key] for key in ("valid", "reasoning_score", "feedback")}
