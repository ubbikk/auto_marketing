"""OPML parser for extracting RSS feed URLs from OPML files."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FeedInfo:
    """Information about an RSS feed from OPML."""

    xml_url: str
    title: str
    html_url: Optional[str] = None


def parse_opml(opml_path: Path) -> list[FeedInfo]:
    """
    Parse OPML file and extract RSS feed URLs.

    Args:
        opml_path: Path to the OPML file

    Returns:
        List of FeedInfo objects with feed URLs and metadata
    """
    tree = ET.parse(opml_path)
    root = tree.getroot()

    feeds = []

    # Find all outline elements with type="rss"
    for outline in root.iter("outline"):
        if outline.get("type") == "rss":
            xml_url = outline.get("xmlUrl")
            if xml_url:
                feeds.append(
                    FeedInfo(
                        xml_url=xml_url,
                        title=outline.get("title") or outline.get("text", ""),
                        html_url=outline.get("htmlUrl"),
                    )
                )

    return feeds


def load_blog_feeds(project_root: Optional[Path] = None) -> list[str]:
    """
    Load blog RSS feed URLs from the OPML file.

    Args:
        project_root: Project root directory (auto-detected if not provided)

    Returns:
        List of RSS feed URLs
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent

    opml_path = project_root / "docs" / "hn-popular-blogs-2025.opml"

    if not opml_path.exists():
        return []

    feeds = parse_opml(opml_path)
    return [f.xml_url for f in feeds]
