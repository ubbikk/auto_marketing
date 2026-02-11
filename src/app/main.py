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
    AccessRequestResponse,
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
    require_approved,
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

    # Store in session (include approval fields)
    request.session['user'] = {
        'id': user_data['id'],
        'firebase_uid': firebase_uid,
        'email': email,
        'display_name': user_data.get('display_name', email.split('@')[0]),
        'photo_url': picture,
        'auth_provider': provider,
        'approved': user_data.get('approved', False),
        'generation_limit': user_data.get('generation_limit'),
        'is_admin': user_data.get('is_admin', False),
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
async def get_me(request: Request, user: User | None = Depends(get_current_user)):
    """Get current user info with approval status (always re-fetched from Firestore)."""
    if not user:
        return {"authenticated": False}

    # Re-fetch from Firestore to get latest approval status
    fs = get_firestore()
    approved = user.approved
    is_admin = user.is_admin
    generation_limit = user.generation_limit
    generations_remaining = None
    access_request_status = None

    if fs:
        fresh = fs.get_user_by_id(user.id)
        if fresh:
            approved = fresh.get('approved', False)
            is_admin = fresh.get('is_admin', False)
            generation_limit = fresh.get('generation_limit')

            # Update session with fresh data
            session_user = request.session.get('user', {})
            session_user['approved'] = approved
            session_user['is_admin'] = is_admin
            session_user['generation_limit'] = generation_limit
            request.session['user'] = session_user

        generations_remaining = fs.get_generations_remaining(user.id)
        access_req = fs.get_user_access_request(user.id)
        if access_req:
            access_request_status = access_req.get('status')

    return {
        "authenticated": True,
        "user": {
            "name": user.display_name,
            "email": user.email,
            "photo_url": user.photo_url,
        },
        "approved": approved or is_admin,
        "is_admin": is_admin,
        "generations_remaining": generations_remaining,
        "access_request_status": access_request_status,
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Log out current user."""
    request.session.clear()
    return {"success": True}


# ============================================================================
# Access Request
# ============================================================================


def send_access_request_notification(email: str, display_name: str):
    """Send email notification about new access request (runs in background thread)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_email = settings.smtp_email
    smtp_password = settings.smtp_password
    notify_email = settings.notify_email

    if not smtp_email or not smtp_password or not notify_email:
        logger.warning("SMTP not configured, skipping access request notification")
        return

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = smtp_email
        msg['To'] = notify_email
        msg['Subject'] = f'[Auto Marketing] New Access Request from {display_name}'

        html = f"""\
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px;">
  <div style="max-width: 480px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
    <h2 style="color: #1a1a2e; margin: 0 0 16px;">New Access Request</h2>
    <p style="color: #555; line-height: 1.6;">
      <strong>{display_name}</strong> ({email}) has requested access to Auto Marketing.
    </p>
    <p style="color: #888; font-size: 13px; margin-top: 24px;">
      Approve or reject in the Firestore console.
    </p>
  </div>
</body>
</html>"""

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, notify_email, msg.as_string())

        logger.info("Access request notification sent for %s", email)
    except Exception as e:
        logger.error("Failed to send access request notification: %s", e)


@app.post("/api/request-access", response_model=AccessRequestResponse)
async def request_access(user: User = Depends(require_auth)):
    """Request access to the application."""
    firestore = get_firestore()
    if not firestore:
        raise HTTPException(status_code=503, detail="Service unavailable")

    # Check if already approved
    fresh = firestore.get_user_by_id(user.id)
    if fresh and (fresh.get('approved', False) or fresh.get('is_admin', False)):
        return AccessRequestResponse(success=True, status="approved", message="Already approved")

    # Check if request already exists
    existing = firestore.get_user_access_request(user.id)
    if existing and existing.get('status') == 'pending':
        return AccessRequestResponse(success=True, status="pending", message="Request already submitted")

    # Create new request
    firestore.create_access_request(user.id, user.email, user.display_name)

    # Send email notification in background thread
    import threading
    threading.Thread(
        target=send_access_request_notification,
        args=(user.email, user.display_name),
        daemon=True,
    ).start()

    logger.info("Access request created for %s", user.email)
    return AccessRequestResponse(success=True, status="pending", message="Access request submitted")


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
async def generate(request: GenerateRequest, user: User = Depends(require_approved)):
    """Run the full generation pipeline."""
    logger.info("Generation requested by user: %s", user.email)

    # Check credits before running
    fs = get_firestore()
    if fs:
        remaining = fs.get_generations_remaining(user.id)
        if remaining is not None and remaining <= 0:
            raise HTTPException(
                status_code=403,
                detail="No generations remaining. Contact admin for more credits."
            )

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
    # Fetch previously used article URLs to avoid repeating
    exclude_urls = None
    if fs and request.source_text.strip().lower() == "auto":
        try:
            exclude_urls = fs.get_used_article_urls(days_back=30)
            if exclude_urls:
                logger.info("Excluding %d previously used article URLs", len(exclude_urls))
        except Exception as e:
            logger.warning("Failed to fetch used article URLs: %s", e)

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
                    exclude_urls=exclude_urls,
                )
            ),
        )
    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Record successful generation (with source URL for future exclusion)
    if fs:
        source_url = getattr(result.source_content, 'url', None) if result.source_content else None
        fs.record_generation(user.id, user.email, source_url=source_url)

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
        source_mode=result.source_mode,
    )


@app.get("/api/carousel/download/{carousel_id}")
async def download_carousel_html(carousel_id: str, user: User = Depends(require_auth)):
    """Serve print-ready carousel HTML for download."""
    from fastapi.responses import Response
    from ..carousel.service import get_printable_html

    html = get_printable_html(carousel_id)
    if html is None:
        raise HTTPException(status_code=404, detail="Carousel not found")

    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="carousel_{carousel_id}.html"',
        },
    )


@app.get("/api/carousel/preview/{carousel_id}")
async def preview_carousel_html(carousel_id: str, slide: int = 0, user: User = Depends(require_auth)):
    """Serve carousel HTML for preview with scaling and navigation."""
    from fastapi.responses import HTMLResponse

    html_path = _CAROUSEL_DIR / f"{carousel_id}.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Carousel not found")

    original_html = html_path.read_text(encoding="utf-8")

    # Inject preview wrapper CSS and JS for scaled carousel
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
    height: 100%;
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
</style>
<script>
document.addEventListener('DOMContentLoaded', () => {
  const slides = document.querySelectorAll('.slide');
  const startSlide = __SLIDE_INDEX__;

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

  // Show the requested slide
  slides.forEach((s, i) => {
    s.classList.toggle('active', i === startSlide);
  });

  updateScale();
  window.addEventListener('resize', updateScale);
});
</script>
"""

    preview_wrapper = preview_wrapper.replace("__SLIDE_INDEX__", str(slide))

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
