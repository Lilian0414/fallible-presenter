import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..models import Claim, InjectedError, PresentationSegment


class ProviderOutputError(RuntimeError):
    pass


class _ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    importance: int = Field(ge=1, le=5)


class _ClaimsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[_ClaimDraft] = Field(min_length=1, max_length=12)


class _ErrorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modified_statement: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class _ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: _ErrorDraft


class _SegmentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_ids: list[str]
    error_ids: list[str]
    contains_error: bool


class _SegmentsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segments: list[_SegmentDraft] = Field(min_length=6, max_length=12)


class _VerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unexpected_errors: list[str]


class _ChallengePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid: bool
    reasoning_score: int = Field(ge=0, le=5)
    feedback: str = Field(min_length=1)


PayloadT = TypeVar("PayloadT", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def extract_claims(self, source_text: str) -> list[Claim]: ...

    @abstractmethod
    async def create_error(self, claim: Claim, error_type: str) -> InjectedError: ...

    @abstractmethod
    async def generate_presentation(
        self, claims: list[Claim], errors: list[InjectedError]
    ) -> list[PresentationSegment]: ...

    @abstractmethod
    async def verify_presentation(
        self,
        segments: list[PresentationSegment],
        claims: list[Claim],
        errors: list[InjectedError],
    ) -> list[str]: ...

    @abstractmethod
    async def evaluate_challenge(
        self, segment: PresentationSegment, reason: str, errors: list[InjectedError]
    ) -> dict[str, Any]: ...


class MockLLMProvider(LLMProvider):
    async def extract_claims(self, source_text: str) -> list[Claim]:
        parts = [
            p.strip()
            for p in re.split(r"(?<=[.!?])\s+|\n+", source_text)
            if len(p.strip()) >= 8
        ]
        if len(parts) < 5:
            raise ValueError(
                "Provide at least five sentence-like statements so a presentation can be created."
            )
        return [
            Claim(
                id=f"claim_{i:03}",
                statement=text,
                evidence=text,
                source_text=source_text,
                importance=5 if i <= 2 else 3,
            )
            for i, text in enumerate(parts[:12], 1)
        ]

    async def create_error(self, claim: Claim, error_type: str) -> InjectedError:
        from .error_injector import inject_errors

        return inject_errors([claim])[0]

    async def generate_presentation(
        self, claims: list[Claim], errors: list[InjectedError]
    ) -> list[PresentationSegment]:
        replacements = {error.claim_id: error for error in errors}
        groups = [[claim] for claim in claims]
        while len(groups) > 12:
            groups[-2].extend(groups.pop())
        while len(groups) < 6:
            groups.append([])
        segments = []
        for i, group in enumerate(groups, 1):
            if group:
                text = " ".join(
                    replacements.get(c.id).modified_statement
                    if c.id in replacements
                    else c.statement
                    for c in group
                )
                error_ids = [replacements[c.id].id for c in group if c.id in replacements]
                ids = [c.id for c in group]
            else:
                text, error_ids, ids = (
                    "Let us pause briefly before continuing with the source's next point.",
                    [],
                    [],
                )
            segments.append(
                PresentationSegment(
                    id=f"segment_{i:03}",
                    text=text,
                    claim_ids=ids,
                    contains_error=bool(error_ids),
                    error_ids=error_ids,
                )
            )
        return segments

    async def verify_presentation(
        self,
        segments: list[PresentationSegment],
        claims: list[Claim],
        errors: list[InjectedError],
    ) -> list[str]:
        allowed = {c.id: c.statement for c in claims} | {
            e.claim_id: e.modified_statement for e in errors
        }
        return [
            s.id
            for s in segments
            if s.claim_ids
            and any(allowed.get(cid, "") not in s.text for cid in s.claim_ids)
        ]

    async def evaluate_challenge(
        self, segment: PresentationSegment, reason: str, errors: list[InjectedError]
    ) -> dict[str, Any]:
        relevant = [e for e in errors if e.id in segment.error_ids]
        if not relevant:
            return {
                "valid": False,
                "reasoning_score": 0 if len(reason.split()) < 3 else 1,
                "feedback": "That concern is not supported by the supplied source, but careful challenges are welcome.",
            }
        error = relevant[0]
        tokens = set(re.findall(r"[a-z0-9]+", reason.lower()))
        issue_tokens = set(
            re.findall(
                r"[a-z0-9]+",
                (error.original_statement + " " + error.explanation).lower(),
            )
        )
        overlap = len(tokens & issue_tokens)
        score = 2 if overlap < 2 else 4
        if any(word in tokens for word in {"actually", "instead", "correct", "source"}):
            score = min(5, score + 1)
        return {
            "valid": True,
            "reasoning_score": score,
            "feedback": "Your challenge identifies a mismatch with the source-supported claim.",
        }


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.client = client or httpx.AsyncClient(timeout=45)

    @staticmethod
    def _schema_unsupported(response: httpx.Response) -> bool:
        if response.status_code not in {400, 404, 422}:
            return False
        detail = response.text.lower()
        mentions_schema = any(
            term in detail
            for term in ("response_format", "json_schema", "structured output", "strict")
        )
        is_unsupported = any(
            term in detail for term in ("not supported", "unsupported", "invalid")
        )
        return mentions_schema and is_unsupported

    async def _json(
        self, stage: str, system: str, user: str, schema: dict[str, Any]
    ) -> Any:
        if not self.api_key:
            raise ProviderOutputError("LLM_API_KEY is required for real provider mode")

        common = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        strict_format = {
            "type": "json_schema",
            "json_schema": {"name": stage, "strict": True, "schema": schema},
        }
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={**common, "response_format": strict_format},
        )
        if self._schema_unsupported(response):
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={**common, "response_format": {"type": "json_object"}},
            )
        if response.is_error:
            raise ProviderOutputError(
                f"{stage.replace('_', ' ')} provider request failed with HTTP {response.status_code}"
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError.from_exception_data(
                "ProviderResponse", []
            ) from exc

    async def _validated(
        self,
        stage: str,
        system: str,
        user: str,
        payload_model: type[PayloadT],
        wrapper_key: str | None = None,
    ) -> PayloadT:
        last_error: Exception | None = None
        for _ in range(2):
            try:
                data = await self._json(
                    stage, system, user, payload_model.model_json_schema()
                )
                if wrapper_key and isinstance(data, list):
                    data = {wrapper_key: data}
                elif (
                    wrapper_key == "error"
                    and isinstance(data, dict)
                    and "error" not in data
                ):
                    data = {"error": data}
                return payload_model.model_validate(data)
            except ValidationError as exc:
                last_error = exc
        raise ProviderOutputError(
            f"The model returned malformed {stage.replace('_', ' ')} JSON twice"
        ) from last_error

    async def extract_claims(self, source_text: str) -> list[Claim]:
        payload = await self._validated(
            "claim_extraction",
            "Extract atomic claims explicitly supported by the source. Use no outside information or speculation. Return only statement, exact evidence, and importance from 1 to 5 for each claim.",
            source_text,
            _ClaimsPayload,
            "claims",
        )
        return [
            Claim(
                id=f"claim_{index:03}",
                statement=draft.statement,
                evidence=draft.evidence,
                source_text=source_text,
                importance=draft.importance,
            )
            for index, draft in enumerate(payload.claims, 1)
        ]

    async def create_error(self, claim: Claim, error_type: str) -> InjectedError:
        payload = await self._validated(
            "error_generation",
            "Create exactly one controlled error of the requested type. Return only the modified statement and explanation.",
            json.dumps(
                {"claim": claim.model_dump(), "error_type": error_type}, default=str
            ),
            _ErrorPayload,
            "error",
        )
        suffix = claim.id.removeprefix("claim_")
        return InjectedError(
            id=f"error_{suffix}",
            claim_id=claim.id,
            error_type=error_type,
            original_statement=claim.statement,
            modified_statement=payload.error.modified_statement,
            explanation=payload.error.explanation,
        )

    async def generate_presentation(
        self, claims: list[Claim], errors: list[InjectedError]
    ) -> list[PresentationSegment]:
        payload = await self._validated(
            "presentation_generation",
            "Create 6-12 natural report segments using only the provided allowed statements. Do not announce errors.",
            json.dumps(
                {
                    "claims": [c.model_dump() for c in claims],
                    "errors": [e.model_dump() for e in errors],
                },
                default=str,
            ),
            _SegmentsPayload,
            "segments",
        )
        return [PresentationSegment.model_validate(item.model_dump()) for item in payload.segments]

    async def verify_presentation(
        self,
        segments: list[PresentationSegment],
        claims: list[Claim],
        errors: list[InjectedError],
    ) -> list[str]:
        payload = await self._validated(
            "presentation_verification",
            "Check every segment only against ground truth and listed intentional modifications. Return IDs of segments containing any unexpected error.",
            json.dumps(
                {
                    "segments": [s.model_dump() for s in segments],
                    "claims": [c.model_dump() for c in claims],
                    "errors": [e.model_dump() for e in errors],
                },
                default=str,
            ),
            _VerificationPayload,
            "unexpected_errors",
        )
        return payload.unexpected_errors

    async def evaluate_challenge(
        self, segment: PresentationSegment, reason: str, errors: list[InjectedError]
    ) -> dict[str, Any]:
        payload = await self._validated(
            "challenge_evaluation",
            "Using only supplied context, evaluate the challenge and score its reasoning from 0 to 5.",
            json.dumps(
                {
                    "segment": segment.model_dump(),
                    "reason": reason,
                    "errors": [e.model_dump() for e in errors],
                },
                default=str,
            ),
            _ChallengePayload,
        )
        return payload.model_dump()


def get_provider() -> LLMProvider:
    return (
        OpenAICompatibleProvider()
        if os.getenv("LLM_PROVIDER", "mock").lower() != "mock"
        else MockLLMProvider()
    )
