"""Website scraper for extracting logo and metadata from target URLs."""

import base64
import io
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image


@dataclass
class WebsiteMetadata:
    """Extracted metadata from a target website."""

    logo_data_url: Optional[str]  # base64 data URL for use in HTML/PDF
    domain: str  # e.g. "example.com"
    brand_color: Optional[str]  # from meta theme-color if available


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


async def scrape_website_metadata(url: str) -> WebsiteMetadata:
    """Fetch a URL and extract logo, domain, and brand color.

    Uses a multi-fallback strategy for logo extraction:
    1. og:image meta tag
    2. apple-touch-icon link
    3. SVG favicon link
    4. Largest icon link
    5. /favicon.ico fallback
    """
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    if domain.startswith("www."):
        domain = domain[4:]
    base_url = f"{parsed.scheme or 'https'}://{parsed.netloc or domain}"

    logo_data_url = None
    brand_color = None

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, headers=_HEADERS
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract brand color
            theme_meta = soup.find("meta", attrs={"name": "theme-color"})
            if theme_meta and theme_meta.get("content"):
                brand_color = theme_meta["content"]

            # Try to find logo URL using fallback chain
            logo_url = _find_logo_url(soup, base_url)

            if logo_url:
                logo_data_url = await _download_as_data_url(client, logo_url)

    except (httpx.HTTPError, Exception):
        pass  # Graceful degradation — no logo is fine

    return WebsiteMetadata(
        logo_data_url=logo_data_url,
        domain=domain,
        brand_color=brand_color,
    )


def _find_logo_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Find the best logo URL from HTML using multi-fallback strategy."""

    # 1. apple-touch-icon (usually high-res, good for logos)
    apple_icon = soup.find("link", rel=lambda r: r and "apple-touch-icon" in r)
    if apple_icon and apple_icon.get("href"):
        return urljoin(base_url, apple_icon["href"])

    # 2. SVG favicon (scales perfectly)
    svg_icon = soup.find("link", rel="icon", type="image/svg+xml")
    if svg_icon and svg_icon.get("href"):
        return urljoin(base_url, svg_icon["href"])

    # 3. Largest icon link by sizes attribute
    icons = soup.find_all("link", rel=lambda r: r and "icon" in r)
    best_icon = None
    best_size = 0
    for icon in icons:
        href = icon.get("href")
        if not href:
            continue
        sizes = icon.get("sizes", "")
        if sizes and "x" in sizes.lower():
            try:
                w = int(sizes.lower().split("x")[0])
                if w > best_size:
                    best_size = w
                    best_icon = href
            except ValueError:
                pass
    if best_icon:
        return urljoin(base_url, best_icon)

    # 4. Any icon link
    if icons:
        for icon in icons:
            href = icon.get("href")
            if href:
                return urljoin(base_url, href)

    # 5. og:image (may be a banner, but better than nothing)
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return urljoin(base_url, og_image["content"])

    # 6. /favicon.ico fallback
    return urljoin(base_url, "/favicon.ico")


async def _download_as_data_url(
    client: httpx.AsyncClient, url: str
) -> Optional[str]:
    """Download an image and convert to base64 data URL."""
    try:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

        # Handle SVG
        if "svg" in content_type or url.endswith(".svg"):
            svg_b64 = base64.b64encode(resp.content).decode()
            return f"data:image/svg+xml;base64,{svg_b64}"

        # Handle ICO — convert to PNG
        if "ico" in content_type or url.endswith(".ico"):
            try:
                img = Image.open(io.BytesIO(resp.content))
                img = img.convert("RGBA")
                # Pick the largest frame
                if hasattr(img, "n_frames") and img.n_frames > 1:
                    best = None
                    best_w = 0
                    for i in range(img.n_frames):
                        img.seek(i)
                        if img.width > best_w:
                            best_w = img.width
                            best = img.copy()
                    if best:
                        img = best
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                png_b64 = base64.b64encode(buf.getvalue()).decode()
                return f"data:image/png;base64,{png_b64}"
            except Exception:
                return None

        # Handle raster images (PNG, JPEG, WEBP, etc.)
        if any(
            t in content_type
            for t in ("png", "jpeg", "jpg", "webp", "gif", "image")
        ):
            try:
                img = Image.open(io.BytesIO(resp.content))
                img = img.convert("RGBA")
                # Resize if too large (keep carousel-friendly)
                if img.width > 512 or img.height > 512:
                    img.thumbnail((512, 512), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                png_b64 = base64.b64encode(buf.getvalue()).decode()
                return f"data:image/png;base64,{png_b64}"
            except Exception:
                return None

    except (httpx.HTTPError, Exception):
        pass

    return None
