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

import os
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .models import (
    AuthResponse,
    CompanyProfile,
    CompanyProfileRequest,
    CompanyProfileResponse,
    CostBreakdown,
    FirebaseAuthRequest,
    GenerateRequest,
    GenerateResponse,
    LogoPreview,
    ModelInfo,
    PersonaInfo,
    ScoreData,
    StepCostData,
    VariantData,
)
from .auth import (
    verify_firebase_token,
    get_provider_from_token,
    get_firestore,
    User,
    get_current_user,
    require_auth,
)
from .pipeline import run_pipeline
from .scraper import scrape_website_metadata
from ..config.settings import settings
from ..company.profile import (
    CompanyContext,
    load_default_context,
    generate_company_profile,
)
from ..utils.cost_tracker import calculate_cost

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_STATIC_DIR = _PROJECT_ROOT / "static"
_CAROUSEL_DIR = _PROJECT_ROOT / "data" / "carousels"
_CONFIG_DIR = _PROJECT_ROOT / "src" / "config"

logger = logging.getLogger(__name__)

app = FastAPI(title="AFTA Marketing for LinkedIn")

# Session middleware for authentication
# Detect Cloud Run production environment
_is_production = os.getenv("K_SERVICE") is not None
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="auto_marketing_session",
    max_age=30 * 24 * 60 * 60,  # 30 days
    same_site="lax",
    https_only=_is_production,
)


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy"}


# ============================================================================
# Authentication Endpoints
# ============================================================================


@app.get("/api/auth/config")
async def get_auth_config():
    """Return Firebase config for frontend initialization."""
    return {
        "apiKey": settings.firebase_api_key,
        "authDomain": settings.firebase_auth_domain,
        "projectId": settings.firebase_project_id,
    }


@app.post("/api/auth/firebase", response_model=AuthResponse)
async def firebase_auth(request: Request, auth_request: FirebaseAuthRequest):
    """Authenticate with Firebase ID token."""
    decoded = verify_firebase_token(auth_request.idToken)
    if not decoded:
        return AuthResponse(success=False, error="Invalid or expired token")

    firestore = get_firestore()
    if not firestore:
        return AuthResponse(success=False, error="Service unavailable")

    firebase_uid = decoded['uid']
    email = decoded.get('email', '')
    name = decoded.get('name')
    picture = decoded.get('picture')
    provider = get_provider_from_token(decoded)

    # Get or create user
    user_data = firestore.get_user_by_firebase_uid(firebase_uid)
    if user_data:
        firestore.update_user_login(user_data['id'], picture)
    else:
        user_data = firestore.create_user(
            firebase_uid=firebase_uid,
            email=email,
            display_name=name,
            photo_url=picture,
            auth_provider=provider
        )

    # Store in session
    request.session['user'] = {
        'id': user_data['id'],
        'firebase_uid': firebase_uid,
        'email': email,
        'display_name': user_data.get('display_name', email.split('@')[0]),
        'photo_url': picture,
        'auth_provider': provider
    }

    logger.info("User logged in: %s (%s)", email, provider)

    return AuthResponse(
        success=True,
        redirect="/",
        user={
            "name": user_data.get('display_name'),
            "email": email,
            "photo_url": picture
        }
    )


@app.get("/api/auth/me")
async def get_me(user: User | None = Depends(get_current_user)):
    """Get current user info."""
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "name": user.display_name,
            "email": user.email,
            "photo_url": user.photo_url
        }
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Log out current user."""
    request.session.clear()
    return {"success": True}


# ============================================================================
# Public Endpoints
# ============================================================================


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
        # Skip disabled personas
        if pdata.get("enabled") is False:
            continue
        result.append(
            PersonaInfo(
                id=pid,
                name=pdata.get("name", pid),
                description=pdata.get("description", ""),
                example_openers=pdata.get("example_openers", []),
            )
        )
    return result


@app.get("/api/models", response_model=list[ModelInfo])
async def list_models():
    """Return available generation models for the selector."""
    return [ModelInfo(**m) for m in settings.available_generation_models]


@app.get("/api/default-company", response_model=CompanyProfile)
async def get_default_company():
    """Return the default company profile (AFTA Systems)."""
    ctx = load_default_context()
    return CompanyProfile(
        name=ctx.name,
        tagline=ctx.tagline,
        core_offering=ctx.core_offering,
        differentiator=ctx.differentiator,
        target_audience=ctx.target_audience,
        key_services=ctx.key_services,
        proof_points=ctx.proof_points,
        pain_points_solved=ctx.pain_points_solved,
        industry_keywords=ctx.industry_keywords,
    )


@app.post("/api/generate-company-profile", response_model=CompanyProfileResponse)
async def generate_profile(
    request: CompanyProfileRequest,
    user: User = Depends(require_auth)
):
    """Generate a company profile from a website URL using Firecrawl + AI."""
    logger.info("Generating company profile from URL: %s (user: %s)", request.url, user.email)
    try:
        result = await generate_company_profile(request.url)

        # Calculate cost
        cost_usd = calculate_cost(
            result.model,
            result.input_tokens,
            result.output_tokens,
        )

        return CompanyProfileResponse(
            profile=CompanyProfile(
                name=result.context.name,
                tagline=result.context.tagline,
                core_offering=result.context.core_offering,
                differentiator=result.context.differentiator,
                target_audience=result.context.target_audience,
                key_services=result.context.key_services,
                proof_points=result.context.proof_points,
                pain_points_solved=result.context.pain_points_solved,
                industry_keywords=result.context.industry_keywords,
            ),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
            cost_usd=cost_usd,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to generate company profile")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, user: User = Depends(require_auth)):
    """Run the full generation pipeline."""
    logger.info("Generation requested by user: %s", user.email)
    # Convert company_profile to CompanyContext if provided
    company_context = None
    if request.company_profile:
        company_context = CompanyContext(
            name=request.company_profile.name,
            tagline=request.company_profile.tagline,
            core_offering=request.company_profile.core_offering,
            differentiator=request.company_profile.differentiator,
            target_audience=request.company_profile.target_audience,
            key_services=request.company_profile.key_services,
            proof_points=request.company_profile.proof_points,
            pain_points_solved=request.company_profile.pain_points_solved,
            industry_keywords=request.company_profile.industry_keywords,
        )

    logger.info(
        "Starting generation: persona=%s, model=%s, generators=%d, url=%s, company=%s",
        request.persona,
        request.generation_model,
        request.num_generators,
        request.target_url,
        company_context.name if company_context else "default",
    )
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
                    num_generators=request.num_generators,
                    generation_model=request.generation_model,
                    auto_summarize=request.auto_summarize,
                    company_context=company_context,
                )
            ),
        )
    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Build response
    carousel_url = f"/api/carousel/download/{result.carousel_id}"

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
                structure_used=v.structure_used,
                persona=v.persona,
                what_makes_it_different=v.what_makes_it_different,
            )
        )

    # Build cost breakdown
    costs_data = None
    if result.costs:
        steps_data = {}
        for step_name, step_info in result.costs.get("steps", {}).items():
            steps_data[step_name] = StepCostData(
                model=step_info.get("model", ""),
                input_tokens=step_info.get("input_tokens", 0),
                output_tokens=step_info.get("output_tokens", 0),
                cost_usd=step_info.get("cost_usd", 0.0),
                call_count=step_info.get("call_count", 0),
            )
        costs_data = CostBreakdown(
            total_cost_usd=result.costs.get("total_cost_usd", 0.0),
            total_input_tokens=result.costs.get("total_input_tokens", 0),
            total_output_tokens=result.costs.get("total_output_tokens", 0),
            steps=steps_data,
        )

    return GenerateResponse(
        winning_post=result.winning_post,
        carousel_html=result.carousel_html,
        carousel_id=result.carousel_id,
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
        costs=costs_data,
    )


@app.get("/api/carousel/download/{carousel_id}")
async def download_carousel_pdf(carousel_id: str, user: User = Depends(require_auth)):
    """Generate and serve carousel PDF on-demand."""
    from ..carousel.service import render_carousel_pdf

    # Check if PDF already exists
    pdf_path = _CAROUSEL_DIR / f"{carousel_id}.pdf"
    if not pdf_path.exists():
        # Check if HTML exists
        html_path = _CAROUSEL_DIR / f"{carousel_id}.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="Carousel not found")

        # Render PDF on-demand
        logger.info("Rendering PDF on-demand for carousel %s", carousel_id)
        pdf_path = await render_carousel_pdf(carousel_id)
        if not pdf_path:
            raise HTTPException(status_code=500, detail="Failed to render PDF")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"carousel_{carousel_id}.pdf",
    )


@app.get("/api/carousel/preview/{carousel_id}")
async def preview_carousel_html(carousel_id: str, user: User = Depends(require_auth)):
    """Serve carousel HTML for preview with scaling and navigation."""
    from fastapi.responses import HTMLResponse

    html_path = _CAROUSEL_DIR / f"{carousel_id}.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Carousel not found")

    original_html = html_path.read_text(encoding="utf-8")

    # Inject preview wrapper CSS and JS for scaled carousel with navigation
    preview_wrapper = """
<style>
  html, body {
    margin: 0;
    padding: 0;
    background: #060918;
    overflow: hidden;
    width: 100%;
    height: 100%;
  }
  body {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }
  .preview-container {
    position: relative;
    width: 100%;
    height: calc(100% - 32px);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .slide {
    display: none !important;
    transform-origin: center center;
    /* Force fixed size - critical for scaling */
    width: 1080px !important;
    height: 1080px !important;
    min-width: 1080px !important;
    min-height: 1080px !important;
    max-width: 1080px !important;
    max-height: 1080px !important;
    flex-shrink: 0 !important;
  }
  .slide.active {
    display: flex !important;
  }
  .preview-nav {
    display: flex;
    gap: 6px;
    padding: 6px 0;
    z-index: 20;
  }
  .preview-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(232, 234, 246, 0.3);
    border: none;
    cursor: pointer;
    transition: all 0.2s;
  }
  .preview-dot:hover {
    background: rgba(0, 212, 255, 0.5);
  }
  .preview-dot.active {
    background: #00d4ff;
    box-shadow: 0 0 8px rgba(0, 212, 255, 0.6);
  }
  .preview-arrows {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 100%;
    display: flex;
    justify-content: space-between;
    padding: 0 4px;
    pointer-events: none;
    z-index: 10;
  }
  .preview-arrow {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.6);
    border: 1px solid rgba(0, 212, 255, 0.4);
    color: #00d4ff;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: auto;
    font-size: 12px;
    transition: all 0.2s;
  }
  .preview-arrow:hover {
    background: rgba(0, 212, 255, 0.3);
  }
</style>
<script>
document.addEventListener('DOMContentLoaded', () => {
  const slides = document.querySelectorAll('.slide');
  const total = slides.length;
  let current = 0;

  // Calculate scale based on container size
  function updateScale() {
    const container = document.querySelector('.preview-container');
    if (!container) return;
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;
    const slideSize = 1080;
    const scale = Math.min(containerWidth / slideSize, containerHeight / slideSize) * 0.95;
    slides.forEach(slide => {
      slide.style.transform = `scale(${scale})`;
    });
  }

  // Show slide
  function showSlide(idx) {
    slides.forEach((s, i) => {
      s.classList.toggle('active', i === idx);
    });
    document.querySelectorAll('.preview-dot').forEach((d, i) => {
      d.classList.toggle('active', i === idx);
    });
    current = idx;
  }

  // Create navigation
  const nav = document.createElement('div');
  nav.className = 'preview-nav';
  for (let i = 0; i < total; i++) {
    const dot = document.createElement('button');
    dot.className = 'preview-dot' + (i === 0 ? ' active' : '');
    dot.onclick = () => showSlide(i);
    nav.appendChild(dot);
  }
  document.body.appendChild(nav);

  // Create arrows
  const arrows = document.createElement('div');
  arrows.className = 'preview-arrows';
  arrows.innerHTML = `
    <button class="preview-arrow" onclick="prevSlide()">‹</button>
    <button class="preview-arrow" onclick="nextSlide()">›</button>
  `;
  document.querySelector('.preview-container').appendChild(arrows);

  window.prevSlide = () => showSlide((current - 1 + total) % total);
  window.nextSlide = () => showSlide((current + 1) % total);

  // Initial setup
  showSlide(0);
  updateScale();
  window.addEventListener('resize', updateScale);
});
</script>
"""

    # Wrap body content in preview container
    modified_html = original_html.replace(
        "<body>",
        f"<body>{preview_wrapper}<div class='preview-container'>"
    ).replace(
        "</body>",
        "</div></body>"
    )

    return HTMLResponse(content=modified_html, media_type="text/html")


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
    import os

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "src.app.main:app",
        host="0.0.0.0",
        port=port,
    )
