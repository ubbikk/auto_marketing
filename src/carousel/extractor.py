"""Extract carousel content from text using Claude Sonnet."""

import json
from typing import Optional

import anthropic

from .models import CarouselContent

SYSTEM_PROMPT = """\
You are a content strategist creating LinkedIn carousel slides.
Your job is to read an article or text and extract the most compelling insights
to fill a 5-slide LinkedIn carousel.

The carousel has this structure:
1. COVER — An attention-grabbing title (max ~10 words) + one-line subtitle.
2. BULLETS — A heading + exactly 3 bullet points with concrete facts/stats.
3. NUMBERED — A heading + exactly 3 numbered items, each with a bold title and a description.
4. STATS — A heading + exactly 3 stat cards (short value like "3×" + label) + a quote.
5. CTA — A closing headline + subtitle + button text.

Rules:
- Keep language punchy and professional. No fluff.
- Use specific numbers and data from the source text whenever possible.
- If the source doesn't contain exact stats, synthesize plausible key takeaways.
- The quote on slide 4 should capture the most memorable or impactful line from the text.
- Badge text for each slide should be a single word reflecting the slide's theme.
- All content should relate to the source text's core topic.
"""

USER_PROMPT_TEMPLATE = """\
Extract carousel content from this text. Return ONLY valid JSON matching the schema below.

Schema:
{{
  "cover": {{
    "title": "string (max ~10 words)",
    "subtitle": "string (one sentence)",
    "badge": "string (one word)"
  }},
  "bullets": {{
    "heading": "string (3-6 words)",
    "badge": "string (one word)",
    "bullets": ["string", "string", "string"]
  }},
  "numbered": {{
    "heading": "string (3-6 words)",
    "badge": "string (one word)",
    "items": [
      {{"title": "string", "description": "string"}},
      {{"title": "string", "description": "string"}},
      {{"title": "string", "description": "string"}}
    ]
  }},
  "stats": {{
    "heading": "string (3-6 words)",
    "badge": "string (one word)",
    "stats": [
      {{"value": "string (MAX 4 chars, e.g. '3×', '87%', '14h')", "label": "string"}},
      {{"value": "string (MAX 4 chars)", "label": "string"}},
      {{"value": "string (MAX 4 chars)", "label": "string"}}
    ],
    "quote_text": "string (1-2 sentences)",
    "quote_attribution": "string (e.g. '— Author, Source')"
  }},
  "cta": {{
    "heading": "string",
    "subtitle": "string",
    "button_text": "string"
  }}
}}

{message_section}SOURCE TEXT:
{text}
"""


async def extract_carousel_content(
    text: str,
    client: Optional[anthropic.Anthropic] = None,
    message: str = "",
) -> CarouselContent:
    """Call Claude Sonnet to extract structured carousel content from text.

    Args:
        text: Source text to extract insights from.
        client: Optional Anthropic client. Creates one if not provided.
        message: Optional key message to guide content direction.

    Returns:
        CarouselContent with structured slide data.
    """
    if client is None:
        client = anthropic.Anthropic()

    message_section = ""
    if message:
        message_section = f"KEY MESSAGE TO CONVEY:\n{message}\n\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        text=text[:5000],
        message_section=message_section,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0.7,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text

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

    data = json.loads(stripped)
    return CarouselContent.model_validate(data)
