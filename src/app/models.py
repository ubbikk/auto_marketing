"""Pydantic request/response models for the web API."""

from pydantic import BaseModel, field_validator
from typing import Optional


class StepCostData(BaseModel):
    """Cost data for a single pipeline step."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    call_count: int


class CostBreakdown(BaseModel):
    """Cost breakdown for pipeline execution."""

    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    steps: dict[str, StepCostData] = {}


class CompanyProfile(BaseModel):
    """Company profile for content generation."""

    name: str
    tagline: str
    core_offering: str
    differentiator: str
    target_audience: list[str] = []
    key_services: list[str] = []
    proof_points: list[str] = []
    pain_points_solved: list[str] = []
    industry_keywords: list[str] = []


class CompanyProfileRequest(BaseModel):
    """Request to generate a company profile from URL."""

    url: str


class CompanyProfileResponse(BaseModel):
    """Response with generated company profile."""

    profile: CompanyProfile
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0


class GenerateRequest(BaseModel):
    """Request body for the /api/generate endpoint."""

    target_url: str
    message: str = ""
    source_text: str = "auto"
    persona: str = "professional"
    num_generators: int = 5
    generation_model: str = "gemini/gemini-3-pro-preview"
    auto_summarize: bool = True
    company_profile: Optional[CompanyProfile] = None

    @field_validator("num_generators")
    @classmethod
    def validate_num_generators(cls, v: int) -> int:
        if not 3 <= v <= 10:
            raise ValueError("num_generators must be between 3 and 10")
        return v


class VariantData(BaseModel):
    """Simplified variant data for API response."""

    content: str
    hook_type: str
    structure_used: str
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
    carousel_html: str
    carousel_id: str
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
    costs: Optional[CostBreakdown] = None


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


class ModelInfo(BaseModel):
    """Model info for the model selector."""

    id: str
    name: str
    provider: str


# Auth Models


class FirebaseAuthRequest(BaseModel):
    """Request body for Firebase authentication."""

    idToken: str


class AuthResponse(BaseModel):
    """Response for authentication endpoints."""

    success: bool
    redirect: Optional[str] = None
    error: Optional[str] = None
    user: Optional[dict] = None


class UserInfo(BaseModel):
    """User info for authenticated responses."""

    name: str
    email: str
    photo_url: Optional[str] = None
