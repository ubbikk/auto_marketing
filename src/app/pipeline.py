"""Web pipeline — adapted orchestrator for single-persona, 5-generator web requests."""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import yaml

logger = logging.getLogger(__name__)

from ..agents.base_agent import BaseAgent
from ..agents.generator_agent import GeneratedVariant, GeneratorAgent, GeneratorResult, SourceContent
from ..agents.litellm_generator import LiteLLMGeneratorAgent
from ..agents.judge_agent import JudgeAgent, JudgmentResult
from ..carousel.service import generate_carousel_html
from ..creativity.anti_slop import AntiSlopValidator
from ..creativity.engine import CreativityEngine
from ..news.fetcher import NewsFetcher
from ..news.batch_filter import BatchNewsFilter
from ..utils.cost_tracker import PipelineCosts, calculate_cost
from ..company.profile import CompanyContext, load_default_context
from .scraper import WebsiteMetadata, scrape_website_metadata

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "src" / "config"
_DATA_DIR = _PROJECT_ROOT / "data"
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "carousels"

NUM_GENERATORS = 5


@dataclass
class SourceAnalysisResult:
    """Result from source text analysis including content and usage."""

    content: SourceContent
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "claude-sonnet-4-20250514"


@dataclass
class SummarizeResult:
    """Result from auto-summarize including message and usage."""

    message: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "claude-sonnet-4-20250514"


@dataclass
class WebPipelineResult:
    """Full result from the web generation pipeline."""

    winning_post: str
    carousel_html: str
    carousel_id: str
    judgment: JudgmentResult
    all_variants: list[GeneratedVariant]
    filtered_variants: list[GeneratedVariant]
    website_metadata: WebsiteMetadata
    source_content: SourceContent
    stats: dict
    costs: dict


async def analyze_source_text(
    client: anthropic.Anthropic,
    text: str,
    message: str = "",
) -> SourceAnalysisResult:
    """Use Claude Sonnet to extract structured context from pasted text."""
    message_hint = f"\nUSER'S KEY MESSAGE: {message}" if message else ""

    prompt = f"""Analyze this text for LinkedIn content creation.

TEXT:
{text[:3000]}
{message_hint}

Return JSON:
{{
    "title": "Brief title summarizing the text",
    "source": "Type of content (blog post, news article, research, etc.)",
    "summary": "2-3 sentence summary of key points",
    "suggested_angle": "How to frame this for the target audience",
    "company_connection": "How a business could relate to this topic",
    "target_icp": "Primary audience for this content"
}}"""

    model = "claude-sonnet-4-20250514"
    response = client.messages.create(
        model=model,
        max_tokens=500,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract usage data
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    raw = response.content[0].text.strip()
    # Extract JSON from markdown fences or surrounding text
    if "```" in raw:
        start = raw.find("```")
        end = raw.rfind("```")
        if start != end:
            inner = raw[start:end]
            first_nl = inner.find("\n")
            raw = inner[first_nl + 1:] if first_nl != -1 else inner[3:]
        else:
            lines = raw.split("\n")
            raw = "\n".join(l for l in lines if not l.strip().startswith("```"))
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1:
        raw = raw[brace_start : brace_end + 1]

    data = json.loads(raw)
    return SourceAnalysisResult(
        content=SourceContent(**data),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )


async def auto_summarize_message(
    client: anthropic.Anthropic,
    text: str,
) -> SummarizeResult:
    """Generate a concise key message from source text when user leaves message empty."""
    model = "claude-sonnet-4-20250514"
    response = client.messages.create(
        model=model,
        max_tokens=100,
        temperature=0.3,
        messages=[
            {
                "role": "user",
                "content": f"Summarize the key message of this text in one sentence (max 20 words):\n\n{text[:2000]}",
            }
        ],
    )
    return SummarizeResult(
        message=response.content[0].text.strip(),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        model=model,
    )


@dataclass
class AutoSourceResult:
    """Result from auto source fetch including content and filter usage."""

    content: SourceContent
    filter_input_tokens: int = 0
    filter_output_tokens: int = 0
    filter_model: str = ""


async def fetch_auto_source(
    client: anthropic.Anthropic,
    company_context: Optional[CompanyContext] = None,
) -> AutoSourceResult:
    """Fetch relevant news using RSS and return as SourceContent with usage data.

    Args:
        client: Anthropic client (unused but kept for API consistency)
        company_context: Company context for relevance filtering (default: AFTA)
    """
    t0 = time.time()
    logger.info("[NEWS] Fetching RSS feeds...")
    fetcher = NewsFetcher(quick_mode=True)
    articles = await fetcher.fetch_all()
    logger.info("[NEWS] Fetched %d articles in %.1fs", len(articles), time.time() - t0)

    if not articles:
        return AutoSourceResult(
            content=SourceContent(
                title="E-commerce Automation Trends",
                source="Industry observation",
                summary="Businesses are increasingly adopting automation to handle repetitive tasks.",
                suggested_angle="The gap between manual and automated operations",
                company_connection="Automation services for e-commerce businesses",
                target_icp="E-commerce operators",
            )
        )

    # Use batch filter to pick the most relevant article (single API call via Gemini Flash)
    t1 = time.time()
    logger.info("[NEWS] Batch filtering %d articles with Gemini Flash...", len(articles))
    news_filter = BatchNewsFilter(company_context=company_context)
    filter_result = await news_filter.filter_articles(articles, max_results=1)
    logger.info("[NEWS] Filtered to %d articles in %.1fs", len(filter_result.articles), time.time() - t1)

    if filter_result.articles:
        item = filter_result.articles[0]
        return AutoSourceResult(
            content=SourceContent(
                title=item.article.title,
                source=item.article.source,
                summary=item.article.summary,
                suggested_angle=item.suggested_angle,
                company_connection=item.company_connection,
                target_icp=item.target_icp,
            ),
            filter_input_tokens=filter_result.input_tokens,
            filter_output_tokens=filter_result.output_tokens,
            filter_model=filter_result.model,
        )

    # Fallback to first article without filtering
    art = articles[0]
    return AutoSourceResult(
        content=SourceContent(
            title=art.title,
            source=art.source,
            summary=art.summary,
            suggested_angle="Connect to business automation trends",
            company_connection="Relevant to automation industry",
            target_icp="E-commerce operators",
        ),
        filter_input_tokens=filter_result.input_tokens,
        filter_output_tokens=filter_result.output_tokens,
        filter_model=filter_result.model,
    )


async def run_pipeline(
    target_url: str,
    message: str = "",
    source_text: str = "auto",
    persona: str = "professional",
    num_generators: int = 5,
    generation_model: str = "claude-opus-4-5-20251101",
    auto_summarize: bool = True,
    company_context: Optional[CompanyContext] = None,
) -> WebPipelineResult:
    """Run the full web generation pipeline.

    Args:
        target_url: Website URL to scrape logo from.
        message: Key message to convey (empty = auto-summarize if enabled).
        source_text: Pasted text or "auto" for news fetch.
        persona: Selected persona name.
        num_generators: Number of parallel generators to run (3-10).
        generation_model: Model ID for generation and judging.
        auto_summarize: Whether to auto-summarize when message is empty.
        company_context: Company context for content generation (default: AFTA).

    Returns:
        WebPipelineResult with winning post, carousel, and all data.
    """
    run_start = datetime.now()
    client = anthropic.Anthropic()
    costs = PipelineCosts()

    # Load default company context if not provided
    if company_context is None:
        company_context = load_default_context()

    logger.info("=" * 60)
    logger.info("[PIPELINE] Starting generation for persona=%s, model=%s, generators=%d, company=%s",
                persona, generation_model, num_generators, company_context.name)

    # Step 1: Scrape target website metadata (logo, domain)
    t0 = time.time()
    logger.info("[STEP 1] Scraping website metadata from %s", target_url)
    website_metadata = await scrape_website_metadata(target_url)
    logger.info("[STEP 1] Done in %.1fs — domain=%s", time.time() - t0, website_metadata.domain)

    # Step 2: Resolve source content
    t0 = time.time()
    logger.info("[STEP 2] Resolving source content (mode=%s)", "auto" if source_text.strip().lower() == "auto" else "pasted")
    if source_text.strip().lower() == "auto":
        auto_result = await fetch_auto_source(client, company_context=company_context)
        source = auto_result.content
        # Track news filter costs
        if auto_result.filter_model:
            cost = calculate_cost(
                auto_result.filter_model,
                auto_result.filter_input_tokens,
                auto_result.filter_output_tokens,
            )
            costs.add_usage(
                "news_filter",
                auto_result.filter_model,
                auto_result.filter_input_tokens,
                auto_result.filter_output_tokens,
                cost,
            )
    else:
        analysis_result = await analyze_source_text(client, source_text, message)
        source = analysis_result.content
        # Track source analysis costs
        cost = calculate_cost(
            analysis_result.model,
            analysis_result.input_tokens,
            analysis_result.output_tokens,
        )
        costs.add_usage(
            "source_analysis",
            analysis_result.model,
            analysis_result.input_tokens,
            analysis_result.output_tokens,
            cost,
        )
    logger.info("[STEP 2] Done in %.1fs — title=%s", time.time() - t0, source.title[:50])

    # Step 3: Auto-summarize message if empty (and enabled)
    effective_message = message
    if not effective_message.strip() and auto_summarize:
        t0 = time.time()
        logger.info("[STEP 3] Auto-summarizing message with Sonnet...")
        summarize_result = await auto_summarize_message(client, source.summary)
        effective_message = summarize_result.message
        # Track auto-summarize costs
        cost = calculate_cost(
            summarize_result.model,
            summarize_result.input_tokens,
            summarize_result.output_tokens,
        )
        costs.add_usage(
            "auto_summarize",
            summarize_result.model,
            summarize_result.input_tokens,
            summarize_result.output_tokens,
            cost,
        )
        logger.info("[STEP 3] Done in %.1fs — message=%s", time.time() - t0, effective_message[:50])
    elif not effective_message.strip():
        logger.info("[STEP 3] Auto-summarize disabled, using source summary as message")
        effective_message = source.summary[:100]

    # Step 4: Load configs
    personas_data = _load_personas()
    company_profile = company_context.to_generator_prompt()
    anti_slop = AntiSlopValidator()

    creativity_engine = CreativityEngine(
        config_path=_CONFIG_DIR / "creativity.yaml",
        data_dir=_DATA_DIR,
        anti_slop_rules=anti_slop.get_rules_for_prompt(),
    )

    persona_config = personas_data.get(persona, personas_data.get("professional", {}))

    # Step 5: Create generators — ALL same persona, different creativity contexts
    t0 = time.time()
    use_litellm = generation_model.startswith("gemini/")
    logger.info("[STEP 5] Creating %d generators with %s (litellm=%s)...",
                num_generators, generation_model, use_litellm)
    generation_tasks = []
    for i in range(num_generators):
        creativity_ctx = creativity_engine.generate_context(persona)

        if use_litellm:
            # Use LiteLLM for Gemini and other non-Anthropic models
            generator = LiteLLMGeneratorAgent(
                model_id=generation_model,
                generator_id=i,
                persona_config=persona_config,
                company_profile=company_profile,
            )
        else:
            # Use Anthropic SDK for Claude models
            generator = GeneratorAgent(
                client=client,
                generator_id=i,
                persona_config=persona_config,
                company_profile=company_profile,
                model_id=generation_model,
            )

        variants_count = random.randint(2, 4)
        logger.info("[STEP 5]   Generator %d: hook=%s, structure=%s, variants=%d",
                    i, creativity_ctx.hook_pattern, creativity_ctx.structure, variants_count)
        generation_tasks.append(
            generator.execute_from_source(source, creativity_ctx, variants_count)
        )

    # Run all generators in parallel
    logger.info("[STEP 5] Running %d generators in parallel...", num_generators)
    all_results = await asyncio.gather(*generation_tasks, return_exceptions=True)
    logger.info("[STEP 5] All generators done in %.1fs", time.time() - t0)

    # Step 6: Collect variants and track generation costs
    all_variants: list[GeneratedVariant] = []
    generation_errors = 0
    for i, result in enumerate(all_results):
        if isinstance(result, GeneratorResult):
            all_variants.extend(result.variants)
            logger.info("[STEP 6] Generator %d produced %d variants", i, len(result.variants))
            # Track generation costs
            if result.usage:
                cost = calculate_cost(
                    result.usage.model,
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                )
                costs.add_usage(
                    "generation",
                    result.usage.model,
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                    cost,
                )
        elif isinstance(result, Exception):
            generation_errors += 1
            logger.warning("[STEP 6] Generator %d failed: %s", i, result)
        else:
            generation_errors += 1
            logger.warning("[STEP 6] Generator %d returned unexpected result: %s", i, type(result))
    logger.info("[STEP 6] Total: %d variants, %d errors", len(all_variants), generation_errors)

    # Step 7: Anti-slop validation
    t0 = time.time()
    logger.info("[STEP 7] Running anti-slop validation on %d variants...", len(all_variants))
    filtered_variants = []
    slop_violations = 0
    for variant in all_variants:
        validation = anti_slop.validate(variant.content)
        if validation.is_valid:
            filtered_variants.append(variant)
        else:
            slop_violations += 1

    # Fallback if all variants fail anti-slop
    if not filtered_variants:
        logger.warning("[STEP 7] All variants failed! Using fallback (top 10)")
        filtered_variants = all_variants[:10]
    logger.info("[STEP 7] Done in %.1fs — %d passed, %d rejected", time.time() - t0, len(filtered_variants), slop_violations)

    # Step 8: Judge picks the winner (uses same model as generation for Claude, defaults to Opus for LiteLLM models)
    t0 = time.time()
    judge_model = generation_model if not use_litellm else "claude-opus-4-5-20251101"
    logger.info("[STEP 8] Judge evaluating %d variants with %s...", len(filtered_variants), judge_model)
    judge = JudgeAgent(
        client=client,
        anti_slop_rules=anti_slop.get_rules_for_prompt(),
        model_id=judge_model,
    )
    source_context = f"Title: {source.title}\nSummary: {source.summary}"
    judgment = await judge.execute(filtered_variants, source_context)
    # Track judge costs
    if judgment.usage:
        cost = calculate_cost(
            judgment.usage.model,
            judgment.usage.input_tokens,
            judgment.usage.output_tokens,
        )
        costs.add_usage(
            "judge",
            judgment.usage.model,
            judgment.usage.input_tokens,
            judgment.usage.output_tokens,
            cost,
        )
    logger.info("[STEP 8] Done in %.1fs — winner score=%.2f", time.time() - t0,
                judgment.winner_score.weighted_total if judgment.winner_score else 0)

    # Step 9: Generate carousel HTML (PDF rendered on-demand)
    t0 = time.time()
    logger.info("[STEP 9] Generating carousel HTML...")
    # Use the full source text for carousel extraction (richer content)
    if source_text.strip().lower() != "auto":
        carousel_source = source_text
    else:
        # Build rich context from source for auto mode
        carousel_source = f"""Title: {source.title}

Summary: {source.summary}

Key Angle: {source.suggested_angle}

Business Connection: {source.company_connection}

Target Audience: {source.target_icp}"""
    logger.info("[STEP 9] Carousel source length: %d chars", len(carousel_source))
    carousel_result = await generate_carousel_html(
        text=carousel_source,
        client=client,
        message=effective_message,
        logo_data_url=website_metadata.logo_data_url,
        footer_domain=website_metadata.domain,
    )
    # Track carousel costs
    cost = calculate_cost(
        carousel_result.model,
        carousel_result.input_tokens,
        carousel_result.output_tokens,
    )
    costs.add_usage(
        "carousel",
        carousel_result.model,
        carousel_result.input_tokens,
        carousel_result.output_tokens,
        cost,
    )
    logger.info("[STEP 9] Done in %.1fs — carousel_id=%s", time.time() - t0, carousel_result.carousel_id)

    # Compile stats
    total_duration = (datetime.now() - run_start).total_seconds()
    stats = {
        "total_generators": num_generators,
        "generation_model": generation_model,
        "generation_errors": generation_errors,
        "total_variants": len(all_variants),
        "slop_violations": slop_violations,
        "filtered_variants": len(filtered_variants),
        "duration_seconds": total_duration,
    }

    # Get cost breakdown
    costs_dict = costs.to_dict()
    logger.info("=" * 60)
    logger.info("[PIPELINE] Complete! Total duration: %.1fs", total_duration)
    logger.info("[PIPELINE] Stats: %s", stats)
    logger.info("[PIPELINE] Total cost: $%.4f", costs_dict["total_cost_usd"])

    return WebPipelineResult(
        winning_post=judgment.winner.content,
        carousel_html=carousel_result.html,
        carousel_id=carousel_result.carousel_id,
        judgment=judgment,
        all_variants=all_variants,
        filtered_variants=filtered_variants,
        website_metadata=website_metadata,
        source_content=source,
        stats=stats,
        costs=costs_dict,
    )


def _load_personas() -> dict:
    """Load persona configurations."""
    personas_path = _CONFIG_DIR / "personas.yaml"
    with open(personas_path) as f:
        data = yaml.safe_load(f)
    return data.get("personas", {})


