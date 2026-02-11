"""Render carousel slides to standalone HTML."""

import html
from pathlib import Path
from typing import Optional

from .models import CarouselContent

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_TEMPLATE_PATH = _PROJECT_ROOT / "data" / "output" / "carousel_template.html"


def _read_logo_base64() -> str:
    """Extract the AFTA logo from the template and make its background transparent."""
    import base64
    import io
    import re

    import numpy as np
    from PIL import Image

    text = _TEMPLATE_PATH.read_text()
    match = re.search(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', text)
    if not match:
        raise RuntimeError("Could not find logo base64 in carousel_template.html")

    img_data = base64.b64decode(match.group(1))
    img = Image.open(io.BytesIO(img_data)).convert("RGBA")
    arr = np.array(img, dtype=np.float32)

    gray = np.mean(arr[:, :, :3], axis=2)
    low, high = 50, 180
    alpha = np.clip((gray - low) / (high - low) * 255, 0, 255).astype(np.uint8)

    result = np.full_like(np.array(img), 255, dtype=np.uint8)
    result[:, :, 3] = alpha

    buf = io.BytesIO()
    Image.fromarray(result).save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _esc(text: str) -> str:
    return html.escape(text)


def build_html(
    content: CarouselContent,
    logo_data_url: Optional[str] = None,
    footer_domain: str = "afta.systems",
) -> str:
    """Build a standalone HTML document with all 5 carousel slides.

    Args:
        content: Structured carousel content for all 5 slides.
        logo_data_url: Optional base64 data URL for the target website's logo.
            Falls back to the built-in AFTA logo if not provided.
        footer_domain: Domain to display in the carousel footer.
    """
    if logo_data_url:
        logo = logo_data_url
    else:
        logo = _read_logo_base64()

    footer_url = _esc(footer_domain)
    cta_href = f"https://{footer_domain}"

    total = 5
    cover = content.cover
    bullets = content.bullets
    numbered = content.numbered
    stats = content.stats
    cta = content.cta

    # Build numbered items HTML
    numbered_items_html = ""
    for item in numbered.items:
        title = _esc(item["title"])
        desc = _esc(item["description"])
        numbered_items_html += (
            f'<li><span><strong style="color:var(--surface-foreground);">'
            f"{title}</strong> — {desc}</span></li>\n"
        )

    # Build stats HTML
    stats_cards_html = ""
    for s in stats.stats:
        stats_cards_html += (
            f'<div class="glass-card glass-card--accent" style="flex:1; text-align:center; padding:28px 20px;">\n'
            f'  <div class="stat-value">{_esc(s.value)}</div>\n'
            f'  <div class="stat-label">{_esc(s.label)}</div>\n'
            f"</div>\n"
        )

    # Build bullet items
    bullet_items_html = ""
    for b in bullets.bullets:
        bullet_items_html += f"<li>{_esc(b)}</li>\n"

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Carousel</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --surface: #060918;
    --surface-muted: #0d1128;
    --surface-highlight: #141938;
    --surface-border: #1a1f3c;
    --surface-foreground: #e8eaf6;
    --primary-300: #4de3ff;
    --primary-400: #1adbff;
    --primary-500: #00d4ff;
    --primary-600: #00a8cc;
    --primary-700: #007c99;
    --accent: #f59e0b;
    --accent-light: #fbbf24;
    --electric-purple: #8b5cf6;
    --electric-pink: #ec4899;
    --font-display: 'Syne', sans-serif;
    --font-body: 'Plus Jakarta Sans', sans-serif;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #111;
    font-family: var(--font-body);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    padding: 0;
  }}
  .slide {{
    width: 1080px;
    height: 1080px;
    position: relative;
    overflow: hidden;
    background: var(--surface);
    color: var(--surface-foreground);
    display: flex;
    flex-direction: column;
    font-feature-settings: "ss01", "ss02", "cv01";
    page-break-after: always;
  }}
  .slide::before {{
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(26, 31, 60, 0.35) 1px, transparent 1px),
      linear-gradient(90deg, rgba(26, 31, 60, 0.35) 1px, transparent 1px);
    background-size: 60px 60px;
    z-index: 0;
  }}
  .slide::after {{
    content: '';
    position: absolute;
    inset: 0;
    opacity: 0.03;
    background: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    z-index: 1;
    pointer-events: none;
  }}
  .slide-inner {{
    position: relative;
    z-index: 2;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 72px 80px;
  }}
  .glow {{
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    z-index: 0;
    pointer-events: none;
  }}
  .glow--cyan {{
    background: radial-gradient(circle, rgba(0, 212, 255, 0.45) 0%, transparent 70%);
  }}
  .glow--accent {{
    background: radial-gradient(circle, rgba(245, 158, 11, 0.25) 0%, transparent 70%);
  }}
  .glow--purple {{
    background: radial-gradient(circle, rgba(139, 92, 246, 0.25) 0%, transparent 70%);
  }}
  .logo {{ height: 72px; width: auto; object-fit: contain; }}
  .logo--small {{ height: 48px; }}
  .logo--large {{ height: 110px; }}
  .heading {{
    font-family: var(--font-display);
    font-weight: 700;
    line-height: 1.25;
    letter-spacing: 0.03em;
  }}
  .heading--xl {{ font-size: 68px; }}
  .heading--lg {{ font-size: 52px; }}
  .heading--md {{ font-size: 42px; }}
  .heading--sm {{ font-size: 32px; }}
  .gradient-text {{
    background: linear-gradient(135deg, #ffffff 0%, #80ebff 40%, #1adbff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .gradient-text--warm {{
    background: linear-gradient(135deg, #4de3ff 0%, #1adbff 50%, #f59e0b 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .subtitle {{
    font-family: var(--font-body);
    font-size: 24px;
    font-weight: 500;
    line-height: 1.5;
    color: rgba(232, 234, 246, 0.55);
  }}
  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid rgba(0, 212, 255, 0.3);
    background: rgba(0, 212, 255, 0.08);
    border-radius: 100px;
    padding: 10px 24px;
    font-family: var(--font-body);
    font-size: 16px;
    font-weight: 600;
    color: var(--primary-300);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    width: fit-content;
  }}
  .badge__dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary-500);
    box-shadow: 0 0 12px rgba(0, 212, 255, 0.6);
  }}
  .glass-card {{
    background: linear-gradient(145deg, rgba(13, 17, 40, 0.8) 0%, rgba(6, 9, 24, 0.9) 100%);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(26, 31, 60, 0.5);
    border-radius: 16px;
    padding: 36px 40px;
  }}
  .glass-card--accent {{
    border-color: rgba(0, 212, 255, 0.15);
    box-shadow: 0 0 40px rgba(0, 212, 255, 0.06);
  }}
  .bullet-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }}
  .bullet-list li {{
    display: flex;
    align-items: flex-start;
    gap: 20px;
    font-family: var(--font-body);
    font-size: 26px;
    line-height: 1.5;
    color: rgba(232, 234, 246, 0.8);
  }}
  .bullet-list li::before {{
    content: '';
    flex-shrink: 0;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--primary-500);
    box-shadow: 0 0 14px rgba(0, 212, 255, 0.6);
    margin-top: 11px;
  }}
  .number-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 28px;
    counter-reset: item;
  }}
  .number-list li {{
    display: flex;
    align-items: flex-start;
    gap: 24px;
    font-family: var(--font-body);
    font-size: 26px;
    line-height: 1.45;
    color: rgba(232, 234, 246, 0.8);
    counter-increment: item;
  }}
  .number-list li::before {{
    content: counter(item, decimal-leading-zero);
    flex-shrink: 0;
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 800;
    background: linear-gradient(135deg, #4de3ff, #00a8cc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
    min-width: 48px;
  }}
  .slide-counter {{
    position: absolute;
    bottom: 40px;
    right: 48px;
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 600;
    color: rgba(232, 234, 246, 0.25);
    letter-spacing: 0.05em;
    z-index: 3;
  }}
  .divider {{
    height: 2px;
    background: linear-gradient(90deg, transparent 0%, rgba(0, 212, 255, 0.3) 50%, transparent 100%);
    border: none;
  }}
  .cta-btn {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    background: linear-gradient(135deg, #00d4ff 0%, #00a8cc 100%);
    color: #060918;
    font-family: var(--font-body);
    font-size: 22px;
    font-weight: 700;
    padding: 20px 48px;
    border-radius: 100px;
    border: none;
    box-shadow: 0 4px 24px rgba(0, 212, 255, 0.35), inset 0 1px 0 rgba(255,255,255,0.2);
    letter-spacing: 0.02em;
    text-decoration: none;
    width: fit-content;
  }}
  .quote-mark {{
    font-family: var(--font-display);
    font-size: 120px;
    font-weight: 800;
    line-height: 0.6;
    background: linear-gradient(135deg, #00d4ff 0%, rgba(0, 212, 255, 0.2) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .bottom-bar {{
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .bottom-bar__url {{
    font-family: var(--font-body);
    font-size: 18px;
    font-weight: 500;
    color: rgba(232, 234, 246, 0.3);
    letter-spacing: 0.03em;
  }}
  .stat-value {{
    font-family: var(--font-display);
    font-size: 60px;
    font-weight: 700;
    background: linear-gradient(135deg, #4de3ff 0%, #1adbff 50%, #f59e0b 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.1;
    white-space: nowrap;
    letter-spacing: 0.02em;
  }}
  .stat-label {{
    font-family: var(--font-body);
    font-size: 18px;
    font-weight: 500;
    color: rgba(232, 234, 246, 0.5);
    margin-top: 10px;
  }}
  .accent-stripe {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--primary-500) 0%, var(--primary-600) 60%, var(--accent) 100%);
    z-index: 5;
  }}
  .powered-by {{
    font-family: var(--font-body);
    font-size: 14px;
    font-weight: 400;
    color: rgba(232, 234, 246, 0.2);
    letter-spacing: 0.02em;
  }}
</style>
</head>
<body>

<!-- SLIDE 1 — COVER -->
<div class="slide" id="slide-1">
  <div class="accent-stripe"></div>
  <div class="glow glow--cyan" style="width:600px;height:600px;top:-120px;right:-160px;opacity:0.3;"></div>
  <div class="glow glow--purple" style="width:400px;height:400px;bottom:-80px;left:-100px;opacity:0.2;"></div>
  <div class="slide-inner" style="justify-content: space-between;">
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <img class="logo" src="{logo}" alt="Logo">
      <div class="badge">
        <span class="badge__dot"></span>
        {_esc(cover.badge)}
      </div>
    </div>
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:28px; padding: 20px 0;">
      <h1 class="heading heading--xl gradient-text">{_esc(cover.title)}</h1>
      <p class="subtitle" style="max-width: 780px;">{_esc(cover.subtitle)}</p>
    </div>
    <div class="bottom-bar">
      <span class="bottom-bar__url">{footer_url}</span>
    </div>
  </div>
  <span class="slide-counter">1 / {total}</span>
</div>

<!-- SLIDE 2 — BULLETS -->
<div class="slide" id="slide-2">
  <div class="accent-stripe"></div>
  <div class="glow glow--cyan" style="width:500px;height:500px;top:50%;left:-140px;opacity:0.18;transform:translateY(-50%);"></div>
  <div class="slide-inner" style="justify-content: space-between;">
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <img class="logo logo--small" src="{logo}" alt="Logo">
      <div class="badge" style="font-size:14px; padding:8px 18px;">
        <span class="badge__dot"></span>
        {_esc(bullets.badge)}
      </div>
    </div>
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px; padding: 20px 0;">
      <h2 class="heading heading--lg gradient-text">{_esc(bullets.heading)}</h2>
      <hr class="divider" style="width:120px;">
      <ul class="bullet-list">
        {bullet_items_html}
      </ul>
    </div>
    <div class="bottom-bar">
      <span class="bottom-bar__url">{footer_url}</span>
      <img class="logo logo--small" src="{logo}" alt="Logo" style="opacity:0.3;">
    </div>
  </div>
  <span class="slide-counter">2 / {total}</span>
</div>

<!-- SLIDE 3 — NUMBERED -->
<div class="slide" id="slide-3">
  <div class="accent-stripe"></div>
  <div class="glow glow--accent" style="width:450px;height:450px;bottom:-100px;right:-80px;opacity:0.2;"></div>
  <div class="slide-inner" style="justify-content: space-between;">
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <img class="logo logo--small" src="{logo}" alt="Logo">
      <div class="badge" style="font-size:14px; padding:8px 18px;">
        <span class="badge__dot"></span>
        {_esc(numbered.badge)}
      </div>
    </div>
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:32px; padding: 20px 0;">
      <h2 class="heading heading--md gradient-text">{_esc(numbered.heading)}</h2>
      <hr class="divider" style="width:120px;">
      <ol class="number-list">
        {numbered_items_html}
      </ol>
    </div>
    <div class="bottom-bar">
      <span class="bottom-bar__url">{footer_url}</span>
      <img class="logo logo--small" src="{logo}" alt="Logo" style="opacity:0.3;">
    </div>
  </div>
  <span class="slide-counter">3 / {total}</span>
</div>

<!-- SLIDE 4 — STATS -->
<div class="slide" id="slide-4">
  <div class="accent-stripe"></div>
  <div class="glow glow--cyan" style="width:500px;height:500px;top:-100px;left:50%;opacity:0.2;transform:translateX(-50%);"></div>
  <div class="slide-inner" style="justify-content: space-between;">
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <img class="logo logo--small" src="{logo}" alt="Logo">
      <div class="badge" style="font-size:14px; padding:8px 18px;">
        <span class="badge__dot"></span>
        {_esc(stats.badge)}
      </div>
    </div>
    <div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:40px; padding: 20px 0;">
      <h2 class="heading heading--md gradient-text">{_esc(stats.heading)}</h2>
      <hr class="divider" style="width:120px;">
      <div style="display:flex; gap:32px;">
        {stats_cards_html}
      </div>
      <div class="glass-card" style="display:flex; gap:20px; align-items:flex-start; margin-top: 8px;">
        <span class="quote-mark">\u201c</span>
        <div>
          <p style="font-size:22px; line-height:1.55; color:rgba(232,234,246,0.75); font-style:italic;">{_esc(stats.quote_text)}</p>
          <p style="font-size:16px; color:var(--primary-400); margin-top:12px; font-weight:600;">{_esc(stats.quote_attribution)}</p>
        </div>
      </div>
    </div>
    <div class="bottom-bar">
      <span class="bottom-bar__url">{footer_url}</span>
      <img class="logo logo--small" src="{logo}" alt="Logo" style="opacity:0.3;">
    </div>
  </div>
  <span class="slide-counter">4 / {total}</span>
</div>

<!-- SLIDE 5 — CTA -->
<div class="slide" id="slide-5">
  <div class="accent-stripe"></div>
  <div class="glow glow--cyan" style="width:700px;height:700px;top:50%;left:50%;opacity:0.25;transform:translate(-50%,-50%);"></div>
  <div class="glow glow--accent" style="width:350px;height:350px;bottom:-60px;right:-60px;opacity:0.15;"></div>
  <div class="slide-inner" style="justify-content:center; align-items:center; text-align:center; gap:48px;">
    <img class="logo logo--large" src="{logo}" alt="Logo">
    <h2 class="heading heading--lg gradient-text--warm" style="max-width:800px;">{_esc(cta.heading)}</h2>
    <p class="subtitle" style="max-width:640px;">{_esc(cta.subtitle)}</p>
    <a class="cta-btn" href="{cta_href}" target="_blank">{_esc(cta.button_text)}</a>
    <p style="font-size:20px; color:rgba(232,234,246,0.35); font-weight:500; margin-top:8px;">{footer_url}</p>
    <p class="powered-by">Generated by AFTA Marketing</p>
  </div>
  <span class="slide-counter">5 / {total}</span>
</div>

</body>
</html>"""


def build_printable_html(html_content: str) -> str:
    """Inject @media print CSS into carousel HTML for print-to-PDF workflow.

    The returned HTML can be opened in Chrome and printed (Cmd+P → Save as PDF)
    to produce a multi-page PDF with one 1080x1080 slide per page.
    """
    print_css = """
<style>
  @media print {
    body { margin: 0; padding: 0; background: #060918; }
    .slide { page-break-after: always; page-break-inside: avoid; }
    .slide:last-child { page-break-after: auto; }
    /* Disable expensive effects that bloat PDF (180MB -> ~5MB) */
    .glow { display: none !important; }
    .slide::after { display: none !important; }
    .slide::before { opacity: 0.1 !important; }
    .glass-card { backdrop-filter: none !important; -webkit-backdrop-filter: none !important; }
  }
  @page { size: 1080px 1080px; margin: 0; }
</style>
"""
    return html_content.replace("</head>", print_css + "</head>")
