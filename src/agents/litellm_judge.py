"""LiteLLM-based Judge Agent for non-Anthropic models.

Uses LiteLLM to support Gemini and other models for variant judging.
"""

import json
import logging
import re
from typing import Optional

from ..creativity.engine import CreativityContext
from ..utils.llm_client import get_completion_async
from ..utils.cost_tracker import extract_usage_from_litellm_response
from .base_agent import UsageData
from .generator_agent import GeneratedVariant
from .judge_agent import JudgmentResult, VariantScore

logger = logging.getLogger(__name__)


class LiteLLMJudgeAgent:
    """
    Judge agent using LiteLLM for Gemini and other non-Anthropic models.

    Provides the same interface as JudgeAgent but uses LiteLLM for API calls.
    """

    def __init__(
        self,
        model_id: str,
        anti_slop_rules: str,
        max_tokens: int = 16384,
    ):
        self.model_id = model_id
        self.anti_slop_rules = anti_slop_rules
        self.max_tokens = max_tokens

    async def execute(
        self,
        variants: list[GeneratedVariant],
        news_context: str,
    ) -> JudgmentResult:
        if not variants:
            raise ValueError("No variants to judge")

        prompt = self._build_prompt(variants, news_context)

        logger.info("[LITELLM_JUDGE] Calling %s with %d variants...", self.model_id, len(variants))

        try:
            response_text, response = await get_completion_async(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=1.0,
                return_full_response=True,
            )

            logger.info(
                "[LITELLM_JUDGE] Got response (%d chars)",
                len(response_text) if response_text else 0,
            )

            result = self._parse_judgment(response_text, variants)

            # Extract usage
            input_tokens, output_tokens, _ = extract_usage_from_litellm_response(response)
            result.usage = UsageData(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model_id,
            )

            return result

        except Exception as e:
            logger.error("[LITELLM_JUDGE] Failed: %s", str(e))
            raise

    def _build_prompt(
        self,
        variants: list[GeneratedVariant],
        news_context: str,
    ) -> str:
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

        return render(
            "judge",
            anti_slop_rules=self.anti_slop_rules,
            news_context=news_context,
            num_variants=str(len(variants)),
            variants_text=variants_text,
        )

    def _parse_judgment(
        self,
        response_text: str,
        variants: list[GeneratedVariant],
    ) -> JudgmentResult:
        json_data = self._extract_json(response_text)

        if not json_data or not isinstance(json_data, dict):
            return self._fallback_result(variants)

        try:
            all_scores = []
            for score_data in json_data.get("all_scores", []):
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

    def _extract_json(self, text: str) -> Optional[dict | list]:
        if not text:
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
            r"\{[\s\S]*\}",
            r"\[[\s\S]*\]",
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
