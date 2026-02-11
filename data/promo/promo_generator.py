#!/usr/bin/env python3
"""
Auto Marketing Promo Video Generator

Creates a 60-second promotional video for the landing page with:
- Animated text slides (Veo 3.1 fast or zoom-out fallback)
- Quick gallery slideshows from carousel screenshots
- Segment concatenation with audio mixing

Adapted from BookTrailers.ai promo pipeline.

Usage:
    python promo_generator.py                    # Generate all slides + assemble
    python promo_generator.py --no-veo           # Use free zoom-out instead of Veo
    python promo_generator.py --slides-only      # Only generate slide images (no video)
    python promo_generator.py --background-only  # Only generate AI background

Requires:
    pip install Pillow google-genai requests
    brew install ffmpeg
"""

import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_DIR = Path(__file__).parent
RESOLUTION = (1920, 1080)
FPS = 24

# Fonts (Syne — matching the app's display font)
FONTS_DIR = OUTPUT_DIR / "fonts"
FONT_BOLD = FONTS_DIR / "syne-latin-700-normal.ttf"
FONT_EXTRABOLD = FONTS_DIR / "syne-latin-800-normal.ttf"
FONT_REGULAR = FONTS_DIR / "syne-latin-400-normal.ttf"

# Design tokens (matching app's CSS variables)
COLOR_SURFACE = "#060918"
COLOR_PRIMARY = "#00d4ff"
COLOR_PURPLE = "#8b5cf6"
COLOR_ACCENT = "#f59e0b"
COLOR_TEXT = "#FFFFFF"

# Font sizes
FONT_SIZE_MAIN = 90
FONT_SIZE_SUBTITLE = 44

# Veo animation prompt (cyan/purple floating particles)
VEO_ANIMATION_PROMPT = (
    "Subtle cinematic animation: cyan and purple bokeh particles slowly floating, "
    "soft blue light rays gently pulsing, very slight camera drift. Text remains "
    "sharp and readable. Dark tech atmosphere, premium feel. Slow, elegant movement."
)

# Background generation prompt
BACKGROUND_PROMPT = """Create a premium cinematic background for a tech startup video promo:
- Very dark background (#060918 deep navy-black)
- Subtle grid pattern overlay (faint lines, like graph paper)
- Soft cyan glow (color #00d4ff) emanating from top-right area
- Soft purple glow (color #8b5cf6) emanating from bottom-left area
- Very subtle noise/grain texture
- Aspect ratio: 16:9 (1920x1080)
- Mood: Dark tech, SaaS product, modern, sleek
- NO TEXT, NO people, NO characters — ONLY elegant dark tech background
"""


# ============================================================
# STORYBOARD DEFINITION
# ============================================================

STORYBOARD = [
    # Act 1: Hook (0-8s)
    {"type": "slide", "id": "01_hook1", "text": "LinkedIn Content That\nSounds Like You", "duration": 4.0},
    {"type": "slide", "id": "02_hook2", "text": "Not Like a Robot", "duration": 4.0},

    # Act 2: Demo (8-30s) — screen recordings interleaved
    {"type": "screen", "id": "03_dashboard", "description": "Dashboard: URL entry + company profile", "duration": 6.0},
    {"type": "slide", "id": "04_personas", "text": "5 AI Personas", "subtitle": "Each With Its Own Voice", "duration": 3.0},
    {"type": "screen", "id": "05_persona_select", "description": "Persona selection + generate click", "duration": 3.0},
    {"type": "screen", "id": "06_generate", "description": "Loading → results appear", "duration": 4.0},
    {"type": "screen", "id": "07_results", "description": "Winning post + score + metrics", "duration": 6.0},

    # Act 3: Carousel (30-42s)
    {"type": "slide", "id": "08_carousel_intro", "text": "Branded Carousels", "subtitle": "One Click", "duration": 3.0},
    {"type": "screen", "id": "09_carousel_modal", "description": "Carousel preview → modal → navigate", "duration": 5.0},
    {"type": "gallery", "id": "10_carousel_gallery", "description": "Carousel slide screenshots", "duration": 4.0},

    # Act 4: Close (42-60s)
    {"type": "slide", "id": "11_antislop", "text": "Anti-Slop Validated", "subtitle": "No Buzzwords. No Hashtags.", "duration": 4.0},
    {"type": "slide", "id": "12_voice", "text": "Your Voice. Your Brand.", "duration": 4.0},
    {"type": "slide", "id": "13_brand", "text": "AFTA Auto Marketing", "subtitle": "for LinkedIn", "duration": 5.0},
    {"type": "slide", "id": "14_cta", "text": "Get Started Free", "duration": 5.0},
]


# ============================================================
# PROMO VIDEO GENERATOR
# ============================================================

class PromoVideoGenerator:
    def __init__(
        self,
        output_dir: Path = OUTPUT_DIR,
        resolution: Tuple[int, int] = RESOLUTION,
        fps: int = FPS,
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.width, self.height = resolution
        self.fps = fps

    # ----------------------------------------------------------
    # SLIDE IMAGE GENERATION (PIL)
    # ----------------------------------------------------------

    def generate_slide_image(
        self,
        main_text: str,
        output_path: str,
        subtitle: str = None,
        background_path: str = None,
        font_size_main: int = FONT_SIZE_MAIN,
        font_size_subtitle: int = FONT_SIZE_SUBTITLE,
    ) -> Optional[str]:
        """Generate slide image with Syne text on dark tech background."""
        print(f"\nGenerating slide: '{main_text[:50]}...'")

        if not FONT_BOLD.exists():
            print(f"  FAILED: Font not found at {FONT_BOLD}")
            return None

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Get background
        if not background_path or not Path(background_path).exists():
            bg_path = str(self.output_dir / "slides" / "_background.png")
            if not Path(bg_path).exists():
                print("  No background image found. Creating solid color fallback...")
                img = Image.new("RGBA", (self.width, self.height), COLOR_SURFACE)
                self._add_glow_orbs(img)
                img.save(bg_path)
            background_path = bg_path

        try:
            image = Image.open(background_path).convert("RGBA")
            if image.size != (self.width, self.height):
                image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)

            draw = ImageDraw.Draw(image)
            font_main = ImageFont.truetype(str(FONT_BOLD), font_size_main)
            font_sub = ImageFont.truetype(str(FONT_REGULAR), font_size_subtitle)

            # Handle multi-line text
            lines = main_text.split("\n")
            line_bboxes = [draw.textbbox((0, 0), line, font=font_main) for line in lines]
            line_heights = [bb[3] - bb[1] for bb in line_bboxes]
            line_widths = [bb[2] - bb[0] for bb in line_bboxes]
            line_spacing = 15
            total_text_h = sum(line_heights) + line_spacing * (len(lines) - 1)

            # Vertical offset if subtitle present
            y_offset = 25 if subtitle else 0
            y_start = (self.height - total_text_h) // 2 - y_offset

            # Draw each line with subtle glow
            glow_offsets = [(2, 2), (-2, -2), (2, -2), (-2, 2),
                            (0, 2), (0, -2), (2, 0), (-2, 0)]

            y_cursor = y_start
            for i, line in enumerate(lines):
                x_line = (self.width - line_widths[i]) // 2

                # Subtle cyan glow (low alpha)
                for ox, oy in glow_offsets:
                    draw.text((x_line + ox, y_cursor + oy), line,
                              font=font_main, fill=COLOR_PRIMARY + "15")

                # Main text
                draw.text((x_line, y_cursor), line, font=font_main, fill=COLOR_TEXT)
                y_cursor += line_heights[i] + line_spacing

            # Subtitle (muted cyan)
            if subtitle:
                bbox_sub = draw.textbbox((0, 0), subtitle, font=font_sub)
                sub_w = bbox_sub[2] - bbox_sub[0]
                x_sub = (self.width - sub_w) // 2
                y_sub = y_cursor + 25

                for ox, oy in glow_offsets:
                    draw.text((x_sub + ox, y_sub + oy), subtitle,
                              font=font_sub, fill=COLOR_PRIMARY + "10")
                draw.text((x_sub, y_sub), subtitle, font=font_sub,
                          fill="#b3f3ff")

            image.convert("RGB").save(output_path, "PNG")
            print(f"  OK: {output_path}")
            return output_path

        except Exception as e:
            print(f"  FAILED: {e}")
            return None

    def _add_glow_orbs(self, image: Image.Image):
        """Add synthetic cyan/purple glow orbs and grid pattern to background."""
        from PIL import ImageFilter

        # Add subtle grid pattern (matching app's CSS grid-bg)
        grid_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        grid_draw = ImageDraw.Draw(grid_overlay)
        grid_color = (26, 31, 60, 25)  # rgba(26, 31, 60, 0.1)
        grid_spacing = 60
        for x in range(0, self.width, grid_spacing):
            grid_draw.line([(x, 0), (x, self.height)], fill=grid_color, width=1)
        for y in range(0, self.height, grid_spacing):
            grid_draw.line([(0, y), (self.width, y)], fill=grid_color, width=1)
        image.paste(Image.alpha_composite(image, grid_overlay))

        # Add glow orbs
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Cyan orb (top right)
        cx, cy = int(self.width * 0.72), int(self.height * 0.22)
        for r in range(350, 0, -5):
            alpha = int(18 * (r / 350))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         fill=(0, 212, 255, alpha))

        # Purple orb (bottom left)
        cx, cy = int(self.width * 0.28), int(self.height * 0.78)
        for r in range(280, 0, -5):
            alpha = int(14 * (r / 280))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         fill=(139, 92, 246, alpha))

        # Small accent orb (center-left, subtle)
        cx, cy = int(self.width * 0.15), int(self.height * 0.35)
        for r in range(150, 0, -5):
            alpha = int(8 * (r / 150))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         fill=(245, 158, 11, alpha))

        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=80))
        image.paste(Image.alpha_composite(image, overlay))

    # ----------------------------------------------------------
    # AI BACKGROUND GENERATION (Gemini)
    # ----------------------------------------------------------

    def generate_background(self, output_path: str) -> Optional[str]:
        """Generate cinematic background using Gemini image generation."""
        print(f"\nGenerating AI background...")

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("VERTEXAI_PROJECT")),
                location="us-central1",
            )

            response = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=BACKGROUND_PROMPT,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                ),
            )

            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(img_bytes)
                print(f"  OK: {output_path}")
                return output_path
            else:
                print("  FAILED: No images generated")
                return None

        except Exception as e:
            print(f"  FAILED: {e}")
            return None

    # ----------------------------------------------------------
    # SLIDE ANIMATION — Veo 3.1 fast (no audio)
    # ----------------------------------------------------------

    def animate_slide_veo(
        self,
        image_path: str,
        output_path: str,
        duration: int = 4,
        prompt: str = VEO_ANIMATION_PROMPT,
    ) -> Optional[str]:
        """Animate a static slide using Veo 3.1 fast without audio."""
        print(f"\nAnimating slide with Veo ({duration}s, no audio)...")

        try:
            from google import genai
            from google.genai import types

            # Try Vertex AI first (supports generate_audio=False for cost savings)
            # Falls back to API key if Vertex fails
            project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("VERTEXAI_PROJECT")
            try:
                client = genai.Client(
                    vertexai=True,
                    project=project,
                    location="us-central1",
                )
                use_vertex = True
            except Exception:
                api_key = os.environ.get("GOOGLE_API_KEY")
                if not api_key:
                    from pathlib import Path as P
                    env_file = P(".env")
                    if env_file.exists():
                        for line in env_file.read_text().splitlines():
                            if line.startswith("GOOGLE_API_KEY="):
                                api_key = line.split("=", 1)[1].strip()
                client = genai.Client(api_key=api_key)
                use_vertex = False

            with open(image_path, "rb") as f:
                image_bytes = f.read()

            ext = Path(image_path).suffix.lower()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
            image = types.Image(
                image_bytes=image_bytes,
                mime_type=mime.get(ext.lstrip("."), "image/png"),
            )

            model_name = "veo-3.1-fast-generate-001" if use_vertex else "veo-3.1-fast-generate-preview"
            print(f"    Using: {model_name} ({'Vertex AI' if use_vertex else 'API key'})")
            print(f"    Prompt: {prompt[:80]}...")

            veo_config = types.GenerateVideosConfig(
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=4,
            )
            # Vertex AI supports generate_audio=False (halves cost)
            if use_vertex:
                veo_config.generate_audio = False
                veo_config.person_generation = "allow_all"

            operation = client.models.generate_videos(
                model=model_name,
                image=image,
                config=veo_config,
            )

            # Poll for completion (must re-fetch operation status)
            start = time.time()
            while not operation.done:
                time.sleep(15)
                operation = client.operations.get(operation)
                elapsed = int(time.time() - start)
                print(f"    Veo: waiting... ({elapsed}s, done={operation.done})")
                if elapsed > 360:
                    print("    Veo: timeout after 360s")
                    return None

            elapsed = int(time.time() - start)
            print(f"    Veo: completed in {elapsed}s")

            if operation.error:
                print(f"    Veo error: {operation.error}")
                return None

            video = operation.result.generated_videos[0].video
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # Vertex AI returns video_bytes directly; API key needs files.download
            if video.video_bytes:
                with open(output_path, "wb") as f:
                    f.write(video.video_bytes)
            else:
                video_bytes = client.files.download(file=video)
                with open(output_path, "wb") as f:
                    f.write(video_bytes)

            print(f"  OK: {output_path}")
            return output_path

        except Exception as e:
            print(f"  FAILED: {e}")
            return None

    # ----------------------------------------------------------
    # SLIDE ANIMATION — Zoom-Out (free, FFmpeg)
    # ----------------------------------------------------------

    def animate_slide_zoom(
        self,
        image_path: str,
        output_path: str,
        duration: float = 4.0,
        zoom_start: float = 1.15,
        zoom_end: float = 1.0,
        fade_in: float = 0.5,
        fade_out: float = 0.5,
        drift_y: float = 20.0,
    ) -> Optional[str]:
        """Create zoom-out reveal animation from static image (free)."""
        print(f"\nCreating zoom-out video ({duration}s)...")

        frames = int(duration * self.fps)
        zoom_decrement = (zoom_start - zoom_end) / frames
        drift_per_frame = drift_y / frames

        zoompan_filter = (
            f"scale=8000:-1,"
            f"zoompan=z='if(eq(on,1),{zoom_start},max({zoom_end},zoom-{zoom_decrement:.8f}))':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)-{drift_per_frame:.6f}*on':"
            f"d={frames}:s={self.width}x{self.height}:fps={self.fps},"
            f"fade=t=in:st=0:d={fade_in},"
            f"fade=t=out:st={duration - fade_out}:d={fade_out}"
        )

        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-vf", zoompan_filter,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            output_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"  OK: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"  FAILED: {e.stderr[:500] if e.stderr else e}")
            return None

    # ----------------------------------------------------------
    # ANIMATED SLIDE (full pipeline: image → animation)
    # ----------------------------------------------------------

    def create_animated_slide(
        self,
        main_text: str,
        output_path: str,
        duration: float = 4.0,
        subtitle: str = None,
        use_veo: bool = True,
    ) -> Optional[str]:
        """Generate a text slide and animate it."""
        slides_dir = self.output_dir / "slides"
        slides_dir.mkdir(exist_ok=True)

        safe_name = "".join(c if c.isalnum() else "_" for c in main_text[:30])
        image_path = slides_dir / f"{safe_name}.png"

        # Step 1: Generate slide image (cached)
        if not image_path.exists():
            result = self.generate_slide_image(
                main_text, str(image_path), subtitle=subtitle
            )
            if not result:
                return None
        else:
            print(f"\nUsing cached slide: {image_path}")

        # Step 2: Animate
        if use_veo:
            veo_path = slides_dir / f"{safe_name}_veo.mp4"
            if not veo_path.exists():
                veo_result = self.animate_slide_veo(str(image_path), str(veo_path))
                if not veo_result:
                    use_veo = False
            else:
                print(f"  Using cached Veo: {veo_path}")

            if use_veo:
                fade_out_start = max(0, duration - 0.5)
                veo_duration = 4.0
                slowdown = f"setpts={duration / veo_duration}*PTS," if duration > veo_duration else ""
                vf = (
                    f"{slowdown}"
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"fps={self.fps},"
                    f"fade=t=out:st={fade_out_start}:d=0.5"
                )
                cmd = [
                    "ffmpeg", "-y", "-i", str(veo_path),
                    "-t", str(duration), "-vf", vf,
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                    output_path,
                ]
                try:
                    subprocess.run(cmd, capture_output=True, check=True)
                    print(f"  Trimmed to {duration}s: {output_path}")
                    return output_path
                except subprocess.CalledProcessError:
                    pass  # Fall through to zoom-out

        # Fallback: zoom-out animation
        return self.animate_slide_zoom(
            str(image_path), output_path, duration=duration
        )

    # ----------------------------------------------------------
    # QUICK GALLERY (crossfade slideshow)
    # ----------------------------------------------------------

    def create_quick_gallery(
        self,
        images: List[str],
        output_path: str,
        duration_per_image: float = 1.5,
        crossfade: float = 0.2,
    ) -> Optional[str]:
        """Create crossfade slideshow from a list of images."""
        if not images:
            return None

        print(f"\nCreating quick gallery ({len(images)} images)...")

        filter_parts = []
        inputs = []

        for i, img in enumerate(images):
            inputs.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img])
            filter_parts.append(
                f"[{i}:v]scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[v{i}]"
            )

        if len(images) > 1:
            prev = "v0"
            for i in range(1, len(images)):
                offset = i * duration_per_image - (i * crossfade) - crossfade
                if offset < 0:
                    offset = (i - 1) * (duration_per_image - crossfade)
                filter_parts.append(
                    f"[{prev}][v{i}]xfade=transition=fade:duration={crossfade}:offset={offset}[xf{i}]"
                )
                prev = f"xf{i}"
            final_label = prev
        else:
            final_label = "v0"

        total_dur = len(images) * duration_per_image - (len(images) - 1) * crossfade
        filter_parts.append(
            f"[{final_label}]fade=t=in:st=0:d=0.3,fade=t=out:st={total_dur - 0.3}:d=0.3[out]"
        )

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", "[out]",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            output_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"  OK: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"  FAILED: {e.stderr[:500] if e.stderr else e}")
            return None

    # ----------------------------------------------------------
    # EMBED EXISTING VIDEO SEGMENT
    # ----------------------------------------------------------

    def embed_video(
        self,
        video_path: str,
        output_path: str,
        max_duration: float = 30.0,
        speed: float = 1.0,
    ) -> Optional[str]:
        """Re-encode an existing video clip, optionally sped up."""
        print(f"\nEmbedding video: {video_path} (max {max_duration}s, speed {speed}x)")

        vf = f"setpts={1/speed}*PTS" if speed != 1.0 else ""
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-t", str(max_duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an",  # Remove audio (promo has its own soundtrack)
        ]
        if vf:
            cmd.extend(["-vf", vf])
        cmd.append(output_path)

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"  OK: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"  FAILED: {e}")
            return None

    # ----------------------------------------------------------
    # CONCATENATE SEGMENTS + ADD AUDIO
    # ----------------------------------------------------------

    def concatenate_segments(
        self,
        segments: List[str],
        output_path: str,
        audio_path: str = None,
        audio_fade_out: float = 2.0,
    ) -> Optional[str]:
        """Concatenate video segments and optionally add soundtrack."""
        if not segments:
            return None

        print(f"\nConcatenating {len(segments)} segments...")

        # Normalize segments with mismatched resolution/fps
        normalized = []
        for seg in segments:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,r_frame_rate",
                 "-of", "csv=p=0", seg],
                capture_output=True, text=True,
            )
            needs_norm = False
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 2:
                    w, h = int(parts[0]), int(parts[1])
                    if w != self.width or h != self.height:
                        needs_norm = True
                        print(f"  Normalizing {Path(seg).name}: {w}x{h}")

            if needs_norm:
                norm_path = str(Path(seg).with_suffix(".norm.mp4"))
                cmd = [
                    "ffmpeg", "-y", "-i", seg,
                    "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                           f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,fps={self.fps}",
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                    "-an", norm_path,
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                normalized.append(norm_path)
            else:
                normalized.append(seg)

        # Concat
        concat_file = self.output_dir / "concat_list.txt"
        with open(concat_file, "w") as f:
            for seg in normalized:
                f.write(f"file '{Path(seg).resolve()}'\n")

        try:
            temp_video = self.output_dir / "temp_concat.mp4"
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                str(temp_video),
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            if audio_path and os.path.exists(audio_path):
                print(f"  Adding audio: {audio_path}")
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(temp_video)],
                    capture_output=True, text=True, check=True,
                )
                video_duration = float(result.stdout.strip())
                fade_start = max(0, video_duration - audio_fade_out)

                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(temp_video),
                    "-stream_loop", "-1", "-i", audio_path,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac",
                    "-af", f"atrim=0:{video_duration},afade=t=out:st={fade_start}:d={audio_fade_out}",
                    "-t", str(video_duration),
                    output_path,
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                temp_video.unlink()
            else:
                temp_video.rename(output_path)

            print(f"  OK: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            print(f"  FAILED: {e.stderr[:500] if e.stderr else e}")
            return None
        finally:
            if concat_file.exists():
                concat_file.unlink()
            temp = self.output_dir / "temp_concat.mp4"
            if temp.exists():
                temp.unlink()


# ============================================================
# MAIN: Build the promo video
# ============================================================

def build_promo(use_veo: bool = True, slides_only: bool = False):
    """Build the full promo video from the storyboard."""
    generator = PromoVideoGenerator()
    segments_dir = generator.output_dir / "segments"
    segments_dir.mkdir(exist_ok=True)
    segments = []

    print("=" * 60)
    print("AUTO MARKETING PROMO VIDEO GENERATOR")
    print(f"  Veo: {'enabled (~$0.20/slide)' if use_veo else 'disabled (free zoom-out)'}")
    print(f"  Slides only: {slides_only}")
    print("=" * 60)

    for item in STORYBOARD:
        seg_path = str(segments_dir / f"{item['id']}.mp4")

        if item["type"] == "slide":
            result = generator.create_animated_slide(
                item["text"],
                seg_path,
                duration=item["duration"],
                subtitle=item.get("subtitle"),
                use_veo=use_veo,
            )
            if result:
                segments.append(seg_path)

        elif item["type"] == "screen":
            # Screen recording segments — check if pre-recorded file exists
            screen_path = generator.output_dir / "screen_recordings" / f"{item['id']}.mp4"
            if screen_path.exists():
                result = generator.embed_video(
                    str(screen_path), seg_path, max_duration=item["duration"]
                )
                if result:
                    segments.append(seg_path)
            else:
                print(f"\n  SKIP: Screen recording not found: {screen_path}")
                print(f"         Run record_walkthrough.py first, then re-run this script.")

        elif item["type"] == "gallery":
            # Gallery from carousel screenshots
            screenshots_dir = generator.output_dir / "screenshots"
            images = sorted(str(p) for p in screenshots_dir.glob("carousel_*.png"))
            if images:
                result = generator.create_quick_gallery(
                    images, seg_path, duration_per_image=item["duration"] / len(images)
                )
                if result:
                    segments.append(seg_path)
            else:
                print(f"\n  SKIP: No carousel screenshots found in {screenshots_dir}")

    if slides_only:
        print(f"\nSlide images generated. Check {generator.output_dir / 'slides'}/")
        return

    # Assemble
    if segments:
        audio_path = generator.output_dir / "soundtrack" / "promo_music.mp3"
        generator.concatenate_segments(
            segments,
            str(generator.output_dir / "auto_marketing_promo.mp4"),
            audio_path=str(audio_path) if audio_path.exists() else None,
        )
    else:
        print("\nNo segments generated. Nothing to assemble.")

    print("\nDone!")


if __name__ == "__main__":
    import sys
    use_veo = "--no-veo" not in sys.argv
    slides_only = "--slides-only" in sys.argv
    bg_only = "--background-only" in sys.argv

    if bg_only:
        gen = PromoVideoGenerator()
        bg_path = str(gen.output_dir / "slides" / "_background.png")
        gen.generate_background(bg_path)
    else:
        build_promo(use_veo=use_veo, slides_only=slides_only)
