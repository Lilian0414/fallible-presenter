import math
import re

from ..models import Claim, ErrorType, InjectedError


def error_count(claim_count: int) -> int:
    """Select 25%, rounding half up; five claims therefore produces one."""
    return max(1, math.floor(claim_count * 0.25 + 0.5)) if claim_count else 0


def inject_errors(claims: list[Claim]) -> list[InjectedError]:
    selected = claims[1::4][: error_count(len(claims))] or claims[: error_count(len(claims))]
    errors: list[InjectedError] = []
    for index, claim in enumerate(selected, 1):
        number = re.search(r"\b\d+(?:\.\d+)?%?\b", claim.statement)
        if number:
            replacement = str(int(float(number.group().rstrip("%"))) + 10) + ("%" if "%" in number.group() else "")
            modified = claim.statement[: number.start()] + replacement + claim.statement[number.end() :]
            kind = ErrorType.numerical_corruption
            explanation = "The presented number was changed from the source-supported value."
        elif re.search(r"\b(increases?|improves?|causes?|leads? to)\b", claim.statement, re.I):
            modified = re.sub(r"\b(increases?|improves?)\b", "reduces", claim.statement, count=1, flags=re.I)
            modified = re.sub(r"\b(causes?|leads? to)\b", "prevents", modified, count=1, flags=re.I)
            kind = ErrorType.direction_or_causal_reversal
            explanation = "The direction or causal relationship was reversed."
        elif index % 2:
            modified = f"It is not true that {claim.statement[0].lower() + claim.statement[1:]}"
            kind = ErrorType.factual_inversion
            explanation = "The presentation inverted the source-supported claim."
        else:
            modified = claim.statement.rstrip(".") + ", proving this outcome is always guaranteed."
            kind = ErrorType.unsupported_conclusion
            explanation = "The presentation added a conclusion that the source does not support."
        errors.append(InjectedError(id=f"error_{index:03}", claim_id=claim.id, error_type=kind,
            original_statement=claim.statement, modified_statement=modified, explanation=explanation))
    return errors
