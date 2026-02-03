# CLAUDE.md

## Project overview

Auto-Marketing is a multi-agent LinkedIn content generation system for AFTA Systems (e-commerce automation company). It fetches news, generates post variants using different personas/hooks/frameworks, filters out AI slop, and selects the best variant via a judge agent.

Early-stage project — currently implements the creativity engine and news-to-post pipeline. Includes a LinkedIn carousel slide template (`output/carousel_template.html`) matching the afta.systems brand for visual content.

## Build and run

```bash
# Install
pip install -e ".[dev]"

# Run full pipeline (CLI)
python -m src.main

# Quick mode (2 feeds only)
python -m src.main --quick

# News fetch only
python -m src.main --news-only

# Web UI (FastAPI)
python -m src.app.main
# Then open http://localhost:8000
```

Requires `ANTHROPIC_API_KEY` in environment or `.env` file.

## Tests

```bash
pytest
```

Uses `pytest-asyncio` with `asyncio_mode = "auto"`.

## Architecture

**Pipeline**: News Fetch → Sonnet Filter → Parallel Generation (Opus) → Anti-Slop Validation → Judge → Winner

Key directories:
- `src/app/` — FastAPI web application (main.py, pipeline.py, scraper.py)
- `src/agents/` — Base agent, generator, judge, orchestrator
- `src/carousel/` — Carousel PDF generation (extractor, renderer, service)
- `src/config/` — Settings, personas.yaml, creativity.yaml
- `src/creativity/` — Creativity engine (randomized context) and anti-slop validator
- `src/news/` — RSS fetcher and relevance filter
- `src/output/` — Result formatter (CLI output)
- `data/` — Few-shot examples, hook templates, banned words list
- `static/` — Web UI static files (HTML, CSS, JS)
- `output/runs/` — Timestamped run outputs (gitignored content)

## Key conventions

- Python 3.11+, async throughout (asyncio)
- Pydantic models for all data structures
- YAML configs for personas, creativity parameters, hook templates
- Claude Opus for generation/judging, Sonnet for news filtering (cost optimization)
- All agent calls use `effort="high"` (extended thinking)
- Generated content rules: no markdown bold, plain URLs only, max 2 emojis, no hashtags
- Anti-slop validation is mandatory before judging — 74 banned words, 16 banned phrases, 8 regex patterns

## Config files that matter

- `src/config/settings.py` — Model names, generator count, lookback hours
- `src/config/personas.yaml` — Three personas (professional, witty, ai_meta) with voice traits, anti-patterns, example openers
- `src/config/creativity.yaml` — Hook patterns (weighted), frameworks, style references, wildcards, content angles
- `data/anti_slop/banned_words.txt` — Extensible banned word list
- `data/hooks/hook_templates.yaml` — Hook type definitions with examples and anti-patterns
