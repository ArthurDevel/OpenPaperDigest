import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
import json
import re
import os
from dotenv import load_dotenv

from shared.config import settings
from shared.openrouter.models import LLMCallResult, LLMJsonCallResult, ApiCallCost

logger = logging.getLogger(__name__)
load_dotenv()
# Constants (keep it simple)
#BASE_URL = "http://feedbackrouter:8000/v1"
BASE_URL = os.environ.get("OPENROUTER_BASE_URL","https://openrouter.ai/api/v1")
TIMEOUT_SECONDS = 300

# Module-level headers using configured API key
_api_key = settings.OPENROUTER_API_KEY
if not _api_key:
    raise ValueError("OPENROUTER_API_KEY not found in settings.")
_HEADERS = {
    "Authorization": f"Bearer {_api_key}",
    "Content-Type": "application/json",
}


# Utilities for robust JSON parsing from LLM responses
def _strip_markdown_fences(text: str) -> str:
    """If content is wrapped in Markdown code fences, extract the inner block."""
    if not isinstance(text, str):
        return text
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else text


def _extract_first_json_snippet(text: str) -> str:
    """Extract the first balanced JSON object/array substring from text."""
    if not isinstance(text, str):
        return text
    start_index = None
    stack: List[str] = []
    for i, ch in enumerate(text):
        if ch == '{' or ch == '[':
            start_index = i
            stack = [ch]
            break
    if start_index is None:
        return text.strip()
    for j in range(start_index + 1, len(text)):
        ch = text[j]
        if ch == '{' or ch == '[':
            stack.append(ch)
        elif ch == '}' or ch == ']':
            if not stack:
                continue
            open_ch = stack[-1]
            if (open_ch == '{' and ch == '}') or (open_ch == '[' and ch == ']'):
                stack.pop()
                if not stack:
                    return text[start_index:j + 1]
    return text[start_index:].strip()


def _safe_json_loads(raw_text: str) -> Any:
    """
    Try multiple strategies to parse JSON from an LLM response content string.
    - Direct json.loads
    - Strip markdown code fences, retry
    - Extract first balanced JSON snippet, retry with strict=False to allow control chars
    """
    candidate = raw_text.strip() if isinstance(raw_text, str) else raw_text
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        pass

    candidate = _strip_markdown_fences(candidate).strip() if isinstance(candidate, str) else candidate
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        pass

    if isinstance(candidate, str):
        candidate = _extract_first_json_snippet(candidate)
    try:
        # Allow control characters in strings
        return json.loads(candidate, strict=False)  # type: ignore[arg-type]
    except Exception:
        logger.error("Failed to parse JSON content. Preview: %s", (candidate[:500] if isinstance(candidate, str) else str(candidate)) )
        raise


async def get_llm_response(messages: List[Dict[str, Any]], model: str) -> LLMCallResult:
    """
    Gets a response from a specified LLM on OpenRouter with a given prompt.
    Supports both text-only and multimodal messages.
    """
    start_time = datetime.utcnow()
    
    json_payload = {
        "model": model,
        "messages": messages
    }
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        try:
            response = await client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            data = response.json()

            usage = data.get("usage", {}) or {}
            choices = data.get("choices", []) or []
            first_message = choices[0].get("message") if choices else None
            response_text = (first_message or {}).get("content") if first_message else None
            generation_id = data.get("id")

            total_cost: Optional[float] = None
            if generation_id:
                try:
                    total_cost = await get_generation_cost(generation_id)
                except Exception as ce:
                    logger.error(f"Failed to retrieve cost for generation {generation_id}: {ce}")

            end_time = datetime.utcnow()
            
            # Create cost info object (pure cost data only) (pure cost data only)
            cost_info = ApiCallCost(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                total_cost=total_cost
            )

            return LLMCallResult(
                model=model,
                generation_id=generation_id,
                start_time=start_time,
                end_time=end_time,
                cost_info=cost_info,
                response_text=response_text,
                response_message=first_message,
                raw_response=data,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter: {e}")
            logger.error(f"Request body: {json_payload}")
            raise


async def get_multimodal_json_response(system_prompt: str, user_prompt_parts: List[Dict[str, Any]], model: str) -> LLMJsonCallResult:
    """
    Gets a structured JSON response from a specified multimodal LLM on OpenRouter.
    """
    start_time = datetime.utcnow()
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt_parts},
    ]
    json_payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        try:
            response = await client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            data = response.json()

            # Extract JSON content
            message = (data.get("choices", [{}])[0] or {}).get("message", {}) or {}
            json_content = message.get("content", "")
            # Fallback: some providers may return structured output via tool_calls
            if (not isinstance(json_content, str)) or (isinstance(json_content, str) and not json_content.strip()):
                tool_calls = message.get("tool_calls") or []
                if isinstance(tool_calls, list) and tool_calls:
                    try:
                        fn = (tool_calls[0] or {}).get("function") or {}
                        args_text = fn.get("arguments")
                        if isinstance(args_text, str) and args_text.strip():
                            json_content = args_text
                            logger.debug("OpenRouter JSON fallback: extracted from tool_calls arguments (len=%s)", len(json_content))
                    except Exception:
                        pass

            usage = data.get("usage", {}) or {}
            choices = data.get("choices", []) or []
            first_message = choices[0].get("message") if choices else None
            response_text = (first_message or {}).get("content") if first_message else None
            generation_id = data.get("id")

            # Logging and guard for empty/invalid JSON content
            content_len = len(json_content or "") if isinstance(json_content, str) else 0
            logger.debug(
                "OpenRouter JSON response meta model=%s generation_id=%s usage=%s content_len=%s",
                model,
                generation_id,
                {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                content_len,
            )

            if not isinstance(json_content, str) or not json_content.strip():
                logger.warning(
                    "Empty JSON content from provider for model=%s generation_id=%s; continuing with {}",
                    model,
                    generation_id,
                )
                parsed = {}
            else:
                try:
                    parsed = _safe_json_loads(json_content)
                except Exception as e:
                    logger.error("Failed to parse JSON content. Preview: %s", (json_content[:500] if isinstance(json_content, str) else str(json_content)))
                    logger.error("Error parsing JSON from OpenRouter response: %s", e)
                    parsed = {}

            total_cost: Optional[float] = None
            if generation_id:
                try:
                    total_cost = await get_generation_cost(generation_id)
                except Exception as ce:
                    logger.error(f"Failed to retrieve cost for generation {generation_id}: {ce}")

            end_time = datetime.utcnow()
            
            # Create cost info object (pure cost data only)
            cost_info = ApiCallCost(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                total_cost=total_cost
            )

            return LLMJsonCallResult(
                model=model,
                generation_id=generation_id,
                start_time=start_time,
                end_time=end_time,
                cost_info=cost_info,
                response_text=response_text,
                response_message=first_message,
                raw_response=data,
                parsed_json=parsed,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter for JSON response: {e}")
            logger.error(f"Request body: {json.dumps(json_payload, indent=2)}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing JSON from OpenRouter response: {e}")
            raise


async def get_json_response(system_prompt: str, user_prompt: str, model: str) -> LLMJsonCallResult:
    """
    Gets a structured JSON response from a specified LLM on OpenRouter.
    """
    start_time = datetime.utcnow()
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    json_payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        try:
            response = await client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            data = response.json()

            # Extract JSON content
            message = (data.get("choices", [{}])[0] or {}).get("message", {}) or {}
            json_content = message.get("content", "")
            # Fallback: some providers may return structured output via tool_calls
            if (not isinstance(json_content, str)) or (isinstance(json_content, str) and not json_content.strip()):
                tool_calls = message.get("tool_calls") or []
                if isinstance(tool_calls, list) and tool_calls:
                    try:
                        fn = (tool_calls[0] or {}).get("function") or {}
                        args_text = fn.get("arguments")
                        if isinstance(args_text, str) and args_text.strip():
                            json_content = args_text
                            logger.debug("OpenRouter JSON fallback: extracted from tool_calls arguments (len=%s)", len(json_content))
                    except Exception:
                        pass

            usage = data.get("usage", {}) or {}
            choices = data.get("choices", []) or []
            first_message = choices[0].get("message") if choices else None
            response_text = (first_message or {}).get("content") if first_message else None
            generation_id = data.get("id")

            # Logging and guard for empty/invalid JSON content
            content_len = len(json_content or "") if isinstance(json_content, str) else 0
            logger.debug(
                "OpenRouter JSON response meta model=%s generation_id=%s usage=%s content_len=%s",
                model,
                generation_id,
                {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                content_len,
            )

            if not isinstance(json_content, str) or not json_content.strip():
                logger.warning(
                    "Empty JSON content from provider for model=%s generation_id=%s; continuing with {}",
                    model,
                    generation_id,
                )
                parsed = {}
            else:
                try:
                    parsed = _safe_json_loads(json_content)
                except Exception as e:
                    logger.error("Failed to parse JSON content. Preview: %s", (json_content[:500] if isinstance(json_content, str) else str(json_content)))
                    logger.error("Error parsing JSON from OpenRouter response: %s", e)
                    parsed = {}

            total_cost: Optional[float] = None
            if generation_id:
                try:
                    total_cost = await get_generation_cost(generation_id)
                except Exception as ce:
                    logger.error(f"Failed to retrieve cost for generation {generation_id}: {ce}")

            end_time = datetime.utcnow()
            
            # Create cost info object (pure cost data only)
            cost_info = ApiCallCost(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                total_cost=total_cost
            )

            return LLMJsonCallResult(
                model=model,
                generation_id=generation_id,
                start_time=start_time,
                end_time=end_time,
                cost_info=cost_info,
                response_text=response_text,
                response_message=first_message,
                raw_response=data,
                parsed_json=parsed,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter for JSON response: {e}")
            logger.error(f"Request body: {json.dumps(json_payload, indent=2)}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing JSON from OpenRouter response structure: {e}")
            # Continue with empty parsed JSON
            fallback_end_time = datetime.utcnow()
            fallback_cost_info = ApiCallCost(
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                total_cost=None
            )
            return LLMJsonCallResult(
                model=model,
                generation_id=None,
                start_time=start_time,
                end_time=fallback_end_time,
                cost_info=fallback_cost_info,
                response_text=None,
                response_message=None,
                raw_response={},
                parsed_json={},
            )


async def get_generation_cost(generation_id: str) -> float:
    """
    Retrieves the cost of a specific generation from OpenRouter.
    """
    # Add a small delay to allow for the generation stats to be processed.
    await asyncio.sleep(2)
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(f"/generation?id={generation_id}")
            response.raise_for_status()
            data = response.json()
            logger.info(f"Received cost data for generation {generation_id}: {json.dumps(data)}")
            generation_data = data.get("data", {})
            return generation_data.get("total_cost", 0.0)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError getting generation cost for id {generation_id}: {e}")
            logger.error(f"Response: {e.response.text}")
            raise


async def get_models() -> List[Dict[str, Any]]:
    """
    Returns the list of available models from OpenRouter.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        try:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError fetching OpenRouter models: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching OpenRouter models: {e}")
            raise


# Intentionally no generic chat() wrapper; keep simple helpers only


