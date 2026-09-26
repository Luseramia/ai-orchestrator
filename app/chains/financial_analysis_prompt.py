import json

from app.schemas.financial_analysis import FinancialAnalysisSummaryRequest


def allowed_evidence_keys(request: FinancialAnalysisSummaryRequest) -> set[str]:
    keys = {f"latestPeriod.metrics.{key}" for key in request.latestPeriod.get("metrics", {})}
    if request.previousPeriod:
        keys.update(
            f"previousPeriod.metrics.{key}"
            for key in request.previousPeriod.get("metrics", {})
        )
    keys.update(f"growth.{key}" for key in request.growth)
    keys.update(
        f"directions.{item.get('dimension')}"
        for item in request.directions
        if item.get("dimension")
    )
    keys.update(
        f"signals.{item.get('id')}" for item in request.signals if item.get("id")
    )
    return keys


def build_financial_analysis_prompt(
    request: FinancialAnalysisSummaryRequest,
) -> str:
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    allowed_keys = sorted(allowed_evidence_keys(request))
    return f"""You explain a company's balance-sheet direction from verified, deterministic metrics.

Rules:
- Return one valid JSON object only. Do not use Markdown fences.
- Write the explanation in Thai, while keeping standard financial ratio names in English when useful.
- Use only the supplied metrics, growth, directions, signals, and deterministic summary.
- Do not write numeric figures in summaryMarkdown. Describe direction qualitatively and use evidenceKeys; the UI displays verified numbers separately.
- Do not make investment recommendations, price targets, forecasts, or GOOD/BAD verdicts.
- Cover liquidity, leverage, asset direction, equity, and material risks when evidence exists.
- If there is only one period, say that trend comparison is not yet available.
- summaryMarkdown must be concise prose with at most four short paragraphs.
- evidenceKeys must contain only keys from the allowed list below that directly support the prose.
- Set requiresHumanReview to true.

Allowed evidence keys:
{json.dumps(allowed_keys, ensure_ascii=False, indent=2)}

Return this shape:
{{
  "status": "COMPLETED",
  "summaryMarkdown": "string",
  "evidenceKeys": ["growth.assets"],
  "warnings": [],
  "requiresHumanReview": true
}}

Verified analysis payload:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
"""
