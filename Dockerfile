FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LLM_PROVIDER=codex \
    CODEX_TRANSPORT=http

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

RUN groupadd --gid 10001 orchestrator \
    && useradd --uid 10001 --gid 10001 --create-home orchestrator

COPY --chown=10001:10001 app ./app

USER 10001:10001
RUN python -c "from app.main import app; assert app.title == 'ai-orchestrator'"

EXPOSE 8000
# Allow an in-flight generation plus JSON repair to finish during a rollout.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "1300"]
