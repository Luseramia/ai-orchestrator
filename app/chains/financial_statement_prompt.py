import json

from app.schemas.financial_statement import FinancialNormalizationRequest


CANONICAL_ACCOUNTS = [
    "ASSET.CURRENT",
    "ASSET.CASH",
    "ASSET.SHORT_TERM_INVESTMENT",
    "ASSET.RECEIVABLE",
    "ASSET.INVENTORY",
    "ASSET.OTHER_CURRENT",
    "ASSET.NON_CURRENT",
    "ASSET.PPE",
    "ASSET.RIGHT_OF_USE",
    "ASSET.INVESTMENT",
    "ASSET.GOODWILL",
    "ASSET.INTANGIBLE",
    "ASSET.DEFERRED_TAX",
    "ASSET.OTHER_NON_CURRENT",
    "ASSET.TOTAL",
    "LIABILITY.CURRENT",
    "LIABILITY.AP",
    "LIABILITY.SHORT_TERM_DEBT",
    "LIABILITY.CURRENT_PORTION_LONG_TERM_DEBT",
    "LIABILITY.CURRENT_LEASE",
    "LIABILITY.OTHER_CURRENT",
    "LIABILITY.NON_CURRENT",
    "LIABILITY.LONG_TERM_DEBT",
    "LIABILITY.BOND",
    "LIABILITY.LEASE",
    "LIABILITY.DEFERRED_TAX",
    "LIABILITY.OTHER_NON_CURRENT",
    "LIABILITY.TOTAL",
    "EQUITY.SHARE_CAPITAL",
    "EQUITY.SHARE_PREMIUM",
    "EQUITY.RETAINED_EARNINGS",
    "EQUITY.RESERVES",
    "EQUITY.ATTRIBUTABLE_TO_PARENT",
    "EQUITY.NON_CONTROLLING_INTEREST",
    "EQUITY.TOTAL",
]


OUTPUT_EXAMPLE = {
    "status": "COMPLETED",
    "statementType": "BALANCE_SHEET",
    "scope": "CONSOLIDATED",
    "currency": "THB",
    "unit": "THOUSAND",
    "rows": [
        {
            "originalLabel": "เงินสดและรายการเทียบเท่าเงินสด",
            "canonicalCode": "ASSET.CASH",
            "confidence": 0.98,
            "mappingSource": "AI",
            "sourceSheet": "BS-Asset",
            "sourceRow": 12,
            "values": [
                {
                    "periodEnd": "2026-06-30",
                    "value": 1234.0,
                    "originalValue": "1234",
                    "sourceColumn": 4,
                }
            ],
        }
    ],
    "warnings": [],
    "requiresHumanReview": True,
}


def build_financial_statement_prompt(
    request: FinancialNormalizationRequest,
) -> str:
    input_json = json.dumps(
        request.model_dump() if hasattr(request, "model_dump") else request.dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    accounts_json = json.dumps(CANONICAL_ACCOUNTS, ensure_ascii=False)
    output_json = json.dumps(OUTPUT_EXAMPLE, ensure_ascii=False, indent=2)

    return f"""You normalize spreadsheet balance sheets into a strict intermediate JSON format.

Rules:
- Return one valid JSON object only. Do not use Markdown fences.
- Extract BALANCE_SHEET rows only. Ignore income statement, OCI, cash flow, notes, and equity movement sheets.
- Use only the requested scope: {request.preferredScope}. Never mix consolidated and separate/company-only columns.
- Copy originalLabel exactly from a workbook cell. sourceSheet, sourceRow, and sourceColumn are 1-based coordinates in the supplied workbook JSON.
- Copy numeric values exactly as displayed in the source cell. Do not calculate, scale, round, infer, or invent a number.
- Convert Buddhist Era years to Gregorian years by subtracting 543. Return periodEnd as YYYY-MM-DD.
- Detect unit from workbook headings: ONES, THOUSAND, MILLION, or BILLION. Do not scale values.
- Detect the ISO currency code; use the request hint when the workbook does not state one.
- canonicalCode must be one of the allowed codes below, or null when uncertain.
- Return only rows that represent one of the allowed canonical accounts; skip unrelated detail rows and headings.
- Do not return two source rows with the same canonicalCode and periodEnd. Prefer an explicit source total or the closest direct label; never add detail rows together.
- Use confidence below 0.70 when a canonical mapping requires human review.
- Include total rows when present. Do not manufacture missing totals.
- A balance sheet may be split across multiple sheets such as assets, liabilities, and equity.
- Every returned value must include the exact sourceColumn containing that value.
- Set requiresHumanReview to true.

Allowed canonical account codes:
{accounts_json}

Expected response shape:
{output_json}

Workbook request:
{input_json}
"""
