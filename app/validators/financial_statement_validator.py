import math
import re
from datetime import date
from typing import Any

from app.chains.financial_statement_prompt import CANONICAL_ACCOUNTS
from app.schemas.financial_statement import FinancialNormalizationRequest


VALID_UNITS = {"ONES", "THOUSAND", "MILLION", "BILLION"}
VALID_SCOPES = {"CONSOLIDATED", "SEPARATE"}
PERIOD_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value).strip()


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    text = str(value).strip()
    if not text or text in {"-", "—"} or text.lower() == "n/a":
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.+-]", "", text.replace(",", ""))
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -abs(number) if negative else number


def _warning_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)] if value else []


def _is_valid_period(value: str) -> bool:
    if not PERIOD_PATTERN.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_financial_normalization(
    data: dict[str, Any], request: FinancialNormalizationRequest
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Financial normalization result must be a JSON object.")

    warnings = _warning_list(data.get("warnings"))
    sheets = {sheet.name: sheet.rows for sheet in request.sheets}
    allowed_codes = set(CANONICAL_ACCOUNTS)
    normalized_rows: list[dict[str, Any]] = []

    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        raise ValueError("Financial normalization rows must be a list.")

    for index, candidate in enumerate(raw_rows):
        if not isinstance(candidate, dict):
            warnings.append(f"Row {index + 1} was ignored because it is not an object.")
            continue

        sheet_name = str(candidate.get("sourceSheet", "")).strip()
        source_rows = sheets.get(sheet_name)
        try:
            source_row_number = int(candidate.get("sourceRow"))
        except (TypeError, ValueError):
            source_row_number = 0
        if source_rows is None or not 1 <= source_row_number <= len(source_rows):
            warnings.append(f"Row {index + 1} has an invalid source sheet or row and was ignored.")
            continue

        source_row = source_rows[source_row_number - 1]
        original_label = str(candidate.get("originalLabel", "")).strip()
        if not original_label or original_label not in [_as_text(cell) for cell in source_row]:
            warnings.append(f"Row {index + 1} label was not found at its source coordinate and was ignored.")
            continue

        canonical_code = candidate.get("canonicalCode")
        if canonical_code not in allowed_codes:
            if canonical_code is not None:
                warnings.append(
                    f"Unsupported canonicalCode '{canonical_code}' on row {index + 1}; set to null."
                )
            canonical_code = None

        try:
            confidence = float(candidate.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = min(1.0, max(0.0, confidence))
        if canonical_code is None:
            confidence = min(confidence, 0.69)

        values: list[dict[str, Any]] = []
        raw_values = candidate.get("values", [])
        if not isinstance(raw_values, list):
            raw_values = []
        for value_index, candidate_value in enumerate(raw_values):
            if not isinstance(candidate_value, dict):
                continue
            period_end = str(candidate_value.get("periodEnd", "")).strip()
            try:
                source_column = int(candidate_value.get("sourceColumn"))
            except (TypeError, ValueError):
                source_column = 0
            if not _is_valid_period(period_end):
                warnings.append(
                    f"Row {index + 1} value {value_index + 1} has an invalid period and was ignored."
                )
                continue
            if not 1 <= source_column <= len(source_row):
                warnings.append(
                    f"Row {index + 1} value {value_index + 1} has an invalid source column and was ignored."
                )
                continue

            source_cell = source_row[source_column - 1]
            verified_value = _parse_number(source_cell)
            if verified_value is None:
                warnings.append(
                    f"Row {index + 1} value {value_index + 1} does not point to a numeric source cell and was ignored."
                )
                continue
            try:
                proposed_value = float(candidate_value.get("value"))
            except (TypeError, ValueError):
                proposed_value = verified_value
            if not math.isclose(proposed_value, verified_value, rel_tol=1e-12, abs_tol=1e-9):
                warnings.append(
                    f"Row {index + 1} value {value_index + 1} differed from the source cell; the source value was used."
                )

            values.append(
                {
                    "periodEnd": period_end,
                    "value": verified_value,
                    "originalValue": _as_text(source_cell),
                    "sourceColumn": source_column,
                }
            )

        if not values:
            warnings.append(f"Row {index + 1} had no verified numeric values and was ignored.")
            continue

        normalized_rows.append(
            {
                "originalLabel": original_label,
                "canonicalCode": canonical_code,
                "confidence": confidence,
                "mappingSource": "AI",
                "sourceSheet": sheet_name,
                "sourceRow": source_row_number,
                "values": values,
            }
        )

    # The downstream financial store has one canonical value per period. Keep
    # the highest-confidence direct source row and never sum model-selected rows.
    unique_rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in sorted(normalized_rows, key=lambda item: item["confidence"], reverse=True):
        canonical_code = row["canonicalCode"]
        if canonical_code is None:
            unique_rows.append(row)
            continue
        unique_values = []
        for value in row["values"]:
            key = (canonical_code, value["periodEnd"])
            if key in seen_keys:
                warnings.append(
                    f"Duplicate {canonical_code} for {value['periodEnd']} was ignored; values were not summed."
                )
                continue
            seen_keys.add(key)
            unique_values.append(value)
        if unique_values:
            row["values"] = unique_values
            unique_rows.append(row)
    normalized_rows = unique_rows

    scope = str(data.get("scope", request.preferredScope)).upper()
    if scope not in VALID_SCOPES or scope != request.preferredScope:
        warnings.append("The generated scope did not match preferredScope; preferredScope was used.")
        scope = request.preferredScope

    unit = str(data.get("unit", request.unitHint or "ONES")).upper()
    if unit not in VALID_UNITS:
        warnings.append(f"Unsupported unit '{unit}'; request hint or ONES was used.")
        unit = request.unitHint or "ONES"

    currency = str(data.get("currency", request.currencyHint or "THB")).upper().strip()
    if not re.fullmatch(r"[A-Z]{3,10}", currency):
        warnings.append("Invalid currency; request hint or THB was used.")
        currency = (request.currencyHint or "THB").upper()

    status = "COMPLETED" if normalized_rows else "FAILED"
    if not normalized_rows:
        warnings.append("No source-verified balance-sheet rows were returned.")

    return {
        "status": status,
        "statementType": "BALANCE_SHEET",
        "scope": scope,
        "currency": currency,
        "unit": unit,
        "rows": normalized_rows,
        "warnings": warnings,
        "requiresHumanReview": True,
    }
