"""Creativity Engine for generating varied prompt contexts.

Handles:
- Semi-random prompt mutations for variability
- Hook pattern selection (weighted random)
- Organic structure selection (replaces formulaic frameworks)
- Few-shot example selection
- Style reference injection with actual samples
- Tone wildcard injection
- Structural break injection (human imperfections)
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
    structure: str
    structure_description: str
    structure_guidance: Optional[str]
    structure_anti_patterns: list[str]
    few_shot_examples: list[str]
    style_reference: Optional[str]
    tone_wildcard: Optional[str]
    structural_break: Optional[str]
    content_angle: str
    mutation_seed: int
    anti_slop_rules: str


@dataclass
class CreativityConfig:
    """Loaded creativity configuration."""

    hook_patterns: dict
    structures: list[dict]
    structure_anti_patterns: list[str]
    few_shot_settings: dict
    style_references: dict
    tone_wildcards: dict
    structural_breaks: dict
    content_angles: dict


class CreativityEngine:
    """
    Generates varied creativity contexts for content generation.

    Each call to generate_context() produces a unique combination of:
    - Hook pattern (weighted random selection)
    - Organic structure (weighted random selection, replaces formulaic frameworks)
    - Few-shot examples (random selection from persona's library)
    - Optional style reference with actual sample text
    - Optional tone wildcard (perspective shift)
    - Optional structural break (human imperfection)

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
            structures=raw_config["structures"],
            structure_anti_patterns=raw_config.get("structure_anti_patterns", []),
            few_shot_settings=raw_config["few_shot"],
            style_references=raw_config["style_references"],
            tone_wildcards=raw_config.get("tone_wildcards", {"probability": 0.4, "options": []}),
            structural_breaks=raw_config.get("structural_breaks", {"probability": 0.3, "options": []}),
            content_angles=raw_config["content_angles"],
        )

        self.examples_cache: dict[str, list[str]] = {}
        self.style_samples_cache: dict[str, str] = {}
        self._load_examples()
        self._load_style_samples()

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

    def _load_style_samples(self) -> None:
        """Load style samples from the sample directory."""
        sample_dir_name = self.config.style_references.get("sample_directory", "data/style_samples")
        # Handle relative path from project root
        if sample_dir_name.startswith("data/"):
            sample_dir = self.data_dir / sample_dir_name.replace("data/", "")
        else:
            sample_dir = Path(sample_dir_name)

        if not sample_dir.exists():
            return

        for author in self.config.style_references.get("authors", []):
            sample_file = author.get("sample_file")
            if sample_file:
                sample_path = sample_dir / sample_file
                if sample_path.exists():
                    with open(sample_path) as f:
                        self.style_samples_cache[author["name"]] = f.read().strip()

    def generate_context(
        self,
        persona: str,
        seed: Optional[int] = None,
    ) -> CreativityContext:
        """
        Generate a creativity context with semi-random mutations.

        Args:
            persona: The persona name (professional, witty, ai_meta, etc.)
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

        # Select organic structure (weighted random)
        structure = self._select_structure()

        # Select few-shot examples
        few_shot = self._select_few_shot(persona)

        # Select optional style reference with sample text
        style_ref = self._select_style_reference(persona)

        # Select optional tone wildcard
        tone_wildcard = self._select_tone_wildcard()

        # Select optional structural break
        structural_break = self._select_structural_break()

        # Select content angle
        angle = self._select_content_angle()

        return CreativityContext(
            persona=persona,
            hook_pattern=hook_name,
            hook_description=hook_data["description"],
            hook_templates=hook_data.get("templates", []),
            structure=structure["name"],
            structure_description=structure["description"],
            structure_guidance=structure.get("guidance"),
            structure_anti_patterns=self.config.structure_anti_patterns,
            few_shot_examples=few_shot,
            style_reference=style_ref,
            tone_wildcard=tone_wildcard,
            structural_break=structural_break,
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

    def _select_structure(self) -> dict:
        """Select organic structure using weighted random selection."""
        structures = self.config.structures
        weights = [s["weight"] for s in structures]

        return random.choices(structures, weights=weights, k=1)[0]

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
        """Select an optional style reference with actual sample text."""
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
        author_name = author["name"]
        style_essence = author.get("style_essence", author.get("style", ""))

        # Try to get actual sample text
        sample_text = self.style_samples_cache.get(author_name, "")

        if sample_text:
            return f"""Write with influence from {author_name}: {style_essence}

Here are actual samples of their writing style:

{sample_text}

Absorb this voice. Don't copy—channel."""
        else:
            # Fallback to essence only if no sample available
            return f"Write with influence from {author_name}: {style_essence}"

    def _select_tone_wildcard(self) -> Optional[str]:
        """Select an optional tone wildcard (perspective shift)."""
        probability = self.config.tone_wildcards.get("probability", 0.4)
        options = self.config.tone_wildcards.get("options", [])

        if not options or random.random() > probability:
            return None

        return random.choice(options)

    def _select_structural_break(self) -> Optional[str]:
        """Select an optional structural break (human imperfection)."""
        probability = self.config.structural_breaks.get("probability", 0.3)
        options = self.config.structural_breaks.get("options", [])

        if not options or random.random() > probability:
            return None

        return random.choice(options)

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
