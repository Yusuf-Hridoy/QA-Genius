"""
QA-Genius 90-second showcase video generator.
Outputs a 1920x1080 30fps MP4 suitable for LinkedIn / X.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from moviepy import (
    AudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

# ── Configuration ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1920, 1080
FPS = 30
DURATION = 90.0
OUTPUT_PATH = Path("assets/qa_genius_showcase.mp4")
SCREENSHOT_PATH = Path("assets/app_screenshot.png")
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
FONT_LIGHT = "C:/Windows/Fonts/segoeui.ttf"  # fallback light
FONT_EMOJI = "C:/Windows/Fonts/seguiemj.ttf"

# Palette (dark theme matching the app)
BG_TOP = (15, 16, 32)
BG_BOTTOM = (26, 26, 46)
CARD_BG = (30, 31, 52, 230)
CARD_BORDER = (124, 58, 237)
ACCENT = (167, 139, 250)
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (148, 163, 184)
TEXT_GREEN = (52, 211, 153)
TEXT_YELLOW = (251, 191, 36)

# ── Helpers ──────────────────────────────────────────────────────────────────

def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def load_font(size: int, bold: bool = False, emoji: bool = False) -> ImageFont.FreeTypeFont:
    if emoji:
        path = FONT_EMOJI
    else:
        path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def gradient_background(width: int, height: int, top: tuple, bottom: tuple) -> Image.Image:
    """Create a vertical gradient background."""
    img = Image.new("RGB", (width, height))
    for y in range(height):
        ratio = y / height
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        ImageDraw.Draw(img).line([(0, y), (width, y)], fill=(r, g, b))
    return img


def add_glow(img: Image.Image, color: tuple, intensity: int = 40) -> Image.Image:
    """Add a subtle top-right glow.

    color: RGB tuple (r, g, b) or RGBA tuple (r, g, b, max_alpha).
    """
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgb = color[:3]
    max_alpha = color[3] if len(color) == 4 else 60
    for i in range(intensity, 0, -1):
        alpha = int(max_alpha * (i / intensity))
        radius = i * 25
        draw.ellipse([WIDTH - radius, -radius // 2, WIDTH + radius // 3, radius], fill=rgb + (alpha,))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def rounded_rectangle(
    draw: ImageDraw.Draw,
    bbox: tuple,
    radius: int,
    fill: tuple | None = None,
    outline: tuple | None = None,
    width: int = 1,
) -> None:
    x1, y1, x2, y2 = bbox
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)


def draw_text(
    draw: ImageDraw.Draw,
    text: str,
    pos: tuple,
    font: ImageFont.FreeTypeFont,
    fill: tuple = TEXT_WHITE,
    anchor: str = "lt",
) -> None:
    draw.text(pos, text, font=font, fill=fill, anchor=anchor)


def text_size(text: str, font: ImageFont.FreeTypeFont) -> tuple:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Simple word-wrap."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        w, _ = text_size(test, font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def pil_to_clip(img: Image.Image, duration: float) -> ImageClip:
    return ImageClip(np.array(img), duration=duration)


# ── Scene builders ───────────────────────────────────────────────────────────

def build_intro_scene(duration: float = 5.0) -> ImageClip:
    """Scene 1: Animated logo intro."""
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (40,))
    draw = ImageDraw.Draw(img)

    # Decorative circles
    for i, alpha in enumerate([15, 10, 5]):
        r = 300 + i * 120
        draw.ellipse([WIDTH // 2 - r, HEIGHT // 2 - r, WIDTH // 2 + r, HEIGHT // 2 + r], outline=ACCENT + (alpha,), width=2)

    title_font = load_font(120, bold=True)
    subtitle_font = load_font(42)
    tagline_font = load_font(28)

    title = "QA-Genius"
    subtitle = "SQA Intelligence Suite"
    tagline = "From vague user stories to production-ready test artifacts"

    tw, th = text_size(title, title_font)
    draw_text(draw, title, (WIDTH // 2, HEIGHT // 2 - 80), title_font, anchor="mm")
    draw_text(draw, subtitle, (WIDTH // 2, HEIGHT // 2 + 30), subtitle_font, fill=ACCENT, anchor="mm")
    draw_text(draw, tagline, (WIDTH // 2, HEIGHT // 2 + 110), tagline_font, fill=TEXT_GRAY, anchor="mm")

    return pil_to_clip(img, duration)


def build_problem_scene(duration: float = 7.0) -> ImageClip:
    """Scene 2: Problem + solution hook."""
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, (239, 68, 68, 30))  # reddish glow
    draw = ImageDraw.Draw(img)

    title_font = load_font(54, bold=True)
    body_font = load_font(36)
    accent_font = load_font(44, bold=True)

    y = 260
    draw_text(draw, "QA teams spend hours writing...", (WIDTH // 2, y), title_font, fill=TEXT_GRAY, anchor="mm")

    bullets = [
        "• Test cases from incomplete user stories",
        "• Bug reports from scattered Slack notes",
        "• k6 scripts, schema checks, security cases",
    ]
    y += 90
    for b in bullets:
        draw_text(draw, b, (WIDTH // 2, y), body_font, fill=TEXT_WHITE, anchor="mm")
        y += 65

    y += 50
    draw_text(draw, "What if AI generated the structure in seconds?", (WIDTH // 2, y), accent_font, fill=TEXT_GREEN, anchor="mm")

    return pil_to_clip(img, duration)


def build_overview_scene(duration: float = 8.0) -> ImageClip:
    """Scene 3: App overview with screenshot."""
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (30,))
    draw = ImageDraw.Draw(img)

    title_font = load_font(52, bold=True)
    subtitle_font = load_font(30)

    draw_text(draw, "One workspace. Eight QA workflows.", (WIDTH // 2, 100), title_font, anchor="mm")

    # Screenshot with rounded corners and shadow
    if SCREENSHOT_PATH.exists():
        shot = Image.open(SCREENSHOT_PATH).convert("RGBA")
        target_w = 1400
        target_h = int(shot.height * (target_w / shot.width))
        shot = shot.resize((target_w, target_h), Image.LANCZOS)

        # rounded mask
        mask = Image.new("L", (target_w, target_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, target_w, target_h], radius=16, fill=255)
        shot.putalpha(mask)

        x = (WIDTH - target_w) // 2
        y = 160
        # shadow
        shadow = Image.new("RGBA", (target_w + 40, target_h + 40), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([20, 20, target_w + 20, target_h + 20], radius=16, fill=(0, 0, 0, 80))
        img.paste(shadow, (x - 20, y - 20), shadow)
        img.paste(shot, (x, y), shot)

        draw_text(draw, "Dark-themed Streamlit app with wide layout & custom CSS", (WIDTH // 2, y + target_h + 40), subtitle_font, fill=TEXT_GRAY, anchor="mm")

    return pil_to_clip(img, duration)


def build_feature_scene(
    icon: str,
    title: str,
    duration: float,
    demo_input: str,
    outputs: list[str],
    export: str,
    glow_color: tuple,
) -> ImageClip:
    """Generic feature scene with demo input/output cards."""
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, glow_color + (35,))
    draw = ImageDraw.Draw(img)

    icon_font = load_font(70, emoji=True)
    title_font = load_font(56, bold=True)
    label_font = load_font(24, bold=True)
    body_font = load_font(26)
    small_font = load_font(22)

    # Header: icon + title side by side, centered
    icon_w, icon_h = text_size(icon, icon_font)
    title_w, title_h = text_size(title, title_font)
    gap = 18
    total_w = icon_w + gap + title_w
    start_x = (WIDTH - total_w) // 2
    icon_y = 110
    draw_text(draw, icon, (start_x + icon_w // 2, icon_y), icon_font, anchor="mm")
    draw_text(draw, title, (start_x + icon_w + gap + title_w // 2, icon_y), title_font, anchor="mm")

    card_radius = 20
    margin = 90
    top = 200
    bottom = HEIGHT - 140
    mid = WIDTH // 2

    # Input card (left)
    left_card = [margin, top, mid - 30, bottom]
    rounded_rectangle(draw, left_card, card_radius, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw_text(draw, "USER INPUT", (left_card[0] + 25, left_card[1] + 20), label_font, fill=ACCENT, anchor="lt")

    # Demo input text
    y = left_card[1] + 70
    for line in demo_input.split("\n"):
        draw_text(draw, line, (left_card[0] + 25, y), body_font, fill=TEXT_WHITE, anchor="lt")
        y += 38

    # Output card (right)
    right_card = [mid + 30, top, WIDTH - margin, bottom]
    rounded_rectangle(draw, right_card, card_radius, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw_text(draw, "AI-GENERATED OUTPUT", (right_card[0] + 25, right_card[1] + 20), label_font, fill=TEXT_GREEN, anchor="lt")

    y = right_card[1] + 70
    for line in outputs:
        draw_text(draw, line, (right_card[0] + 25, y), body_font, fill=TEXT_WHITE, anchor="lt")
        y += 38

    # Export badge
    badge_h = 50
    badge_w = 360
    badge_x = WIDTH // 2 - badge_w // 2
    badge_y = HEIGHT - 105
    rounded_rectangle(draw, [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], 12, fill=CARD_BORDER + (60,), outline=ACCENT, width=2)
    draw_text(draw, f"Export: {export}", (WIDTH // 2, badge_y + badge_h // 2 + 2), small_font, fill=TEXT_WHITE, anchor="mm")

    return pil_to_clip(img, duration)


def build_tech_scene(duration: float = 10.0) -> ImageClip:
    """Scene 12: Tech stack + reliability."""
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (30,))
    draw = ImageDraw.Draw(img)

    title_font = load_font(52, bold=True)
    badge_font = load_font(26, bold=True)
    body_font = load_font(30)
    check_font = load_font(32, emoji=True)

    draw_text(draw, "Built for reliability", (WIDTH // 2, 110), title_font, anchor="mm")

    badges = [
        ("Streamlit", "#FF4B4B"),
        ("LangChain", "#1C3C3C"),
        ("Gemini 2.5 Flash", "#4285F4"),
        ("Pydantic v2", "#E92063"),
        ("Tenacity", "#38BDF8"),
    ]

    badge_w = 210
    gap = 18
    total_w = len(badges) * badge_w + (len(badges) - 1) * gap
    start_x = (WIDTH - total_w) // 2 + badge_w // 2
    y = 230
    for i, (name, color) in enumerate(badges):
        x = start_x + i * (badge_w + gap)
        rounded_rectangle(draw, [x - badge_w // 2, y - 35, x + badge_w // 2, y + 35], 16, fill=hex_to_rgb(color) + (220,), outline=TEXT_WHITE, width=1)
        draw_text(draw, name, (x, y + 2), badge_font, fill=TEXT_WHITE, anchor="mm")

    highlights = [
        ("✓", "Structured outputs via Pydantic schemas"),
        ("✓", "5-stage JSON repair for malformed LLM responses"),
        ("✓", "Exponential backoff retries on transient failures"),
        ("✓", "Export to CSV / Excel / Markdown / ZIP / .js"),
    ]
    y = 380
    for check, text in highlights:
        check_w, _ = text_size(check, check_font)
        text_w, text_h = text_size(text, body_font)
        total_w = check_w + 16 + text_w
        start_x = (WIDTH - total_w) // 2
        draw_text(draw, check, (start_x + check_w // 2, y + text_h // 2), check_font, fill=TEXT_GREEN, anchor="mm")
        draw_text(draw, text, (start_x + check_w + 16, y + text_h // 2), body_font, fill=TEXT_WHITE, anchor="lm")
        y += 65

    return pil_to_clip(img, duration)


def build_outro_scene(duration: float = 8.0) -> ImageClip:
    """Scene 13: CTA / outro."""
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (45,))
    draw = ImageDraw.Draw(img)

    big_font = load_font(90, bold=True)
    medium_font = load_font(44)
    small_font = load_font(30)

    draw_text(draw, "QA-Genius", (WIDTH // 2, HEIGHT // 2 - 90), big_font, anchor="mm")
    draw_text(draw, "Built for QA engineers, by a QA engineer", (WIDTH // 2, HEIGHT // 2 + 20), medium_font, fill=TEXT_GRAY, anchor="mm")
    draw_text(draw, "Run it locally  •  Star it on GitHub  •  Share your feedback", (WIDTH // 2, HEIGHT // 2 + 110), small_font, fill=ACCENT, anchor="mm")

    return pil_to_clip(img, duration)


# ── Feature data ─────────────────────────────────────────────────────────────

FEATURES = [
    {
        "icon": "📝",
        "title": "Story Analyzer",
        "input": "Story:\n\"As a user I want to login quickly\"",
        "outputs": [
            "• INVEST score per criterion",
            "• Vague phrases flagged: \"quickly\"",
            "• Suggested rewrite + Gherkin AC",
        ],
        "export": "Markdown report",
        "color": (236, 72, 153),  # pink
    },
    {
        "icon": "🧪",
        "title": "Test Cases",
        "input": "E-commerce checkout flow:\nlogin → cart → payment → receipt",
        "outputs": [
            "• Functional / boundary / edge / negative",
            "• Steps, test data, BDD scenarios",
            "• Traceability tags + coverage gaps",
        ],
        "export": "CSV / Excel",
        "color": (52, 211, 153),  # green
    },
    {
        "icon": "🐛",
        "title": "Bug Report",
        "input": "Notes:\n500 error on checkout after coupon",
        "outputs": [
            "• Title, environment, repro steps",
            "• Severity / priority classification",
            "• Suspected pattern + investigation checklist",
        ],
        "export": "Markdown",
        "color": (239, 68, 68),  # red
    },
    {
        "icon": "📊",
        "title": "Quality Analytics",
        "input": "Sprint summary:\n120 tests, 14 defects, 3 reopened",
        "outputs": [
            "• Pass rate, defect density, MTTR",
            "• Trend comparison vs last sprint",
            "• Prioritized recommendations + owners",
        ],
        "export": "Markdown report",
        "color": (59, 130, 246),  # blue
    },
    {
        "icon": "⚙️",
        "title": "Automation Script",
        "input": "App: login + dashboard\nStack: JS / Playwright / POM",
        "outputs": [
            "• Test files + page objects",
            "• Config + package.json",
            "• Run instructions (JS or TS)",
        ],
        "export": "ZIP project",
        "color": (245, 158, 11),  # amber
    },
    {
        "icon": "🔍",
        "title": "Schema Validator",
        "input": "API JSON response:\nuser { id, email, ssn, role }",
        "outputs": [
            "• Type mismatch detection",
            "• Format violations",
            "• PII exposure + security risks",
        ],
        "export": "Markdown findings",
        "color": (139, 92, 246),  # violet
    },
    {
        "icon": "🔒",
        "title": "Security Tests",
        "input": "Stack: Node.js / JWT / Postgres\nCompliance: OWASP Top 10",
        "outputs": [
            "• OWASP-mapped test cases",
            "• Attack payloads + severity",
            "• Remediation + tool hints",
        ],
        "export": "Markdown / checklist",
        "color": (239, 68, 68),  # red
    },
    {
        "icon": "⚡",
        "title": "Performance Tests",
        "input": "Endpoints: /login, /checkout\nSLA: p95 < 500ms",
        "outputs": [
            "• k6 script with 6 load profiles",
            "• Smoke → Load → Stress → Breakpoint",
            "• Correlation + execution plan",
        ],
        "export": ".js k6 script",
        "color": (234, 179, 8),  # yellow
    },
]


# ── Audio generator ──────────────────────────────────────────────────────────

def make_ambient_music(duration: float, fps: int = 44100) -> AudioClip:
    """Generate a soft ambient background pad."""
    t = np.linspace(0, duration, int(duration * fps), False)

    # Chord progression frequencies (Cm7 → Abmaj7 → Ebmaj7 → Bb)
    chords = [
        [130.81, 155.56, 196.00, 233.08],  # C3, Eb3, G3, Bb3
        [103.83, 130.81, 155.56, 196.00],  # Ab2, C3, Eb3, G3
        [82.41, 103.83, 130.81, 164.81],   # Eb2, Ab2, C3, E3
        [116.54, 146.83, 174.61, 207.65],  # Bb2, D3, F3, Ab3
    ]
    chord_duration = duration / len(chords)

    audio = np.zeros_like(t)
    for i, chord in enumerate(chords):
        start = int(i * chord_duration * fps)
        end = int((i + 1) * chord_duration * fps)
        seg_t = t[start:end]
        # envelope
        env = np.ones_like(seg_t)
        fade = int(0.5 * fps)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)

        chord_wave = np.zeros_like(seg_t)
        for f in chord:
            chord_wave += np.sin(2 * np.pi * f * seg_t) * 0.08
            chord_wave += np.sin(2 * np.pi * f * 2 * seg_t) * 0.04  # octave
        audio[start:end] += chord_wave * env

    # Subtle arpeggio texture
    arp_freqs = [261.63, 329.63, 392.00, 523.25] * int(np.ceil(duration / 2))
    for i, f in enumerate(arp_freqs[: int(duration * 2)]):
        start = int(i * 0.5 * fps)
        end = min(start + int(0.4 * fps), len(audio))
        seg_t = np.linspace(0, 0.4, end - start)
        env = np.exp(-seg_t * 4)
        audio[start:end] += np.sin(2 * np.pi * f * seg_t) * 0.03 * env

    # Lowpass-ish smoothing via simple moving average
    window = 20
    audio = np.convolve(audio, np.ones(window) / window, mode="same")

    # Normalize
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.25

    def frame_function(t):
        t = np.asarray(t)
        indices = (t * fps).astype(int)
        indices = np.clip(indices, 0, len(audio) - 1)
        result = audio[indices]
        return result if result.shape else float(result)

    return AudioClip(frame_function, duration=duration, fps=fps)


# ── Main assembly ────────────────────────────────────────────────────────────

def build_video() -> CompositeVideoClip:
    scenes = []

    # Intro
    scenes.append(build_intro_scene(5.0))

    # Problem
    scenes.append(build_problem_scene(7.0))

    # Overview
    scenes.append(build_overview_scene(8.0))

    # Features: 8 tabs x 7.0s = 56s
    for feat in FEATURES:
        scenes.append(
            build_feature_scene(
                icon=feat["icon"],
                title=feat["title"],
                duration=7.0,
                demo_input=feat["input"],
                outputs=feat["outputs"],
                export=feat["export"],
                glow_color=feat["color"],
            )
        )

    # Tech stack
    scenes.append(build_tech_scene(10.0))

    # Outro
    scenes.append(build_outro_scene(8.0))

    # Crossfade between scenes
    crossfade = 0.4
    final = concatenate_videoclips(scenes, method="compose", padding=-crossfade)

    # Add background music
    music = make_ambient_music(final.duration)
    final = final.with_audio(music)

    return final


if __name__ == "__main__":
    print("Building QA-Genius showcase video...")
    video = build_video()
    print(f"Total duration: {video.duration:.1f}s, size: {video.size}")
    print(f"Rendering to {OUTPUT_PATH} ...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(OUTPUT_PATH),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(OUTPUT_PATH.with_suffix(".m4a")),
        remove_temp=True,
        threads=4,
        preset="medium",
    )
    print(f"Done! Video saved at {OUTPUT_PATH.resolve()}")
