"""URL detection and content resolution for pasted text input.

Detects when pasted text is a single URL and resolves it:
- Generic URLs: scraped via Firecrawl (reuses scraper.py)
- YouTube URLs: summarized via Gemini's video understanding API
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UrlResolveResult:
    """Result from URL content resolution."""

    url: str
    url_type: str  # "youtube" or "generic"
    content: str  # Resolved text content
    title: str
    success: bool
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0


def detect_url(text: str) -> Optional[str]:
    """Return URL if text is a single URL, else None.

    Strips whitespace, checks for single-line text starting with http(s)://.
    """
    stripped = text.strip()
    # Must be single line (no newlines in the meaningful content)
    if "\n" in stripped:
        return None
    # Must start with http:// or https://
    if not re.match(r"^https?://", stripped, re.IGNORECASE):
        return None
    # Basic URL validation — no spaces allowed
    if " " in stripped:
        return None
    return stripped


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube video URL."""
    return bool(
        re.match(
            r"^https?://(www\.)?(youtube\.com/(watch|shorts|live)|youtu\.be/)",
            url,
            re.IGNORECASE,
        )
    )


async def resolve_url(url: str) -> UrlResolveResult:
    """Resolve a URL to text content. Routes to YouTube or generic handler."""
    if is_youtube_url(url):
        return await resolve_youtube_url(url)
    return await resolve_generic_url(url)


async def resolve_generic_url(url: str) -> UrlResolveResult:
    """Scrape a generic URL via Firecrawl (reuses existing scraper)."""
    from .scraper import scrape_article_content

    logger.info("[URL_RESOLVER] Scraping generic URL: %s", url)
    article = await scrape_article_content(url)

    if article.success and article.content:
        return UrlResolveResult(
            url=url,
            url_type="generic",
            content=article.content,
            title=article.title,
            success=True,
        )

    return UrlResolveResult(
        url=url,
        url_type="generic",
        content="",
        title="",
        success=False,
        error=article.error or "Failed to scrape URL",
    )


async def resolve_youtube_url(url: str) -> UrlResolveResult:
    """Summarize a YouTube video using Gemini's video understanding API.

    Uses google-generativeai SDK directly since LiteLLM doesn't support
    file_data for video URLs.
    """
    from ..prompts import render

    logger.info("[URL_RESOLVER] Summarizing YouTube video: %s", url)
    model_name = "gemini-3-flash-preview"

    try:
        import google.generativeai as genai

        prompt = render("youtube_summary")

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            [
                {"file_data": {"file_uri": url, "mime_type": "video/mp4"}},
                prompt,
            ],
        )

        content = response.text.strip()
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0

        # Extract a title from the first line of the summary
        first_line = content.split("\n")[0].strip()
        title = first_line.lstrip("#").strip()[:120]

        # Estimate cost (Gemini 2.5 Flash pricing)
        # ~$0.15/M input, $0.60/M output (text); video tokens are ~$0.15/M
        cost_usd = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000

        logger.info(
            "[URL_RESOLVER] YouTube summary: %d chars, %d+%d tokens",
            len(content),
            input_tokens,
            output_tokens,
        )

        return UrlResolveResult(
            url=url,
            url_type="youtube",
            content=content,
            title=title,
            success=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model_name,
            cost_usd=cost_usd,
        )

    except Exception as e:
        logger.error("[URL_RESOLVER] YouTube resolution failed: %s", e)
        return UrlResolveResult(
            url=url,
            url_type="youtube",
            content="",
            title="",
            success=False,
            error=str(e),
            model=model_name,
        )
