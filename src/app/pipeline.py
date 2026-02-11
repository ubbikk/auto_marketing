"""Web pipeline — adapted orchestrator for single-persona, 5-generator web requests."""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import anthropic
import yaml

logger = logging.getLogger(__name__)

from ..agents.base_agent import BaseAgent
from ..agents.generator_agent import GeneratedVariant, GeneratorAgent, GeneratorResult, SourceContent
from ..agents.litellm_generator import LiteLLMGeneratorAgent
from ..agents.litellm_judge import LiteLLMJudgeAgent
from ..agents.judge_agent import JudgeAgent, JudgmentResult
from ..carousel.service import generate_carousel_html
from ..creativity.anti_slop import AntiSlopValidator
from ..creativity.engine import CreativityEngine
from ..news.fetcher import NewsFetcher
from ..news.batch_filter import BatchNewsFilter
from ..news.embedding_filter import EmbeddingPreFilter
from ..utils.cost_tracker import PipelineCosts, calculate_cost
from ..company.profile import CompanyContext, load_default_context
from ..config.settings import settings
from .scraper import ArticleContent, WebsiteMetadata, scrape_article_content, scrape_website_metadata
from .url_resolver import UrlResolveResult, detect_url, resolve_url

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "src" / "config"
_DATA_DIR = _PROJECT_ROOT / "data"
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "carousels"
_RUNS_DIR = _PROJECT_ROOT / "output" / "runs"

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
    source_mode: str = "paste"  # "auto" | "paste" | "url_generic" | "url_youtube"


async def analyze_source_text(
    client: anthropic.Anthropic,
    text: str,
    message: str = "",
) -> SourceAnalysisResult:
    """Use Claude Sonnet to extract structured context from pasted text."""
    from ..prompts import render

    message_hint = f"\nUSER'S KEY MESSAGE: {message}" if message else ""
    prompt = render("source_analysis", text=text[:3000], message_hint=message_hint)

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
    from ..prompts import render

    model = "claude-sonnet-4-20250514"
    prompt = render("auto_summarize", text=text[:2000])
    response = client.messages.create(
        model=model,
        max_tokens=100,
        temperature=0.3,
        messages=[
            {
                "role": "user",
                "content": prompt,
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
    # Embedding pre-filter stats
    embedding_input_tokens: int = 0
    embedding_model: str = ""
    embedding_cost_usd: float = 0.0
    total_articles_fetched: int = 0
    articles_after_embedding: int = 0
    # Substep timings
    timings: dict = field(default_factory=dict)


async def fetch_auto_source(
    client: anthropic.Anthropic,
    company_context: Optional[CompanyContext] = None,
    exclude_urls: Optional[set[str]] = None,
) -> AutoSourceResult:
    """Fetch relevant news using RSS and return as SourceContent with usage data.

    Args:
        client: Anthropic client (unused but kept for API consistency)
        company_context: Company context for relevance filtering (default: AFTA)
    """
    # Load default company context if not provided
    if company_context is None:
        company_context = load_default_context()

    # Step 1: Fetch all articles (news + blogs if enabled)
    substep_timings = {}
    t0 = time.time()
    logger.info("[NEWS] Fetching RSS feeds (include_blogs=%s)...", settings.include_blog_feeds)
    fetcher = NewsFetcher(
        quick_mode=False,
        include_blogs=settings.include_blog_feeds,
        blog_days_back=settings.blog_days_back,
    )
    articles = await fetcher.fetch_all()
    total_fetched = len(articles)
    substep_timings["source_news_fetch"] = round(time.time() - t0, 2)
    logger.info("[NEWS] Fetched %d articles in %.1fs", total_fetched, time.time() - t0)

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

    # Step 2: Embedding pre-filter (if enabled and enough articles)
    embedding_input_tokens = 0
    embedding_model = ""
    embedding_cost_usd = 0.0
    articles_after_embedding = len(articles)

    if settings.embedding_enabled and len(articles) > settings.embedding_top_k:
        t1 = time.time()
        logger.info(
            "[EMBEDDING] Pre-filtering %d articles to top %d...",
            len(articles),
            settings.embedding_top_k,
        )
        embedding_filter = EmbeddingPreFilter(
            model=settings.embedding_model,
            top_k=settings.embedding_top_k,
            batch_size=settings.embedding_batch_size,
        )
        embedding_result = await embedding_filter.filter_articles(articles, company_context)
        articles = embedding_result.articles
        embedding_input_tokens = embedding_result.input_tokens
        embedding_model = embedding_result.model
        embedding_cost_usd = embedding_result.cost_usd
        articles_after_embedding = len(articles)
        substep_timings["source_embedding_filter"] = round(time.time() - t1, 2)
        logger.info(
            "[EMBEDDING] Done in %.1fs — %d articles remaining",
            time.time() - t1,
            len(articles),
        )

    # Step 2.5: Exclude previously used article URLs
    if exclude_urls and articles:
        articles_before_exclusion = articles
        articles = [a for a in articles if a.link not in exclude_urls]
        excluded_count = len(articles_before_exclusion) - len(articles)
        if excluded_count > 0:
            logger.info("[NEWS] Excluded %d previously used articles, %d remaining", excluded_count, len(articles))
        if not articles:
            logger.warning("[NEWS] All articles were previously used — re-including them as fallback")
            articles = articles_before_exclusion

    # Step 3: AI filter (Gemini Flash) to pick the most relevant article
    t2 = time.time()
    logger.info("[NEWS] AI filtering %d articles with Gemini Flash...", len(articles))
    news_filter = BatchNewsFilter(company_context=company_context)
    filter_result = await news_filter.filter_articles(articles, max_results=1)
    substep_timings["source_ai_filter"] = round(time.time() - t2, 2)
    logger.info(
        "[NEWS] Filtered to %d articles in %.1fs",
        len(filter_result.articles),
        time.time() - t2,
    )

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
                url=item.article.link,
            ),
            filter_input_tokens=filter_result.input_tokens,
            filter_output_tokens=filter_result.output_tokens,
            filter_model=filter_result.model,
            embedding_input_tokens=embedding_input_tokens,
            embedding_model=embedding_model,
            embedding_cost_usd=embedding_cost_usd,
            total_articles_fetched=total_fetched,
            articles_after_embedding=articles_after_embedding,
            timings=substep_timings,
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
        embedding_input_tokens=embedding_input_tokens,
        embedding_model=embedding_model,
        embedding_cost_usd=embedding_cost_usd,
        total_articles_fetched=total_fetched,
        articles_after_embedding=articles_after_embedding,
        timings=substep_timings,
    )


def _save_run_artifacts(
    run_dir: Path,
    *,
    target_url: str,
    message: str,
    source_text: str,
    persona: str,
    num_generators: int,
    generation_model: str,
    auto_summarize_enabled: bool,
    company_context: CompanyContext,
    source_content: SourceContent,
    source_raw: Optional[dict],
    auto_summarize_result: Optional[dict],
    effective_message: str,
    all_variants: list[GeneratedVariant],
    filtered_variants: list[GeneratedVariant],
    slop_validations: list[dict],
    creativity_contexts: list[dict],
    judgment: JudgmentResult,
    carousel_html: str,
    carousel_id: str,
    stats: dict,
    costs: dict,
    timings: dict,
    run_start: datetime,
) -> Path:
    """Save all pipeline artifacts to a timestamped run directory. Never raises."""
    try:
        run_dir.mkdir(parents=True, exist_ok=True)

        def _write_json(filename: str, data: Any) -> None:
            try:
                (run_dir / filename).write_text(
                    json.dumps(data, indent=2, default=str, ensure_ascii=False)
                )
            except Exception as e:
                logger.warning("[ARTIFACTS] Failed to write %s: %s", filename, e)

        def _write_text(filename: str, text: str) -> None:
            try:
                (run_dir / filename).write_text(text, encoding="utf-8")
            except Exception as e:
                logger.warning("[ARTIFACTS] Failed to write %s: %s", filename, e)

        timestamp = run_start.strftime("%Y-%m-%d_%H-%M-%S")

        # 1. run_metadata.json
        _write_json("run_metadata.json", {
            "run_id": f"web_{timestamp}",
            "timestamp": run_start.isoformat(),
            "timestamp_human": run_start.strftime("%Y-%m-%d %H:%M:%S"),
            "pipeline": "web",
            "request": {
                "target_url": target_url,
                "message": message,
                "effective_message": effective_message,
                "source_mode": _source_mode,
                "persona": persona,
                "num_generators": num_generators,
                "generation_model": generation_model,
                "auto_summarize_enabled": auto_summarize_enabled,
            },
            "results_summary": {
                "total_variants": len(all_variants),
                "filtered_variants": len(filtered_variants),
                "winner_score": judgment.winner_score.weighted_total if judgment.winner_score else None,
                "winner_persona": judgment.winner.persona,
            },
        })

        # 2. company_profile.json
        _write_json("company_profile.json", company_context.to_dict())

        # 3. source_content.json
        _write_json("source_content.json", {
            "title": source_content.title,
            "source": source_content.source,
            "summary": source_content.summary,
            "suggested_angle": source_content.suggested_angle,
            "company_connection": source_content.company_connection,
            "target_icp": source_content.target_icp,
        })

        # 4. source_raw.json
        if source_raw:
            _write_json("source_raw.json", source_raw)

        # 5. auto_summarize.json
        if auto_summarize_result:
            _write_json("auto_summarize.json", auto_summarize_result)
        else:
            _write_json("auto_summarize.json", {
                "skipped": True,
                "reason": "message provided by user or auto-summarize disabled",
            })

        # 6. all_variants.json
        _write_json("all_variants.json", {
            "total": len(all_variants),
            "creativity_contexts": creativity_contexts,
            "variants": [
                {
                    "content": v.content,
                    "persona": v.persona,
                    "hook_type": v.hook_type,
                    "structure_used": v.structure_used,
                    "generator_id": v.generator_id,
                    "variant_id": v.variant_id,
                    "what_makes_it_different": v.what_makes_it_different,
                }
                for v in all_variants
            ],
        })

        # 7. filtered_variants.json
        _write_json("filtered_variants.json", {
            "total": len(filtered_variants),
            "variants": [
                {
                    "content": v.content,
                    "persona": v.persona,
                    "hook_type": v.hook_type,
                    "structure_used": v.structure_used,
                    "generator_id": v.generator_id,
                    "variant_id": v.variant_id,
                    "what_makes_it_different": v.what_makes_it_different,
                }
                for v in filtered_variants
            ],
        })

        # 8. slop_validation.json
        _write_json("slop_validation.json", {
            "total_variants": len(slop_validations),
            "passed": sum(1 for v in slop_validations if v["is_valid"]),
            "failed": sum(1 for v in slop_validations if not v["is_valid"]),
            "validations": slop_validations,
        })

        # 9. judgment.json
        _write_json("judgment.json", {
            "total_variants_judged": judgment.total_variants_judged,
            "winner_reasoning": judgment.winner_reasoning,
            "improvement_notes": judgment.improvement_notes,
            "all_scores": [
                {
                    "generator_id": s.generator_id,
                    "variant_id": s.variant_id,
                    "hook_strength": s.hook_strength,
                    "anti_slop": s.anti_slop,
                    "distinctiveness": s.distinctiveness,
                    "relevance": s.relevance,
                    "persona_fit": s.persona_fit,
                    "weighted_total": s.weighted_total,
                    "notes": s.notes,
                }
                for s in judgment.all_scores
            ],
        })

        # 10. winner.json
        winner = judgment.winner
        ws = judgment.winner_score
        _write_json("winner.json", {
            "content": winner.content,
            "persona": winner.persona,
            "hook_type": winner.hook_type,
            "structure_used": winner.structure_used,
            "generator_id": winner.generator_id,
            "variant_id": winner.variant_id,
            "what_makes_it_different": winner.what_makes_it_different,
            "score": {
                "hook_strength": ws.hook_strength,
                "anti_slop": ws.anti_slop,
                "distinctiveness": ws.distinctiveness,
                "relevance": ws.relevance,
                "persona_fit": ws.persona_fit,
                "weighted_total": ws.weighted_total,
            } if ws else None,
        })

        # 11. winner.md
        score_table = ""
        if ws:
            score_table = f"""
## Scores

| Criterion | Score |
|-----------|-------|
| Hook Strength | {ws.hook_strength}/10 |
| Anti-Slop | {ws.anti_slop}/10 |
| Distinctiveness | {ws.distinctiveness}/10 |
| Relevance | {ws.relevance}/10 |
| Persona Fit | {ws.persona_fit}/10 |
| **Weighted Total** | **{ws.weighted_total:.1f}/10** |
"""
        _write_text("winner.md", f"""# LinkedIn Post - {run_start.strftime('%Y-%m-%d %H:%M')}

## Source
**Title:** {source_content.title}
**Source:** {source_content.source}
**Summary:** {source_content.summary}
**Angle:** {source_content.suggested_angle}

---

## Winning Post

**Persona:** {winner.persona} | **Hook:** {winner.hook_type} | **Structure:** {winner.structure_used}

---

{winner.content}

---
{score_table}
## Judge Reasoning

{judgment.winner_reasoning}

## Improvement Notes

{judgment.improvement_notes or 'None'}
""")

        # 12. carousel.html
        _write_text("carousel.html", carousel_html)

        # 13. costs.json
        _write_json("costs.json", costs)

        # 14. timings.json
        _write_json("timings.json", {
            "total_duration_seconds": stats.get("duration_seconds", 0),
            "steps": timings,
        })

        # 15. stats.json
        _write_json("stats.json", stats)

        logger.info("[ARTIFACTS] Saved %d artifact files to %s", 15, run_dir)

    except Exception as e:
        logger.warning("[ARTIFACTS] Failed to save run artifacts: %s", e)

    return run_dir


async def run_pipeline(
    target_url: str,
    message: str = "",
    source_text: str = "auto",
    persona: str = "professional",
    num_generators: int = 5,
    generation_model: str = "gemini/gemini-3-pro-preview",
    auto_summarize: bool = True,
    company_context: Optional[CompanyContext] = None,
    exclude_urls: Optional[set[str]] = None,
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
    timings = {}  # step_name -> duration_seconds

    # Artifact capture accumulators
    _artifact_source_raw = None
    _artifact_auto_summarize = None
    _artifact_creativity_contexts = []
    _artifact_slop_validations = []
    _resolved_source_text = None  # URL-resolved content for carousel (Step 9)
    _source_mode = "auto"  # Will be updated in Step 2

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
    timings["scrape_metadata"] = round(time.time() - t0, 2)
    logger.info("[STEP 1] Done in %.1fs — domain=%s", time.time() - t0, website_metadata.domain)

    # Step 2: Resolve source content
    t0 = time.time()
    logger.info("[STEP 2] Resolving source content (mode=%s)", "auto" if source_text.strip().lower() == "auto" else "pasted")
    if source_text.strip().lower() == "auto":
        auto_result = await fetch_auto_source(client, company_context=company_context, exclude_urls=exclude_urls)
        source = auto_result.content
        timings.update(auto_result.timings)
        # Capture raw source artifact
        _artifact_source_raw = {
            "mode": "auto",
            "total_articles_fetched": auto_result.total_articles_fetched,
            "articles_after_embedding": auto_result.articles_after_embedding,
            "filter_model": auto_result.filter_model,
            "filter_input_tokens": auto_result.filter_input_tokens,
            "filter_output_tokens": auto_result.filter_output_tokens,
            "embedding_model": auto_result.embedding_model,
            "embedding_input_tokens": auto_result.embedding_input_tokens,
            "embedding_cost_usd": auto_result.embedding_cost_usd,
            "substep_timings": auto_result.timings,
        }
        # Track embedding pre-filter costs
        if auto_result.embedding_model:
            costs.add_usage(
                "embedding_prefilter",
                auto_result.embedding_model,
                auto_result.embedding_input_tokens,
                0,  # No output tokens for embeddings
                auto_result.embedding_cost_usd,
            )
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
        # Check if pasted text is a single URL
        detected_url = detect_url(source_text)
        _source_mode = "paste"

        if detected_url:
            logger.info("[STEP 2] Detected URL in pasted text: %s", detected_url)
            url_result = await resolve_url(detected_url)

            if url_result.success and url_result.content:
                _source_mode = f"url_{url_result.url_type}"
                _resolved_source_text = url_result.content
                logger.info("[STEP 2] URL resolved: type=%s, %d chars", url_result.url_type, len(url_result.content))

                # Track URL resolution costs (YouTube uses LLM)
                if url_result.model:
                    costs.add_usage(
                        "url_resolution",
                        url_result.model,
                        url_result.input_tokens,
                        url_result.output_tokens,
                        url_result.cost_usd,
                    )

                # Use resolved content for analysis
                analysis_text = url_result.content
            else:
                logger.warning("[STEP 2] URL resolution failed: %s — falling back to raw text", url_result.error)
                analysis_text = source_text
        else:
            analysis_text = source_text

        analysis_result = await analyze_source_text(client, analysis_text, message)
        source = analysis_result.content

        # Set source URL if we detected one
        if detected_url and _resolved_source_text:
            source.url = detected_url

        # Capture raw source artifact
        _artifact_source_raw = {
            "mode": _source_mode,
            "pasted_text": source_text,
            "detected_url": detected_url,
            "analysis_model": analysis_result.model,
            "analysis_input_tokens": analysis_result.input_tokens,
            "analysis_output_tokens": analysis_result.output_tokens,
        }
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
    timings["resolve_source"] = round(time.time() - t0, 2)
    logger.info("[STEP 2] Done in %.1fs — title=%s", time.time() - t0, source.title[:50])

    # Step 3: Auto-summarize message if empty (and enabled)
    effective_message = message
    if not effective_message.strip() and auto_summarize:
        t0 = time.time()
        logger.info("[STEP 3] Auto-summarizing message with Sonnet...")
        summarize_result = await auto_summarize_message(client, source.summary)
        effective_message = summarize_result.message
        # Capture auto-summarize artifact
        _artifact_auto_summarize = {
            "original_text": source.summary,
            "generated_message": summarize_result.message,
            "model": summarize_result.model,
            "input_tokens": summarize_result.input_tokens,
            "output_tokens": summarize_result.output_tokens,
        }
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
        timings["auto_summarize"] = round(time.time() - t0, 2)
        logger.info("[STEP 3] Done in %.1fs — message=%s", time.time() - t0, effective_message[:50])
    elif not effective_message.strip():
        logger.info("[STEP 3] Auto-summarize disabled, using source summary as message")
        effective_message = source.summary[:100]

    # Step 4: Load configs
    t0 = time.time()
    personas_data = _load_personas()
    company_profile = company_context.to_generator_prompt()
    anti_slop = AntiSlopValidator()

    creativity_engine = CreativityEngine(
        config_path=_CONFIG_DIR / "creativity.yaml",
        data_dir=_DATA_DIR,
        anti_slop_rules=anti_slop.get_rules_for_prompt(),
    )

    persona_config = personas_data.get(persona, personas_data.get("professional", {}))
    timings["load_configs"] = round(time.time() - t0, 2)

    # Step 5: Create generators — ALL same persona, different creativity contexts
    t0 = time.time()
    use_litellm = generation_model.startswith("gemini/")
    logger.info("[STEP 5] Creating %d generators with %s (litellm=%s)...",
                num_generators, generation_model, use_litellm)
    generation_tasks = []
    for i in range(num_generators):
        creativity_ctx = creativity_engine.generate_context(persona)

        # Capture creativity context artifact
        _artifact_creativity_contexts.append({
            "generator_id": i,
            "persona": creativity_ctx.persona,
            "hook_pattern": creativity_ctx.hook_pattern,
            "hook_description": creativity_ctx.hook_description,
            "structure": creativity_ctx.structure,
            "structure_description": creativity_ctx.structure_description,
            "style_reference": creativity_ctx.style_reference[:200] if creativity_ctx.style_reference else None,
            "tone_wildcard": creativity_ctx.tone_wildcard,
            "structural_break": creativity_ctx.structural_break,
            "content_angle": creativity_ctx.content_angle,
            "mutation_seed": creativity_ctx.mutation_seed,
        })

        if use_litellm:
            # Use LiteLLM for Gemini and other non-Anthropic models
            generator = LiteLLMGeneratorAgent(
                model_id=generation_model,
                generator_id=i,
                persona_config=persona_config,
                company_name=company_context.name,
                company_profile=company_profile,
            )
        else:
            # Use Anthropic SDK for Claude models
            generator = GeneratorAgent(
                client=client,
                generator_id=i,
                persona_config=persona_config,
                company_name=company_context.name,
                company_profile=company_profile,
                model_id=generation_model,
            )

        logger.info("[STEP 5]   Generator %d: hook=%s, structure=%s",
                    i, creativity_ctx.hook_pattern, creativity_ctx.structure)
        generation_tasks.append(
            generator.execute(source, creativity_ctx, num_variants=1)
        )

    # Run all generators in parallel
    logger.info("[STEP 5] Running %d generators in parallel...", num_generators)
    all_results = await asyncio.gather(*generation_tasks, return_exceptions=True)
    timings["generation"] = round(time.time() - t0, 2)
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
        # Capture per-variant slop validation artifact
        _artifact_slop_validations.append({
            "generator_id": variant.generator_id,
            "variant_id": variant.variant_id,
            "is_valid": validation.is_valid,
            "score": validation.score,
            "violations": validation.violations,
            "warnings": validation.warnings,
        })
        if validation.is_valid:
            filtered_variants.append(variant)
        else:
            slop_violations += 1

    # Fallback if all variants fail anti-slop
    if not filtered_variants:
        logger.warning("[STEP 7] All variants failed! Using fallback (top 10)")
        filtered_variants = all_variants[:10]
    timings["anti_slop"] = round(time.time() - t0, 2)
    logger.info("[STEP 7] Done in %.1fs — %d passed, %d rejected", time.time() - t0, len(filtered_variants), slop_violations)

    # Step 8: Judge picks the winner
    t0 = time.time()
    judge_model = generation_model
    logger.info("[STEP 8] Judge evaluating %d variants with %s...", len(filtered_variants), judge_model)
    source_context = f"Title: {source.title}\nSummary: {source.summary}"

    if use_litellm:
        judge = LiteLLMJudgeAgent(
            model_id=judge_model,
            anti_slop_rules=anti_slop.get_rules_for_prompt(),
        )
    else:
        judge = JudgeAgent(
            client=client,
            anti_slop_rules=anti_slop.get_rules_for_prompt(),
            model_id=judge_model,
        )

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
    timings["judge"] = round(time.time() - t0, 2)
    logger.info("[STEP 8] Done in %.1fs — winner score=%.2f", time.time() - t0,
                judgment.winner_score.weighted_total if judgment.winner_score else 0)

    # Step 9: Generate carousel HTML (PDF rendered on-demand)
    t0 = time.time()
    logger.info("[STEP 9] Generating carousel HTML...")
    # Use the full source text for carousel extraction (richer content)
    # For URL-resolved sources, use the resolved content instead of the raw URL
    if source_text.strip().lower() != "auto" and _resolved_source_text:
        carousel_source = _resolved_source_text
    elif source_text.strip().lower() != "auto":
        carousel_source = source_text
    else:
        # For auto mode, scrape the actual article content using Playwright
        carousel_source = ""
        if source.url:
            logger.info("[STEP 9] Scraping article content from %s", source.url)
            article_content = await scrape_article_content(source.url)
            if article_content.success and article_content.content:
                carousel_source = f"""Title: {article_content.title or source.title}

{article_content.content}

Key Angle: {source.suggested_angle}

Business Connection: {source.company_connection}"""
                logger.info("[STEP 9] Scraped %d chars of article content", len(article_content.content))
            else:
                logger.warning("[STEP 9] Article scraping failed: %s", article_content.error)

        # Fallback to metadata-based source if scraping failed
        if not carousel_source:
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
    timings["carousel"] = round(time.time() - t0, 2)
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
        "timings": timings,
    }

    # Get cost breakdown
    costs_dict = costs.to_dict()
    logger.info("=" * 60)
    logger.info("[PIPELINE] Complete! Total duration: %.1fs", total_duration)
    logger.info("[PIPELINE] Stats: %s", stats)
    logger.info("[PIPELINE] Total cost: $%.4f", costs_dict["total_cost_usd"])

    # Save all run artifacts to disk
    timestamp = run_start.strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = _RUNS_DIR / timestamp
    _save_run_artifacts(
        run_dir,
        target_url=target_url,
        message=message,
        source_text=source_text,
        persona=persona,
        num_generators=num_generators,
        generation_model=generation_model,
        auto_summarize_enabled=auto_summarize,
        company_context=company_context,
        source_content=source,
        source_raw=_artifact_source_raw,
        auto_summarize_result=_artifact_auto_summarize,
        effective_message=effective_message,
        all_variants=all_variants,
        filtered_variants=filtered_variants,
        slop_validations=_artifact_slop_validations,
        creativity_contexts=_artifact_creativity_contexts,
        judgment=judgment,
        carousel_html=carousel_result.html,
        carousel_id=carousel_result.carousel_id,
        stats=stats,
        costs=costs_dict,
        timings=timings,
        run_start=run_start,
    )

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
        source_mode=_source_mode,
    )


def _load_personas() -> dict:
    """Load persona configurations."""
    personas_path = _CONFIG_DIR / "personas.yaml"
    with open(personas_path) as f:
        data = yaml.safe_load(f)
    return data.get("personas", {})
