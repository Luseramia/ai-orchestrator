from typing import Any, Literal

from pydantic import BaseModel, Field


class FinancialAnalysisSummaryRequest(BaseModel):
    companyName: str = Field(min_length=1, max_length=240)
    currency: str = Field(min_length=3, max_length=10)
    latestPeriod: dict[str, Any]
    previousPeriod: dict[str, Any] | None = None
    growth: dict[str, Any] = Field(default_factory=dict)
    directions: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    deterministicSummary: str


class FinancialAnalysisSummaryResponse(BaseModel):
    status: Literal["COMPLETED", "FAILED"]
    summaryMarkdown: str
    evidenceKeys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requiresHumanReview: bool = True
