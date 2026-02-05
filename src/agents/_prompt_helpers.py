"""Shared prompt builder for generator agents.

Used by both GeneratorAgent (Anthropic SDK) and LiteLLMGeneratorAgent
to eliminate prompt construction duplication.
"""

from ..creativity.engine import CreativityContext
from ..prompts import render


def build_generator_prompt(
    source,
    persona: dict,
    company_name: str,
    company_profile: str,
    ctx: CreativityContext,
    num_variants: int,
    num_generators: str = "several",
) -> str:
    """Build the complete generator prompt from template.

    Args:
        source: SourceContent with title, source, summary, etc.
        persona: Persona configuration dict with voice_traits, anti_patterns, etc.
        company_name: Company name for the prompt header.
        company_profile: Formatted company context string.
        ctx: Creativity context with examples, style, tone, etc.
        num_variants: Number of variants to generate.
        num_generators: How many generators run in parallel (for role context).

    Returns:
        Rendered prompt string.
    """
    persona_name = persona.get("name", ctx.persona)
    voice_traits = persona.get("voice_traits", [])
    relationship = persona.get("relationship_to_reader", "A peer")
    anti_patterns = persona.get("anti_patterns", [])
    example_openers = persona.get("example_openers", [])

    # Build conditional sections
    few_shot_section = ""
    if ctx.few_shot_examples:
        few_shot_section = (
            "\nFEW-SHOT EXAMPLES (study these, don't copy verbatim):\n"
            + "\n".join(f"---\n{ex}\n---" for ex in ctx.few_shot_examples)
            + "\n"
        )

    style_section = ""
    if ctx.style_reference:
        style_section = f"\nSTYLE INFLUENCE:\n{ctx.style_reference}\n"

    tone_wildcard_section = ""
    if ctx.tone_wildcard:
        tone_wildcard_section = f"\nPERSPECTIVE FOR THIS GENERATION:\n{ctx.tone_wildcard}\n"

    structural_break_section = ""
    if ctx.structural_break:
        structural_break_section = (
            f"\nSTRUCTURAL BREAK (include this human imperfection):\n{ctx.structural_break}\n"
        )

    anti_patterns_section = ""
    if ctx.structure_anti_patterns:
        anti_patterns_section = (
            "\nSTRUCTURE ANTI-PATTERNS (avoid these formulaic patterns):\n"
            + "\n".join(f"- {p}" for p in ctx.structure_anti_patterns)
            + "\n"
        )

    structure_guidance_line = (
        f"- Structure guidance: {ctx.structure_guidance}"
        if ctx.structure_guidance
        else "- No structural guidance: just write naturally"
    )

    return render(
        "generator",
        num_generators=num_generators,
        company_name=company_name,
        company_profile=company_profile,
        persona_name=persona_name,
        voice_traits="\n".join(f"- {t}" for t in voice_traits),
        relationship=relationship,
        anti_patterns="\n".join(f"- {p}" for p in anti_patterns),
        example_openers="\n".join(f'- "{o}"' for o in example_openers),
        few_shot_section=few_shot_section,
        style_section=style_section,
        tone_wildcard_section=tone_wildcard_section,
        structural_break_section=structural_break_section,
        anti_patterns_section=anti_patterns_section,
        anti_slop_rules=ctx.anti_slop_rules,
        title=source.title,
        source=source.source,
        summary=source.summary,
        suggested_angle=source.suggested_angle,
        company_connection=source.company_connection,
        target_icp=source.target_icp,
        content_angle=ctx.content_angle,
        hook_pattern=ctx.hook_pattern,
        hook_description=ctx.hook_description,
        structure=ctx.structure,
        structure_description=ctx.structure_description,
        structure_guidance_line=structure_guidance_line,
        num_variants=str(num_variants),
    )
