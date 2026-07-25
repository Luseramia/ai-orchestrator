# ai-orchestrator

Standalone FastAPI service for generating SDLC AI artifacts from project context.

The service receives SDLC context from the backend or n8n, runs a LangGraph workflow, calls OpenRouter through LangChain, and returns generated artifacts as structured JSON. It does not persist jobs or artifacts.

## Setup

Requires Python 3.10 or newer.

Create and activate a virtual environment:

```bash
cd ai-orchestrator
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional syntax check:

```bash
python -m compileall app
```

Create an environment file:

```bash
cp .env.example .env
```

Default OpenRouter settings:

```env
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=your-openrouter-api-key
MAIN_MODEL=openai/gpt-4o
```

This config calls OpenRouter's chat completions API:

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
    "model": "openai/gpt-4o",
    "messages": [
      {
        "role": "user",
        "content": "What is the meaning of life?"
      }
    ]
  }'
```

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## Health Check

```bash
curl http://127.0.0.1:8001/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "ai-orchestrator"
}
```

## Generate Artifacts

Only `sourceType=USER_STORY` is supported in this MVP.

```bash
curl -X POST http://127.0.0.1:8001/generate \
  -H "Content-Type: application/json" \
  -d '{
    "jobId": "JOB001",
    "projectId": "P001",
    "sourceType": "USER_STORY",
    "sourceId": "US001",
    "triggerEvent": "user_story.saved",
    "artifactTypes": [
      "ACCEPTANCE_CRITERIA_IMPROVEMENT",
      "MISSING_QUESTIONS",
      "BUSINESS_RULES",
      "DATA_FLOW_DIAGRAM",
      "DATA_MODEL",
      "API_DESIGN",
      "TEST_CASE_SUGGESTION",
      "RISK_ANALYSIS"
    ],
    "context": {
      "project": {
        "id": "P001",
        "name": "Shopping System",
        "description": "Online shopping platform"
      },
      "source": {
        "type": "USER_STORY",
        "data": {
          "actor": "Customer",
          "iWant": "to place an order",
          "soThat": "I can buy products online",
          "acceptanceCriteria": [
            "Customer can add product to cart",
            "Customer can checkout",
            "Customer can see order status"
          ]
        }
      },
      "related": {
        "requirements": [],
        "risks": [],
        "existingDesign": [],
        "traceability": []
      }
    }
  }'
```

Example successful response shape:

```json
{
  "jobId": "JOB001",
  "status": "COMPLETED",
  "artifacts": [
    {
      "artifactType": "ACCEPTANCE_CRITERIA_IMPROVEMENT",
      "title": "Improved Acceptance Criteria",
      "contentMarkdown": "...",
      "contentJson": null,
      "mermaidCode": null
    }
  ],
  "warnings": [],
  "requiresHumanReview": true
}
```

If OpenRouter is unavailable or generation fails, the API returns `status=FAILED` with warnings instead of crashing.
