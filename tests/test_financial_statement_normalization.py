import json
import unittest
from unittest.mock import AsyncMock, patch

from app.graphs.financial_statement_graph import normalize_financial_statement
from app.schemas.financial_statement import FinancialNormalizationRequest


class FinancialStatementNormalizationTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return FinancialNormalizationRequest(
            fileName="sample.xlsx",
            preferredScope="CONSOLIDATED",
            currencyHint="THB",
            unitHint="THOUSAND",
            sheets=[
                {
                    "name": "BS-Asset",
                    "rows": [
                        ["งบแสดงฐานะการเงิน", None, None],
                        ["รายการ", "30 มิถุนายน 2569", "31 ธันวาคม 2568"],
                        ["เงินสดและรายการเทียบเท่าเงินสด", 1250, "(300)"],
                    ],
                }
            ],
        )

    async def test_uses_source_cell_instead_of_model_number(self):
        model_output = {
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
                    "sourceRow": 3,
                    "values": [
                        {
                            "periodEnd": "2026-06-30",
                            "value": 999999,
                            "originalValue": "invented",
                            "sourceColumn": 2,
                        },
                        {
                            "periodEnd": "2025-12-31",
                            "value": -300,
                            "originalValue": "(300)",
                            "sourceColumn": 3,
                        },
                    ],
                }
            ],
            "warnings": [],
            "requiresHumanReview": True,
        }

        with patch(
            "app.graphs.financial_statement_graph.call_main_model",
            new_callable=AsyncMock,
            return_value=json.dumps(model_output, ensure_ascii=False),
        ) as model:
            response = await normalize_financial_statement(self.request())

        self.assertEqual(response.status, "COMPLETED")
        self.assertEqual(response.rows[0].values[0].value, 1250)
        self.assertEqual(response.rows[0].values[0].originalValue, "1250")
        self.assertEqual(response.rows[0].values[1].value, -300)
        self.assertTrue(any("source value was used" in item for item in response.warnings))
        prompt = model.await_args.args[0]
        self.assertIn("Never mix consolidated", prompt)
        self.assertIn("BS-Asset", prompt)

    async def test_drops_unverifiable_coordinates_and_unknown_codes(self):
        model_output = {
            "scope": "SEPARATE",
            "currency": "not currency",
            "unit": "CRORE",
            "rows": [
                {
                    "originalLabel": "เงินสดและรายการเทียบเท่าเงินสด",
                    "canonicalCode": "ASSET.MADE_UP",
                    "confidence": 1,
                    "sourceSheet": "BS-Asset",
                    "sourceRow": 3,
                    "values": [
                        {
                            "periodEnd": "2026-06-30",
                            "value": 1250,
                            "sourceColumn": 2,
                        }
                    ],
                },
                {
                    "originalLabel": "missing",
                    "canonicalCode": "ASSET.CASH",
                    "confidence": 1,
                    "sourceSheet": "missing-sheet",
                    "sourceRow": 999,
                    "values": [],
                },
            ],
        }

        with patch(
            "app.graphs.financial_statement_graph.call_main_model",
            new_callable=AsyncMock,
            return_value=json.dumps(model_output, ensure_ascii=False),
        ):
            response = await normalize_financial_statement(self.request())

        self.assertEqual(response.scope, "CONSOLIDATED")
        self.assertEqual(response.currency, "THB")
        self.assertEqual(response.unit, "THOUSAND")
        self.assertIsNone(response.rows[0].canonicalCode)
        self.assertLess(response.rows[0].confidence, 0.70)
        self.assertEqual(len(response.rows), 1)


if __name__ == "__main__":
    unittest.main()
