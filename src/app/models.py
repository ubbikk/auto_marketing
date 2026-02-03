"""Pydantic request/response models for the web API."""

from pydantic import BaseModel
from typing import Optional


class GenerateRequest(BaseModel):
    """Request body for the /api/generate endpoint."""

    target_url: str
    message: str = ""
    source_text: str = "auto"
    persona: str = "professional"


class VariantData(BaseModel):
    """Simplified variant data for API response."""

    content: str
    hook_type: str
    framework_used: str
    persona: str
    what_makes_it_different: str


class ScoreData(BaseModel):
    """Score breakdown for a variant."""

    hook_strength: float
    anti_slop: float
    distinctiveness: float
    relevance: float
    persona_fit: float
    weighted_total: float
    notes: str


class GenerateResponse(BaseModel):
    """Response body for the /api/generate endpoint."""

    winning_post: str
    carousel_pdf_url: str
    persona_used: str
    source_title: str
    source_summary: str
    score: Optional[float] = None
    score_breakdown: Optional[ScoreData] = None
    judge_reasoning: str = ""
    improvement_notes: Optional[str] = None
    all_variants: list[VariantData] = []
    stats: dict = {}


class PersonaInfo(BaseModel):
    """Persona info for the persona selector."""

    id: str
    name: str
    description: str
    example_openers: list[str]


class LogoPreview(BaseModel):
    """Response for logo scrape preview."""

    logo_data_url: Optional[str] = None
    domain: str = ""
