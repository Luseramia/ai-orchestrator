from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.chains.llm import call_main_model
from app.chains.prompts import build_user_story_prompt
from app.schemas.sdlc import GenerationRequest, GenerationResponse
from app.validators.artifact_validator import (
    extract_json_payload,
    validate_generation_result,
)


SUPPORTED_USER_STORY_ARTIFACT_TYPES = {
    "ACCEPTANCE_CRITERIA_IMPROVEMENT",
    "MISSING_QUESTIONS",
    "BUSINESS_RULES",
    "DATA_FLOW_DIAGRAM",
    "DATA_MODEL",
    "API_DESIGN",
    "TEST_CASE_SUGGESTION",
    "RISK_ANALYSIS",
}


class UserStoryGraphState(TypedDict, total=False):
    jobId: str
    projectId: str
    sourceType: str
    sourceId: str
    artifactTypes: list[str]
    context: dict[str, Any]
    prompt: str
    rawOutput: str
    repairedOutput: str
    parsedOutput: dict[str, Any]
    result: dict[str, Any]
    warnings: list[str]


def _failure_response(job_id: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "jobId": job_id,
        "status": "FAILED",
        "artifacts": [],
        "warnings": warnings,
        "requiresHumanReview": True,
    }


def _append_warning(state: UserStoryGraphState, message: str) -> list[str]:
    return [*state.get("warnings", []), message]


def _build_json_repair_prompt(raw_output: str, parse_error: str) -> str:
    return f"""The following LLM output was intended to be a single JSON object, but it does not parse.

Repair it into valid JSON only.

Rules:
- Return only the repaired JSON object.
- Do not include Markdown fences or explanatory text.
- Preserve the jobId, status, artifactType, title, contentMarkdown, contentJson, mermaidCode, warnings, and requiresHumanReview fields as much as possible.
- Fix invalid escaping such as \\n or \\" appearing outside JSON strings.
- If a nested contentJson section is too malformed to repair safely, set that contentJson value to null and keep the useful details in contentMarkdown.
- Do not invent new artifacts.

Parse error:
{parse_error}

Invalid output:
{raw_output}
"""


def build_prompt(state: UserStoryGraphState) -> dict[str, Any]:
    prompt = build_user_story_prompt(
        job_id=state["jobId"],
        project_id=state["projectId"],
        source_type=state["sourceType"],
        source_id=state["sourceId"],
        artifact_types=state["artifactTypes"],
        context=state["context"],
    )
    return {"prompt": prompt}


async def call_llm(state: UserStoryGraphState) -> dict[str, Any]:
    try:
        raw_output = await call_main_model(state["prompt"])
        return {"rawOutput": raw_output}
    except Exception as exc:
        warnings = _append_warning(state, str(exc))
        return {"result": _failure_response(state["jobId"], warnings), "warnings": warnings}


async def parse_result(state: UserStoryGraphState) -> dict[str, Any]:
    if state.get("result", {}).get("status") == "FAILED":
        return {}

    raw_output = state.get("rawOutput", "")
    try:
        parsed_output = extract_json_payload(raw_output)
        return {"parsedOutput": parsed_output}
    except ValueError as parse_error:
        try:
            repaired_output = await call_main_model(
                _build_json_repair_prompt(raw_output, str(parse_error))
            )
            parsed_output = extract_json_payload(repaired_output)
            warnings = _append_warning(
                state,
                f"Repaired invalid LLM JSON after parse error: {parse_error}",
            )
            return {
                "repairedOutput": repaired_output,
                "parsedOutput": parsed_output,
                "warnings": warnings,
            }
        except Exception as repair_error:
            warnings = _append_warning(
                state,
                f"{parse_error} JSON repair failed: {repair_error}",
            )
            return {
                "result": _failure_response(state["jobId"], warnings),
                "warnings": warnings,
            }


def validate_result(state: UserStoryGraphState) -> dict[str, Any]:
    if state.get("result", {}).get("status") == "FAILED":
        return {}

    try:
        result = validate_generation_result(
            state.get("parsedOutput", {}),
            expected_job_id=state["jobId"],
            requested_artifact_types=state["artifactTypes"],
            existing_warnings=state.get("warnings", []),
        )
        return {"result": result, "warnings": result["warnings"]}
    except ValueError as exc:
        warnings = _append_warning(state, str(exc))
        return {"result": _failure_response(state["jobId"], warnings), "warnings": warnings}


def final_response(state: UserStoryGraphState) -> dict[str, Any]:
    result = state.get("result")
    if result:
        result["requiresHumanReview"] = True
        return {"result": result}

    return {
        "result": _failure_response(
            state["jobId"],
            _append_warning(state, "Generation ended without a result."),
        )
    }


def build_user_story_graph():
    graph = StateGraph(UserStoryGraphState)
    graph.add_node("build_prompt", build_prompt)
    graph.add_node("call_llm", call_llm)
    graph.add_node("parse_result", parse_result)
    graph.add_node("validate_result", validate_result)
    graph.add_node("final_response", final_response)

    graph.set_entry_point("build_prompt")
    graph.add_edge("build_prompt", "call_llm")
    graph.add_edge("call_llm", "parse_result")
    graph.add_edge("parse_result", "validate_result")
    graph.add_edge("validate_result", "final_response")
    graph.add_edge("final_response", END)

    return graph.compile()


def _to_generation_response(data: dict[str, Any]) -> GenerationResponse:
    if hasattr(GenerationResponse, "model_validate"):
        return GenerationResponse.model_validate(data)
    return GenerationResponse.parse_obj(data)


async def generate_user_story_artifacts(
    request: GenerationRequest,
) -> GenerationResponse:
    unsupported_types = [
        artifact_type
        for artifact_type in request.artifactTypes
        if artifact_type not in SUPPORTED_USER_STORY_ARTIFACT_TYPES
    ]
    supported_types = [
        artifact_type
        for artifact_type in request.artifactTypes
        if artifact_type in SUPPORTED_USER_STORY_ARTIFACT_TYPES
    ]

    warnings = [
        f"Unsupported artifactType '{artifact_type}' was ignored."
        for artifact_type in unsupported_types
    ]

    if not supported_types:
        warnings.append("No supported artifactTypes requested for USER_STORY.")
        return GenerationResponse(
            jobId=request.jobId,
            status="FAILED",
            artifacts=[],
            warnings=warnings,
            requiresHumanReview=True,
        )

    initial_state: UserStoryGraphState = {
        "jobId": request.jobId,
        "projectId": request.projectId,
        "sourceType": request.sourceType,
        "sourceId": request.sourceId,
        "artifactTypes": supported_types,
        "context": request.context,
        "warnings": warnings,
    }

    graph = build_user_story_graph()
    final_state = await graph.ainvoke(initial_state)
    return _to_generation_response(final_state["result"])
