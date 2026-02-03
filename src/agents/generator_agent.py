"""Generator Agent for LinkedIn content creation.

Generates multiple post variants for a given news item,
using persona-specific voice and creativity context.
"""

import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from ..creativity.engine import CreativityContext
from ..news.models import FilteredNewsItem
from .base_agent import BaseAgent


@dataclass
class SourceContent:
    """Generic source content that both news items and pasted text can populate."""

    title: str
    source: str
    summary: str
    suggested_angle: str
    company_connection: str
    target_icp: str


@dataclass
class GeneratedVariant:
    """A single generated LinkedIn post variant."""

    content: str
    hook_type: str
    framework_used: str
    persona: str
    generator_id: int
    variant_id: int
    what_makes_it_different: str


class GeneratorAgent(BaseAgent):
    """
    Generates LinkedIn post variants using Claude Opus 4.5.

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
        company_profile: str,
        **kwargs,
    ):
        """
        Initialize generator agent.

        Args:
            client: Anthropic API client
            generator_id: Unique ID for this generator
            persona_config: Persona configuration dict
            company_profile: Company description for context
        """
        super().__init__(client, **kwargs)
        self.generator_id = generator_id
        self.persona = persona_config
        self.company_profile = company_profile

    async def execute(
        self,
        news_item: FilteredNewsItem,
        creativity_ctx: CreativityContext,
        num_variants: int = 3,
    ) -> list[GeneratedVariant]:
        """
        Generate content variants for the given news item.

        Args:
            news_item: Filtered news article with AFTA context
            creativity_ctx: Creativity context with hooks, examples, etc.
            num_variants: Number of variants to generate (2-4)

        Returns:
            List of GeneratedVariant
        """
        system_prompt = self._build_system_prompt(creativity_ctx)
        user_prompt = self._build_user_prompt(news_item, creativity_ctx, num_variants)

        response = self._create_message(system_prompt, user_prompt)

        return self._parse_response(response, creativity_ctx)

    def _build_system_prompt(self, ctx: CreativityContext) -> str:
        """Build system prompt with persona and anti-slop rules."""
        persona_name = self.persona.get("name", ctx.persona)
        voice_traits = self.persona.get("voice_traits", [])
        relationship = self.persona.get("relationship_to_reader", "A peer")
        anti_patterns = self.persona.get("anti_patterns", [])
        example_openers = self.persona.get("example_openers", [])

        # Build few-shot section if examples exist
        few_shot_section = ""
        if ctx.few_shot_examples:
            few_shot_section = f"""
FEW-SHOT EXAMPLES (study these, don't copy verbatim):
{chr(10).join(f'---{chr(10)}{ex}{chr(10)}---' for ex in ctx.few_shot_examples)}
"""

        # Build style reference if present
        style_section = ""
        if ctx.style_reference:
            style_section = f"""
STYLE INFLUENCE:
{ctx.style_reference}
"""

        # Build wildcard if present
        wildcard_section = ""
        if ctx.wildcard:
            wildcard_section = f"""
SPECIAL CONSTRAINT FOR THIS GENERATION:
{ctx.wildcard}
"""

        return f"""You are a LinkedIn content creator for AFTA Systems.

COMPANY CONTEXT:
{self.company_profile}

YOUR PERSONA: {persona_name}

Voice traits you MUST embody:
{chr(10).join(f'- {t}' for t in voice_traits)}

Relationship to reader: {relationship}

Things to NEVER do (anti-patterns):
{chr(10).join(f'- {p}' for p in anti_patterns)}

Example openers that capture this voice:
{chr(10).join(f'- "{o}"' for o in example_openers)}

{few_shot_section}
{style_section}
{wildcard_section}

{ctx.anti_slop_rules}

CRITICAL INSTRUCTIONS:
1. First 2 lines are EVERYTHING - that's all that shows before "see more"
2. LinkedIn has NO markdown bold - never use **text** or __text__
3. Use plain URLs only - no [text](url) format
4. Max 2 emojis per post, and only if natural
5. No hashtags (algorithm reads content, not tags)
6. BE SPECIFIC - exact numbers, concrete examples, real scenarios
7. SURPRISE THE READER - say something unexpected or contrarian
8. Each variant must be MEANINGFULLY different, not just word swaps
"""

    async def execute_from_source(
        self,
        source: SourceContent,
        creativity_ctx: CreativityContext,
        num_variants: int = 3,
    ) -> list[GeneratedVariant]:
        """Generate content variants from generic source content.

        Args:
            source: Source content (from pasted text or news).
            creativity_ctx: Creativity context with hooks, examples, etc.
            num_variants: Number of variants to generate (2-4).

        Returns:
            List of GeneratedVariant.
        """
        system_prompt = self._build_system_prompt(creativity_ctx)
        user_prompt = self._build_user_prompt_from_source(
            source, creativity_ctx, num_variants
        )

        response = self._create_message(system_prompt, user_prompt)

        return self._parse_response(response, creativity_ctx)

    def _build_user_prompt_from_source(
        self,
        source: SourceContent,
        ctx: CreativityContext,
        num_variants: int,
    ) -> str:
        """Build user prompt from generic source content."""
        return f"""
SOURCE CONTENT TO REACT TO:
Title: {source.title}
Source: {source.source}
Summary: {source.summary}

ANGLE GUIDANCE:
- Suggested angle: {source.suggested_angle}
- Company connection: {source.company_connection}
- Target audience: {source.target_icp}
- Key message to weave in: {ctx.content_angle}

CREATIVITY PARAMETERS FOR THIS GENERATION:
- Hook pattern to use: {ctx.hook_pattern}
- Hook description: {ctx.hook_description}
- Framework: {ctx.framework} ({ctx.framework_description})
- Framework structure: {' -> '.join(ctx.framework_structure)}

TASK:
Generate {num_variants} DISTINCT LinkedIn post variants.

Requirements:
1. Each post must grab attention in the first 2 lines
2. Each must connect the source content to the company's value proposition naturally
3. Each must embody the {self.persona.get('name', ctx.persona)} persona
4. Each must be meaningfully different from the others
5. NO banned words or phrases (see anti-slop rules)
6. Include at least one specific number or statistic per post
7. Keep each post between 150-300 words

Output ONLY valid JSON array (no markdown blocks, no explanation):
[
  {{
    "content": "The full LinkedIn post text here",
    "hook_type": "{ctx.hook_pattern}",
    "what_makes_it_different": "Brief explanation of unique angle"
  }},
  ...
]
"""

    def _build_user_prompt(
        self,
        news: FilteredNewsItem,
        ctx: CreativityContext,
        num_variants: int,
    ) -> str:
        """Build user prompt with news and generation instructions."""
        return f"""
NEWS TO REACT TO:
Title: {news.article.title}
Source: {news.article.source}
Summary: {news.article.summary}

ANGLE GUIDANCE:
- Suggested angle: {news.suggested_angle}
- Company connection: {news.company_connection}
- Target audience: {news.target_icp}
- Key message to weave in: {ctx.content_angle}

CREATIVITY PARAMETERS FOR THIS GENERATION:
- Hook pattern to use: {ctx.hook_pattern}
- Hook description: {ctx.hook_description}
- Framework: {ctx.framework} ({ctx.framework_description})
- Framework structure: {' -> '.join(ctx.framework_structure)}

TASK:
Generate {num_variants} DISTINCT LinkedIn post variants.

Requirements:
1. Each post must grab attention in the first 2 lines
2. Each must connect the news to AFTA's value proposition naturally
3. Each must embody the {self.persona.get('name', ctx.persona)} persona
4. Each must be meaningfully different from the others
5. NO banned words or phrases (see anti-slop rules)
6. Include at least one specific number or statistic per post
7. Keep each post between 150-300 words

Output ONLY valid JSON array (no markdown blocks, no explanation):
[
  {{
    "content": "The full LinkedIn post text here",
    "hook_type": "{ctx.hook_pattern}",
    "what_makes_it_different": "Brief explanation of unique angle"
  }},
  ...
]
"""

    def _parse_response(
        self,
        response: anthropic.types.Message,
        ctx: CreativityContext,
    ) -> list[GeneratedVariant]:
        """Parse response into GeneratedVariant objects."""
        json_data = self._extract_json(response)

        if not json_data or not isinstance(json_data, list):
            # Return empty list if parsing fails
            return []

        variants = []
        for i, item in enumerate(json_data):
            if isinstance(item, dict) and "content" in item:
                variants.append(
                    GeneratedVariant(
                        content=item["content"],
                        hook_type=item.get("hook_type", ctx.hook_pattern),
                        framework_used=ctx.framework,
                        persona=ctx.persona,
                        generator_id=self.generator_id,
                        variant_id=i,
                        what_makes_it_different=item.get("what_makes_it_different", ""),
                    )
                )

        return variants

    def execute_sync(
        self,
        news_item: FilteredNewsItem,
        creativity_ctx: CreativityContext,
        num_variants: int = 3,
    ) -> list[GeneratedVariant]:
        """Synchronous wrapper for execute()."""
        import asyncio

        return asyncio.run(self.execute(news_item, creativity_ctx, num_variants))
