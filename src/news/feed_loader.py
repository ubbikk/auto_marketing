"""Load feed sources from JSON configuration."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FeedEntry:
    """A feed source from feeds.json."""

    name: str
    xml_url: str
    type: str  # "news" or "blog"
    category: str
    enabled: bool = True
    quick: bool = False
    html_url: Optional[str] = None
    description: Optional[str] = None


def load_feeds(path: Optional[Path] = None) -> list[FeedEntry]:
    """
    Load feed entries from JSON file.

    Args:
        path: Path to feeds.json. Auto-detected if not provided.

    Returns:
        List of enabled FeedEntry objects.
    """
    if path is None:
        path = Path(__file__).parent.parent.parent / "data" / "feeds.json"

    if not path.exists():
        logger.warning("[FEEDS] Feed file not found: %s", path)
        return []

    with open(path) as f:
        data = json.load(f)

    feeds = []
    for entry in data.get("feeds", []):
        feed = FeedEntry(
            name=entry["name"],
            xml_url=entry["xml_url"],
            type=entry.get("type", "news"),
            category=entry.get("category", "tech"),
            enabled=entry.get("enabled", True),
            quick=entry.get("quick", False),
            html_url=entry.get("html_url"),
            description=entry.get("description"),
        )
        if feed.enabled:
            feeds.append(feed)

    logger.info("[FEEDS] Loaded %d enabled feeds from %s", len(feeds), path.name)
    return feeds


def get_news_feeds(quick: bool = False, path: Optional[Path] = None) -> list[str]:
    """
    Get news feed URLs.

    Args:
        quick: If True, return only quick-mode feeds.
        path: Path to feeds.json.

    Returns:
        List of RSS feed URLs for news sources.
    """
    feeds = load_feeds(path)
    if quick:
        return [f.xml_url for f in feeds if f.quick]
    return [f.xml_url for f in feeds if f.type == "news"]


def get_blog_feeds(path: Optional[Path] = None) -> list[str]:
    """
    Get blog feed URLs.

    Args:
        path: Path to feeds.json.

    Returns:
        List of RSS feed URLs for blog sources.
    """
    feeds = load_feeds(path)
    return [f.xml_url for f in feeds if f.type == "blog"]
