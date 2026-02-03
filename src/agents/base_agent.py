"""Base agent class for Claude Opus 4.5 with extended thinking.

All agents inherit from this class to get consistent API access
with the effort parameter for maximum quality.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

import anthropic


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
        system_prompt: str,
        user_prompt: str,
        temperature: float = 1.0,
    ) -> anthropic.types.Message:
        """
        Create a message using Claude Opus 4.5 with effort parameter.

        The effort parameter controls the depth of extended thinking:
        - "high": Maximum reasoning depth (default, equivalent to no setting)
        - "medium": Balanced reasoning
        - "low": Faster responses, less reasoning

        Args:
            system_prompt: System instructions
            user_prompt: User message content
            temperature: Sampling temperature

        Returns:
            Anthropic Message response
        """
        return self.client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
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

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute the agent's primary function.

        Must be implemented by all subclasses.
        """
        pass
