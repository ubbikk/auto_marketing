# Performance Analysis: Pipeline Bottlenecks

## Summary

The content generation pipeline takes 3-5 minutes for a full run. The primary bottleneck is **sequential news filtering**, which accounts for 60-70% of total runtime.

## Findings (Feb 2025)

### Pipeline Timing Breakdown

Based on production logging, here's where time is spent:

| Step | Operation | Duration | % of Total |
|------|-----------|----------|------------|
| 1 | Website scraping | ~0.2s | <1% |
| 2 | News fetch + filter | **150s** | **65-70%** |
| 3 | Message summarization | ~2.5s | 1% |
| 5 | 5x Opus generators (parallel) | ~40-60s | 20-25% |
| 7 | Anti-slop validation | <0.5s | <1% |
| 8 | Judge evaluation (Opus) | ~20-30s | 10-15% |
| 9 | Carousel PDF generation | ~5-10s | 3-5% |

**Total: ~220-250s (3.5-4 minutes)**

### The Bottleneck: Sequential News Filtering

Location: `src/news/filter.py:84-87`

```python
for article in articles:
    scored = await self._score_article(article)
    if scored and scored.relevance_score >= self.relevance_threshold:
        filtered.append(scored)
```

The problem:
- Fetches ~35 articles from RSS feeds
- Each article requires a Claude Sonnet API call (~4s each)
- **Processed sequentially**: 35 articles × 4s = 140-150s

### Potential Optimization

Parallelize the news filtering with `asyncio.gather()`:

```python
async def filter_articles(self, articles: list[NewsArticle], max_results: int = 5):
    if not articles:
        return []

    # Process ALL articles in parallel
    tasks = [self._score_article(article) for article in articles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter valid results
    filtered = [
        r for r in results
        if isinstance(r, FilteredNewsItem) and r.relevance_score >= self.relevance_threshold
    ]

    filtered.sort(key=lambda x: x.relevance_score, reverse=True)
    return filtered[:max_results]
```

**Expected improvement**: 150s → ~5-8s (parallel Sonnet calls)

### Other Observations

1. **Opus generators already parallelized** - 5 generators run via `asyncio.gather()`, which is correct

2. **Sync vs Async client issue** (fixed) - The Anthropic client in FastAPI was blocking the event loop. Fixed with `run_in_executor()` pattern.

3. **JSON parsing robustness** (fixed) - LLM responses sometimes include markdown fences around JSON. Added extraction logic to handle ````json` blocks.

## Recommendations

1. **High Impact**: Parallelize news filtering in `src/news/filter.py`
   - Effort: Low (one function change)
   - Impact: Save ~145s per run

2. **Medium Impact**: Add caching for news articles
   - RSS feeds don't change every minute
   - Cache filtered results for 15-30 minutes

3. **Low Impact**: Consider Haiku for news filtering
   - Currently uses Sonnet for cost balance
   - Haiku would be faster but may have lower quality scores

## Logging

Comprehensive logging was added to `src/app/pipeline.py` with timing for each step:

```
18:06:04 INFO [PIPELINE] Starting generation for persona=ai_meta
18:06:04 INFO [STEP 1] Scraping website metadata from https://afta.systems
18:06:04 INFO [STEP 1] Done in 0.2s — domain=afta.systems
18:06:04 INFO [STEP 2] Resolving source content (mode=auto)
18:06:04 INFO [NEWS] Fetching RSS feeds...
18:06:05 INFO [NEWS] Fetched 35 articles in 0.7s
18:06:05 INFO [NEWS] Filtering articles with Sonnet...
18:08:36 INFO [NEWS] Filtered to 1 articles in 150.4s   <-- BOTTLENECK
...
```
