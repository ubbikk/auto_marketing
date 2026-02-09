"""Base agent class for Claude Opus 4.5 with extended thinking.

All agents inherit from this class to get consistent API access
with the effort parameter for maximum quality.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import anthropic


@dataclass
class UsageData:
    """Token usage data from an API call."""

    input_tokens: int
    output_tokens: int
    model: str


class BaseAgent(ABC):
    """
    Base class for all agents using Claude Opus 4.5 with extended thinking.

    Uses the effort parameter via beta API for enhanced reasoning quality.
    All subclasses should implement the execute() method.
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        model_id: str = "claude-opus-4-5-20251101",
        effort: str = "high",
        max_tokens: int = 16384,
    ):
        """
        Initialize the base agent.

        Args:
            client: Anthropic API client
            model_id: Model to use (default: claude-opus-4-5-20251101)
            effort: Effort level for extended thinking ("high", "medium", "low")
            max_tokens: Maximum tokens for response
        """
        self.client = client
        self.model_id = model_id
        self.effort = effort
        self.max_tokens = max_tokens

    def _create_message(
        self,
        prompt: str,
        temperature: float = 1.0,
    ) -> anthropic.types.Message:
        """
        Create a message using Claude with the given prompt.

        Args:
            prompt: Full prompt content (sent as user message)
            temperature: Sampling temperature

        Returns:
            Anthropic Message response
        """
        return self.client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

    def _extract_text(self, response: anthropic.types.Message) -> str:
        """Extract text content from response."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    def _extract_json(self, response: anthropic.types.Message) -> Optional[dict | list]:
        """
        Extract and parse JSON from response.

        Handles common cases:
        - Pure JSON response
        - JSON wrapped in markdown code blocks
        - JSON embedded in text

        Returns:
            Parsed JSON as dict/list, or None if parsing fails
        """
        text = self._extract_text(response)

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
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
                    return json.loads(match.group(1) if "```" in pattern else match.group(0))
                except (json.JSONDecodeError, IndexError):
                    continue

        return None

    def _extract_thinking(self, response: anthropic.types.Message) -> Optional[str]:
        """Extract thinking content from response if available."""
        for block in response.content:
            if block.type == "thinking":
                return block.thinking
        return None

    def _extract_usage(self, response: anthropic.types.Message) -> UsageData:
        """Extract token usage from response.

        Args:
            response: Anthropic Message response

        Returns:
            UsageData with token counts and model info
        """
        return UsageData(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model_id,
        )

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute the agent's primary function.

        Must be implemented by all subclasses.
        """
        pass
