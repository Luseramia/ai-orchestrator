from typing import Any

from app.chains.financial_statement_prompt import build_financial_statement_prompt
from app.chains.llm import call_main_model
from app.schemas.financial_statement import (
    FinancialNormalizationRequest,
    FinancialNormalizationResponse,
)
from app.validators.artifact_validator import extract_json_payload
from app.validators.financial_statement_validator import (
    validate_financial_normalization,
)


def _repair_prompt(raw_output: str, parse_error: str) -> str:
    return f"""Repair this financial-statement normalization output into one valid JSON object.
Return JSON only. Preserve sourceSheet, sourceRow, sourceColumn, periodEnd, canonicalCode,
scope, currency, unit, and rows. Do not add rows or numbers.

Parse error: {parse_error}

Invalid output:
{raw_output}
"""


def _to_response(data: dict[str, Any]) -> FinancialNormalizationResponse:
    if hasattr(FinancialNormalizationResponse, "model_validate"):
        return FinancialNormalizationResponse.model_validate(data)
    return FinancialNormalizationResponse.parse_obj(data)


async def normalize_financial_statement(
    request: FinancialNormalizationRequest,
) -> FinancialNormalizationResponse:
    raw_output = await call_main_model(build_financial_statement_prompt(request))
    repair_warning: str | None = None
    try:
        parsed = extract_json_payload(raw_output)
    except ValueError as parse_error:
        repaired_output = await call_main_model(_repair_prompt(raw_output, str(parse_error)))
        parsed = extract_json_payload(repaired_output)
        repair_warning = f"Repaired invalid LLM JSON after parse error: {parse_error}"

    result = validate_financial_normalization(parsed, request)
    if repair_warning:
        result["warnings"].insert(0, repair_warning)
    return _to_response(result)
