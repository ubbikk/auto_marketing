"""Extract carousel content from text using Claude Sonnet."""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import anthropic

from .models import CarouselContent, ExplanatoryCarouselContent

logger = logging.getLogger(__name__)


@dataclass
class CarouselExtractionResult:
    """Result from carousel extraction including content and usage."""

    content: CarouselContent
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "claude-sonnet-4-20250514"

from ..prompts import render as render_prompt


async def extract_carousel_content(
    text: str,
    client: Optional[anthropic.Anthropic] = None,
    message: str = "",
) -> CarouselExtractionResult:
    """Call Claude Sonnet to extract structured carousel content from text.

    Args:
        text: Source text to extract insights from.
        client: Optional Anthropic client. Creates one if not provided.
        message: Optional key message to guide content direction.

    Returns:
        CarouselExtractionResult with content and usage data.
    """
    if client is None:
        client = anthropic.Anthropic()

    message_section = ""
    if message:
        message_section = f"KEY MESSAGE TO CONVEY:\n{message}\n\n"

    prompt = render_prompt("carousel", text=text[:5000], message_section=message_section)

    model = "claude-sonnet-4-20250514"
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract usage data
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    raw = response.content[0].text
    logger.debug("Carousel extraction raw response: %s", raw[:500])

    # Extract JSON from response, handling markdown fences and surrounding text
    stripped = raw.strip()
    if "```" in stripped:
        # Extract content between first ``` and last ```
        start = stripped.find("```")
        end = stripped.rfind("```")
        if start != end:
            inner = stripped[start:end]
            # Remove the opening ``` line (e.g. ```json)
            first_newline = inner.find("\n")
            if first_newline != -1:
                stripped = inner[first_newline + 1:]
            else:
                stripped = inner[3:]
        else:
            # Single ```, strip lines starting with it
            lines = stripped.split("\n")
            stripped = "\n".join(l for l in lines if not l.strip().startswith("```"))

    # Try to find JSON object boundaries if there's surrounding text
    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end != -1:
        stripped = stripped[brace_start : brace_end + 1]
    else:
        # No JSON at all — Claude returned a text refusal
        logger.error("Carousel extraction returned no JSON. Raw response: %s", raw[:500])
        raise ValueError(
            "Could not generate carousel — the source text may be too short or incomplete. "
            "Try providing more detailed content."
        )

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error in carousel extraction: %s. Content: %s", e, stripped[:500])
        raise ValueError(
            "Could not generate carousel — the AI returned an unexpected format. "
            "Try again or use different source text."
        )

    content = CarouselContent.model_validate(data)
    return CarouselExtractionResult(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )


@dataclass
class ExplanatoryCarouselExtractionResult:
    """Result from explanatory carousel extraction."""

    content: ExplanatoryCarouselContent
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "claude-sonnet-4-20250514"


async def extract_carousel_content_explanatory(
    text: str,
    client: Optional[anthropic.Anthropic] = None,
    message: str = "",
) -> ExplanatoryCarouselExtractionResult:
    """Extract structured carousel content for explanatory mode (flexible slides).

    Args:
        text: Source text to extract insights from.
        client: Optional Anthropic client.
        message: Optional focus area to guide content direction.

    Returns:
        ExplanatoryCarouselExtractionResult with content and usage data.
    """
    if client is None:
        client = anthropic.Anthropic()

    message_section = ""
    if message:
        message_section = f"FOCUS AREA:\n{message}\n\n"

    prompt = render_prompt("carousel_explanatory", text=text[:8000], message_section=message_section)

    model = "claude-sonnet-4-20250514"
    response = client.messages.create(
        model=model,
        max_tokens=3000,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    raw = response.content[0].text
    logger.debug("Explanatory carousel extraction raw response: %s", raw[:500])

    # Extract JSON (same parsing logic as marketing carousel)
    stripped = raw.strip()
    if "```" in stripped:
        start = stripped.find("```")
        end = stripped.rfind("```")
        if start != end:
            inner = stripped[start:end]
            first_newline = inner.find("\n")
            if first_newline != -1:
                stripped = inner[first_newline + 1:]
            else:
                stripped = inner[3:]
        else:
            lines = stripped.split("\n")
            stripped = "\n".join(l for l in lines if not l.strip().startswith("```"))

    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end != -1:
        stripped = stripped[brace_start : brace_end + 1]
    else:
        logger.error("Explanatory carousel extraction returned no JSON. Raw: %s", raw[:500])
        raise ValueError(
            "Could not generate carousel — the source text may be too short or incomplete."
        )

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error in explanatory carousel: %s. Content: %s", e, stripped[:500])
        raise ValueError(
            "Could not generate carousel — the AI returned an unexpected format."
        )

    content = ExplanatoryCarouselContent.model_validate(data)
    return ExplanatoryCarouselExtractionResult(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )
