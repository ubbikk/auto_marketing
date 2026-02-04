"""Cost tracking utilities for LLM API calls.

Tracks token usage and calculates costs across different providers
using LiteLLM's pricing data.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import litellm

logger = logging.getLogger(__name__)


@dataclass
class StepCost:
    """Cost data for a single pipeline step."""

    step_name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0


@dataclass
class PipelineCosts:
    """Aggregate cost tracking for entire pipeline."""

    steps: dict[str, StepCost] = field(default_factory=dict)

    def add_usage(
        self,
        step_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Add usage from an API call to a step.

        Args:
            step_name: Name of the pipeline step (e.g., "generation", "judge")
            model: Model identifier used for the call
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens
            cost_usd: Cost in USD for this call
        """
        if step_name not in self.steps:
            self.steps[step_name] = StepCost(step_name=step_name, model=model)

        step = self.steps[step_name]
        step.input_tokens += input_tokens
        step.output_tokens += output_tokens
        step.cost_usd += cost_usd
        step.call_count += 1

    def total_cost(self) -> float:
        """Return total cost across all steps."""
        return sum(s.cost_usd for s in self.steps.values())

    def total_tokens(self) -> tuple[int, int]:
        """Return total (input_tokens, output_tokens) across all steps."""
        return (
            sum(s.input_tokens for s in self.steps.values()),
            sum(s.output_tokens for s in self.steps.values()),
        )

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        input_total, output_total = self.total_tokens()
        return {
            "total_cost_usd": round(self.total_cost(), 6),
            "total_input_tokens": input_total,
            "total_output_tokens": output_total,
            "steps": {
                name: {
                    "model": step.model,
                    "input_tokens": step.input_tokens,
                    "output_tokens": step.output_tokens,
                    "cost_usd": round(step.cost_usd, 6),
                    "call_count": step.call_count,
                }
                for name, step in self.steps.items()
            },
        }


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for an API call using LiteLLM pricing.

    Args:
        model: Model identifier (e.g., "claude-opus-4-5-20251101", "gemini/gemini-3-pro")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens

    Returns:
        Cost in USD
    """
    try:
        cost = litellm.completion_cost(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return cost if cost else 0.0
    except Exception as e:
        logger.warning("Failed to calculate cost for model %s: %s", model, e)
        # Fallback pricing (per 1M tokens)
        # Claude Opus 4.5: $15 input, $75 output
        # Claude Sonnet 4: $3 input, $15 output
        if "opus" in model.lower():
            return (input_tokens * 15 + output_tokens * 75) / 1_000_000
        elif "sonnet" in model.lower():
            return (input_tokens * 3 + output_tokens * 15) / 1_000_000
        elif "gemini" in model.lower():
            # Gemini pricing varies; use conservative estimate
            return (input_tokens * 0.5 + output_tokens * 1.5) / 1_000_000
        return 0.0


def extract_usage_from_anthropic_response(
    response: Any, model: str
) -> tuple[int, int, float]:
    """Extract tokens and cost from Anthropic SDK response.

    Args:
        response: Anthropic Message response object
        model: Model identifier for cost calculation

    Returns:
        Tuple of (input_tokens, output_tokens, cost_usd)
    """
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calculate_cost(model, input_tokens, output_tokens)
    return input_tokens, output_tokens, cost


def extract_usage_from_litellm_response(response: Any) -> tuple[int, int, float]:
    """Extract tokens and cost from LiteLLM response object.

    Args:
        response: LiteLLM completion response object

    Returns:
        Tuple of (input_tokens, output_tokens, cost_usd)
    """
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens

    try:
        cost = litellm.completion_cost(completion_response=response)
        cost = cost if cost else 0.0
    except Exception as e:
        logger.warning("Failed to extract cost from LiteLLM response: %s", e)
        # Try manual calculation
        model = getattr(response, "model", "unknown")
        cost = calculate_cost(model, input_tokens, output_tokens)

    return input_tokens, output_tokens, cost
