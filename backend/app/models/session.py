from pydantic import BaseModel, Field

from .claim import Claim, InjectedError
from .presentation import PresentationSegment


class Challenge(BaseModel):
    id: str
    segment_id: str
    user_reason: str
    valid: bool
    identified_error_id: str | None = None
    reasoning_score: int = Field(ge=0, le=5)
    feedback: str


class PresentationSession(BaseModel):
    id: str
    source_text: str
    claims: list[Claim]
    errors: list[InjectedError]
    segments: list[PresentationSegment]
    current_segment_index: int = 0
    challenges: list[Challenge] = Field(default_factory=list)
    completed: bool = False
