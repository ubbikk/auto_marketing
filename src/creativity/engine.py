"""Creativity Engine for generating varied prompt contexts.

Handles:
- Semi-random prompt mutations for variability
- Hook pattern selection (weighted random)
- Framework selection
- Few-shot example selection
- Style reference injection
- Wildcard constraint injection
"""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CreativityContext:
    """Context passed to generators for creative variation."""

    persona: str
    hook_pattern: str
    hook_description: str
    hook_templates: list[str]
    framework: str
    framework_description: str
    framework_structure: list[str]
    few_shot_examples: list[str]
    style_reference: Optional[str]
    wildcard: Optional[str]
    content_angle: str
    mutation_seed: int
    anti_slop_rules: str


@dataclass
class CreativityConfig:
    """Loaded creativity configuration."""

    hook_patterns: dict
    frameworks: list[dict]
    few_shot_settings: dict
    style_references: dict
    wildcards: list[str]
    content_angles: dict


class CreativityEngine:
    """
    Generates varied creativity contexts for content generation.

    Each call to generate_context() produces a unique combination of:
    - Hook pattern (weighted random selection)
    - Framework (weighted random selection)
    - Few-shot examples (random selection from persona's library)
    - Optional style reference
    - Optional wildcard constraint

    This ensures diversity across generators while maintaining quality constraints.
    """

    def __init__(self, config_path: Path, data_dir: Path, anti_slop_rules: str):
        """Initialize creativity engine with configuration."""
        self.data_dir = data_dir
        self.anti_slop_rules = anti_slop_rules

        with open(config_path) as f:
            raw_config = yaml.safe_load(f)["creativity_engine"]

        self.config = CreativityConfig(
            hook_patterns=raw_config["hook_patterns"],
            frameworks=raw_config["frameworks"],
            few_shot_settings=raw_config["few_shot"],
            style_references=raw_config["style_references"],
            wildcards=raw_config["wildcards"],
            content_angles=raw_config["content_angles"],
        )

        self.examples_cache: dict[str, list[str]] = {}
        self._load_examples()

    def _load_examples(self) -> None:
        """Load few-shot examples from data directory."""
        examples_dir = self.data_dir / "examples"
        if not examples_dir.exists():
            return

        for persona_dir in examples_dir.iterdir():
            if persona_dir.is_dir():
                persona_name = persona_dir.name
                good_dir = persona_dir / "good"
                if good_dir.exists():
                    examples = []
                    for example_file in good_dir.glob("*.md"):
                        with open(example_file) as f:
                            examples.append(f.read().strip())
                    if examples:
                        self.examples_cache[persona_name] = examples

    def generate_context(
        self,
        persona: str,
        seed: Optional[int] = None,
    ) -> CreativityContext:
        """
        Generate a creativity context with semi-random mutations.

        Args:
            persona: The persona name (professional, witty, ai_meta)
            seed: Optional seed for reproducibility

        Returns:
            CreativityContext with all randomized elements
        """
        if seed is not None:
            random.seed(seed)
        else:
            seed = random.randint(0, 999999)
            random.seed(seed)

        # Select hook pattern (weighted random)
        hook_name, hook_data = self._select_hook()

        # Select framework (weighted random)
        framework = self._select_framework()

        # Select few-shot examples
        few_shot = self._select_few_shot(persona)

        # Select optional style reference
        style_ref = self._select_style_reference(persona)

        # Select optional wildcard
        wildcard = self._select_wildcard()

        # Select content angle
        angle = self._select_content_angle()

        return CreativityContext(
            persona=persona,
            hook_pattern=hook_name,
            hook_description=hook_data["description"],
            hook_templates=hook_data.get("templates", []),
            framework=framework["name"],
            framework_description=framework["description"],
            framework_structure=framework.get("structure", []),
            few_shot_examples=few_shot,
            style_reference=style_ref,
            wildcard=wildcard,
            content_angle=angle,
            mutation_seed=seed,
            anti_slop_rules=self.anti_slop_rules,
        )

    def _select_hook(self) -> tuple[str, dict]:
        """Select hook pattern using weighted random selection."""
        hooks = self.config.hook_patterns
        names = list(hooks.keys())
        weights = [hooks[name]["weight"] for name in names]

        selected = random.choices(names, weights=weights, k=1)[0]
        return selected, hooks[selected]

    def _select_framework(self) -> dict:
        """Select framework using weighted random selection."""
        frameworks = self.config.frameworks
        weights = [f["weight"] for f in frameworks]

        return random.choices(frameworks, weights=weights, k=1)[0]

    def _select_few_shot(self, persona: str) -> list[str]:
        """Select few-shot examples for the given persona."""
        num_examples = self.config.few_shot_settings["num_examples"]

        examples = self.examples_cache.get(persona, [])
        if not examples:
            return []

        if len(examples) <= num_examples:
            return examples

        return random.sample(examples, num_examples)

    def _select_style_reference(self, persona: str) -> Optional[str]:
        """Select an optional style reference for the persona."""
        if not self.config.style_references.get("enabled", False):
            return None

        # 50% chance to include a style reference
        if random.random() > 0.5:
            return None

        authors = self.config.style_references.get("authors", [])
        valid_authors = [a for a in authors if persona in a.get("use_for", [])]

        if not valid_authors:
            return None

        author = random.choice(valid_authors)
        return f"Write with influence from {author['name']}: {author['style']}"

    def _select_wildcard(self) -> Optional[str]:
        """Select an optional wildcard constraint."""
        # 40% chance to include a wildcard
        if random.random() > 0.4:
            return None

        return random.choice(self.config.wildcards)

    def _select_content_angle(self) -> str:
        """Select content angle using weighted random selection."""
        angles = self.config.content_angles
        names = list(angles.keys())
        weights = [angles[name]["weight"] for name in names]

        selected = random.choices(names, weights=weights, k=1)[0]
        return angles[selected]["key_message"]

    def get_all_personas(self) -> list[str]:
        """Return list of all available personas."""
        return list(self.examples_cache.keys()) or ["professional", "witty", "ai_meta"]
