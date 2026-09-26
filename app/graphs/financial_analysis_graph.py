import re
from typing import Any

from app.chains.financial_analysis_prompt import (
    allowed_evidence_keys,
    build_financial_analysis_prompt,
)
from app.chains.llm import call_main_model
from app.schemas.financial_analysis import (
    FinancialAnalysisSummaryRequest,
    FinancialAnalysisSummaryResponse,
)
from app.validators.artifact_validator import extract_json_payload


def _repair_prompt(raw_output: str, parse_error: str) -> str:
    return f"""Repair this financial analysis summary into one valid JSON object only.
Preserve summaryMarkdown, evidenceKeys, warnings, and requiresHumanReview.
Do not add claims, evidence, or numbers.

Parse error: {parse_error}

Invalid output:
{raw_output}
"""


def _to_response(data: dict[str, Any]) -> FinancialAnalysisSummaryResponse:
    if hasattr(FinancialAnalysisSummaryResponse, "model_validate"):
        return FinancialAnalysisSummaryResponse.model_validate(data)
    return FinancialAnalysisSummaryResponse.parse_obj(data)


async def summarize_financial_analysis(
    request: FinancialAnalysisSummaryRequest,
) -> FinancialAnalysisSummaryResponse:
    raw_output = await call_main_model(build_financial_analysis_prompt(request))
    warnings: list[str] = []
    try:
        parsed = extract_json_payload(raw_output)
    except ValueError as parse_error:
        repaired = await call_main_model(_repair_prompt(raw_output, str(parse_error)))
        parsed = extract_json_payload(repaired)
        warnings.append(f"Repaired invalid LLM JSON after parse error: {parse_error}")

    summary = str(parsed.get("summaryMarkdown", "")).strip()
    if not summary:
        raise ValueError("AI summary was empty.")
    if re.search(r"\d", summary):
        raise ValueError("AI summary contained numeric figures; use the deterministic fallback.")

    allowed = allowed_evidence_keys(request)
    raw_evidence = parsed.get("evidenceKeys", [])
    if not isinstance(raw_evidence, list):
        raw_evidence = []
        warnings.append("AI summary evidenceKeys was not a list.")
    evidence = []
    for key in raw_evidence:
        normalized = str(key)
        if normalized in allowed and normalized not in evidence:
            evidence.append(normalized)
        elif normalized not in allowed:
            warnings.append(f"Unsupported evidence key '{normalized}' was ignored.")

    model_warnings = parsed.get("warnings", [])
    if isinstance(model_warnings, list):
        warnings.extend(str(item) for item in model_warnings if item is not None)

    return _to_response(
        {
            "status": "COMPLETED",
            "summaryMarkdown": summary,
            "evidenceKeys": evidence,
            "warnings": warnings,
            "requiresHumanReview": True,
        }
    )
