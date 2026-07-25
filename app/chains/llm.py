import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MAIN_MODEL = "openai/gpt-4o"



DEFAULT_OLLAMA_BASE_URL = "http://192.168.1.33:11434"
DEFAULT_MAIN_OLLAMA_MODEL = "gemma4:e4b"



def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required for OpenRouter. Set it in .env.")
    return value


def get_main_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MAIN_MODEL", DEFAULT_MAIN_MODEL),
        base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL),
        api_key=_required_env("OPENROUTER_API_KEY"),
        temperature=0.2,
    )


def get_main_ollama_llm():
    return ChatOllama(
        model=DEFAULT_MAIN_OLLAMA_MODEL,
        base_url=DEFAULT_OLLAMA_BASE_URL,  # default ollama
        temperature=0.2,
    )


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


async def call_main_model(prompt: str) -> str:
    try:
        message = await get_main_ollama_llm().ainvoke(prompt)
        return _message_content_to_text(getattr(message, "content", message))
    except Exception as exc:
        raise RuntimeError(f"Failed to call OpenRouter: {exc}") from exc
