import json
from typing import Any


OUTPUT_SCHEMA = {
    "jobId": "JOB001",
    "status": "COMPLETED",
    "artifacts": [
        {
            "artifactType": "ACCEPTANCE_CRITERIA_IMPROVEMENT",
            "title": "Improved Acceptance Criteria",
            "contentMarkdown": "string or null",
            "contentJson": "object, array, or null",
            "mermaidCode": "string or null",
        }
    ],
    "warnings": [],
    "requiresHumanReview": True,
}


def build_user_story_prompt(
    job_id: str,
    project_id: str,
    source_type: str,
    source_id: str,
    artifact_types: list[str],
    context: dict[str, Any],
) -> str:
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    artifact_types_json = json.dumps(artifact_types, ensure_ascii=False, indent=2)
    output_schema_json = json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)

    return f"""You are a senior software architect and system analyst.

You generate SDLC design artifacts from a saved User Story.

Rules:
- Return valid JSON only.
- Do not include Markdown outside JSON.
- Do not include triple backticks anywhere, including inside JSON string fields.
- Do not overwrite real SDLC data.
- Generate suggestions only.
- All artifacts require human review.
- Preserve identifiers in English.
- Do not translate table names, column names, API paths, enum values, code, SQL, JSON, or Mermaid syntax.
- Explanations can be Thai, but technical identifiers must remain English.
- If information is missing, add missing questions instead of inventing facts.
- Mermaid syntax must be valid.
- Generate only the requested artifact types.

Generation metadata:
- jobId: {job_id}
- projectId: {project_id}
- sourceType: {source_type}
- sourceId: {source_id}

Requested artifact types:
{artifact_types_json}

Input context as JSON:
{context_json}

Artifact guidance:
- ACCEPTANCE_CRITERIA_IMPROVEMENT: improve acceptance criteria as reviewable suggestions.
- MISSING_QUESTIONS: list questions needed to clarify the User Story.
- BUSINESS_RULES: identify candidate business rules and assumptions.
- DATA_FLOW_DIAGRAM: return Mermaid flowchart code in mermaidCode.
- DATA_MODEL: return Mermaid erDiagram code in mermaidCode and optional structured contentJson.
- API_DESIGN: put endpoint suggestions, request/response shapes, errors, and authorization notes in contentMarkdown; use null for contentJson.
- TEST_CASE_SUGGESTION: suggest functional, edge, negative, and integration tests.
- RISK_ANALYSIS: identify delivery, requirement, design, security, data, and operational risks.

Return JSON matching this exact output schema:
{output_schema_json}

Important:
- Use the input jobId exactly.
- Set status to COMPLETED when generation succeeds.
- Set requiresHumanReview to true.
- For each artifact, include artifactType and title.
- Use null for contentMarkdown, contentJson, or mermaidCode when not applicable.
- Put Mermaid code directly in mermaidCode without Markdown fences.
- Do not put escaped JSON snippets such as \\" or \\n outside JSON strings.
- Avoid deeply nested OpenAPI-style examples in contentJson; use contentMarkdown for examples instead.
"""
