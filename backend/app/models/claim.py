from enum import Enum

from pydantic import BaseModel, Field


class ErrorType(str, Enum):
    factual_inversion = "factual_inversion"
    numerical_corruption = "numerical_corruption"
    direction_or_causal_reversal = "direction_or_causal_reversal"
    unsupported_conclusion = "unsupported_conclusion"


class Claim(BaseModel):
    id: str
    statement: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    importance: int = Field(ge=1, le=5)


class InjectedError(BaseModel):
    id: str
    claim_id: str
    error_type: ErrorType
    original_statement: str
    modified_statement: str
    explanation: str
