from typing import Any, Literal

from pydantic import BaseModel, Field


FinancialUnit = Literal["ONES", "THOUSAND", "MILLION", "BILLION"]
FinancialScope = Literal["CONSOLIDATED", "SEPARATE"]


class WorkbookSheet(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    rows: list[list[Any]] = Field(default_factory=list, max_length=500)


class FinancialNormalizationRequest(BaseModel):
    fileName: str = Field(min_length=1, max_length=500)
    statementType: Literal["BALANCE_SHEET"] = "BALANCE_SHEET"
    preferredScope: FinancialScope = "CONSOLIDATED"
    currencyHint: str | None = None
    unitHint: FinancialUnit | None = None
    sheets: list[WorkbookSheet] = Field(min_length=1)


class NormalizedFinancialValue(BaseModel):
    periodEnd: str
    value: float
    originalValue: str
    sourceColumn: int = Field(ge=1)


class NormalizedFinancialRow(BaseModel):
    originalLabel: str
    canonicalCode: str | None = None
    confidence: float = Field(ge=0, le=1)
    mappingSource: Literal["AI"] = "AI"
    sourceSheet: str
    sourceRow: int = Field(ge=1)
    values: list[NormalizedFinancialValue] = Field(min_length=1)


class FinancialNormalizationResponse(BaseModel):
    status: Literal["COMPLETED", "FAILED"]
    statementType: Literal["BALANCE_SHEET"] = "BALANCE_SHEET"
    scope: FinancialScope
    currency: str = "THB"
    unit: FinancialUnit = "ONES"
    rows: list[NormalizedFinancialRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requiresHumanReview: bool = True
