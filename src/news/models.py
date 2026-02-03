"""Data models for news articles and filtered items."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NewsArticle:
    """Raw news article from RSS feed."""

    title: str
    link: str
    summary: str
    published: datetime
    source: str
    full_text: Optional[str] = None


@dataclass
class FilteredNewsItem:
    """News article after relevance filtering with AFTA-specific context."""

    article: NewsArticle
    relevance_score: float  # 0.0 to 1.0
    relevance_reason: str
    suggested_angle: str  # How to connect to AFTA
    company_connection: str  # Specific tie-in to services
    target_icp: str  # Which ICP this appeals to most
