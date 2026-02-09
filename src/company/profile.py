"""Company profile generation and management.

Provides CompanyContext dataclass for representing target company information,
and functions to load defaults or generate profiles from website URLs.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CompanyContext:
    """Company context for content generation and news filtering."""

    name: str
    tagline: str
    core_offering: str
    differentiator: str
    target_audience: list[str] = field(default_factory=list)
    key_services: list[str] = field(default_factory=list)
    proof_points: list[str] = field(default_factory=list)
    pain_points_solved: list[str] = field(default_factory=list)
    industry_keywords: list[str] = field(default_factory=list)

    def to_filter_prompt(self) -> str:
        """Format context for news filtering prompt."""
        icps = "\n".join(f"{i+1}. {icp}" for i, icp in enumerate(self.target_audience))
        pains = "\n".join(f"- {p}" for p in self.pain_points_solved)

        return f"""{self.name}: {self.tagline}
- {self.core_offering}
- Differentiator: {self.differentiator}

Target ICPs (Ideal Customer Profiles):
{icps}

Key pain points we solve:
{pains}
"""

    def to_generator_prompt(self) -> str:
        """Format context for generator prompts."""
        return f"""Company: {self.name}
Tagline: {self.tagline}
Core Offering: {self.core_offering}
Differentiator: {self.differentiator}
Target Audience: {', '.join(self.target_audience)}
Key Services: {', '.join(self.key_services)}
Proof Points: {', '.join(self.proof_points)}
"""

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "tagline": self.tagline,
            "core_offering": self.core_offering,
            "differentiator": self.differentiator,
            "target_audience": self.target_audience,
            "key_services": self.key_services,
            "proof_points": self.proof_points,
            "pain_points_solved": self.pain_points_solved,
            "industry_keywords": self.industry_keywords,
        }


@dataclass
class CompanyProfileResult:
    """Result from company profile generation."""

    context: CompanyContext
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cached: bool = False


def load_default_context() -> CompanyContext:
    """
    Load the default company context from YAML config.

    Returns:
        CompanyContext with default AFTA configuration
    """
    config_path = Path(__file__).parent.parent / "config" / "default_company.yaml"

    if not config_path.exists():
        logger.warning("Default company config not found, using hardcoded fallback")
        return CompanyContext(
            name="AFTA Systems",
            tagline="AI Automation for E-commerce",
            core_offering="Business process discovery + production-ready n8n automation",
            differentiator="We analyze your business first, then automate. No DIY fumbling.",
            target_audience=[
                "DIY Automation Survivors - tried Zapier/Make.com, failed, need expert help",
                "Struggling E-commerce Operators - drowning in manual tasks, 3+ hours/day wasted",
                "Growing E-commerce Businesses - ready to scale, need infrastructure",
            ],
            key_services=[
                "Order processing automation",
                "Inventory management",
                "Customer support automation",
                "Marketing campaign automation",
            ],
            proof_points=[
                "2-4 weeks to production",
                "No technical knowledge required from client",
                "n8n expertise (not generic Zapier)",
            ],
            pain_points_solved=[
                "Manual data entry eating time",
                "Inventory sync failures",
                "Customer response delays",
                "Marketing campaign management overhead",
            ],
            industry_keywords=[
                "e-commerce",
                "automation",
                "n8n",
                "inventory",
                "order processing",
            ],
        )

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return CompanyContext(
        name=data.get("name", ""),
        tagline=data.get("tagline", ""),
        core_offering=data.get("core_offering", ""),
        differentiator=data.get("differentiator", ""),
        target_audience=data.get("target_audience", []),
        key_services=data.get("key_services", []),
        proof_points=data.get("proof_points", []),
        pain_points_solved=data.get("pain_points_solved", []),
        industry_keywords=data.get("industry_keywords", []),
    )


async def scrape_website_content(url: str) -> Optional[str]:
    """
    Scrape website content using Firecrawl.

    Args:
        url: Website URL to scrape

    Returns:
        Markdown content of the website, or None if failed
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.error("FIRECRAWL_API_KEY not set in environment")
        raise ValueError("FIRECRAWL_API_KEY environment variable is required")

    try:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(url, params={"formats": ["markdown"]})

        if result and isinstance(result, dict):
            return result.get("markdown", result.get("content", ""))
        return str(result) if result else None

    except ImportError:
        logger.error("firecrawl-py not installed. Run: pip install firecrawl-py")
        raise
    except Exception as e:
        logger.error("Firecrawl scrape failed for %s: %s", url, e)
        raise


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from response text."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown blocks
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\{[\s\S]*\}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                json_str = match.group(1) if "```" in pattern else match.group(0)
                return json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                continue

    return None


async def generate_company_profile(
    url: str,
    model: str = "gemini/gemini-3-flash-preview",
) -> CompanyProfileResult:
    """
    Generate a company profile from website URL using Firecrawl + AI.

    Args:
        url: Website URL to analyze
        model: LiteLLM model identifier for profile generation

    Returns:
        CompanyProfileResult with structured company context
    """
    from ..utils.llm_client import get_completion_async
    from ..utils.cost_tracker import extract_usage_from_litellm_response

    # Step 1: Scrape website content
    logger.info("[PROFILE] Scraping %s with Firecrawl...", url)
    content = await scrape_website_content(url)

    if not content:
        raise ValueError(f"Could not scrape content from {url}")

    # Truncate to reasonable size for prompt
    content = content[:12000]
    logger.info("[PROFILE] Got %d chars of content, generating profile...", len(content))

    # Step 2: Generate structured profile using AI
    from ..prompts import render
    prompt = render("company_profile", content=content)

    response_text, response = await get_completion_async(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.3,
        return_full_response=True,
    )

    # Extract usage
    input_tokens, output_tokens, _ = extract_usage_from_litellm_response(response)

    # Parse response
    data = _extract_json(response_text)

    if not data:
        logger.error("[PROFILE] Failed to parse JSON from response: %s", response_text[:500])
        raise ValueError("Failed to parse company profile from AI response")

    logger.info("[PROFILE] Generated profile for %s", data.get("name", "unknown"))

    return CompanyProfileResult(
        context=CompanyContext(
            name=data.get("name", ""),
            tagline=data.get("tagline", ""),
            core_offering=data.get("core_offering", ""),
            differentiator=data.get("differentiator", ""),
            target_audience=data.get("target_audience", []),
            key_services=data.get("key_services", []),
            proof_points=data.get("proof_points", []),
            pain_points_solved=data.get("pain_points_solved", []),
            industry_keywords=data.get("industry_keywords", []),
        ),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )
