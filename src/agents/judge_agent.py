"""Judge Agent for evaluating and selecting the best content variant.

Uses Claude Opus 4.5 with extended thinking to rigorously
evaluate all generated variants and select the winner.
"""

import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from .base_agent import BaseAgent
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
        **kwargs,
    ):
        """
        Initialize judge agent.

        Args:
            client: Anthropic API client
            anti_slop_rules: Anti-slop rules for reference
        """
        super().__init__(client, **kwargs)
        self.anti_slop_rules = anti_slop_rules

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

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(variants, news_context)

        response = self._create_message(system_prompt, user_prompt)

        return self._parse_judgment(response, variants)

    def _build_system_prompt(self) -> str:
        """Build system prompt for judging."""
        return f"""You are a ruthless quality judge for LinkedIn content.

Your job: identify the ONE post that would actually make someone stop scrolling.
BE HARSH. Most content is mediocre. Only select a winner if it's genuinely good.

SCORING CRITERIA (weighted):

1. HOOK STRENGTH (30%)
   - Would the first 2 lines make YOU stop scrolling? Be brutally honest.
   - Does it create curiosity or tension?
   - Is there a specific detail that grabs attention?
   - Score 1-3: Generic, forgettable opener
   - Score 4-6: Decent but not compelling
   - Score 7-8: Strong, would make most people pause
   - Score 9-10: Exceptional, impossible to scroll past

2. ANTI-SLOP (25%)
   - Any banned words? (delve, leverage, unlock, etc.)
   - Any AI tells? (em-dash overuse, snappy triads, weak openers)
   - Any engagement bait? ("What do you think?", emoji spam)
   - Score 1-3: Multiple violations
   - Score 4-6: Some AI patterns visible
   - Score 7-8: Clean, sounds human
   - Score 9-10: Distinctively human voice

3. DISTINCTIVENESS (20%)
   - Does this sound like everyone else or is there a point of view?
   - Is there something surprising or contrarian?
   - Would you remember this post tomorrow?
   - Score 1-3: Generic, could be anyone
   - Score 4-6: Some personality but safe
   - Score 7-8: Clear voice and perspective
   - Score 9-10: Memorable, quotable

4. RELEVANCE (15%)
   - Does it connect the news to AFTA's value proposition naturally?
   - Is the company mention earned, not forced?
   - Would the target ICP find this valuable?
   - Score 1-3: Forced connection
   - Score 4-6: Logical but obvious
   - Score 7-8: Natural, insightful connection
   - Score 9-10: Brilliant angle I wouldn't have thought of

5. PERSONA FIT (10%)
   - Does it sound like the intended persona?
   - Is the tone consistent throughout?
   - Score 1-3: Wrong voice entirely
   - Score 4-6: Somewhat matches
   - Score 7-8: Good persona match
   - Score 9-10: Perfect embodiment of persona

{self.anti_slop_rules}

Remember: Your job is to be the human taste filter. Don't be nice. Be right.
"""

    def _build_user_prompt(
        self,
        variants: list[GeneratedVariant],
        news_context: str,
    ) -> str:
        """Build user prompt with all variants."""
        variants_text = ""
        for i, v in enumerate(variants):
            variants_text += f"""
=== VARIANT {i + 1} ===
Persona: {v.persona}
Generator: {v.generator_id}
Hook Type: {v.hook_type}
Framework: {v.framework_used}

CONTENT:
{v.content}

"""

        return f"""
NEWS CONTEXT:
{news_context}

VARIANTS TO JUDGE ({len(variants)} total):
{variants_text}

TASK:
1. Score EVERY variant on all 5 criteria (0-10 each)
2. Calculate weighted total for each
3. Select the winner (highest score)
4. Explain your reasoning for the winner
5. If the winner could be improved, note how

Output ONLY valid JSON (no markdown, no extra text):
{{
  "all_scores": [
    {{
      "variant_id": 0,
      "generator_id": 0,
      "hook_strength": 0,
      "anti_slop": 0,
      "distinctiveness": 0,
      "relevance": 0,
      "persona_fit": 0,
      "weighted_total": 0.0,
      "notes": "specific feedback for this variant"
    }}
  ],
  "winner_index": 0,
  "winner_reasoning": "detailed explanation of why this won",
  "improvement_notes": "optional suggestions to make winner even better"
}}
"""

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
