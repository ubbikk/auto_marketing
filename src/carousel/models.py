"""Pydantic models for carousel slide content."""

from typing import Literal

from pydantic import BaseModel, Field


class StatItem(BaseModel):
    """A single stat card (e.g. '3x' / 'Faster processing')."""

    value: str = Field(description="Short stat value like '3×', '87%', '14h'")
    label: str = Field(description="Brief label explaining the stat")


class CoverSlide(BaseModel):
    """Slide 1 — attention-grabbing title."""

    title: str = Field(description="Main headline, max ~10 words")
    subtitle: str = Field(description="One-sentence supporting line")
    badge: str = Field(default="E-Commerce", description="Top-right badge text")


class BulletSlide(BaseModel):
    """Slide 2 — three bullet points."""

    heading: str = Field(description="Section heading, 3-6 words")
    badge: str = Field(default="Insight", description="Badge text")
    bullets: list[str] = Field(
        description="Exactly 3 bullet points",
        min_length=3,
        max_length=3,
    )


class NumberedSlide(BaseModel):
    """Slide 3 — three numbered items with title + description."""

    heading: str = Field(description="Section heading, 3-6 words")
    badge: str = Field(default="Framework", description="Badge text")
    items: list[dict[str, str]] = Field(
        description="Exactly 3 items, each with 'title' and 'description' keys",
        min_length=3,
        max_length=3,
    )


class StatsSlide(BaseModel):
    """Slide 4 — three stats + a quote."""

    heading: str = Field(description="Section heading, 3-6 words")
    badge: str = Field(default="Data", description="Badge text")
    stats: list[StatItem] = Field(
        description="Exactly 3 stat items",
        min_length=3,
        max_length=3,
    )
    quote_text: str = Field(description="Short impactful quote (1-2 sentences)")
    quote_attribution: str = Field(description="Who said it, e.g. '— CTO, Acme Corp'")


class CTASlide(BaseModel):
    """Slide 5 — call to action."""

    heading: str = Field(description="CTA headline")
    subtitle: str = Field(description="Supporting line")
    button_text: str = Field(default="Get Started →", description="CTA button label")


class CarouselContent(BaseModel):
    """Full carousel content extracted from source text."""

    cover: CoverSlide
    bullets: BulletSlide
    numbered: NumberedSlide
    stats: StatsSlide
    cta: CTASlide


# --- Explanatory mode carousel models ---


class ExplanatoryContentSlide(BaseModel):
    """A single content slide with flexible type for explanatory carousels."""

    type: Literal["bullet", "numbered", "quote", "stats"]
    heading: str = Field(description="Section heading, 3-6 words")
    badge: str = Field(default="Insight", description="Badge text (one word)")
    # Type-specific fields (all optional; prompt ensures correct ones per type)
    bullets: list[str] = Field(default_factory=list, description="Bullet points (for bullet type)")
    items: list[dict[str, str]] = Field(default_factory=list, description="Numbered items (for numbered type)")
    quote_text: str = Field(default="", description="Quote text (for quote type)")
    quote_attribution: str = Field(default="", description="Quote attribution (for quote type)")
    stats: list[StatItem] = Field(default_factory=list, description="Stat items (for stats type)")


class ExplanatoryClosingSlide(BaseModel):
    """Closing slide with key takeaway and source attribution."""

    takeaway: str = Field(description="One-sentence key takeaway")
    source_title: str = Field(default="", description="Source article/video title")
    source_author: str = Field(default="", description="Author name if known")


class ExplanatoryCarouselContent(BaseModel):
    """Full explanatory carousel content with flexible slide count."""

    cover: CoverSlide  # Reuse existing cover slide model
    slides: list[ExplanatoryContentSlide] = Field(
        description="Content slides (3-8)",
        min_length=1,
        max_length=10,
    )
    closing: ExplanatoryClosingSlide
