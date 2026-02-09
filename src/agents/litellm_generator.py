"""LiteLLM-based Generator Agent for non-Anthropic models.

Uses LiteLLM to support Gemini, OpenAI, and other models for content generation.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..creativity.engine import CreativityContext
from ..utils.llm_client import get_completion_async
from ..utils.cost_tracker import extract_usage_from_litellm_response
from .base_agent import UsageData
from .generator_agent import GeneratedVariant, GeneratorResult, SourceContent

logger = logging.getLogger(__name__)


class LiteLLMGeneratorAgent:
    """
    Generator agent using LiteLLM for Gemini and other non-Anthropic models.

    Provides the same interface as GeneratorAgent but uses LiteLLM for API calls.
    """

    def __init__(
        self,
        model_id: str,
        generator_id: int,
        persona_config: dict,
        company_name: str,
        company_profile: str,
        max_tokens: int = 16384,
    ):
        """
        Initialize LiteLLM generator agent.

        Args:
            model_id: LiteLLM model identifier (e.g., "gemini/gemini-3-pro-preview")
            generator_id: Unique ID for this generator
            persona_config: Persona configuration dict
            company_name: Company name for prompt context
            company_profile: Company description for context
            max_tokens: Maximum tokens for response
        """
        self.model_id = model_id
        self.generator_id = generator_id
        self.persona = persona_config
        self.company_name = company_name
        self.company_profile = company_profile
        self.max_tokens = max_tokens

    async def execute(
        self,
        source: SourceContent,
        creativity_ctx: CreativityContext,
        num_variants: int = 3,
    ) -> GeneratorResult:
        """
        Generate content variants from source content.

        Args:
            source: Source content (from news, pasted text, URL, etc.).
            creativity_ctx: Creativity context with hooks, examples, etc.
            num_variants: Number of variants to generate (2-4).

        Returns:
            GeneratorResult with variants and usage data.
        """
        from ._prompt_helpers import build_generator_prompt

        prompt = build_generator_prompt(
            source, self.persona, self.company_name, self.company_profile,
            creativity_ctx, num_variants,
        )

        logger.info(
            "[LITELLM_GEN] Generator %d calling %s...",
            self.generator_id,
            self.model_id,
        )

        try:
            response_text, response = await get_completion_async(
                model=self.model_id,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=1.0,
                return_full_response=True,
            )

            logger.info(
                "[LITELLM_GEN] Generator %d got response (%d chars)",
                self.generator_id,
                len(response_text) if response_text else 0,
            )

            variants = self._parse_response(response_text, creativity_ctx)

            # Extract usage data from LiteLLM response
            input_tokens, output_tokens, _ = extract_usage_from_litellm_response(
                response
            )
            usage = UsageData(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model_id,
            )

            return GeneratorResult(variants=variants, usage=usage)

        except Exception as e:
            logger.error(
                "[LITELLM_GEN] Generator %d failed: %s",
                self.generator_id,
                str(e),
            )
            raise

    def _parse_response(
        self,
        response_text: str,
        ctx: CreativityContext,
    ) -> list[GeneratedVariant]:
        """Parse response into GeneratedVariant objects."""
        json_data = self._extract_json(response_text)

        if not json_data or not isinstance(json_data, list):
            logger.warning(
                "[LITELLM_GEN] Generator %d failed to parse JSON response",
                self.generator_id,
            )
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

        logger.info(
            "[LITELLM_GEN] Generator %d parsed %d variants",
            self.generator_id,
            len(variants),
        )
        return variants

    def _extract_json(self, text: str) -> Optional[dict | list]:
        """Extract and parse JSON from response text."""
        if not text:
            return None

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        json_patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
            r"\[[\s\S]*\]",
            r"\{[\s\S]*\}",
        ]

        for pattern in json_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if "```" in pattern else match.group(0)
                    return json.loads(json_str)
                except (json.JSONDecodeError, IndexError):
                    continue

        return None
