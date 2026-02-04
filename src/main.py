#!/usr/bin/env python3
"""
Multi-Agent LinkedIn Content Generation Pipeline

Entry point for the auto-marketing system.
Fetches news, generates content variants, judges quality, outputs winner.

Usage:
    python -m src.main                    # Full pipeline
    python -m src.main --quick            # Quick mode (fewer feeds)
    python -m src.main --generators 5     # Custom generator count
    python -m src.main --news-only        # Just fetch and filter news
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

import anthropic

from .agents.orchestrator import Orchestrator
from .config.settings import settings
from .news.fetcher import NewsFetcher
from .news.batch_filter import BatchNewsFilter
from .news.embedding_filter import EmbeddingPreFilter
from .company.profile import load_default_context
from .output.formatter import OutputFormatter


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-agent LinkedIn content generation pipeline"
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: fewer feeds, faster execution",
    )

    parser.add_argument(
        "--generators",
        type=int,
        default=settings.num_generators,
        help=f"Number of generator agents (default: {settings.num_generators})",
    )

    parser.add_argument(
        "--news-only",
        action="store_true",
        help="Only fetch and filter news, skip generation",
    )

    parser.add_argument(
        "--news-index",
        type=int,
        default=0,
        help="Index of filtered news item to use (default: 0 = top)",
    )

    parser.add_argument(
        "--hours-back",
        type=int,
        default=settings.news_hours_back,
        help=f"Hours back to fetch news (default: {settings.news_hours_back})",
    )

    parser.add_argument(
        "--blog-days",
        type=int,
        default=settings.blog_days_back,
        help=f"Days back for blog posts (default: {settings.blog_days_back})",
    )

    parser.add_argument(
        "--include-blogs",
        action="store_true",
        default=settings.include_blog_feeds,
        help="Include blog feeds from OPML file",
    )

    parser.add_argument(
        "--no-embedding",
        action="store_true",
        help="Disable embedding pre-filter",
    )

    parser.add_argument(
        "--embedding-top-k",
        type=int,
        default=settings.embedding_top_k,
        help=f"Articles to keep after embedding filter (default: {settings.embedding_top_k})",
    )

    return parser.parse_args()


async def fetch_news(args: argparse.Namespace, client: anthropic.Anthropic) -> list:
    """Fetch and filter news articles."""
    print("\n📰 Fetching news...")

    fetcher = NewsFetcher(
        hours_back=args.hours_back,
        blog_days_back=args.blog_days,
        quick_mode=args.quick,
        include_blogs=args.include_blogs,
    )

    articles = await fetcher.fetch_all()
    print(f"   Found {len(articles)} articles from last {args.hours_back} hours (news) / {args.blog_days} days (blogs)")

    if not articles:
        print("   No articles found. Try increasing --hours-back or --blog-days")
        return []

    # Embedding pre-filter (if enabled and enough articles)
    if not args.no_embedding and len(articles) > args.embedding_top_k:
        print(f"\n🔮 Embedding pre-filter: {len(articles)} -> top {args.embedding_top_k}...")
        company_context = load_default_context()
        embedding_filter = EmbeddingPreFilter(
            model=settings.embedding_model,
            top_k=args.embedding_top_k,
        )
        embedding_result = await embedding_filter.filter_articles(articles, company_context)
        articles = embedding_result.articles
        print(f"   Pre-filtered to {len(articles)} articles (cost: ${embedding_result.cost_usd:.4f})")

    print("\n🔍 AI filtering for relevance...")
    news_filter = BatchNewsFilter()
    filter_result = await news_filter.filter_articles(articles, max_results=5)
    filtered = filter_result.articles

    print(f"   {len(filtered)} relevant articles found\n")

    for i, item in enumerate(filtered):
        print(f"   {i + 1}. [{item.relevance_score:.0%}] {item.article.title[:60]}...")
        print(f"      Angle: {item.suggested_angle[:50]}...")

    return filtered


async def run_pipeline(
    args: argparse.Namespace,
    client: anthropic.Anthropic,
    filtered_news: list,
) -> None:
    """Run the full generation pipeline."""
    if not filtered_news:
        print("\n❌ No relevant news to generate content for")
        return

    # Select news item
    if args.news_index >= len(filtered_news):
        args.news_index = 0

    news_item = filtered_news[args.news_index]
    print(f"\n📝 Generating content for: {news_item.article.title[:50]}...")

    # Initialize orchestrator
    orchestrator = Orchestrator(
        client=client,
        config_dir=settings.config_dir,
        data_dir=settings.data_dir,
        num_generators=args.generators,
        model_id=settings.model_id,
    )

    print(f"\n🤖 Running {args.generators} generators in parallel...")
    print("   This may take 1-2 minutes with Opus 4.5...\n")

    # Run pipeline
    result = await orchestrator.run(news_item)

    # Output results
    print(f"\n✅ Generation complete!")
    print(f"   Total variants: {result.stats['total_variants']}")
    print(f"   Slop filtered: {result.stats['slop_violations']}")
    print(f"   Duration: {result.stats['duration_seconds']:.1f}s")

    # Save outputs
    formatter = OutputFormatter(settings.output_dir)
    run_dir = formatter.save_run(result)

    print(f"\n📁 Output saved to: {run_dir}")

    # Print winner
    print("\n" + "=" * 60)
    print("🏆 WINNING POST")
    print("=" * 60)
    print(f"\nPersona: {result.judgment.winner.persona}")
    if result.judgment.winner_score:
        print(f"Score: {result.judgment.winner_score.weighted_total:.1f}/10")
    print(f"\n{result.judgment.winner.content}")
    print("\n" + "=" * 60)

    if result.judgment.improvement_notes:
        print(f"\n💡 Suggested improvement: {result.judgment.improvement_notes}")


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Validate API key
    if not settings.anthropic_api_key:
        print("❌ ANTHROPIC_API_KEY not set in .env file")
        return 1

    # Initialize client
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    print("=" * 60)
    print("🚀 AFTA LinkedIn Content Generator")
    print("=" * 60)
    print(f"Model: {settings.model_id}")
    print(f"Generators: {args.generators}")
    print(f"Mode: {'Quick' if args.quick else 'Full'}")

    # Fetch news
    filtered_news = await fetch_news(args, client)

    if args.news_only:
        print("\n--news-only flag set, skipping generation")
        return 0

    # Run pipeline
    await run_pipeline(args, client, filtered_news)

    return 0


def cli() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    cli()
