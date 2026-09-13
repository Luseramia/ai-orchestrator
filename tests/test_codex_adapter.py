import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.chains.codex_adapter import call_codex, CodexCliError, CodexCliTimeoutError, CodexRemoteError


class CodexAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.environment = patch.dict(os.environ, {
            "CODEX_TRANSPORT": "http", "CODEX_REMOTE_URL": "http://127.0.0.1:18080",
            "CODEX_REMOTE_TOKEN": "test-token-" + "x" * 40,
            "CODEX_REMOTE_TIMEOUT_SECONDS": "1",
            # This deliberately does not exist: HTTP mode must never inspect it.
            "CODEX_WORKDIR": "/does/not/exist/on/windows",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def transport(self, handler):
        real_client = httpx.AsyncClient
        return patch("httpx.AsyncClient", side_effect=lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler), **kwargs,
        ))

    async def test_unicode_prompt_and_matching_final_response(self):
        def handler(request):
            self.assertEqual(request.url.path, "/v1/generate")
            self.assertTrue(request.headers["authorization"].startswith("Bearer test-token-"))
            body = json.loads(request.content)
            self.assertEqual(body["prompt"], 'คำถาม\n{"foo":"bar"}')
            self.assertEqual(set(body), {"requestId", "prompt"})
            return httpx.Response(200, json={"requestId": body["requestId"], "output": " คำตอบ "})
        with self.transport(handler):
            self.assertEqual(await call_codex('คำถาม\n{"foo":"bar"}'), "คำตอบ")

    async def test_local_mode_still_dispatches_to_original_runner(self):
        with patch.dict(os.environ, {"CODEX_TRANSPORT": "local"}), patch(
            "app.chains.codex_adapter._call_local_codex", new_callable=AsyncMock, return_value="local"
        ) as local:
            self.assertEqual(await call_codex("prompt"), "local")
            local.assert_awaited_once_with("prompt")

    async def test_http_failures_are_sanitized_and_never_retried(self):
        for status in [401, 403, 413, 422, 429, 502, 503, 504, 500, 302]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, text="SECRET_INTERNAL_ERROR", headers={"location": "http://elsewhere/"})
            with self.subTest(status=status), self.transport(handler):
                with self.assertRaises(CodexCliError) as raised:
                    await call_codex("prompt")
                self.assertNotIn("SECRET_INTERNAL_ERROR", str(raised.exception))
                self.assertEqual(len(calls), 1)

    async def test_timeout_does_not_repeat_post(self):
        calls = []
        async def handler(request):
            calls.append(request)
            await asyncio.sleep(10)
        with self.transport(handler):
            with self.assertRaises(CodexCliTimeoutError):
                await call_codex("prompt")
        self.assertEqual(len(calls), 1)

    async def test_disconnect_is_reported_without_remote_details(self):
        def handler(request):
            raise httpx.ConnectError("SECRET_INTERNAL_ERROR", request=request)
        with self.transport(handler), self.assertRaises(CodexRemoteError) as raised:
            await call_codex("prompt")
        self.assertNotIn("SECRET_INTERNAL_ERROR", str(raised.exception))

    async def test_invalid_response_and_wrong_request_id(self):
        for payload in [{}, [], {"requestId": "wrong", "output": "answer"}, {"output": 123}]:
            with self.transport(lambda request: httpx.Response(200, json=payload)):
                with self.assertRaises(CodexRemoteError):
                    await call_codex("prompt")
        with self.transport(lambda request: httpx.Response(200, text="not json")):
            with self.assertRaises(CodexRemoteError):
                await call_codex("prompt")

    async def test_invalid_configuration_and_blank_prompt_fail_before_network(self):
        for variable, value in [
            ("CODEX_TRANSPORT", "ssh"), ("CODEX_REMOTE_TOKEN", ""),
            ("CODEX_REMOTE_URL", "http://user:secret@example.test"),
            ("CODEX_REMOTE_URL", "http://localhost?token=secret"),
            ("CODEX_REMOTE_URL", "file:///tmp/server"),
        ]:
            with patch.dict(os.environ, {variable: value}), self.assertRaises(CodexCliError):
                await call_codex("prompt")
        with self.assertRaises(CodexCliError):
            await call_codex("  ")
