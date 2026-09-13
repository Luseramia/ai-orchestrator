from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4


DEFAULT_CODEX_TIMEOUT_SECONDS = 600
DEFAULT_CODEX_SANDBOX = "read-only"
ALLOWED_CODEX_SANDBOXES = {"read-only", "workspace-write"}


class CodexCliError(RuntimeError):
    """Raised when the Codex CLI cannot produce a final response."""


class CodexCliTimeoutError(CodexCliError):
    """Raised when the Codex CLI exceeds its configured timeout."""


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        return default

    return value if value > 0 else default


def _codex_workdir() -> Path:
    configured = os.getenv("CODEX_WORKDIR", "").strip()
    workdir = Path(configured).expanduser() if configured else Path(__file__).resolve().parents[2]
    if not workdir.is_dir():
        raise CodexCliError(f"CODEX_WORKDIR does not exist: {workdir}")
    return workdir


def _codex_sandbox() -> str:
    sandbox = os.getenv("CODEX_SANDBOX", DEFAULT_CODEX_SANDBOX).strip().lower()
    if sandbox not in ALLOWED_CODEX_SANDBOXES:
        allowed = ", ".join(sorted(ALLOWED_CODEX_SANDBOXES))
        raise CodexCliError(
            f"Unsupported CODEX_SANDBOX '{sandbox}'. Use one of: {allowed}."
        )
    return sandbox


def build_codex_command(output_file: Path) -> list[str]:
    """Build a non-interactive, read-only Codex command for one prompt."""

    executable = os.getenv("CODEX_CLI_PATH", "codex").strip() or "codex"
    command = [
        executable,
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        _codex_sandbox(),
        "--color",
        "never",
        "--output-last-message",
        str(output_file),
    ]

    model = os.getenv("CODEX_MODEL", "").strip()
    if model:
        command.extend(["--model", model])

    # A single '-' makes Codex read the prompt from stdin. This avoids shell
    # quoting issues when the SDLC context contains newlines or JSON.
    command.append("-")
    return command


def _decode(value: bytes | None) -> str:
    return (value or b"").decode("utf-8", errors="replace").strip()


def _tail(value: str, max_length: int = 2000) -> str:
    if len(value) <= max_length:
        return value
    return value[-max_length:]


async def _call_local_codex(prompt: str) -> str:
    """Run Codex CLI once and return only its final assistant message.

    The CLI uses the user's existing Codex authentication. No API key is
    copied into the orchestrator or sent through the request payload.
    """

    if not prompt.strip():
        raise CodexCliError("Cannot call Codex with an empty prompt.")

    timeout_seconds = _positive_int_env(
        "CODEX_TIMEOUT_SECONDS", DEFAULT_CODEX_TIMEOUT_SECONDS
    )
    workdir = _codex_workdir()

    output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="ai-orchestrator-codex-",
            suffix=".txt",
            delete=False,
        ) as output_file:
            output_path = Path(output_file.name)

        process = await asyncio.create_subprocess_exec(
            *build_codex_command(output_path),
            cwd=str(workdir),
            env=os.environ.copy(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise CodexCliTimeoutError(
                f"Codex CLI timed out after {timeout_seconds} seconds."
            ) from exc

        final_message = ""
        if output_path.exists():
            final_message = output_path.read_text(encoding="utf-8").strip()

        if process.returncode != 0:
            details = _tail(_decode(stderr) or _decode(stdout))
            suffix = f" Output: {details}" if details else ""
            raise CodexCliError(
                f"Codex CLI exited with code {process.returncode}.{suffix}"
            )

        # Older or alternate Codex builds may not honor --output-last-message;
        # stdout is a safe fallback for those builds.
        final_message = final_message or _decode(stdout)
        if not final_message:
            details = _tail(_decode(stderr))
            suffix = f" Details: {details}" if details else ""
            raise CodexCliError(f"Codex CLI returned an empty response.{suffix}")

        return final_message
    except FileNotFoundError as exc:
        executable = os.getenv("CODEX_CLI_PATH", "codex").strip() or "codex"
        raise CodexCliError(
            f"Codex CLI was not found: '{executable}'. Set CODEX_CLI_PATH or add codex to PATH."
        ) from exc
    finally:
        if output_path is not None:
            output_path.unlink(missing_ok=True)


class CodexRemoteError(CodexCliError):
    """Raised when the remote gateway cannot complete a request."""


async def _call_http_codex(prompt: str) -> str:
    import httpx

    base_url = os.getenv("CODEX_REMOTE_URL", "").strip().rstrip("/")
    token = os.getenv("CODEX_REMOTE_TOKEN", "").strip()
    try:
        parsed = urlsplit(base_url)
        valid_url = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.port != 0
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        raise CodexRemoteError("CODEX_REMOTE_URL must be an HTTP(S) base URL without credentials, query, or fragment.")
    if not token or not token.isascii() or any(character.isspace() for character in token):
        raise CodexRemoteError("CODEX_REMOTE_TOKEN must contain an ASCII gateway bearer token without whitespace.")

    timeout = _positive_int_env(
        "CODEX_REMOTE_TIMEOUT_SECONDS",
        _positive_int_env("CODEX_TIMEOUT_SECONDS", DEFAULT_CODEX_TIMEOUT_SECONDS) + 30,
    )
    request_id = str(uuid4())
    try:
        # Internal Service DNS and localhost must not accidentally use a host proxy.
        # HTTPX does not retry POSTs here; a lost reply may represent a completed run.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(10, timeout)),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await asyncio.wait_for(
                client.post(
                    f"{base_url}/v1/generate",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"requestId": request_id, "prompt": prompt},
                ),
                timeout=timeout,
            )
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        raise CodexCliTimeoutError(
            f"Codex gateway timed out after {timeout} seconds (request {request_id}). "
            "The remote outcome is unknown; the request was not retried."
        ) from exc
    except httpx.RequestError as exc:
        raise CodexRemoteError(
            f"Cannot communicate with Codex gateway (request {request_id}). "
            "Check the Service URL or Windows port-forward. The request was not retried."
        ) from exc

    # Never propagate raw remote error bodies, which can contain prompts or tokens.
    errors = {
        401: "Gateway authentication failed; check CODEX_REMOTE_TOKEN.",
        403: "Gateway access was denied.",
        413: "The prompt exceeds the gateway request size limit.",
        422: "The gateway rejected the request format.",
        429: "The Codex gateway is busy; try again later.",
        502: "Codex failed on the gateway; check its login status and server logs.",
        503: "The Codex gateway is not ready; check its login status and configuration.",
        504: "Codex exceeded the gateway execution deadline.",
    }
    if response.status_code != 200:
        message = errors.get(response.status_code, f"Codex gateway returned HTTP {response.status_code}.")
        error_type = CodexCliTimeoutError if response.status_code == 504 else CodexRemoteError
        raise error_type(f"{message} Request: {request_id}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CodexRemoteError("Codex gateway returned invalid JSON.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("requestId") != request_id
        or not isinstance(payload.get("output"), str)
        or not payload["output"].strip()
    ):
        raise CodexRemoteError("Codex gateway returned an invalid or mismatched response.")
    return payload["output"].strip()


async def call_codex(prompt: str) -> str:
    """Return a final message from the local CLI or the authenticated HTTP gateway."""
    if not prompt.strip():
        raise CodexCliError("Cannot call Codex with an empty prompt.")
    transport = os.getenv("CODEX_TRANSPORT", "local").strip().lower()
    if transport == "local":
        return await _call_local_codex(prompt)
    if transport == "http":
        return await _call_http_codex(prompt)
    raise CodexCliError("Unsupported CODEX_TRANSPORT. Use local or http.")
