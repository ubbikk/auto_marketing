# Auto-Marketing

Multi-agent AI system for generating LinkedIn content that doesn't read like AI slop. Built for [AFTA Systems](https://afta.systems), an e-commerce automation company.

## What it does

Pulls recent tech/business news, filters for relevance, generates multiple LinkedIn post variants using different personas and creative strategies, validates against an anti-slop ruleset, and picks the best one via a judge agent.

### Pipeline

```
RSS Feeds (7 sources) → News Filter (Sonnet) → 7 Generators (Opus, parallel)
    → Anti-Slop Validator → Judge Agent → Winner
```

1. **Fetch** — Aggregates articles from TechCrunch, Hacker News, ArsTechnica, VentureBeat, Wired, IEEE Spectrum
2. **Filter** — Claude Sonnet scores each article for relevance to AFTA's audience, suggests angles
3. **Generate** — 7 generator agents run in parallel, each producing 2–4 variants with randomized hook/framework/persona combos (14–28 total)
4. **Validate** — Anti-slop engine checks for 74 banned words, 16 banned phrases, 8 structural patterns (emoji spam, em-dash overuse, listicle format, etc.)
5. **Judge** — Scores surviving variants on hook strength (30%), anti-slop (25%), distinctiveness (20%), relevance (15%), persona fit (10%)

### Personas

- **Professional** — Confident peer with specific data, admits uncertainty
- **Witty** — Observational humor, deadpan, friend-who-knows-stuff energy
- **AI-Meta** — Self-aware AI, fourth-wall breaks, honest about its own limitations

### Creativity engine

Each generator gets a unique combination of:
- **Hook pattern** (weighted): contrarian, specificity, open loop, identity callout, story drop, bold statement
- **Framework**: PAS, BAB, or HSO
- **Few-shot examples** from the assigned persona
- **Style reference** (50% chance): Ethan Mollick, Gary Provost, Wendy's Twitter, etc.
- **Wildcard constraint** (40% chance): e.g. "assume reader has 10 seconds attention"
- **Content angle** (weighted): DIY automation trap, time drain reality, quick wins, etc.

## Planned features

- Blog post to LinkedIn carousel conversion using image generation
- Automated comment generation for engagement
- Scheduling and posting integration

## Setup

Requires Python 3.11+.

```bash
# Install dependencies
pip install -e ".[dev]"

# Set your Anthropic API key
cp .env.example .env  # then edit with your key
# or
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### CLI

```bash
# Full pipeline
python -m src.main

# Quick mode (fewer feeds, faster)
python -m src.main --quick

# Fetch news only (no generation)
python -m src.main --news-only

# Custom settings
python -m src.main --generators 5 --hours-back 24 --news-index 1
```

### Streamlit UI

```bash
streamlit run src/ui.py
```

Interactive interface with news browsing, configurable generation, variant explorer, and score breakdowns.

### Output

Each run saves to `output/runs/{timestamp}/`:
- `winner.json` / `winner.md` — Best post with scores and reasoning
- `all_variants.json` — Every generated variant
- `run_log.json` — Execution stats
- `news_input.json` — Source article data

## Project structure

```
src/
├── agents/
│   ├── base_agent.py        # Claude API wrapper with extended thinking
│   ├── generator_agent.py   # Content variant generation
│   ├── judge_agent.py       # Scoring and selection
│   └── orchestrator.py      # Pipeline coordination
├── config/
│   ├── settings.py          # Runtime configuration
│   ├── personas.yaml        # Persona definitions and voice traits
│   └── creativity.yaml      # Hooks, frameworks, wildcards, angles
├── creativity/
│   ├── engine.py            # Randomized creativity context generation
│   └── anti_slop.py         # Banned words/phrases/patterns validation
├── news/
│   ├── fetcher.py           # RSS feed aggregation
│   ├── filter.py            # Relevance scoring via Sonnet
│   └── models.py            # Data structures
├── output/
│   └── formatter.py         # Multi-format result export
├── main.py                  # CLI entry point
└── ui.py                    # Streamlit web interface

data/
├── examples/                # Few-shot examples per persona
├── hooks/                   # Hook pattern templates
└── anti_slop/               # Banned words database

tests/                       # Pytest suite
```

## Cost

Roughly ~$0.15 per generator (Opus) + ~$0.30 for judging + minor Sonnet costs for filtering. A full run with 7 generators costs approximately $1.30–$1.50.

## Background

This started as a question: can taste in content be systematized? Most AI-generated LinkedIn posts are immediately recognizable — the emoji openers, the "let's dive in," the listicle structure. The anti-slop detection here is based on research showing certain words (delve, tapestry, leverage, etc.) increased 700–1500% in frequency post-ChatGPT.

The multi-agent approach generates diversity (different personas, hooks, frameworks), while the judge agent acts as a taste filter. It's not perfect — the best output still benefits from human editing — but it's a step toward content that doesn't make people reflexively scroll past.
