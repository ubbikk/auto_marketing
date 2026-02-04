"""Unified LLM client using LiteLLM.

Provides a single interface for multiple LLM providers (Anthropic, Google, OpenAI, etc.)
"""

import logging
from typing import Any, Optional, Union

import litellm
from litellm import completion

# Suppress verbose LiteLLM logging
litellm.set_verbose = False
logging.getLogger("LiteLLM").setLevel(logging.WARNING)


def get_completion(
    model: str,
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.3,
    response_format: Optional[dict] = None,
    return_full_response: bool = False,
) -> Union[str, tuple[str, Any]]:
    """
    Get completion from any supported model via LiteLLM.

    Args:
        model: Model identifier. Examples:
            - "gemini/gemini-2.5-flash-preview-05-20" (Google)
            - "gemini/gemini-2.5-pro-preview-05-06" (Google)
            - "claude-opus-4-5-20251101" (Anthropic)
            - "gpt-4o" (OpenAI)
        messages: List of message dicts with role and content
        max_tokens: Maximum response tokens
        temperature: Sampling temperature (0.0-2.0)
        response_format: Optional response format (e.g., {"type": "json_object"})
        return_full_response: If True, return (text, response) tuple for cost tracking

    Returns:
        Response text content, or (text, response) tuple if return_full_response=True

    Raises:
        Exception: If API call fails
    """
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if response_format:
        kwargs["response_format"] = response_format

    response = completion(**kwargs)
    text = response.choices[0].message.content

    if return_full_response:
        return text, response
    return text


async def get_completion_async(
    model: str,
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.3,
    response_format: Optional[dict] = None,
    return_full_response: bool = False,
) -> Union[str, tuple[str, Any]]:
    """
    Async version of get_completion.

    Args:
        model: Model identifier
        messages: List of message dicts with role and content
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        response_format: Optional response format
        return_full_response: If True, return (text, response) tuple for cost tracking

    Returns:
        Response text content, or (text, response) tuple if return_full_response=True
    """
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if response_format:
        kwargs["response_format"] = response_format

    response = await litellm.acompletion(**kwargs)
    text = response.choices[0].message.content

    if return_full_response:
        return text, response
    return text
