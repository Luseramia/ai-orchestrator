import json
import unittest
from unittest.mock import AsyncMock, patch

from app.graphs.financial_analysis_graph import summarize_financial_analysis
from app.schemas.financial_analysis import FinancialAnalysisSummaryRequest


class FinancialAnalysisSummaryTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return FinancialAnalysisSummaryRequest(
            companyName="Example PCL",
            currency="THB",
            latestPeriod={
                "periodEnd": "2026-06-30",
                "metrics": {"totalAssets": 120, "currentRatio": 1.4, "debtToEquity": 1.1},
            },
            previousPeriod={
                "periodEnd": "2025-12-31",
                "metrics": {"totalAssets": 100, "currentRatio": 1.6, "debtToEquity": 0.8},
            },
            growth={"assets": 20, "debt": 30},
            directions=[{"dimension": "Leverage", "trend": "INCREASING"}],
            signals=[{"id": "INCREASING_LEVERAGE", "severity": "warning"}],
            deterministicSummary="Assets increased 20%.",
        )

    async def test_keeps_only_evidence_from_verified_payload(self):
        output = {
            "status": "COMPLETED",
            "summaryMarkdown": "สินทรัพย์ขยายตัว ขณะที่ leverage เพิ่มขึ้น ควรติดตามโครงสร้างหนี้",
            "evidenceKeys": [
                "growth.assets",
                "signals.INCREASING_LEVERAGE",
                "invented.metric",
            ],
            "warnings": [],
            "requiresHumanReview": False,
        }
        with patch(
            "app.graphs.financial_analysis_graph.call_main_model",
            new_callable=AsyncMock,
            return_value=json.dumps(output, ensure_ascii=False),
        ):
            response = await summarize_financial_analysis(self.request())

        self.assertEqual(response.status, "COMPLETED")
        self.assertEqual(
            response.evidenceKeys,
            ["growth.assets", "signals.INCREASING_LEVERAGE"],
        )
        self.assertTrue(response.requiresHumanReview)
        self.assertTrue(any("invented.metric" in item for item in response.warnings))

    async def test_rejects_numeric_figures_for_deterministic_fallback(self):
        output = {
            "summaryMarkdown": "Debt increased 99%.",
            "evidenceKeys": ["growth.debt"],
        }
        with patch(
            "app.graphs.financial_analysis_graph.call_main_model",
            new_callable=AsyncMock,
            return_value=json.dumps(output),
        ), self.assertRaisesRegex(ValueError, "numeric figures"):
            await summarize_financial_analysis(self.request())


if __name__ == "__main__":
    unittest.main()
