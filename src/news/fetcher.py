"""RSS feed fetching for news aggregation.

Fetches articles from multiple tech and AI news sources,
filtering by recency (default: last 48 hours for news, 14 days for blogs).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import feedparser

from .feed_loader import get_blog_feeds, get_news_feeds
from .models import NewsArticle

logger = logging.getLogger(__name__)


class NewsFetcher:
    """
    Fetches news articles from RSS feeds.

    Supports concurrent fetching from multiple sources and filters
    by publication date. Can fetch from both news feeds (shorter time window)
    and blog feeds (longer time window).
    """

    def __init__(
        self,
        feeds: Optional[list[str]] = None,
        hours_back: int = 48,
        blog_days_back: int = 14,
        quick_mode: bool = False,
        include_blogs: bool = False,
        project_root: Optional[Path] = None,
    ):
        """
        Initialize news fetcher.

        Args:
            feeds: List of RSS feed URLs (default: loaded from feeds.json)
            hours_back: How far back to look for news articles
            blog_days_back: How far back to look for blog posts (days)
            quick_mode: Use minimal feed list for faster testing
            include_blogs: Include blog feeds from feeds.json
            project_root: Project root for locating feeds.json
        """
        if feeds:
            self.feeds = feeds
        elif quick_mode:
            self.feeds = get_news_feeds(quick=True)
        else:
            self.feeds = get_news_feeds()

        self.hours_back = hours_back
        self.blog_hours_back = blog_days_back * 24

        # Load blog feeds if requested
        self.blog_feeds: list[str] = []
        if include_blogs and not quick_mode:
            self.blog_feeds = get_blog_feeds()
            logger.info("[FETCHER] Loaded %d blog feeds", len(self.blog_feeds))

    async def fetch_all(self) -> list[NewsArticle]:
        """
        Fetch articles from all configured feeds concurrently.

        News feeds use the shorter time window (hours_back), while blog feeds
        use the longer time window (blog_hours_back).

        Returns:
            List of NewsArticle sorted by publication date (newest first)
        """
        loop = asyncio.get_event_loop()

        # Create tasks for news feeds (shorter time window)
        news_tasks = [
            loop.run_in_executor(None, self._fetch_feed, url, self.hours_back)
            for url in self.feeds
        ]

        # Create tasks for blog feeds (longer time window)
        blog_tasks = [
            loop.run_in_executor(None, self._fetch_feed, url, self.blog_hours_back)
            for url in self.blog_feeds
        ]

        # Run all in parallel
        all_tasks = news_tasks + blog_tasks
        if all_tasks:
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
        else:
            results = []

        # Collect all articles, skip failed feeds
        articles = []
        successful_feeds = 0
        failed_feeds = 0
        for result in results:
            if isinstance(result, list):
                articles.extend(result)
                successful_feeds += 1
            else:
                failed_feeds += 1

        logger.info(
            "[FETCHER] Fetched %d articles from %d feeds (%d failed)",
            len(articles),
            successful_feeds,
            failed_feeds,
        )

        # Sort by recency
        return sorted(articles, key=lambda x: x.published, reverse=True)

    def _fetch_feed(self, feed_url: str, hours_back: Optional[int] = None) -> list[NewsArticle]:
        """
        Fetch and parse a single RSS feed.

        Args:
            feed_url: URL of the RSS feed
            hours_back: How far back to look for articles (default: self.hours_back)

        Returns:
            List of NewsArticle from the feed
        """
        if hours_back is None:
            hours_back = self.hours_back

        try:
            feed = feedparser.parse(feed_url)

            # Make cutoff timezone-aware
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

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
