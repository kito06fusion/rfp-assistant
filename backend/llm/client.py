import logging
import os
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

HF_BASE_URL = "https://router.huggingface.co/v1"

load_dotenv()

def get_hf_client() -> OpenAI:
    api_key = os.environ.get("HF_TOKEN")
    if not api_key:
        raise RuntimeError("HF_TOKEN environment variable is not set.")

    logger.debug("Creating HF OpenAI client with base_url=%s", HF_BASE_URL)
    return OpenAI(
        base_url=HF_BASE_URL,
        api_key=api_key,
    )


def chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    logger.info("Calling LLM model=%s temperature=%s", model, temperature)
    client = get_hf_client()
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    message = completion.choices[0].message
    content = getattr(message, "content", "") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    logger.debug("LLM model=%s returned %d chars", model, len(content))
    return content


def chat_completion_with_vision(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    logger.info("Calling vision LLM model=%s temperature=%s", model, temperature)
    client = get_hf_client()
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    message = completion.choices[0].message
    content = getattr(message, "content", "") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    logger.debug("Vision LLM model=%s returned %d chars", model, len(content))
    return content


