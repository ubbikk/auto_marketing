"""Batch XML filtering for news articles using LiteLLM.

Compiles all articles into XML format and makes a single API call
to filter them, dramatically reducing latency compared to sequential calls.

Performance:
- Before: 50 articles = 50 API calls = ~100 seconds
- After: 50 articles = 1 API call = ~3-5 seconds
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from typing import TYPE_CHECKING

from ..config.settings import settings
from ..utils.llm_client import get_completion_async
from ..utils.cost_tracker import extract_usage_from_litellm_response
from .models import FilteredNewsItem, NewsArticle

if TYPE_CHECKING:
    from ..company.profile import CompanyContext

logger = logging.getLogger(__name__)


@dataclass
class BatchFilterResult:
    """Result from batch filtering including articles and usage data."""

    articles: list[FilteredNewsItem]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

class BatchNewsFilter:
    """
    Batch filters news articles using XML compilation and single API call.

    Instead of N sequential calls (one per article), this compiles all
    articles into XML and makes ONE call to get all relevance scores.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        relevance_threshold: float = 0.6,
        company_context: Optional["CompanyContext"] = None,
    ):
        """
        Initialize batch filter.

        Args:
            model_id: LiteLLM model identifier (default: settings.filter_model)
            relevance_threshold: Minimum relevance score to keep (0.0-1.0)
            company_context: Company context for relevance filtering (default: AFTA)
        """
        self.model_id = model_id or settings.filter_model
        self.relevance_threshold = relevance_threshold

        # Load default context if not provided
        if company_context is None:
            from ..company.profile import load_default_context

            self.company_context = load_default_context()
        else:
            self.company_context = company_context

    def _compile_articles_to_xml(self, articles: list[NewsArticle]) -> str:
        """Compile articles into XML format for batch processing."""
        xml_parts = ["<articles>"]

        for i, article in enumerate(articles):
            # Escape XML special characters
            title = self._escape_xml(article.title)
            summary = self._escape_xml(article.summary[:600])
            source = self._escape_xml(article.source)

            xml_parts.append(
                f"""  <article id="{i}">
    <title>{title}</title>
    <summary>{summary}</summary>
    <source>{source}</source>
  </article>"""
            )

        xml_parts.append("</articles>")
        return "\n".join(xml_parts)

    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    async def filter_articles(
        self,
        articles: list[NewsArticle],
        max_results: int = 5,
    ) -> BatchFilterResult:
        """
        Filter articles for relevance to target company using batch XML approach.

        Args:
            articles: Raw articles to filter
            max_results: Maximum number of results to return

        Returns:
            BatchFilterResult with top N most relevant articles and usage data
        """
        if not articles:
            return BatchFilterResult(articles=[], model=self.model_id)

        # Compile all articles into XML
        articles_xml = self._compile_articles_to_xml(articles)

        # Get company context for filtering
        company_name = self.company_context.name
        company_filter_context = self.company_context.to_filter_prompt()

        # Build prompt for batch evaluation
        prompt = f"""Evaluate these news articles for {company_name}'s LinkedIn content.

{company_filter_context}

{articles_xml}

TASK: For each article, determine if it can be connected to {company_name}'s messaging and audience.

Consider for each:
- Can we tie this to the company's core themes and offerings?
- Does it relate to the target audience's pain points?
- Can we offer a unique perspective or contrarian take?
- Would the target ICPs find this relevant to their problems?

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "relevant_articles": [
        {{
            "id": <article_id_number>,
            "relevance_score": <0.0-1.0>,
            "relevance_reason": "Brief explanation",
            "suggested_angle": "How to frame for {company_name}'s audience",
            "company_connection": "Specific tie-in to {company_name}'s services",
            "target_icp": "One of the target audience segments"
        }}
    ]
}}

Only include articles with relevance_score >= {self.relevance_threshold}.
Sort by relevance_score descending.
Return at most {max_results * 2} articles (we'll pick the top {max_results}).
"""

        try:
            logger.info(
                "[BATCH_FILTER] Sending %d articles to %s...",
                len(articles),
                self.model_id,
            )
            response_text, response = await get_completion_async(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3,
                return_full_response=True,
            )

            # Extract usage data
            input_tokens, output_tokens, _ = extract_usage_from_litellm_response(
                response
            )

            # Parse JSON response
            data = self._extract_json(response_text)

            if not data or "relevant_articles" not in data:
                logger.warning("[BATCH_FILTER] No relevant_articles in response")
                return BatchFilterResult(
                    articles=[],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=self.model_id,
                )

            # Convert to FilteredNewsItem objects
            filtered = []
            for item in data["relevant_articles"]:
                article_id = item.get("id")
                if article_id is None or not (0 <= article_id < len(articles)):
                    continue

                score = float(item.get("relevance_score", 0))
                if score < self.relevance_threshold:
                    continue

                filtered.append(
                    FilteredNewsItem(
                        article=articles[article_id],
                        relevance_score=score,
                        relevance_reason=item.get("relevance_reason", ""),
                        suggested_angle=item.get("suggested_angle", ""),
                        company_connection=item.get("company_connection", ""),
                        target_icp=item.get("target_icp", ""),
                    )
                )

            # Sort and limit (model should already do this, but ensure)
            filtered.sort(key=lambda x: x.relevance_score, reverse=True)
            logger.info(
                "[BATCH_FILTER] Found %d relevant articles (threshold=%.1f)",
                len(filtered),
                self.relevance_threshold,
            )
            return BatchFilterResult(
                articles=filtered[:max_results],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model_id,
            )

        except Exception as e:
            logger.error("[BATCH_FILTER] Error: %s", e)
            return BatchFilterResult(articles=[], model=self.model_id)

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from response text."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown blocks
        patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
            r"\{[\s\S]*\}",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if "```" in pattern else match.group(0)
                    return json.loads(json_str)
                except (json.JSONDecodeError, IndexError):
                    continue

        return None

    def filter_sync(
        self,
        articles: list[NewsArticle],
        max_results: int = 5,
    ) -> BatchFilterResult:
        """Synchronous wrapper for filter_articles()."""
        import asyncio

        return asyncio.run(self.filter_articles(articles, max_results))
