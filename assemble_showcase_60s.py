"""
Assemble the final 60-second QA-Genius showcase video from the captured screen recording,
intro/outro/tech cards, AI voiceover, and background music.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import edge_tts
import numpy as np
from moviepy import (
    AudioClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1920, 1080
FPS = 30
TOTAL_DURATION = 60.0
OUTPUT_PATH = Path("assets/qa_genius_showcase_60s.mp4")
RAW_RECORDING = Path("assets/recordings/page@ea071dbfc0a3bbe73141890b80594292.webm")
VOICEOVER_PATH = Path("assets/voiceover.mp3")

FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
FONT_EMOJI = "C:/Windows/Fonts/seguiemj.ttf"

BG_TOP = (15, 16, 32)
BG_BOTTOM = (26, 26, 46)
ACCENT = (167, 139, 250)
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (148, 163, 184)
TEXT_GREEN = (52, 211, 153)

NARRATION = """Meet QA-Genius, the SQA Intelligence Suite that turns plain text into structured QA artifacts.
Start with a vague user story. The Story Analyzer evaluates INVEST criteria, flags ambiguous words, and suggests a clearer rewrite with Gherkin acceptance criteria.
Then generate comprehensive test cases with functional, boundary, edge, and negative scenarios, complete with BDD steps and traceability tags.
Turn messy bug notes into production-grade bug reports with severity, root cause, and investigation checklists.
Plus quality analytics, automation projects, schema validation, security tests, and k6 performance scripts.
Built with Streamlit, LangChain, and Gemini, featuring structured Pydantic outputs, JSON repair, and retry logic.
QA-Genius. Built for QA engineers, by a QA engineer."""

# ── Timing ───────────────────────────────────────────────────────────────────
SEGMENTS = {
    "intro": (0.0, 5.4),
    "story": (5.4, 18.8),
    "test_cases": (18.8, 32.2),
    "bug_report": (32.2, 42.2),
    "montage": (42.2, 50.6),
    "tech": (50.6, 57.0),
    "outro": (57.0, 62.4),
}

RAW_CUTS = {
    "story": (6.0, 19.4),
    "test_cases": (20.0, 33.4),
    "bug_report": (40.0, 50.0),
    "montage": (50.0, 58.4),
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_font(size: int, bold: bool = False, emoji: bool = False):
    path = FONT_EMOJI if emoji else (FONT_BOLD if bold else FONT_REGULAR)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def gradient_background(width: int, height: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (width, height))
    for y in range(height):
        ratio = y / height
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        ImageDraw.Draw(img).line([(0, y), (width, y)], fill=(r, g, b))
    return img


def add_glow(img: Image.Image, color: tuple, intensity: int = 40) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgb = color[:3]
    max_alpha = color[3] if len(color) == 4 else 60
    for i in range(intensity, 0, -1):
        alpha = int(max_alpha * (i / intensity))
        radius = i * 25
        draw.ellipse([WIDTH - radius, -radius // 2, WIDTH + radius // 3, radius], fill=rgb + (alpha,))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def text_size(text: str, font) -> tuple:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def pil_to_clip(img: Image.Image, duration: float) -> ImageClip:
    return ImageClip(np.array(img), duration=duration)


# ── Card builders ────────────────────────────────────────────────────────────

def build_intro_card() -> ImageClip:
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (50,))
    draw = ImageDraw.Draw(img)

    for i, alpha in enumerate([15, 10, 5]):
        r = 300 + i * 120
        draw.ellipse([WIDTH // 2 - r, HEIGHT // 2 - r, WIDTH // 2 + r, HEIGHT // 2 + r], outline=ACCENT + (alpha,), width=2)

    title_font = load_font(110, bold=True)
    subtitle_font = load_font(36)
    tagline_font = load_font(26)

    draw.text((WIDTH // 2, HEIGHT // 2 - 80), "QA-Genius", font=title_font, fill=TEXT_WHITE, anchor="mm")
    draw.text((WIDTH // 2, HEIGHT // 2 + 25), "SQA Intelligence Suite", font=subtitle_font, fill=ACCENT, anchor="mm")
    draw.text((WIDTH // 2, HEIGHT // 2 + 95), "Turn plain text into structured QA artifacts", font=tagline_font, fill=TEXT_GRAY, anchor="mm")

    return pil_to_clip(img, SEGMENTS["intro"][1] - SEGMENTS["intro"][0])


def build_tech_card() -> ImageClip:
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (35,))
    draw = ImageDraw.Draw(img)

    title_font = load_font(52, bold=True)
    badge_font = load_font(26, bold=True)
    body_font = load_font(30)
    check_font = load_font(32, emoji=True)

    draw.text((WIDTH // 2, 110), "Built for reliability", font=title_font, fill=TEXT_WHITE, anchor="mm")

    badges = [
        ("Streamlit", "#FF4B4B"),
        ("LangChain", "#1C3C3C"),
        ("Gemini", "#4285F4"),
        ("Pydantic v2", "#E92063"),
        ("Tenacity", "#38BDF8"),
    ]

    def hex_to_rgb(h: str) -> tuple:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    badge_w = 210
    gap = 18
    total_w = len(badges) * badge_w + (len(badges) - 1) * gap
    start_x = (WIDTH - total_w) // 2 + badge_w // 2
    y = 230
    for i, (name, color) in enumerate(badges):
        x = start_x + i * (badge_w + gap)
        draw.rounded_rectangle([x - badge_w // 2, y - 35, x + badge_w // 2, y + 35], radius=16, fill=hex_to_rgb(color) + (220,), outline=TEXT_WHITE, width=1)
        draw.text((x, y + 2), name, font=badge_font, fill=TEXT_WHITE, anchor="mm")

    highlights = [
        ("✓", "Structured outputs via Pydantic schemas"),
        ("✓", "5-stage JSON repair for malformed LLM responses"),
        ("✓", "Exponential backoff retries on transient failures"),
    ]
    y = 380
    for check, text in highlights:
        check_w, _ = text_size(check, check_font)
        text_w, text_h = text_size(text, body_font)
        total_w = check_w + 16 + text_w
        start_x = (WIDTH - total_w) // 2
        draw.text((start_x + check_w // 2, y + text_h // 2), check, font=check_font, fill=TEXT_GREEN, anchor="mm")
        draw.text((start_x + check_w + 16, y + text_h // 2), text, font=body_font, fill=TEXT_WHITE, anchor="lm")
        y += 65

    return pil_to_clip(img, SEGMENTS["tech"][1] - SEGMENTS["tech"][0])


def build_outro_card() -> ImageClip:
    img = gradient_background(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = add_glow(img, ACCENT + (50,))
    draw = ImageDraw.Draw(img)

    big_font = load_font(90, bold=True)
    medium_font = load_font(40)
    small_font = load_font(28)

    draw.text((WIDTH // 2, HEIGHT // 2 - 70), "QA-Genius", font=big_font, fill=TEXT_WHITE, anchor="mm")
    draw.text((WIDTH // 2, HEIGHT // 2 + 30), "Built for QA engineers, by a QA engineer", font=medium_font, fill=TEXT_GRAY, anchor="mm")
    draw.text((WIDTH // 2, HEIGHT // 2 + 110), "Run it locally  •  Star it on GitHub  •  Share feedback", font=small_font, fill=ACCENT, anchor="mm")

    return pil_to_clip(img, SEGMENTS["outro"][1] - SEGMENTS["outro"][0])


# ── Voiceover ────────────────────────────────────────────────────────────────

async def generate_voiceover() -> None:
    communicate = edge_tts.Communicate(NARRATION, voice="en-US-AriaNeural", rate="+5%")
    await communicate.save(str(VOICEOVER_PATH))


def ensure_voiceover() -> None:
    if VOICEOVER_PATH.exists():
        return
    print("Generating voiceover with edge-tts...")
    asyncio.run(generate_voiceover())


# ── Music ────────────────────────────────────────────────────────────────────

def make_music(duration: float, fps: int = 44100) -> AudioClip:
    t = np.linspace(0, duration, int(duration * fps), False)
    chords = [
        [130.81, 155.56, 196.00, 233.08],
        [103.83, 130.81, 155.56, 196.00],
        [82.41, 103.83, 130.81, 164.81],
        [116.54, 146.83, 174.61, 207.65],
    ]
    chord_duration = duration / len(chords)
    audio = np.zeros_like(t)

    for i, chord in enumerate(chords):
        start = int(i * chord_duration * fps)
        end = int((i + 1) * chord_duration * fps)
        seg_t = t[start:end]
        env = np.ones_like(seg_t)
        fade = int(0.5 * fps)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        chord_wave = np.zeros_like(seg_t)
        for f in chord:
            chord_wave += np.sin(2 * np.pi * f * seg_t) * 0.08
            chord_wave += np.sin(2 * np.pi * f * 2 * seg_t) * 0.04
        audio[start:end] += chord_wave * env

    arp_freqs = [261.63, 329.63, 392.00, 523.25] * int(np.ceil(duration / 2))
    for i, f in enumerate(arp_freqs[: int(duration * 2)]):
        start = int(i * 0.5 * fps)
        end = min(start + int(0.4 * fps), len(audio))
        seg_t = np.linspace(0, 0.4, end - start)
        env = np.exp(-seg_t * 4)
        audio[start:end] += np.sin(2 * np.pi * f * seg_t) * 0.03 * env

    window = 20
    audio = np.convolve(audio, np.ones(window) / window, mode="same")
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.18

    def frame_function(t_):
        t_ = np.asarray(t_)
        indices = (t_ * fps).astype(int)
        indices = np.clip(indices, 0, len(audio) - 1)
        result = audio[indices]
        if result.ndim == 0:
            result = np.array([[float(result), float(result)]])
        elif result.ndim == 1:
            result = np.column_stack([result, result])
        return result

    return AudioClip(frame_function, duration=duration, fps=fps)


# ── Main assembly ────────────────────────────────────────────────────────────

def assemble() -> CompositeVideoClip:
    ensure_voiceover()

    # Load raw recording and cut segments
    raw = VideoFileClip(str(RAW_RECORDING))
    segments = {}
    for name, (start, end) in RAW_CUTS.items():
        segments[name] = raw.subclipped(start, end)

    # Build cards
    intro = build_intro_card()
    tech = build_tech_card()
    outro = build_outro_card()

    # Order and durations must match SEGMENTS
    scene_clips = [intro, segments["story"], segments["test_cases"], segments["bug_report"], segments["montage"], tech, outro]

    # Verify total duration
    total = sum(c.duration for c in scene_clips)
    print(f"Scene clips total duration: {total:.1f}s")

    # Crossfade
    crossfade = 0.4
    video = concatenate_videoclips(scene_clips, method="compose", padding=-crossfade)

    # Voiceover
    voice = AudioFileClip(str(VOICEOVER_PATH))
    print(f"Voiceover duration: {voice.duration:.1f}s")
    # If voiceover is shorter than video, pad with silence at end
    if voice.duration < video.duration:
        silence = AudioClip(lambda t: 0, duration=video.duration - voice.duration, fps=voice.fps)
        voice = concatenate_audioclips([voice, silence])
    else:
        voice = voice.subclipped(0, video.duration)

    # Background music
    music = make_music(video.duration)

    # Mix audio
    final_audio = CompositeAudioClip([voice.with_volume_scaled(1.0), music.with_volume_scaled(0.35)])
    video = video.with_audio(final_audio)

    return video


if __name__ == "__main__":
    print("Assembling 60-second QA-Genius showcase...")
    video = assemble()
    print(f"Final duration: {video.duration:.1f}s")
    print(f"Rendering to {OUTPUT_PATH}...")
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
