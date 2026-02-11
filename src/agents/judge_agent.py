"""Judge Agent for evaluating and selecting the best content variant.

Uses Claude Opus 4.5 with extended thinking to rigorously
evaluate all generated variants and select the winner.
"""

import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from .base_agent import BaseAgent, UsageData
from .generator_agent import GeneratedVariant


@dataclass
class VariantScore:
    """Detailed scoring for a single variant."""

    variant_id: int
    generator_id: int
    hook_strength: float  # 0-10
    anti_slop: float  # 0-10
    distinctiveness: float  # 0-10
    relevance: float  # 0-10
    persona_fit: float  # 0-10
    weighted_total: float  # 0-10
    notes: str


@dataclass
class JudgmentResult:
    """Result of judging all variants."""

    winner: GeneratedVariant
    winner_score: VariantScore
    winner_reasoning: str
    all_scores: list[VariantScore]
    improvement_notes: Optional[str]
    total_variants_judged: int
    usage: Optional[UsageData] = None


class JudgeAgent(BaseAgent):
    """
    Evaluates and selects the best content variant.

    Uses weighted scoring across 5 criteria:
    1. Hook Strength (30%) - Would first 2 lines stop scrolling?
    2. Anti-Slop (25%) - Any banned words/AI tells?
    3. Distinctiveness (20%) - Does it have a point of view?
    4. Relevance (15%) - Connects news to AFTA value prop?
    5. Persona Fit (10%) - Sounds like intended persona?
    """

    SCORING_WEIGHTS = {
        "hook_strength": 0.30,
        "anti_slop": 0.25,
        "distinctiveness": 0.20,
        "relevance": 0.15,
        "persona_fit": 0.10,
    }

    def __init__(
        self,
        client: anthropic.Anthropic,
        anti_slop_rules: str,
        explanatory_mode: bool = False,
        **kwargs,
    ):
        """
        Initialize judge agent.

        Args:
            client: Anthropic API client
            anti_slop_rules: Anti-slop rules for reference
            explanatory_mode: If True, use explanatory judge prompt
        """
        super().__init__(client, **kwargs)
        self.anti_slop_rules = anti_slop_rules
        self.explanatory_mode = explanatory_mode

    async def execute(
        self,
        variants: list[GeneratedVariant],
        news_context: str,
    ) -> JudgmentResult:
        """
        Judge all variants and select the winner.

        Args:
            variants: All generated variants to judge
            news_context: News article context for relevance scoring

        Returns:
            JudgmentResult with winner and all scores
        """
        if not variants:
            raise ValueError("No variants to judge")

        prompt = self._build_prompt(variants, news_context)

        response = self._create_message(prompt)
        usage = self._extract_usage(response)
        result = self._parse_judgment(response, variants)
        result.usage = usage

        return result

    def _build_prompt(
        self,
        variants: list[GeneratedVariant],
        news_context: str,
    ) -> str:
        """Build the complete judge prompt."""
        from ..prompts import render

        variants_text = ""
        for i, v in enumerate(variants):
            variants_text += f"""
=== VARIANT {i + 1} ===
Persona: {v.persona}
Generator: {v.generator_id}
Hook Type: {v.hook_type}
Structure: {v.structure_used}

CONTENT:
{v.content}

"""

        template = "judge_explanatory" if self.explanatory_mode else "judge"
        return render(
            template,
            anti_slop_rules=self.anti_slop_rules,
            news_context=news_context,
            num_variants=str(len(variants)),
            variants_text=variants_text,
        )

    def _parse_judgment(
        self,
        response: anthropic.types.Message,
        variants: list[GeneratedVariant],
    ) -> JudgmentResult:
        """Parse response into JudgmentResult."""
        json_data = self._extract_json(response)

        if not json_data or not isinstance(json_data, dict):
            # Fallback: return first variant as winner
            return self._fallback_result(variants)

        try:
            all_scores = []
            for score_data in json_data.get("all_scores", []):
                # Calculate weighted total if not provided
                weighted = score_data.get("weighted_total")
                if not weighted:
                    weighted = (
                        score_data.get("hook_strength", 5) * 0.30
                        + score_data.get("anti_slop", 5) * 0.25
                        + score_data.get("distinctiveness", 5) * 0.20
                        + score_data.get("relevance", 5) * 0.15
                        + score_data.get("persona_fit", 5) * 0.10
                    )

                all_scores.append(
                    VariantScore(
                        variant_id=score_data.get("variant_id", 0),
                        generator_id=score_data.get("generator_id", 0),
                        hook_strength=score_data.get("hook_strength", 5),
                        anti_slop=score_data.get("anti_slop", 5),
                        distinctiveness=score_data.get("distinctiveness", 5),
                        relevance=score_data.get("relevance", 5),
                        persona_fit=score_data.get("persona_fit", 5),
                        weighted_total=weighted,
                        notes=score_data.get("notes", ""),
                    )
                )

            winner_index = json_data.get("winner_index", 0)

            # Ensure winner_index is valid
            if winner_index >= len(variants):
                winner_index = 0

            winner_score = all_scores[winner_index] if all_scores else None

            return JudgmentResult(
                winner=variants[winner_index],
                winner_score=winner_score,
                winner_reasoning=json_data.get("winner_reasoning", ""),
                all_scores=all_scores,
                improvement_notes=json_data.get("improvement_notes"),
                total_variants_judged=len(variants),
            )

        except (KeyError, IndexError, TypeError):
            return self._fallback_result(variants)

    def _fallback_result(self, variants: list[GeneratedVariant]) -> JudgmentResult:
        """Create fallback result when parsing fails."""
        winner = variants[0]
        return JudgmentResult(
            winner=winner,
            winner_score=VariantScore(
                variant_id=0,
                generator_id=winner.generator_id,
                hook_strength=5,
                anti_slop=5,
                distinctiveness=5,
                relevance=5,
                persona_fit=5,
                weighted_total=5.0,
                notes="Fallback selection (parsing failed)",
            ),
            winner_reasoning="Selected first variant as fallback due to parsing error",
            all_scores=[],
            improvement_notes=None,
            total_variants_judged=len(variants),
        )

    def execute_sync(
        self,
        variants: list[GeneratedVariant],
        news_context: str,
    ) -> JudgmentResult:
        """Synchronous wrapper for execute()."""
        import asyncio

        return asyncio.run(self.execute(variants, news_context))
