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
from ..agents.generator_agent import GeneratedVariant, GeneratorAgent, SourceContent
from ..agents.judge_agent import JudgeAgent, JudgmentResult
from ..carousel.service import generate_carousel
from ..creativity.anti_slop import AntiSlopValidator
from ..creativity.engine import CreativityEngine
from ..news.fetcher import NewsFetcher
from ..news.filter import NewsFilter
from .scraper import WebsiteMetadata, scrape_website_metadata

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "src" / "config"
_DATA_DIR = _PROJECT_ROOT / "data"
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "carousels"

NUM_GENERATORS = 5


@dataclass
class WebPipelineResult:
    """Full result from the web generation pipeline."""

    winning_post: str
    carousel_pdf_path: Path
    judgment: JudgmentResult
    all_variants: list[GeneratedVariant]
    filtered_variants: list[GeneratedVariant]
    website_metadata: WebsiteMetadata
    source_content: SourceContent
    stats: dict


async def analyze_source_text(
    client: anthropic.Anthropic,
    text: str,
    message: str = "",
) -> SourceContent:
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

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )

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
    return SourceContent(**data)


async def auto_summarize_message(
    client: anthropic.Anthropic,
    text: str,
) -> str:
    """Generate a concise key message from source text when user leaves message empty."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        temperature=0.3,
        messages=[
            {
                "role": "user",
                "content": f"Summarize the key message of this text in one sentence (max 20 words):\n\n{text[:2000]}",
            }
        ],
    )
    return response.content[0].text.strip()


async def fetch_auto_source(client: anthropic.Anthropic) -> SourceContent:
    """Fetch relevant news using RSS and return as SourceContent."""
    t0 = time.time()
    logger.info("[NEWS] Fetching RSS feeds...")
    fetcher = NewsFetcher(quick_mode=True)
    articles = await fetcher.fetch_all()
    logger.info("[NEWS] Fetched %d articles in %.1fs", len(articles), time.time() - t0)

    if not articles:
        return SourceContent(
            title="E-commerce Automation Trends",
            source="Industry observation",
            summary="Businesses are increasingly adopting automation to handle repetitive tasks.",
            suggested_angle="The gap between manual and automated operations",
            company_connection="Automation services for e-commerce businesses",
            target_icp="E-commerce operators",
        )

    # Use the news filter to pick the most relevant article
    t1 = time.time()
    logger.info("[NEWS] Filtering articles with Sonnet...")
    news_filter = NewsFilter(client)
    filtered = await news_filter.filter_articles(articles, max_results=1)
    logger.info("[NEWS] Filtered to %d articles in %.1fs", len(filtered), time.time() - t1)

    if filtered:
        item = filtered[0]
        return SourceContent(
            title=item.article.title,
            source=item.article.source,
            summary=item.article.summary,
            suggested_angle=item.suggested_angle,
            company_connection=item.company_connection,
            target_icp=item.target_icp,
        )

    # Fallback to first article without filtering
    art = articles[0]
    return SourceContent(
        title=art.title,
        source=art.source,
        summary=art.summary,
        suggested_angle="Connect to business automation trends",
        company_connection="Relevant to automation industry",
        target_icp="E-commerce operators",
    )


async def run_pipeline(
    target_url: str,
    message: str = "",
    source_text: str = "auto",
    persona: str = "professional",
) -> WebPipelineResult:
    """Run the full web generation pipeline.

    Args:
        target_url: Website URL to scrape logo from.
        message: Key message to convey (empty = auto-summarize).
        source_text: Pasted text or "auto" for news fetch.
        persona: Selected persona name.

    Returns:
        WebPipelineResult with winning post, carousel, and all data.
    """
    run_start = datetime.now()
    client = anthropic.Anthropic()
    logger.info("=" * 60)
    logger.info("[PIPELINE] Starting generation for persona=%s", persona)

    # Step 1: Scrape target website metadata (logo, domain)
    t0 = time.time()
    logger.info("[STEP 1] Scraping website metadata from %s", target_url)
    website_metadata = await scrape_website_metadata(target_url)
    logger.info("[STEP 1] Done in %.1fs — domain=%s", time.time() - t0, website_metadata.domain)

    # Step 2: Resolve source content
    t0 = time.time()
    logger.info("[STEP 2] Resolving source content (mode=%s)", "auto" if source_text.strip().lower() == "auto" else "pasted")
    if source_text.strip().lower() == "auto":
        source = await fetch_auto_source(client)
    else:
        source = await analyze_source_text(client, source_text, message)
    logger.info("[STEP 2] Done in %.1fs — title=%s", time.time() - t0, source.title[:50])

    # Step 3: Auto-summarize message if empty
    effective_message = message
    if not effective_message.strip():
        t0 = time.time()
        logger.info("[STEP 3] Auto-summarizing message with Sonnet...")
        effective_message = await auto_summarize_message(client, source.summary)
        logger.info("[STEP 3] Done in %.1fs — message=%s", time.time() - t0, effective_message[:50])

    # Step 4: Load configs
    personas_data = _load_personas()
    company_profile = _load_company_profile()
    anti_slop = AntiSlopValidator()

    creativity_engine = CreativityEngine(
        config_path=_CONFIG_DIR / "creativity.yaml",
        data_dir=_DATA_DIR,
        anti_slop_rules=anti_slop.get_rules_for_prompt(),
    )

    persona_config = personas_data.get(persona, personas_data.get("professional", {}))

    # Step 5: Create 5 generators — ALL same persona, different creativity contexts
    t0 = time.time()
    logger.info("[STEP 5] Creating %d generators with Opus (extended thinking)...", NUM_GENERATORS)
    generation_tasks = []
    for i in range(NUM_GENERATORS):
        creativity_ctx = creativity_engine.generate_context(persona)
        generator = GeneratorAgent(
            client=client,
            generator_id=i,
            persona_config=persona_config,
            company_profile=company_profile,
            model_id="claude-opus-4-5-20251101",
        )
        num_variants = random.randint(2, 4)
        logger.info("[STEP 5]   Generator %d: hook=%s, framework=%s, variants=%d",
                    i, creativity_ctx.hook_pattern, creativity_ctx.framework, num_variants)
        generation_tasks.append(
            generator.execute_from_source(source, creativity_ctx, num_variants)
        )

    # Run all generators in parallel
    logger.info("[STEP 5] Running %d generators in parallel...", NUM_GENERATORS)
    all_results = await asyncio.gather(*generation_tasks, return_exceptions=True)
    logger.info("[STEP 5] All generators done in %.1fs", time.time() - t0)

    # Step 6: Collect variants
    all_variants: list[GeneratedVariant] = []
    generation_errors = 0
    for i, result in enumerate(all_results):
        if isinstance(result, list):
            all_variants.extend(result)
            logger.info("[STEP 6] Generator %d produced %d variants", i, len(result))
        else:
            generation_errors += 1
            logger.warning("[STEP 6] Generator %d failed: %s", i, result)
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

    # Step 8: Judge picks the winner
    t0 = time.time()
    logger.info("[STEP 8] Judge evaluating %d variants with Opus (extended thinking)...", len(filtered_variants))
    judge = JudgeAgent(
        client=client,
        anti_slop_rules=anti_slop.get_rules_for_prompt(),
        model_id="claude-opus-4-5-20251101",
    )
    source_context = f"Title: {source.title}\nSummary: {source.summary}"
    judgment = await judge.execute(filtered_variants, source_context)
    logger.info("[STEP 8] Done in %.1fs — winner score=%.2f", time.time() - t0,
                judgment.winner_score.weighted_total if judgment.winner_score else 0)

    # Step 9: Generate carousel PDF
    t0 = time.time()
    logger.info("[STEP 9] Generating carousel PDF...")
    # Use the full source text for carousel extraction (richer content)
    carousel_source = source_text if source_text.strip().lower() != "auto" else source.summary
    carousel_pdf_path = await generate_carousel(
        text=carousel_source,
        client=client,
        message=effective_message,
        logo_data_url=website_metadata.logo_data_url,
        footer_domain=website_metadata.domain,
    )
    logger.info("[STEP 9] Done in %.1fs — path=%s", time.time() - t0, carousel_pdf_path.name)

    # Compile stats
    total_duration = (datetime.now() - run_start).total_seconds()
    stats = {
        "total_generators": NUM_GENERATORS,
        "generation_errors": generation_errors,
        "total_variants": len(all_variants),
        "slop_violations": slop_violations,
        "filtered_variants": len(filtered_variants),
        "duration_seconds": total_duration,
    }
    logger.info("=" * 60)
    logger.info("[PIPELINE] Complete! Total duration: %.1fs", total_duration)
    logger.info("[PIPELINE] Stats: %s", stats)

    return WebPipelineResult(
        winning_post=judgment.winner.content,
        carousel_pdf_path=carousel_pdf_path,
        judgment=judgment,
        all_variants=all_variants,
        filtered_variants=filtered_variants,
        website_metadata=website_metadata,
        source_content=source,
        stats=stats,
    )


def _load_personas() -> dict:
    """Load persona configurations."""
    personas_path = _CONFIG_DIR / "personas.yaml"
    with open(personas_path) as f:
        data = yaml.safe_load(f)
    return data.get("personas", {})


def _load_company_profile() -> str:
    """Load company profile for context."""
    personas_path = _CONFIG_DIR / "personas.yaml"
    with open(personas_path) as f:
        data = yaml.safe_load(f)

    ctx = data.get("company_context", {})
    return f"""
Company: {ctx.get('name', 'AFTA Systems')}
Tagline: {ctx.get('tagline', '')}
Core Offering: {ctx.get('core_offering', '')}
Differentiator: {ctx.get('differentiator', '')}
Target Audience: {', '.join(ctx.get('target_audience', []))}
Key Services: {', '.join(ctx.get('key_services', []))}
Proof Points: {', '.join(ctx.get('proof_points', []))}
"""
