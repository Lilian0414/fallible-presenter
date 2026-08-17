import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from ..models import Claim, InjectedError, PresentationSegment


class ProviderOutputError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    async def extract_claims(self, source_text: str) -> list[Claim]: ...
    @abstractmethod
    async def create_error(self, claim: Claim, error_type: str) -> InjectedError: ...
    @abstractmethod
    async def generate_presentation(self, claims: list[Claim], errors: list[InjectedError]) -> list[PresentationSegment]: ...
    @abstractmethod
    async def verify_presentation(self, segments: list[PresentationSegment], claims: list[Claim], errors: list[InjectedError]) -> list[str]: ...
    @abstractmethod
    async def evaluate_challenge(self, segment: PresentationSegment, reason: str, errors: list[InjectedError]) -> dict[str, Any]: ...


class MockLLMProvider(LLMProvider):
    async def extract_claims(self, source_text: str) -> list[Claim]:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", source_text) if len(p.strip()) >= 8]
        if len(parts) < 5:
            raise ValueError("Provide at least five sentence-like statements so a presentation can be created.")
        return [Claim(id=f"claim_{i:03}", statement=text, evidence=text, source_text=source_text, importance=5 if i <= 2 else 3) for i, text in enumerate(parts[:12], 1)]

    async def create_error(self, claim: Claim, error_type: str) -> InjectedError:
        from .error_injector import inject_errors
        return inject_errors([claim])[0]

    async def generate_presentation(self, claims: list[Claim], errors: list[InjectedError]) -> list[PresentationSegment]:
        replacements = {error.claim_id: error for error in errors}
        groups = [[claim] for claim in claims]
        while len(groups) > 12:
            groups[-2].extend(groups.pop())
        while len(groups) < 6:
            groups.append([])
        segments = []
        for i, group in enumerate(groups, 1):
            if group:
                text = " ".join(replacements.get(c.id).modified_statement if c.id in replacements else c.statement for c in group)
                error_ids = [replacements[c.id].id for c in group if c.id in replacements]
                ids = [c.id for c in group]
            else:
                text, error_ids, ids = "Let us pause briefly before continuing with the source's next point.", [], []
            segments.append(PresentationSegment(id=f"segment_{i:03}", text=text, claim_ids=ids, contains_error=bool(error_ids), error_ids=error_ids))
        return segments

    async def verify_presentation(self, segments: list[PresentationSegment], claims: list[Claim], errors: list[InjectedError]) -> list[str]:
        allowed = {c.id: c.statement for c in claims} | {e.claim_id: e.modified_statement for e in errors}
        return [s.id for s in segments if s.claim_ids and any(allowed.get(cid, "") not in s.text for cid in s.claim_ids)]

    async def evaluate_challenge(self, segment: PresentationSegment, reason: str, errors: list[InjectedError]) -> dict[str, Any]:
        relevant = [e for e in errors if e.id in segment.error_ids]
        if not relevant:
            return {"valid": False, "reasoning_score": 0 if len(reason.split()) < 3 else 1, "feedback": "That concern is not supported by the supplied source, but careful challenges are welcome."}
        error = relevant[0]
        tokens = set(re.findall(r"[a-z0-9]+", reason.lower()))
        issue_tokens = set(re.findall(r"[a-z0-9]+", (error.original_statement + " " + error.explanation).lower()))
        overlap = len(tokens & issue_tokens)
        score = 2 if overlap < 2 else 4
        if any(word in tokens for word in {"actually", "instead", "correct", "source"}): score = min(5, score + 1)
        return {"valid": True, "reasoning_score": score, "feedback": "Your challenge identifies a mismatch with the source-supported claim."}


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.client = client or httpx.AsyncClient(timeout=45)

    async def _json(self, system: str, user: str) -> Any:
        if not self.api_key: raise ProviderOutputError("LLM_API_KEY is required for real provider mode")
        response = await self.client.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": self.model, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])

    async def extract_claims(self, source_text: str) -> list[Claim]:
        prompt = "Extract atomic claims explicitly supported by the source. Include exact source evidence; use no outside information or speculation. Return JSON {claims:[{id,statement,evidence,source_text,importance}]} with importance 1-5."
        for attempt in range(2):
            try:
                data = await self._json(prompt, source_text)
                return TypeAdapter(list[Claim]).validate_python(data["claims"])
            except (KeyError, json.JSONDecodeError, ValidationError, TypeError) as exc:
                if attempt: raise ProviderOutputError("The model returned malformed claim JSON twice") from exc
        raise AssertionError

    async def create_error(self, claim: Claim, error_type: str) -> InjectedError:
        data = await self._json("Create exactly one controlled error of the requested type. Return {error:{id,claim_id,error_type,original_statement,modified_statement,explanation}}.", json.dumps({"claim": claim.model_dump(), "error_type": error_type}))
        return InjectedError.model_validate(data["error"])

    async def generate_presentation(self, claims: list[Claim], errors: list[InjectedError]) -> list[PresentationSegment]:
        data = await self._json("Create 6-12 natural report segments using only the provided allowed statements. Return {segments:[{id,text,claim_ids,error_ids,contains_error}]}. Do not announce errors.", json.dumps({"claims": [c.model_dump() for c in claims], "errors": [e.model_dump() for e in errors]}, default=str))
        return TypeAdapter(list[PresentationSegment]).validate_python(data["segments"])

    async def verify_presentation(self, segments: list[PresentationSegment], claims: list[Claim], errors: list[InjectedError]) -> list[str]:
        data = await self._json("Check every segment only against ground truth and listed intentional modifications. Return {unexpected_errors:[segment_id,...]}.", json.dumps({"segments": [s.model_dump() for s in segments], "claims": [c.model_dump() for c in claims], "errors": [e.model_dump() for e in errors]}, default=str))
        return list(data.get("unexpected_errors", []))

    async def evaluate_challenge(self, segment: PresentationSegment, reason: str, errors: list[InjectedError]) -> dict[str, Any]:
        return await self._json("Using only supplied context, score 0-5. Return only {valid,reasoning_score,feedback}.", json.dumps({"segment": segment.model_dump(), "reason": reason, "errors": [e.model_dump() for e in errors]}, default=str))


def get_provider() -> LLMProvider:
    return OpenAICompatibleProvider() if os.getenv("LLM_PROVIDER", "mock").lower() != "mock" else MockLLMProvider()
