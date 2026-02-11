#!/usr/bin/env python3
"""
Playwright Screen Recording for Auto Marketing Promo Video

Records 4 screen segments of the app walkthrough:
1. Dashboard: URL entry + company profile generation
2. Persona selection
3. Generate click + loading + results reveal
4. Carousel modal navigation

Requires:
    pip install playwright
    playwright install chromium

Usage:
    # Record all segments (app must be running on localhost:8000)
    python record_walkthrough.py

    # Take screenshots only (for carousel gallery)
    python record_walkthrough.py --screenshots-only
"""

import asyncio
import os
import time
from pathlib import Path

# Output directories
OUTPUT_DIR = Path(__file__).parent
SCREEN_DIR = OUTPUT_DIR / "screen_recordings"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"


async def record_walkthrough(base_url: str = "http://localhost:8000"):
    """Record the full walkthrough as separate video segments."""
    from playwright.async_api import async_playwright

    SCREEN_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        # --- Segment 1: Dashboard URL entry + company profile ---
        print("\n--- Recording Segment 1: Dashboard + URL Entry ---")
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(SCREEN_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Navigate to dashboard (assumes already logged in via cookie/session)
        await page.goto(f"{base_url}/#dashboard")
        await page.wait_for_timeout(1000)

        # Type URL slowly for visual effect
        url_input = page.locator("#target-url")
        await url_input.click()
        await url_input.type("https://afta.systems", delay=80)
        await page.wait_for_timeout(2000)

        # Wait for company profile to appear
        await page.wait_for_selector("#company-profile-card:not(.hidden)", timeout=15000)
        await page.wait_for_timeout(2000)

        # Close and save video
        video_path_1 = await page.video.path()
        await context.close()
        final_path_1 = SCREEN_DIR / "03_dashboard.mp4"
        Path(video_path_1).rename(final_path_1)
        print(f"  Saved: {final_path_1}")

        # --- Segment 2: Persona selection ---
        print("\n--- Recording Segment 2: Persona Selection ---")
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(SCREEN_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.goto(f"{base_url}/#dashboard")
        await page.wait_for_timeout(1000)

        # Scroll to persona section
        await page.locator("#persona-grid").scroll_into_view_if_needed()
        await page.wait_for_timeout(500)

        # Click through personas for visual effect
        for persona in ["professional", "witty", "storyteller", "witty"]:
            await page.locator(f'[data-persona="{persona}"]').click()
            await page.wait_for_timeout(600)

        await page.wait_for_timeout(500)

        video_path_2 = await page.video.path()
        await context.close()
        final_path_2 = SCREEN_DIR / "05_persona_select.mp4"
        Path(video_path_2).rename(final_path_2)
        print(f"  Saved: {final_path_2}")

        # --- Segment 3: Generate + Loading + Results ---
        print("\n--- Recording Segment 3: Generate + Results ---")
        # For this segment, we need pre-seeded results.
        # Option A: Actually click generate and wait (slow)
        # Option B: Inject results via JS (fast)
        # Using Option B: we'll show the loading animation briefly,
        # then inject pre-built results

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(SCREEN_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.goto(f"{base_url}/#dashboard")
        await page.wait_for_timeout(1000)

        # Click generate button
        generate_btn = page.locator("#generate-btn")
        await generate_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await generate_btn.click()

        # Show loading for 3 seconds
        await page.wait_for_timeout(3000)

        # Stop loading and show results (inject via JS)
        # This triggers the results display with mock data
        await page.evaluate("""() => {
            // Hide loading, show results
            document.getElementById('loading-section').classList.add('hidden');
            document.getElementById('form-section').classList.remove('hidden');
            document.getElementById('results-section').classList.remove('hidden');

            // Scroll to results
            document.getElementById('results-section').scrollIntoView({behavior: 'smooth'});
        }""")

        await page.wait_for_timeout(3000)

        # Scroll through results slowly
        await page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'})")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'})")
        await page.wait_for_timeout(2000)

        video_path_3 = await page.video.path()
        await context.close()
        final_path_3 = SCREEN_DIR / "06_generate.mp4"
        Path(video_path_3).rename(final_path_3)
        print(f"  Saved: {final_path_3}")

        # --- Segment 4: Carousel modal ---
        print("\n--- Recording Segment 4: Carousel Modal ---")
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(SCREEN_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Navigate to a page with carousel results
        await page.goto(f"{base_url}/#dashboard")
        await page.wait_for_timeout(1000)

        # Open carousel modal (assumes results are visible)
        await page.evaluate("openCarouselModal()")
        await page.wait_for_timeout(1500)

        # Navigate through carousel slides
        for _ in range(4):
            await page.locator("#modal-next-btn").click()
            await page.wait_for_timeout(1200)

        await page.wait_for_timeout(1000)

        # Close modal
        await page.locator(".carousel-modal__close").click()
        await page.wait_for_timeout(500)

        video_path_4 = await page.video.path()
        await context.close()
        final_path_4 = SCREEN_DIR / "09_carousel_modal.mp4"
        Path(video_path_4).rename(final_path_4)
        print(f"  Saved: {final_path_4}")

        await browser.close()

    print("\n--- All segments recorded! ---")
    print(f"  Output directory: {SCREEN_DIR}")


async def take_carousel_screenshots(base_url: str = "http://localhost:8000"):
    """Take screenshots of carousel slides for the gallery segment."""
    from playwright.async_api import async_playwright

    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Navigate to a carousel preview page
        # The carousel slides are rendered as HTML iframes
        # We need pre-existing carousel data

        # Option: Take screenshots of the carousel modal slides
        await page.goto(f"{base_url}/#dashboard")
        await page.wait_for_timeout(2000)

        # If we have a carousel, open modal and screenshot each slide
        try:
            await page.evaluate("openCarouselModal()")
            await page.wait_for_timeout(1000)

            for i in range(5):
                screenshot_path = SCREENSHOTS_DIR / f"carousel_{i+1:02d}.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"  Screenshot: {screenshot_path}")

                if i < 4:
                    await page.locator("#modal-next-btn").click()
                    await page.wait_for_timeout(800)

        except Exception as e:
            print(f"  Carousel screenshots failed: {e}")
            print("  Make sure the app has pre-seeded carousel results.")

        await browser.close()

    print(f"\n--- Screenshots saved to {SCREENSHOTS_DIR} ---")


if __name__ == "__main__":
    import sys

    if "--screenshots-only" in sys.argv:
        asyncio.run(take_carousel_screenshots())
    else:
        asyncio.run(record_walkthrough())
