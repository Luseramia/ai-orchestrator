import json
import re
from typing import Any


MERMAID_PREFIXES = (
    "flowchart",
    "graph",
    "erDiagram",
    "stateDiagram-v2",
    "sequenceDiagram",
    "classDiagram",
)


def extract_json_payload(raw_output: str) -> dict[str, Any]:
    text = (raw_output or "").strip()
    if not text:
        raise ValueError("LLM output was empty.")

    fenced_match = re.fullmatch(
        r"```(?:json)?\s*(.*?)```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced_match:
        text = fenced_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in LLM output.")

    json_text = text[start : end + 1]
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse LLM JSON: {exc.msg} at line {exc.lineno} column {exc.colno}."
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError("Parsed LLM JSON must be an object.")
    return parsed


def _as_warning_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _normalize_artifact(
    artifact: Any,
    index: int,
    requested_artifact_types: list[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        warnings.append(f"Artifact at index {index} was ignored because it is not an object.")
        return None

    artifact_type = artifact.get("artifactType")
    if not artifact_type:
        artifact_type = "UNKNOWN"
        warnings.append(f"Artifact at index {index} is missing artifactType.")

    title = artifact.get("title")
    if not title:
        title = str(artifact_type) if artifact_type != "UNKNOWN" else "Untitled Artifact"
        warnings.append(f"Artifact at index {index} is missing title.")

    if requested_artifact_types and artifact_type not in requested_artifact_types:
        warnings.append(
            f"Artifact '{artifact_type}' was returned but was not requested."
        )

    normalized = {
        "artifactType": str(artifact_type),
        "title": str(title),
        "contentMarkdown": artifact.get("contentMarkdown"),
        "contentJson": artifact.get("contentJson"),
        "mermaidCode": artifact.get("mermaidCode"),
    }

    mermaid_code = normalized["mermaidCode"]
    if isinstance(mermaid_code, str) and mermaid_code.strip():
        stripped = mermaid_code.strip()
        if not stripped.startswith(MERMAID_PREFIXES):
            warnings.append(
                f"Artifact '{normalized['artifactType']}' has mermaidCode with an unsupported diagram prefix."
            )

    return normalized


def validate_generation_result(
    data: dict[str, Any],
    expected_job_id: str,
    requested_artifact_types: list[str] | None = None,
    existing_warnings: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Generation result must be a JSON object.")

    warnings = [*(existing_warnings or []), *_as_warning_list(data.get("warnings"))]
    requested_artifact_types = requested_artifact_types or []

    job_id = data.get("jobId")
    if not job_id:
        warnings.append("Generated result is missing jobId; using request jobId.")
        job_id = expected_job_id
    elif job_id != expected_job_id:
        warnings.append("Generated result jobId did not match request jobId; using request jobId.")
        job_id = expected_job_id

    status = data.get("status")
    if not status:
        warnings.append("Generated result is missing status; using COMPLETED.")
        status = "COMPLETED"
    elif status not in {"COMPLETED", "FAILED"}:
        warnings.append(f"Generated result has unsupported status '{status}'; using COMPLETED.")
        status = "COMPLETED"

    artifacts_value = data.get("artifacts")
    if artifacts_value is None:
        warnings.append("Generated result is missing artifacts; using an empty list.")
        artifacts_value = []
    elif not isinstance(artifacts_value, list):
        warnings.append("Generated result artifacts field was not a list; using an empty list.")
        artifacts_value = []

    artifacts = []
    for index, artifact in enumerate(artifacts_value):
        normalized = _normalize_artifact(
            artifact,
            index,
            requested_artifact_types,
            warnings,
        )
        if normalized is not None:
            artifacts.append(normalized)

    if data.get("requiresHumanReview") is not True:
        warnings.append("requiresHumanReview was missing or false; forced to true.")

    return {
        "jobId": job_id,
        "status": status,
        "artifacts": artifacts,
        "warnings": warnings,
        "requiresHumanReview": True,
    }
