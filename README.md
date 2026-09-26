# ai-orchestrator

Standalone FastAPI service for generating SDLC AI artifacts from project context.

The service receives SDLC context from the backend or n8n, runs a LangGraph workflow, calls a configurable model provider, and returns generated artifacts as structured JSON. It does not persist jobs or artifacts.

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

For a local Codex CLI test, use these settings:

```env
LLM_PROVIDER=codex
CODEX_CLI_PATH=codex
CODEX_MODEL=
CODEX_WORKDIR=
CODEX_TIMEOUT_SECONDS=600
CODEX_SANDBOX=read-only
```

Make sure the CLI is authenticated before starting the API:

```bash
codex login
codex login status
```

`CODEX_WORKDIR` defaults to this repository. `CODEX_SANDBOX=read-only` prevents the model from changing the orchestrator workspace. The adapter runs `codex exec --ephemeral` and uses the Codex CLI's existing local authentication; no API key is added to the request body.

To use OpenRouter instead:

```env
LLM_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=your-openrouter-api-key
MAIN_MODEL=openai/gpt-4o
```

To use Ollama instead:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:e4b
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

## Test the Codex adapter

After configuring `LLM_PROVIDER=codex`, start the service:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Then send the example request below. The `/generate` response is produced through the local Codex CLI and is normalized by the same validator used by the other providers.

## Generate Artifacts

Only `sourceType=USER_STORY` is supported in this MVP.

## Normalize Financial Statements

`POST /financial-statements/normalize` converts multi-sheet balance-sheet data
into the shared financial import schema. The caller sends workbook cells as JSON
and chooses `CONSOLIDATED` or `SEPARATE`. The model identifies the layout,
periods, and canonical accounts; the service then reads every numeric value back
from its declared source cell before returning it. Unverifiable rows are dropped
and the response always requires human review.

The endpoint does not require a caller API key. When running the caller locally,
port-forward this service and use `http://127.0.0.1:18000`. The orchestrator's
credential for the Codex gateway remains inside Kubernetes and is never sent by
the browser or backend caller.

Example request:

```json
{
  "fileName": "financial-statements.xlsx",
  "statementType": "BALANCE_SHEET",
  "preferredScope": "CONSOLIDATED",
  "currencyHint": "THB",
  "unitHint": "THOUSAND",
  "sheets": [
    {
      "name": "BS-Asset",
      "rows": [
        ["รายการ", "30 มิถุนายน 2569"],
        ["เงินสดและรายการเทียบเท่าเงินสด", 1250]
      ]
    }
  ]
}
```

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

## Remote Codex on Kubernetes

The Codex provider supports `CODEX_TRANSPORT=local` (the default) and `CODEX_TRANSPORT=http`. HTTP mode sends the prompt to an authenticated gateway running with the Codex CLI in the existing Kubernetes workspace. It does not require a local Codex installation or OpenAI login. The gateway implementation, image, and Helm chart are in the sibling `k8s-project-helm/codex-workspace` directory.

Deploy that gateway before using HTTP mode. Its default Service is `codex-gateway`, port 8080, in namespace `codex`. Set the actual namespace and name in the examples if your release differs. The gateway owns the working directory, model, sandbox, and execution timeout; local `CODEX_WORKDIR`, `CODEX_MODEL`, and `CODEX_SANDBOX` do not configure the remote process.

### Develop on Windows

Install dependencies as above. With a local kubeconfig, open one PowerShell terminal for the tunnel:

```powershell
.\scripts\dev-port-forward.ps1 -Namespace codex
```

If kubectl is only configured on your SSH server, use this instead:

```powershell
.\scripts\dev-port-forward.ps1 -SshHost tarchunk@192.168.1.51 -Namespace codex
```

The SSH variant forwards `127.0.0.1:18080` on Windows to a remote localhost `kubectl port-forward`. It uses the remote host's current kubectl context. Complete any SSH authentication in the terminal and keep it open. Restart the script after the selected Pod restarts or the SSH connection drops. Direct mode also accepts `-Context` and `-Kubeconfig`; both modes accept `-LocalPort` and `-Service`.

If PowerShell's execution policy blocks a local script, run that reviewed script in a separate process, for example `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-port-forward.ps1 -SshHost tarchunk@192.168.1.51`. This does not change the machine's persistent execution policy. The same invocation works for the configuration helper below.

In a second terminal, configure the local `.env`. The helper reads only the gateway Secret, stores the token in the ignored `.env`, preserves unrelated settings, and does not print the token:

```powershell
# Use this when kubectl is configured on Windows:
.\scripts\configure-codex-dev.ps1 -Namespace codex

# Or use the SSH host's kubectl:
.\scripts\configure-codex-dev.ps1 -SshHost tarchunk@192.168.1.51 -Namespace codex
```

The helper needs permission to read that Secret. A developer with port-forward permission but no Secret-read permission can set a securely supplied token manually. The `.env.dev.example` file shows the required settings; the application reads `.env`, not `.env.dev.example` automatically.

```env
LLM_PROVIDER=codex
CODEX_TRANSPORT=http
CODEX_REMOTE_URL=http://127.0.0.1:18080
CODEX_REMOTE_TOKEN=<gateway-token>
CODEX_TIMEOUT_SECONDS=600
CODEX_REMOTE_TIMEOUT_SECONDS=630
```

Check the tunnel and start the orchestrator:

```powershell
Invoke-RestMethod http://127.0.0.1:18080/health
Invoke-RestMethod http://127.0.0.1:18080/ready
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Use the existing `/generate` request example to generate SDLC artifacts. A generation request uses the server's Codex account and its available quota.

### Run inside Kubernetes

Use `.env.k8s.example` as the reference. Set `CODEX_REMOTE_URL=http://codex-gateway.codex.svc.cluster.local:8080` and inject `CODEX_REMOTE_TOKEN` from a Secret in the orchestrator's own namespace. Configure the gateway chart's `gateway.networkPolicy.allowedNamespace` and label the orchestrator Pod `app.kubernetes.io/name: ai-orchestrator`. The chart README includes the Deployment snippet. Namespace and label must both match.

The deployment manifests are in `ai-orchestrator/` of the sibling `k8s-project-helm` repository. They use namespace `codex` to share the existing `codex-gateway-auth` Secret and match the gateway's default NetworkPolicy. The internal API URL is `http://ai-orchestrator.codex.svc.cluster.local:8000/generate`.

This repository now provides a `Dockerfile` and `Jenkinsfile`. Jenkins checks out both repositories, tests the adapter and API health endpoint, builds with Kaniko, pushes to the existing internal registry, and commits the image tag to the deployment repository. Argo CD automatically syncs that Git revision. See `k8s-project-helm/ai-orchestrator/README.md` for first-deployment steps and cluster smoke checks. No gateway token is needed in Jenkins or the image; Kubernetes injects the decoded Secret value at runtime.

For a local container build (Docker daemon required):

```bash
docker build -t ai-orchestrator:dev .
```

The image runs `uvicorn app.main:app` on `0.0.0.0:8000` as UID 10001. `.dockerignore` limits the build context to application code and dependencies, excluding local `.env`, CLI credentials, virtual environments, and scratch files. Kubernetes allows 1320 seconds for termination so generation plus a possible repair can complete during rollouts.

### Deadlines and errors

`CODEX_REMOTE_TIMEOUT_SECONDS` defaults to `CODEX_TIMEOUT_SECONDS + 30` on the client. Align it with the gateway's actual execution deadline (600 seconds by default). A complete SDLC request can include generation plus a second Codex call to repair malformed JSON; the backend/n8n/proxy must allow both calls, roughly 1260 seconds plus overhead with the defaults.

HTTP calls do not retry or follow redirects. A lost reply can mean the server already executed the request, so an automatic retry could consume quota twice. Request IDs identify individual calls in gateway logs, including separate IDs for generation and repair; they are not idempotency keys. Authentication, busy, readiness, and execution failures flow into the existing `FAILED` response with sanitized warnings.

### Verify the integration locally

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r ..\k8s-project-helm\codex-workspace\gateway\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s ..\k8s-project-helm\codex-workspace\tests -v
```

Tests cover both transports, error handling, real localhost HTTP through `/generate` including JSON repair, token validation, readiness, concurrent requests, client disconnects, and subprocess cleanup. They use a simulated Codex process and do not call the model. Set `CODEX_GATEWAY_CHART` if the chart is checked out at a different path; the cross-repository test is skipped if the gateway sources are unavailable.
