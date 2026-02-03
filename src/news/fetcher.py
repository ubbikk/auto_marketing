"""RSS feed fetching for news aggregation.

Fetches articles from multiple tech and AI news sources,
filtering by recency (default: last 48 hours).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser

from .models import NewsArticle

# AI and Tech News RSS Feeds (from NEWS_SOURCES.md)
AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.wired.com/feed/category/business/topic/artificial-intelligence/latest/rss",
    "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
]

BUSINESS_FEEDS = [
    "https://techcrunch.com/category/startups/feed/",
    "https://hnrss.org/frontpage",
]

# Lighter feed list for faster testing
QUICK_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://hnrss.org/frontpage",
]


class NewsFetcher:
    """
    Fetches news articles from RSS feeds.

    Supports concurrent fetching from multiple sources and filters
    by publication date.
    """

    def __init__(
        self,
        feeds: Optional[list[str]] = None,
        hours_back: int = 48,
        quick_mode: bool = False,
    ):
        """
        Initialize news fetcher.

        Args:
            feeds: List of RSS feed URLs (default: AI + Business feeds)
            hours_back: How far back to look for articles
            quick_mode: Use minimal feed list for faster testing
        """
        if feeds:
            self.feeds = feeds
        elif quick_mode:
            self.feeds = QUICK_FEEDS
        else:
            self.feeds = AI_FEEDS + BUSINESS_FEEDS

        self.hours_back = hours_back

    async def fetch_all(self) -> list[NewsArticle]:
        """
        Fetch articles from all configured feeds concurrently.

        Returns:
            List of NewsArticle sorted by publication date (newest first)
        """
        # Run feed fetching in thread pool since feedparser is synchronous
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, self._fetch_feed, url) for url in self.feeds]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all articles, skip failed feeds
        articles = []
        for result in results:
            if isinstance(result, list):
                articles.extend(result)
            # Log errors but continue with other feeds

        # Sort by recency
        return sorted(articles, key=lambda x: x.published, reverse=True)

    def _fetch_feed(self, feed_url: str) -> list[NewsArticle]:
        """
        Fetch and parse a single RSS feed.

        Args:
            feed_url: URL of the RSS feed

        Returns:
            List of NewsArticle from the feed
        """
        try:
            feed = feedparser.parse(feed_url)

            # Make cutoff timezone-aware
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hours_back)

            articles = []
            for entry in feed.entries:
                published = self._parse_date(entry)

                # Skip articles older than cutoff
                if published and published > cutoff:
                    summary = entry.get("summary", "")
                    # Clean up summary (remove HTML, truncate)
                    summary = self._clean_summary(summary)

                    articles.append(
                        NewsArticle(
                            title=entry.title,
                            link=entry.link,
                            summary=summary,
                            published=published,
                            source=feed.feed.get("title", feed_url),
                        )
                    )

            return articles

        except Exception:
            # Return empty list on feed failure
            return []

    def _parse_date(self, entry: feedparser.FeedParserDict) -> Optional[datetime]:
        """Parse entry date from various RSS formats."""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            # Convert time.struct_time to datetime with UTC timezone
            dt = datetime(*entry.published_parsed[:6])
            return dt.replace(tzinfo=timezone.utc)

        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            dt = datetime(*entry.updated_parsed[:6])
            return dt.replace(tzinfo=timezone.utc)

        return None

    def _clean_summary(self, summary: str, max_length: int = 500) -> str:
        """Clean HTML and truncate summary."""
        import re

        # Remove HTML tags
        clean = re.sub(r"<[^>]+>", "", summary)

        # Remove extra whitespace
        clean = re.sub(r"\s+", " ", clean).strip()

        # Truncate
        if len(clean) > max_length:
            clean = clean[:max_length] + "..."

        return clean

    def fetch_sync(self) -> list[NewsArticle]:
        """Synchronous wrapper for fetch_all()."""
        return asyncio.run(self.fetch_all())
