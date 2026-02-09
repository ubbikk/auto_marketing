"""Orchestrator for coordinating parallel content generation.

Manages the full pipeline:
1. Configure generator agents
2. Run generators in parallel
3. Collect and validate variants
4. Run judge agent
5. Return results
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import yaml

from ..company.profile import load_default_context
from ..creativity.anti_slop import AntiSlopValidator
from ..creativity.engine import CreativityEngine
from ..news.models import FilteredNewsItem
from .generator_agent import GeneratedVariant, GeneratorAgent, GeneratorResult, SourceContent
from .judge_agent import JudgeAgent, JudgmentResult


@dataclass
class GeneratorConfig:
    """Configuration for a single generator."""

    generator_id: int
    persona_name: str
    persona_config: dict
    num_variants: int


@dataclass
class PipelineResult:
    """Full result from the generation pipeline."""

    judgment: JudgmentResult
    all_variants: list[GeneratedVariant]
    filtered_variants: list[GeneratedVariant]  # After anti-slop check
    source: SourceContent
    run_timestamp: datetime
    stats: dict


class Orchestrator:
    """
    Orchestrates parallel content generation and judging.

    Pipeline flow:
    1. Load personas and creativity config
    2. Create generator configurations (distribute personas)
    3. Run generators in parallel
    4. Validate variants against anti-slop rules
    5. Run judge agent on valid variants
    6. Return full results
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        config_dir: Path,
        data_dir: Path,
        num_generators: int = 7,
        variants_range: tuple[int, int] = (1, 1),
        model_id: str = "claude-opus-4-5-20251101",
    ):
        """
        Initialize orchestrator.

        Args:
            client: Anthropic API client
            config_dir: Path to config directory
            data_dir: Path to data directory
            num_generators: Number of generator agents (5-10)
            variants_range: (min, max) variants per generator
            model_id: Model to use for all agents
        """
        self.client = client
        self.config_dir = config_dir
        self.data_dir = data_dir
        self.num_generators = num_generators
        self.variants_range = variants_range
        self.model_id = model_id

        # Load configurations
        self.personas = self._load_personas()
        self.company_context = load_default_context()
        self.company_profile = self.company_context.to_generator_prompt()

        # Initialize anti-slop validator
        self.anti_slop = AntiSlopValidator()

        # Initialize creativity engine
        creativity_path = config_dir / "creativity.yaml"
        self.creativity_engine = CreativityEngine(
            config_path=creativity_path,
            data_dir=data_dir,
            anti_slop_rules=self.anti_slop.get_rules_for_prompt(),
        )

    def _load_personas(self) -> dict:
        """Load persona configurations."""
        personas_path = self.config_dir / "personas.yaml"
        with open(personas_path) as f:
            data = yaml.safe_load(f)
        return data.get("personas", {})

    async def run(self, news_item: FilteredNewsItem) -> PipelineResult:
        """
        Run the full generation pipeline.

        Args:
            news_item: Filtered news article to generate content for

        Returns:
            PipelineResult with all outputs
        """
        # Convert FilteredNewsItem to unified SourceContent
        source = SourceContent(
            title=news_item.article.title,
            source=news_item.article.source,
            summary=news_item.article.summary,
            suggested_angle=news_item.suggested_angle,
            company_connection=news_item.company_connection,
            target_icp=news_item.target_icp,
        )
        return await self.run_from_source(source)

    async def run_from_source(self, source: SourceContent) -> PipelineResult:
        """
        Run the full generation pipeline from unified source content.

        Args:
            source: Source content to generate posts for.

        Returns:
            PipelineResult with all outputs.
        """
        run_start = datetime.now()

        # Step 1: Create generator configurations
        generator_configs = self._create_generator_configs()

        # Step 2: Run generators in parallel
        generation_tasks = [
            self._run_generator(config, source) for config in generator_configs
        ]

        all_results = await asyncio.gather(*generation_tasks, return_exceptions=True)

        # Step 3: Collect all variants
        all_variants: list[GeneratedVariant] = []
        generation_errors = 0
        for result in all_results:
            if isinstance(result, GeneratorResult):
                all_variants.extend(result.variants)
            elif isinstance(result, list):
                all_variants.extend(result)
            else:
                generation_errors += 1

        # Step 4: Filter variants through anti-slop validation
        filtered_variants = []
        slop_violations = 0
        for variant in all_variants:
            validation = self.anti_slop.validate(variant.content)
            if validation.is_valid:
                filtered_variants.append(variant)
            else:
                slop_violations += 1

        # Step 5: Run judge agent
        if not filtered_variants:
            # If all variants failed anti-slop, use unfiltered
            filtered_variants = all_variants[:10]  # Limit to prevent huge prompts

        judge = JudgeAgent(
            client=self.client,
            anti_slop_rules=self.anti_slop.get_rules_for_prompt(),
            model_id=self.model_id,
        )

        source_context = f"Title: {source.title}\nSummary: {source.summary}"
        judgment = await judge.execute(filtered_variants, source_context)

        # Compile stats
        stats = {
            "total_generators": self.num_generators,
            "generation_errors": generation_errors,
            "total_variants": len(all_variants),
            "slop_violations": slop_violations,
            "filtered_variants": len(filtered_variants),
            "variants_per_persona": self._count_by_persona(all_variants),
            "duration_seconds": (datetime.now() - run_start).total_seconds(),
        }

        return PipelineResult(
            judgment=judgment,
            all_variants=all_variants,
            filtered_variants=filtered_variants,
            source=source,
            run_timestamp=run_start,
            stats=stats,
        )

    def _create_generator_configs(self) -> list[GeneratorConfig]:
        """Create configurations for each generator."""
        configs = []
        persona_names = list(self.personas.keys())

        for i in range(self.num_generators):
            # Distribute personas: ensure each gets at least 2 generators
            if i < len(persona_names) * 2:
                persona_name = persona_names[i % len(persona_names)]
            else:
                persona_name = random.choice(persona_names)

            configs.append(
                GeneratorConfig(
                    generator_id=i,
                    persona_name=persona_name,
                    persona_config=self.personas[persona_name],
                    num_variants=random.randint(*self.variants_range),
                )
            )

        return configs

    async def _run_generator(
        self,
        config: GeneratorConfig,
        source: SourceContent,
    ) -> GeneratorResult:
        """Run a single generator agent."""
        # Get creativity context
        creativity_ctx = self.creativity_engine.generate_context(config.persona_name)

        # Create generator
        generator = GeneratorAgent(
            client=self.client,
            generator_id=config.generator_id,
            persona_config=config.persona_config,
            company_name=self.company_context.name,
            company_profile=self.company_profile,
            model_id=self.model_id,
        )

        # Run generation
        return await generator.execute(
            source=source,
            creativity_ctx=creativity_ctx,
            num_variants=config.num_variants,
        )

    def _count_by_persona(self, variants: list[GeneratedVariant]) -> dict[str, int]:
        """Count variants by persona."""
        counts: dict[str, int] = {}
        for v in variants:
            counts[v.persona] = counts.get(v.persona, 0) + 1
        return counts

    def run_sync(self, news_item: FilteredNewsItem) -> PipelineResult:
        """Synchronous wrapper for run()."""
        return asyncio.run(self.run(news_item))
