from ..models import Claim, InjectedError, PresentationSegment
from .llm import LLMProvider, ProviderOutputError


async def create_verified_presentation(provider: LLMProvider, claims: list[Claim], errors: list[InjectedError]) -> list[PresentationSegment]:
    segments = await provider.generate_presentation(claims, errors)
    unexpected = await provider.verify_presentation(segments, claims, errors)
    if unexpected:
        segments = await provider.generate_presentation(claims, errors)
        unexpected = await provider.verify_presentation(segments, claims, errors)
    if unexpected:
        raise ProviderOutputError("Presentation could not be verified without unexpected claims")
    return segments
