from dotenv import load_dotenv
from fastapi import FastAPI

# Allow running this module directly (python app/main.py) by
# ensuring the project root is on sys.path so `import app...` works.
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graphs.user_story_graph import generate_user_story_artifacts
from app.graphs.financial_statement_graph import normalize_financial_statement
from app.schemas.financial_statement import (
    FinancialNormalizationRequest,
    FinancialNormalizationResponse,
)
from app.schemas.sdlc import GenerationRequest, GenerationResponse

load_dotenv()

app = FastAPI(title="ai-orchestrator", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ai-orchestrator",
    }


@app.post("/generate", response_model=GenerationResponse)
async def generate(request: GenerationRequest) -> GenerationResponse:
    print('request',request.sourceType)
    if request.sourceType != "USER_STORY":
        return GenerationResponse(
            jobId=request.jobId,
            status="FAILED",
            artifacts=[],
            warnings=[
                f"Unsupported sourceType '{request.sourceType}'. Only USER_STORY is supported."
            ],
            requiresHumanReview=True,
        )

    try:
        return await generate_user_story_artifacts(request)
    except Exception as exc:
        return GenerationResponse(
            jobId=request.jobId,
            status="FAILED",
            artifacts=[],
            warnings=[f"Artifact generation failed: {exc}"],
            requiresHumanReview=True,
        )


@app.post(
    "/financial-statements/normalize",
    response_model=FinancialNormalizationResponse,
)
async def normalize_statement(
    request: FinancialNormalizationRequest,
) -> FinancialNormalizationResponse:
    try:
        return await normalize_financial_statement(request)
    except Exception as exc:
        return FinancialNormalizationResponse(
            status="FAILED",
            scope=request.preferredScope,
            currency=(request.currencyHint or "THB").upper(),
            unit=request.unitHint or "ONES",
            rows=[],
            warnings=[f"Financial statement normalization failed: {exc}"],
            requiresHumanReview=True,
        )


if __name__ == "__main__":
    # Simple launcher for local development. Prefer `python -m app.main`
    # or using an ASGI server directly in production.
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
