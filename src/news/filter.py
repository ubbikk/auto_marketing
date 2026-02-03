"""AI-based relevance filtering for news articles.

Uses Claude to score articles for relevance to AFTA's
target audience and suggest content angles.
"""

import json
from typing import Optional

import anthropic

from .models import FilteredNewsItem, NewsArticle

# Company context for filtering
AFTA_CONTEXT = """
AFTA Systems: E-commerce automation company using n8n.
- Helps SMB e-commerce businesses automate operations
- Services: Order processing, inventory management, customer support, marketing automation
- Differentiator: Business process discovery BEFORE building automation
- Quick delivery: 2-4 weeks to production

Target ICPs (Ideal Customer Profiles):
1. DIY Automation Survivors - tried Zapier/Make.com, failed, need expert help
2. Struggling E-commerce Operators - drowning in manual tasks, 3+ hours/day wasted
3. Growing E-commerce Businesses - ready to scale, need infrastructure

Key pain points we solve:
- Manual data entry eating time
- Inventory sync failures
- Customer response delays
- Marketing campaign management overhead
"""


class NewsFilter:
    """
    Filters news articles for relevance to AFTA's audience.

    Uses Claude to:
    1. Score relevance (0.0 - 1.0)
    2. Suggest content angle
    3. Identify company connection
    4. Map to target ICP
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        model_id: str = "claude-sonnet-4-20250514",  # Use Sonnet for cost efficiency
        relevance_threshold: float = 0.6,
    ):
        """
        Initialize news filter.

        Args:
            client: Anthropic API client
            model_id: Model to use for filtering (Sonnet for efficiency)
            relevance_threshold: Minimum relevance score to keep
        """
        self.client = client
        self.model_id = model_id
        self.relevance_threshold = relevance_threshold

    async def filter_articles(
        self,
        articles: list[NewsArticle],
        max_results: int = 5,
    ) -> list[FilteredNewsItem]:
        """
        Filter articles for relevance to AFTA.

        Args:
            articles: Raw articles to filter
            max_results: Maximum number of results to return

        Returns:
            Top N most relevant articles with context
        """
        if not articles:
            return []

        # Process in batches for efficiency
        filtered = []
        for article in articles:
            scored = await self._score_article(article)
            if scored and scored.relevance_score >= self.relevance_threshold:
                filtered.append(scored)

        # Sort by relevance and return top N
        filtered.sort(key=lambda x: x.relevance_score, reverse=True)
        return filtered[:max_results]

    async def _score_article(self, article: NewsArticle) -> Optional[FilteredNewsItem]:
        """Score a single article for relevance."""
        prompt = f"""
Evaluate this news article for AFTA Systems' LinkedIn content.

{AFTA_CONTEXT}

ARTICLE TO EVALUATE:
Title: {article.title}
Summary: {article.summary[:600]}
Source: {article.source}

TASK: Determine if this news can be connected to AFTA's messaging and audience.

Consider:
- Can we tie this to automation/efficiency themes?
- Does it relate to e-commerce pain points?
- Can we offer a unique perspective or contrarian take?
- Would our ICPs find this relevant to their problems?

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "relevance_score": 0.0-1.0,
    "relevance_reason": "Brief explanation of why relevant or not",
    "suggested_angle": "How to frame this for AFTA's audience",
    "company_connection": "Specific tie-in to AFTA services",
    "target_icp": "DIY Survivor | Struggling Operator | Growing Business"
}}

If not relevant at all, set relevance_score to 0.0.
"""

        try:
            response = self.client.messages.create(
                model=self.model_id,
                max_tokens=500,
                temperature=0.3,  # Lower temp for more consistent scoring
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract and parse JSON response
            text = response.content[0].text
            data = json.loads(text)

            return FilteredNewsItem(
                article=article,
                relevance_score=float(data["relevance_score"]),
                relevance_reason=data["relevance_reason"],
                suggested_angle=data["suggested_angle"],
                company_connection=data["company_connection"],
                target_icp=data["target_icp"],
            )

        except (json.JSONDecodeError, KeyError, IndexError):
            return None

    def filter_sync(
        self,
        articles: list[NewsArticle],
        max_results: int = 5,
    ) -> list[FilteredNewsItem]:
        """Synchronous wrapper for filter_articles()."""
        import asyncio

        return asyncio.run(self.filter_articles(articles, max_results))
