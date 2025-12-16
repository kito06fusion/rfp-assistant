import logging
import os
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI
from openai import APITimeoutError

logger = logging.getLogger(__name__)

HF_BASE_URL = "https://router.huggingface.co/v1"
REQUEST_TIMEOUT = 120.0  # Export for use in other modules

load_dotenv()

_HF_CLIENT = None
_AZURE_CLIENT = None


def get_hf_client() -> OpenAI:
    api_key = os.environ.get("HF_TOKEN")
    if not api_key:
        raise RuntimeError("HF_TOKEN environment variable is not set.")
    global _HF_CLIENT
    if _HF_CLIENT is None:
        logger.debug("Creating HF OpenAI client with base_url=%s, timeout=%s", HF_BASE_URL, REQUEST_TIMEOUT)
        _HF_CLIENT = OpenAI(
            base_url=HF_BASE_URL,
            api_key=api_key,
            timeout=REQUEST_TIMEOUT,
        )
    return _HF_CLIENT

def get_azure_client() -> AzureOpenAI:
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")    
    if not api_key:
        raise RuntimeError("AZURE_OPENAI_API_KEY environment variable is not set.")
    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT environment variable is not set.")  
    global _AZURE_CLIENT
    if _AZURE_CLIENT is None:
        logger.debug("Creating Azure OpenAI client with endpoint=%s, api_version=%s, timeout=%s", 
                     endpoint, api_version, REQUEST_TIMEOUT)
        _AZURE_CLIENT = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            timeout=REQUEST_TIMEOUT,
        )
    return _AZURE_CLIENT

def chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    max_retries: int = 2,
) -> str:
    logger.info("Calling LLM model=%s temperature=%s max_tokens=%s", model, temperature, max_tokens)
    use_azure = model.startswith("gpt-5") or "azure" in model.lower()
    if use_azure:
        client = get_azure_client()
        deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", model)
    else:
        client = get_hf_client()
        deployment_name = model
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            start_time = time.time()
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            elapsed = time.time() - start_time
            message = completion.choices[0].message
            content = getattr(message, "content", "") or ""
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            logger.info("LLM model=%s returned %d chars in %.2fs", model, len(content), elapsed)
            return content
        except (APITimeoutError, TimeoutError) as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.warning(
                    "LLM model=%s timeout on attempt %d/%d, retrying in %ds...",
                    model, attempt + 1, max_retries + 1, wait_time
                )
                time.sleep(wait_time)
            else:
                logger.error("LLM model=%s timeout after %d attempts", model, max_retries + 1)
                raise
        except Exception as e:
            logger.error("LLM model=%s error: %s", model, str(e))
            raise
    if last_error:
        raise last_error
    raise RuntimeError(f"LLM model={model} failed after {max_retries + 1} attempts")

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


