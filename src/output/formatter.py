"""Output formatting for pipeline results.

Generates both JSON (structured) and Markdown (human-readable)
outputs for the winning post and full run data.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..agents.generator_agent import GeneratedVariant, SourceContent
from ..agents.judge_agent import JudgmentResult, VariantScore
from ..agents.orchestrator import PipelineResult


class OutputFormatter:
    """Formats pipeline output in multiple formats."""

    def __init__(self, output_dir: Path):
        """
        Initialize formatter.

        Args:
            output_dir: Base directory for output files
        """
        self.output_dir = output_dir

    def save_run(self, result: PipelineResult) -> Path:
        """
        Save complete run output.

        Creates:
        - winner.json: Winning post with metadata
        - winner.md: Human-readable winning post
        - all_variants.json: All generated variants
        - run_log.json: Full execution log

        Returns:
            Path to run directory
        """
        # Create timestamped run directory
        timestamp = result.run_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = self.output_dir / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save winner
        winner_json = self.format_winner_json(result)
        (run_dir / "winner.json").write_text(json.dumps(winner_json, indent=2, default=str))

        winner_md = self.format_winner_markdown(result)
        (run_dir / "winner.md").write_text(winner_md)

        # Save all variants
        variants_json = self.format_all_variants(result)
        (run_dir / "all_variants.json").write_text(
            json.dumps(variants_json, indent=2, default=str)
        )

        # Save run log
        run_log = self.format_run_log(result)
        (run_dir / "run_log.json").write_text(json.dumps(run_log, indent=2, default=str))

        # Save source input
        source_json = self.format_source_input(result.source)
        (run_dir / "source_input.json").write_text(json.dumps(source_json, indent=2, default=str))

        return run_dir

    def format_winner_json(self, result: PipelineResult) -> dict:
        """Format winner as JSON."""
        winner = result.judgment.winner
        score = result.judgment.winner_score

        return {
            "generated_at": result.run_timestamp.isoformat(),
            "source": {
                "title": result.source.title,
                "source": result.source.source,
            },
            "winner": {
                "content": winner.content,
                "persona": winner.persona,
                "hook_type": winner.hook_type,
                "structure": winner.structure_used,
                "generator_id": winner.generator_id,
                "variant_id": winner.variant_id,
                "what_makes_it_different": winner.what_makes_it_different,
            },
            "scores": {
                "hook_strength": score.hook_strength if score else None,
                "anti_slop": score.anti_slop if score else None,
                "distinctiveness": score.distinctiveness if score else None,
                "relevance": score.relevance if score else None,
                "persona_fit": score.persona_fit if score else None,
                "weighted_total": score.weighted_total if score else None,
            },
            "reasoning": result.judgment.winner_reasoning,
            "improvement_notes": result.judgment.improvement_notes,
        }

    def format_winner_markdown(self, result: PipelineResult) -> str:
        """Format winner as human-readable markdown."""
        winner = result.judgment.winner
        score = result.judgment.winner_score
        source = result.source

        score_section = ""
        if score:
            score_section = f"""
## Scores

| Criterion | Score |
|-----------|-------|
| Hook Strength | {score.hook_strength}/10 |
| Anti-Slop | {score.anti_slop}/10 |
| Distinctiveness | {score.distinctiveness}/10 |
| Relevance | {score.relevance}/10 |
| Persona Fit | {score.persona_fit}/10 |
| **Weighted Total** | **{score.weighted_total:.1f}/10** |
"""

        improvement_section = ""
        if result.judgment.improvement_notes:
            improvement_section = f"""
## Suggested Improvements

{result.judgment.improvement_notes}
"""

        return f"""# LinkedIn Post - {result.run_timestamp.strftime('%Y-%m-%d %H:%M')}

## Source

**Title:** {source.title}
**Source:** {source.source}
**Summary:** {source.summary}

**Suggested Angle:** {source.suggested_angle}

---

## Winning Post

**Persona:** {winner.persona}
**Hook Type:** {winner.hook_type}
**Structure:** {winner.structure_used}

---

{winner.content}

---
{score_section}

## Judge's Reasoning

{result.judgment.winner_reasoning}
{improvement_section}

## Generation Stats

- Total variants generated: {result.stats['total_variants']}
- Slop violations filtered: {result.stats['slop_violations']}
- Final candidates: {result.stats['filtered_variants']}
- Duration: {result.stats['duration_seconds']:.1f}s
- Variants by persona: {result.stats['variants_per_persona']}
"""

    def format_all_variants(self, result: PipelineResult) -> dict:
        """Format all variants with scores."""
        variants_data = []

        for i, variant in enumerate(result.all_variants):
            # Find matching score if available
            score = next(
                (
                    s
                    for s in result.judgment.all_scores
                    if s.generator_id == variant.generator_id
                    and s.variant_id == variant.variant_id
                ),
                None,
            )

            variants_data.append(
                {
                    "index": i,
                    "content": variant.content,
                    "persona": variant.persona,
                    "hook_type": variant.hook_type,
                    "structure": variant.structure_used,
                    "generator_id": variant.generator_id,
                    "variant_id": variant.variant_id,
                    "what_makes_it_different": variant.what_makes_it_different,
                    "score": score.weighted_total if score else None,
                    "notes": score.notes if score else None,
                }
            )

        return {
            "total_variants": len(variants_data),
            "variants": variants_data,
        }

    def format_run_log(self, result: PipelineResult) -> dict:
        """Format full execution log."""
        return {
            "run_id": f"run_{result.run_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}",
            "started_at": result.run_timestamp.isoformat(),
            "source_input": {
                "title": result.source.title,
                "source": result.source.source,
                "summary": result.source.summary,
            },
            "generation": {
                "total_generators": result.stats["total_generators"],
                "generation_errors": result.stats["generation_errors"],
                "total_variants": result.stats["total_variants"],
                "variants_per_persona": result.stats["variants_per_persona"],
            },
            "filtering": {
                "slop_violations": result.stats["slop_violations"],
                "filtered_variants": result.stats["filtered_variants"],
            },
            "judging": {
                "variants_judged": result.judgment.total_variants_judged,
                "winner_score": (
                    result.judgment.winner_score.weighted_total
                    if result.judgment.winner_score
                    else None
                ),
                "winner_persona": result.judgment.winner.persona,
            },
            "duration_seconds": result.stats["duration_seconds"],
        }

    def format_source_input(self, source: SourceContent) -> dict:
        """Format source input data."""
        return {
            "title": source.title,
            "source": source.source,
            "summary": source.summary,
            "suggested_angle": source.suggested_angle,
            "company_connection": source.company_connection,
            "target_icp": source.target_icp,
        }
