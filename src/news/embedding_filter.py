"""Embedding-based pre-filter using Vertex AI embeddings for semantic similarity.

Uses Vertex AI's text-embedding-005 model via LiteLLM to calculate semantic
similarity between the company profile and news articles, filtering to the
most relevant articles before the more expensive AI filter step.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import litellm
import numpy as np

if TYPE_CHECKING:
    from ..company.profile import CompanyContext
    from .models import NewsArticle

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result from embedding pre-filter."""

    articles: list  # List of NewsArticle
    total_articles: int  # Original count before filtering
    input_tokens: int
    model: str
    cost_usd: float


class EmbeddingPreFilter:
    """
    Pre-filters articles using semantic similarity to company profile.

    Uses Vertex AI embeddings via LiteLLM to:
    1. Embed the company context (name, tagline, offering, audience, etc.)
    2. Embed each article (title + summary)
    3. Calculate cosine similarity
    4. Return top K most similar articles
    """

    def __init__(
        self,
        model: str = "vertex_ai/text-embedding-005",
        top_k: int = 20,
        batch_size: int = 100,
    ):
        """
        Initialize embedding pre-filter.

        Args:
            model: LiteLLM embedding model name (e.g., vertex_ai/text-embedding-005)
            top_k: Number of top articles to return
            batch_size: Maximum embeddings per API call
        """
        self.model = model
        self.top_k = top_k
        self.batch_size = batch_size

    def _build_company_text(self, company_context: "CompanyContext") -> str:
        """Build text representation of company for embedding."""
        parts = [
            company_context.name,
            company_context.tagline,
            company_context.core_offering,
            company_context.differentiator,
        ]

        # Add target audience
        if company_context.target_audience:
            parts.extend(company_context.target_audience)

        # Add pain points (key for relevance)
        if company_context.pain_points_solved:
            parts.extend(company_context.pain_points_solved)

        # Add industry keywords
        if company_context.industry_keywords:
            parts.extend(company_context.industry_keywords)

        return " ".join(filter(None, parts))

    def _build_article_text(self, article: "NewsArticle") -> str:
        """Build text representation of article for embedding."""
        # Combine title and summary for richer context
        parts = [article.title]
        if article.summary:
            # Truncate summary to reasonable length
            parts.append(article.summary[:500])
        return " ".join(parts)

    async def _get_embeddings(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """
        Get embeddings for a list of texts using LiteLLM.

        Args:
            texts: List of texts to embed

        Returns:
            Tuple of (embeddings, total_tokens)
        """
        embeddings = []
        total_tokens = 0

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]

            # Run embedding in thread pool since litellm.embedding is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda b=batch: litellm.embedding(
                    model=self.model,
                    input=b,
                ),
            )

            # Extract embeddings from LiteLLM response
            for item in response.data:
                embeddings.append(item["embedding"])

            # Track tokens from usage
            if response.usage:
                total_tokens += response.usage.prompt_tokens

        return embeddings, total_tokens

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    async def filter_articles(
        self,
        articles: list,
        company_context: "CompanyContext",
    ) -> EmbeddingResult:
        """
        Filter articles by semantic similarity to company context.

        Args:
            articles: List of NewsArticle to filter
            company_context: Company context for similarity comparison

        Returns:
            EmbeddingResult with top K most relevant articles
        """
        if not articles:
            return EmbeddingResult(
                articles=[],
                total_articles=0,
                input_tokens=0,
                model=self.model,
                cost_usd=0.0,
            )

        total_articles = len(articles)

        # If we have fewer articles than top_k, skip embedding
        if len(articles) <= self.top_k:
            logger.info(
                "[EMBEDDING] Skipping filter: %d articles <= top_k=%d",
                len(articles),
                self.top_k,
            )
            return EmbeddingResult(
                articles=articles,
                total_articles=total_articles,
                input_tokens=0,
                model=self.model,
                cost_usd=0.0,
            )

        logger.info(
            "[EMBEDDING] Filtering %d articles to top %d using %s...",
            len(articles),
            self.top_k,
            self.model,
        )

        # Build texts for embedding
        company_text = self._build_company_text(company_context)
        article_texts = [self._build_article_text(a) for a in articles]

        # Get all embeddings in one batch (company + all articles)
        all_texts = [company_text] + article_texts
        embeddings, total_tokens = await self._get_embeddings(all_texts)

        if len(embeddings) < len(all_texts):
            logger.warning(
                "[EMBEDDING] Got fewer embeddings (%d) than texts (%d), falling back to original articles",
                len(embeddings),
                len(all_texts),
            )
            return EmbeddingResult(
                articles=articles[: self.top_k],
                total_articles=total_articles,
                input_tokens=total_tokens,
                model=self.model,
                cost_usd=self._calculate_cost(total_tokens),
            )

        company_embedding = embeddings[0]
        article_embeddings = embeddings[1:]

        # Calculate similarities
        similarities = []
        for i, article_emb in enumerate(article_embeddings):
            if i < len(articles):
                sim = self._cosine_similarity(company_embedding, article_emb)
                similarities.append((i, sim, articles[i]))

        # Sort by similarity (descending) and take top K
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_articles = [item[2] for item in similarities[: self.top_k]]

        # Log similarity distribution
        if similarities:
            top_sim = similarities[0][1]
            cutoff_sim = (
                similarities[self.top_k - 1][1]
                if len(similarities) >= self.top_k
                else similarities[-1][1]
            )
            bottom_sim = similarities[-1][1]
            logger.info(
                "[EMBEDDING] Similarity range: %.3f - %.3f, cutoff: %.3f",
                bottom_sim,
                top_sim,
                cutoff_sim,
            )

        cost_usd = self._calculate_cost(total_tokens)

        return EmbeddingResult(
            articles=top_articles,
            total_articles=total_articles,
            input_tokens=total_tokens,
            model=self.model,
            cost_usd=cost_usd,
        )

    def _calculate_cost(self, input_tokens: int) -> float:
        """Calculate cost for embedding API call.

        Vertex AI embedding pricing (as of 2024):
        - text-embedding-005: $0.000025 per 1K characters (roughly $0.0001 per 1K tokens)
        We use a conservative estimate based on tokens.
        """
        # Vertex AI charges per character, but we track tokens
        # Rough estimate: 1 token ~= 4 chars, so ~$0.0001 per 1K tokens
        price_per_1k = 0.0001
        return (input_tokens / 1000) * price_per_1k
