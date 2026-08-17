from pydantic import BaseModel, Field


class PresentationSegment(BaseModel):
    id: str
    text: str = Field(min_length=1)
    claim_ids: list[str]
    contains_error: bool = False
    error_ids: list[str] = Field(default_factory=list)
