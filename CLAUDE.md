# CLAUDE.md

## Project overview

Auto-Marketing is a multi-agent LinkedIn content generation system for AFTA Systems (e-commerce automation company). It fetches news, generates post variants using different personas/hooks/organic structures, filters out AI slop, and selects the best variant via a judge agent.

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
Optional: `FIRECRAWL_API_KEY` for generating company profiles from URLs.

## Tests

```bash
pytest
```

Uses `pytest-asyncio` with `asyncio_mode = "auto"`.

## Architecture

**Pipeline**: News Fetch → Embedding Pre-Filter → AI Filter → Parallel Generation → Anti-Slop Validation → Judge → Winner

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Parallel Fetch │ ──▶ │ Embedding Filter│ ──▶ │ AI Filter       │ ──▶ │ Generation      │
│  (news + blogs) │     │ (top K by sim)  │     │ (Gemini Flash)  │     │ (Gemini Pro)    │
│  ~300 articles  │     │ 300 → 20        │     │ 20 → 5          │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

Key directories:
- `src/app/` — FastAPI web application (main.py, pipeline.py, scraper.py)
- `src/agents/` — Base agent, generator, judge, orchestrator
- `src/company/` — Company profile generation (Firecrawl + Gemini AI)
- `src/carousel/` — Carousel PDF generation (extractor, renderer, service)
- `src/config/` — Settings, personas.yaml, creativity.yaml
- `src/creativity/` — Creativity engine (randomized context) and anti-slop validator
- `src/news/` — RSS fetcher, OPML parser, embedding filter, batch filter
- `src/output/` — Result formatter (CLI output)
- `data/` — Few-shot examples, hook templates, banned words list
- `docs/` — News sources documentation, OPML blog feeds
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

## Company Profile Generation

The system supports dynamic company profiles for any website via Firecrawl + Gemini AI:

1. **Firecrawl** scrapes website content (markdown format)
2. **Gemini 3 Flash** extracts structured company profile with 9 fields:
   - name, tagline, core_offering, differentiator
   - target_audience, key_services, proof_points
   - pain_points_solved, industry_keywords

**API Endpoints:**
- `GET /api/default-company` — Returns default AFTA profile from `src/config/default_company.yaml`
- `POST /api/generate-company-profile` — Scrapes URL, generates profile with AI

**UI:** Company profile section with "Use Default" or "Generate from URL" options. Generated profiles show all fields plus generation stats (model, tokens, cost).

**Files:**
- `src/company/profile.py` — `CompanyContext` dataclass, `generate_company_profile()` function
- `src/config/default_company.yaml` — Default AFTA company context

## Embedding Pre-Filter

The system uses an embedding-based pre-filter to efficiently narrow down articles before the expensive AI filter. This allows fetching from many sources (92 blog feeds + 7 news feeds) while keeping costs low.

**How it works:**
1. Fetches articles from news feeds (48h lookback) and blog feeds (14 days lookback) in parallel
2. Uses Vertex AI `text-embedding-005` via LiteLLM to embed company profile and all articles
3. Calculates cosine similarity between company embedding and each article
4. Keeps top K (default: 20) most relevant articles
5. Passes filtered articles to Gemini Flash AI filter for final selection

**Configuration** (`src/config/settings.py`):
```python
blog_days_back: int = 14              # Days to look back for blog posts
include_blog_feeds: bool = True       # Enable OPML blog feeds
embedding_enabled: bool = True        # Enable embedding pre-filter
embedding_model: str = "vertex_ai/text-embedding-005"
embedding_top_k: int = 20             # Articles to pass to AI filter
embedding_batch_size: int = 100       # Max embeddings per API call
```

**CLI flags:**
- `--include-blogs` — Include blog feeds from OPML file
- `--blog-days N` — Days back for blog posts (default: 14)
- `--no-embedding` — Disable embedding pre-filter
- `--embedding-top-k N` — Articles to keep after embedding filter (default: 20)

**Files:**
- `src/news/opml_parser.py` — Parses `docs/hn-popular-blogs-2025.opml` (92 feeds)
- `src/news/embedding_filter.py` — `EmbeddingPreFilter` class using Vertex AI embeddings
- `src/news/fetcher.py` — Extended to support dual time windows (news vs blogs)

**Cost:** ~$0.003 per 300 articles (10x cheaper than AI filter alone)

## Config files that matter

- `src/config/settings.py` — Model names, generator count, lookback hours, embedding settings
- `src/config/default_company.yaml` — Default company context (AFTA Systems)
- `src/config/personas.yaml` — Five personas (professional, witty, ai_meta, storyteller, provocateur) with voice traits, anti-patterns, example openers
- `src/config/creativity.yaml` — Hook patterns (weighted), organic structures (not frameworks), style references with author samples, tone wildcards, structural breaks, content angles
- `data/style_samples/` — Actual prose samples from authors (Sivers, Graham, Bourdain, Leonard, Carver, Vonnegut) for style injection
- `data/anti_slop/banned_words.txt` — Extensible banned word list
- `data/hooks/hook_templates.yaml` — Hook type definitions with examples and anti-patterns

## GCP Configuration

This project uses **personal GCP** (gcloud config: `personal`).

**Project:** books
**Project ID:** `gen-lang-client-0463729029`
**Account:** dd.petrovskiy@gmail.com

**Setup with direnv** (recommended for multi-project workflows):

The `.envrc` file in project root auto-activates the correct gcloud config:
```bash
export CLOUDSDK_ACTIVE_CONFIG_NAME=personal
export VERTEXAI_PROJECT=gen-lang-client-0463729029
```

Run `direnv allow` after cloning. Now `cd`-ing into this directory auto-switches GCP context.

Verify with:
```bash
echo $CLOUDSDK_ACTIVE_CONFIG_NAME  # should be "personal"
gcloud config get-value project    # should be gen-lang-client-0463729029
```

## Cloud Run Deployment

**Live URL:** https://auto-marketing-345011742806.us-central1.run.app

```bash
# Build and deploy
gcloud builds submit --tag us-central1-docker.pkg.dev/gen-lang-client-0463729029/auto-marketing/app:latest
gcloud run deploy auto-marketing \
    --image us-central1-docker.pkg.dev/gen-lang-client-0463729029/auto-marketing/app:latest \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 600 \
    --set-secrets="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,FIRECRAWL_API_KEY=FIRECRAWL_API_KEY:latest" \
    --port 8000 \
    --execution-environment gen2 \
    --no-cpu-throttling
```
