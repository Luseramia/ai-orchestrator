"""Run with CODEX_GATEWAY_CHART set to the sibling codex-workspace chart."""
import asyncio
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

import httpx
import uvicorn


CHART = Path(os.getenv("CODEX_GATEWAY_CHART", str(Path(__file__).resolve().parents[2] / "k8s-project-helm" / "codex-workspace")))


@unittest.skipUnless((CHART / "gateway" / "app.py").exists(), "Set CODEX_GATEWAY_CHART to run the cross-repository HTTP integration test.")
class GatewayIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uses_http_gateway_and_repairs_json_with_distinct_requests(self):
        sys.path.insert(0, str(CHART))
        self.addCleanup(lambda: sys.path.remove(str(CHART)))
        from gateway.app import create_app

        final = {
            "jobId": "HTTP_TEST", "status": "COMPLETED",
            "artifacts": [{"artifactType": "BUSINESS_RULES", "title": "Business rules", "contentMarkdown": "กฎตัวอย่าง"}],
            "warnings": [], "requiresHumanReview": True,
        }
        class Runner:
            def __init__(self):
                self.prompts = []
            async def ready(self):
                return True
            async def run(self, prompt):
                self.prompts.append(prompt)
                return "invalid JSON for repair" if len(self.prompts) == 1 else json.dumps(final, ensure_ascii=False)

        runner = Runner()
        token = "integration-test-" + "x" * 40
        application = create_app(runner=runner, token=token)
        request_ids = []
        @application.middleware("http")
        async def track_requests(request, call_next):
            if request.url.path == "/v1/generate":
                request_ids.append((await request.json())["requestId"])
            return await call_next(request)

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(application, log_level="error", timeout_graceful_shutdown=2))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.02)
            self.assertTrue(server.started)
            with patch.dict(os.environ, {
                "LLM_PROVIDER": "codex", "CODEX_TRANSPORT": "http",
                "CODEX_REMOTE_URL": f"http://127.0.0.1:{port}", "CODEX_REMOTE_TOKEN": token,
                "CODEX_REMOTE_TIMEOUT_SECONDS": "5",
            }):
                from app.main import app
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://orchestrator") as client:
                    response = await client.post("/generate", json={
                        "jobId": "HTTP_TEST", "projectId": "PROJECT", "sourceType": "USER_STORY",
                        "sourceId": "US1", "triggerEvent": "user_story.saved",
                        "artifactTypes": ["BUSINESS_RULES"],
                        "context": {"source": {"data": {"iWant": "ทดสอบการเชื่อมต่อ"}}},
                    })
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["status"], "COMPLETED", result)
            self.assertEqual(result["jobId"], "HTTP_TEST")
            self.assertEqual(result["artifacts"][0]["contentMarkdown"], "กฎตัวอย่าง")
            self.assertTrue(result["requiresHumanReview"])
            self.assertEqual(len(runner.prompts), 2)
            self.assertIn("Repair it into valid JSON", runner.prompts[1])
            self.assertEqual(len(set(request_ids)), 2)
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            listener.close()
