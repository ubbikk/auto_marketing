"""FastAPI web application for AFTA Marketing for LinkedIn."""

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    GenerateRequest,
    GenerateResponse,
    LogoPreview,
    PersonaInfo,
    ScoreData,
    VariantData,
)
from .pipeline import run_pipeline
from .scraper import scrape_website_metadata

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_STATIC_DIR = _PROJECT_ROOT / "static"
_CAROUSEL_DIR = _PROJECT_ROOT / "data" / "carousels"
_CONFIG_DIR = _PROJECT_ROOT / "src" / "config"

logger = logging.getLogger(__name__)

app = FastAPI(title="AFTA Marketing for LinkedIn")


@app.get("/")
async def landing_page():
    """Serve the landing page."""
    index = _STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Landing page not found")
    return FileResponse(str(index))


@app.get("/api/personas", response_model=list[PersonaInfo])
async def list_personas():
    """Return available personas for the selector."""
    personas_path = _CONFIG_DIR / "personas.yaml"
    with open(personas_path) as f:
        data = yaml.safe_load(f)

    personas = data.get("personas", {})
    result = []
    for pid, pdata in personas.items():
        result.append(
            PersonaInfo(
                id=pid,
                name=pdata.get("name", pid),
                description=pdata.get("description", ""),
                example_openers=pdata.get("example_openers", []),
            )
        )
    return result


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """Run the full generation pipeline."""
    logger.info("Starting generation: persona=%s, url=%s", request.persona, request.target_url)
    try:
        # run_pipeline uses sync anthropic client internally, so run in a
        # thread pool to avoid blocking the event loop.
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: asyncio.run(
                run_pipeline(
                    target_url=request.target_url,
                    message=request.message,
                    source_text=request.source_text,
                    persona=request.persona,
                )
            ),
        )
    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Build response
    carousel_filename = result.carousel_pdf_path.name
    carousel_url = f"/api/carousel/{carousel_filename}"

    # Build score breakdown
    score_breakdown = None
    if result.judgment.winner_score:
        ws = result.judgment.winner_score
        score_breakdown = ScoreData(
            hook_strength=ws.hook_strength,
            anti_slop=ws.anti_slop,
            distinctiveness=ws.distinctiveness,
            relevance=ws.relevance,
            persona_fit=ws.persona_fit,
            weighted_total=ws.weighted_total,
            notes=ws.notes,
        )

    # Build simplified variants list
    variants_data = []
    for v in result.all_variants:
        variants_data.append(
            VariantData(
                content=v.content,
                hook_type=v.hook_type,
                framework_used=v.framework_used,
                persona=v.persona,
                what_makes_it_different=v.what_makes_it_different,
            )
        )

    return GenerateResponse(
        winning_post=result.winning_post,
        carousel_pdf_url=carousel_url,
        persona_used=request.persona,
        source_title=result.source_content.title,
        source_summary=result.source_content.summary,
        score=result.judgment.winner_score.weighted_total
        if result.judgment.winner_score
        else None,
        score_breakdown=score_breakdown,
        judge_reasoning=result.judgment.winner_reasoning,
        improvement_notes=result.judgment.improvement_notes,
        all_variants=variants_data,
        stats=result.stats,
    )


@app.get("/api/carousel/{filename}")
async def download_carousel(filename: str):
    """Serve generated carousel PDF for download."""
    filepath = _CAROUSEL_DIR / filename
    if not filepath.exists() or not filepath.suffix == ".pdf":
        raise HTTPException(status_code=404, detail="Carousel not found")
    return FileResponse(
        str(filepath),
        media_type="application/pdf",
        filename=filename,
    )


@app.get("/api/scrape-logo", response_model=LogoPreview)
async def scrape_logo(url: str):
    """Preview logo extraction from a URL."""
    try:
        metadata = await scrape_website_metadata(url)
        return LogoPreview(
            logo_data_url=metadata.logo_data_url,
            domain=metadata.domain,
        )
    except Exception:
        return LogoPreview(domain="")


# Mount static files last (so API routes take priority)
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


if __name__ == "__main__":
    uvicorn.run(
        "src.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
