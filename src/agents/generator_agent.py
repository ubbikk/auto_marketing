"""Generator Agent for LinkedIn content creation.

Generates multiple post variants for a given source content,
using persona-specific voice and creativity context.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from ..creativity.engine import CreativityContext
from .base_agent import BaseAgent, UsageData


@dataclass
class SourceContent:
    """Generic source content — the unified input for all generators."""

    title: str
    source: str
    summary: str
    suggested_angle: str
    company_connection: str
    target_icp: str
    url: str = ""  # Article URL for scraping full content
    key_insights: list[str] = field(default_factory=list)  # For explanatory mode


@dataclass
class GeneratedVariant:
    """A single generated LinkedIn post variant."""

    content: str
    hook_type: str
    structure_used: str
    persona: str
    generator_id: int
    variant_id: int
    what_makes_it_different: str


@dataclass
class GeneratorResult:
    """Result from generator including variants and usage data."""

    variants: list[GeneratedVariant]
    usage: Optional[UsageData] = None


class GeneratorAgent(BaseAgent):
    """
    Generates LinkedIn post variants using Claude.

    Each generator instance:
    - Has a specific persona assignment
    - Receives a unique creativity context (randomized hooks, examples, etc.)
    - Produces 2-4 variants per invocation
    - Uses extended thinking for quality generation
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        generator_id: int,
        persona_config: dict,
        company_name: str,
        company_profile: str,
        explanatory_mode: bool = False,
        **kwargs,
    ):
        """
        Initialize generator agent.

        Args:
            client: Anthropic API client
            generator_id: Unique ID for this generator
            persona_config: Persona configuration dict
            company_name: Company name for prompt context
            company_profile: Company description for context
            explanatory_mode: If True, use explanatory prompts (no company context)
        """
        super().__init__(client, **kwargs)
        self.generator_id = generator_id
        self.persona = persona_config
        self.company_name = company_name
        self.company_profile = company_profile
        self.explanatory_mode = explanatory_mode

    async def execute(
        self,
        source: SourceContent,
        creativity_ctx: CreativityContext,
        num_variants: int = 3,
    ) -> GeneratorResult:
        """Generate content variants from source content.

        Args:
            source: Source content (from news, pasted text, URL, etc.).
            creativity_ctx: Creativity context with hooks, examples, etc.
            num_variants: Number of variants to generate (2-4).

        Returns:
            GeneratorResult with variants and usage data.
        """
        if self.explanatory_mode:
            from ._prompt_helpers import build_generator_prompt_explanatory
            prompt = build_generator_prompt_explanatory(
                source, self.persona, creativity_ctx, num_variants,
            )
        else:
            from ._prompt_helpers import build_generator_prompt
            prompt = build_generator_prompt(
                source, self.persona, self.company_name, self.company_profile,
                creativity_ctx, num_variants,
            )

        response = self._create_message(prompt)
        variants = self._parse_response(response, creativity_ctx)
        usage = self._extract_usage(response)

        return GeneratorResult(variants=variants, usage=usage)

    def _parse_response(
        self,
        response: anthropic.types.Message,
        ctx: CreativityContext,
    ) -> list[GeneratedVariant]:
        """Parse response into GeneratedVariant objects."""
        json_data = self._extract_json(response)

        if not json_data or not isinstance(json_data, list):
            return []

        variants = []
        for i, item in enumerate(json_data):
            if isinstance(item, dict) and "content" in item:
                variants.append(
                    GeneratedVariant(
                        content=item["content"],
                        hook_type=item.get("hook_type", ctx.hook_pattern),
                        structure_used=ctx.structure,
                        persona=ctx.persona,
                        generator_id=self.generator_id,
                        variant_id=i,
                        what_makes_it_different=item.get("what_makes_it_different", ""),
                    )
                )

        return variants
