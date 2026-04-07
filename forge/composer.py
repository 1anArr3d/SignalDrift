"""
composer.py
FFmpeg pipeline that assembles the final vertical MP4.

Steps:
  1. Pick a random atmospheric loop from assets/backgrounds/ (fallback: dark gradient)
  2. Scale/crop to 1080x1920 portrait, apply dark overlay + film grain
  3. Overlay a styled "CASE FILE" panel for the first N seconds
  4. Add a persistent subreddit watermark in the bottom-left corner
  5. Burn word-level captions (ASS subtitles) in the same pass
  6. Mix narration + background music inline, then mux into output MP4

Requires: ffmpeg on PATH, ffmpeg-python, Pillow.
"""

import os
import random
import subprocess
import tempfile
import textwrap
from pathlib import Path

import ffmpeg


# ---------------------------------------------------------------------------
# Captions (merged from caption_burner.py)
# ---------------------------------------------------------------------------

def _seconds_to_ass_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _sanitise_ass(text: str) -> str:
    text = text.replace("\\", "")
    text = text.replace("{", "")
    text = text.replace("}", "")
    text = text.replace("\n", " ")
    return text


def _group_words(word_timings: list[dict], n: int = 2, sentence_gap: float = 0.7) -> list[dict]:
    """
    Merge consecutive words into n-word caption chunks.
    Gaps <= sentence_gap are filled (word holds until next).
    Gaps > sentence_gap are treated as sentence boundaries (caption clears).
    """
    groups = []
    bucket: list[dict] = []

    def flush():
        if bucket:
            groups.append({
                "word":  " ".join(w["word"] for w in bucket),
                "start": bucket[0]["start"],
                "end":   bucket[-1]["end"],
            })
        bucket.clear()

    for i, w in enumerate(word_timings):
        if bucket:
            prev_original_end = word_timings[i - 1]["end"]
            gap = w["start"] - prev_original_end
            if gap > sentence_gap:
                flush()
            elif gap > 0:
                prev = bucket[-1]
                bucket[-1] = {**prev, "end": w["start"]}
        bucket.append(w)
        if len(bucket) >= n:
            flush()

    flush()
    return groups


def _write_ass(word_timings: list[dict], width: int, height: int, path: str, start_after: float = 0.0, words_per_caption: int = 2) -> None:
    font_size = max(100, width // 9)
    outline   = 22
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Bahnschrift,{font_size},"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},0,5,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    eligible = [w for w in word_timings if w["start"] >= start_after]
    for g in _group_words(eligible, n=words_per_caption):
        start = _seconds_to_ass_time(g["start"])
        end   = _seconds_to_ass_time(g["end"])
        text  = _sanitise_ass(g["word"].upper())
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

_FFMPEG_DIR = os.environ.get(
    "FFMPEG_BIN",
    r"C:\Users\ianme\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
)
os.environ["PATH"] = _FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

_FONT_DIR   = r"C:\Windows\Fonts"
_FONT_PATH  = r"C\:/Windows/Fonts/arialbd.ttf"
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "backgrounds"
_MUSIC_DIR  = Path(__file__).resolve().parent.parent / "assets" / "music"

CARD_SHOW_SECONDS = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         audio_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _sanitise_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


# ---------------------------------------------------------------------------
# Asset pickers
# ---------------------------------------------------------------------------

def _pick_background_loop() -> str | None:
    if not _ASSETS_DIR.exists():
        print(f"[composer] assets/backgrounds/ not found at {_ASSETS_DIR}")
        return None
    loops = [
        _ASSETS_DIR / f
        for f in os.listdir(_ASSETS_DIR)
        if Path(f).suffix in {".mp4", ".mov", ".MP4", ".MOV"}
    ]
    if not loops:
        print(f"[composer] No video files found in {_ASSETS_DIR}. Files: {os.listdir(_ASSETS_DIR)}")
        return None
    chosen = random.choice(loops)
    print(f"[composer] Background loop: {chosen.name}")
    return str(chosen)


def _pick_music_track() -> str | None:
    if not _MUSIC_DIR.exists():
        return None
    tracks = [_MUSIC_DIR / f for f in os.listdir(_MUSIC_DIR) if Path(f).suffix in {".mp3", ".wav", ".m4a"}]
    if not tracks:
        return None
    chosen = random.choice(tracks)
    print(f"[composer] Music track: {chosen.name}")
    return str(chosen)


# ---------------------------------------------------------------------------
# Stream builders
# ---------------------------------------------------------------------------

def _build_background_stream(loop_path: str | None, width: int, height: int, duration: float, fps: int):
    """Return a video stream scaled/cropped to target resolution."""
    if loop_path:
        raw    = ffmpeg.input(loop_path, stream_loop=-1, t=duration).video
        scaled = raw.filter("scale", -2, height)
        return scaled.filter("crop", width, height)
    # Fallback: solid dark colour generated entirely within FFmpeg — no temp file needed
    return ffmpeg.input(
        f"color=c=0x050a1a:size={width}x{height}:rate={fps}:duration={duration}",
        f="lavfi",
    ).video


def _build_audio_stream(audio_path: str, music_path: str | None, duration: float):
    """Return a mixed audio stream (narration + optional background music, single graph)."""
    narration = ffmpeg.input(audio_path).audio
    if not music_path:
        return narration
    music   = ffmpeg.input(music_path, stream_loop=-1, t=duration).audio
    music_q = music.filter("volume", 0.20)
    print("[composer] Mixing narration + music")
    return ffmpeg.filter([narration, music_q], "amix", inputs=2, duration="first", normalize=0)


# ---------------------------------------------------------------------------
# Case file panel — niche styles
# ---------------------------------------------------------------------------

# Each niche defines the badge label, badge colour, card background, and outline colour.
_NICHE_PANEL_STYLES = {
    "unsolved_mysteries": {
        "badge":        "UNSOLVED CASE",
        "badge_color":  (220, 50,  50,  255),   # red
        "card_fill":    (15,  15,  18,  245),   # near-black
        "card_outline": (80,  80,  90,  200),   # dark grey
        "divider":      (80,  80,  90,  180),
    },
    "first_person_horror": {
        "badge":        "TRUE STORY",
        "badge_color":  (180, 30,  220, 255),   # deep purple
        "card_fill":    (10,  5,   15,  245),   # very dark purple-black
        "card_outline": (100, 40,  120, 200),   # muted purple
        "divider":      (100, 40,  120, 180),
    },
}

_DEFAULT_NICHE_STYLE = "unsolved_mysteries"


def _render_case_panel(post_info: dict, width: int, height: int, output_path: str, niche: str = "unsolved_mysteries") -> None:
    """
    Reddit-style card centred on screen. Transparent PNG overlaid for first N seconds.
    Visual style adapts to the niche defined in config.
    """
    from PIL import Image, ImageDraw, ImageFont

    style  = _NICHE_PANEL_STYLES.get(niche, _NICHE_PANEL_STYLES[_DEFAULT_NICHE_STYLE])
    pad    = 40
    card_w = int(width * 0.92)

    try:
        font_badge = ImageFont.truetype(os.path.join(_FONT_DIR, "segoeuib.ttf"), 30)
        font_title = ImageFont.truetype(os.path.join(_FONT_DIR, "segoeuib.ttf"), 52)
        font_sub   = ImageFont.truetype(os.path.join(_FONT_DIR, "segoeuib.ttf"), 32)
    except Exception:
        font_badge = font_title = font_sub = ImageFont.load_default()

    hook     = post_info.get("hook", "")
    subreddit = post_info.get("subreddit", "SignalDrift")
    wrapped  = textwrap.wrap(hook, width=26)[:4]
    line_h   = 64
    card_h   = pad * 2 + 38 + 20 + 2 + 20 + len(wrapped) * line_h + 20 + 40
    card_top = int(height * 0.38)

    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    x0 = (width - card_w) // 2
    x1 = x0 + card_w
    y0 = card_top
    y1 = card_top + card_h

    draw.rounded_rectangle([x0, y0, x1, y1], radius=20, fill=style["card_fill"])
    draw.rounded_rectangle([x0, y0, x1, y1], radius=20, outline=style["card_outline"], width=2)

    y = y0 + pad
    draw.text((x0 + pad, y), style["badge"], font=font_badge, fill=style["badge_color"])
    y += 38
    draw.line([(x0 + pad, y + 10), (x1 - pad, y + 10)], fill=style["divider"], width=1)
    y += 22

    for line in wrapped:
        draw.text((x0 + pad, y), line, font=font_title, fill=(255, 255, 255, 255))
        y += line_h

    y += 16
    draw.text((x0 + pad, y), f"r/{subreddit}", font=font_sub, fill=(255, 69, 0, 255))

    img.save(output_path, "PNG")


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------

def compose(
    audio_path: str,
    output_path: str,
    config: dict,
    post_info: dict | None = None,
    word_timings: list | None = None,
) -> str:
    """
    Assemble audio + atmospheric background into a vertical MP4 in a single encode pass.

    Args:
        audio_path:   Path to TTS MP3/WAV file.
        output_path:  Destination for the rendered MP4.
        config:       Parsed config.yaml dict.
        post_info:    Dict with 'hook' and 'subreddit'.
        word_timings: Word-level timing dicts — captions burned in same pass.

    Returns:
        Path to the rendered MP4.
    """
    forge_cfg = config["forge"]
    width, height = map(int, forge_cfg["resolution"].split("x"))
    fps = forge_cfg["fps"]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    duration   = _get_audio_duration(audio_path)
    loop_path  = _pick_background_loop()
    music_path = _pick_music_track()

    with tempfile.TemporaryDirectory() as tmpdir:

        # --- Video pipeline ---
        video = _build_background_stream(loop_path, width, height, duration, fps)
        video = video.filter("drawbox", x=0, y=0, w="iw", h="ih", color="black@0.45", t="fill")
        video = video.filter("noise", alls=10, allf="t+u")

        if post_info:
            card_path = os.path.join(tmpdir, "case_panel.png")
            niche = config.get("farm", {}).get("niche", "unsolved_mysteries")
            try:
                _render_case_panel(post_info, width, height, card_path, niche=niche)
                card  = ffmpeg.input(card_path).video
                video = ffmpeg.overlay(video, card, x=0, y=0, enable=f"lte(t,{CARD_SHOW_SECONDS})")
            except Exception as e:
                print(f"[composer] Case panel skipped: {e}")

        if post_info and post_info.get("subreddit"):
            sub_text = _sanitise_drawtext(f"r/{post_info['subreddit']}")
            video = video.filter(
                "drawtext",
                fontfile=_FONT_PATH,
                text=sub_text,
                fontsize=max(28, width // 36),
                fontcolor="white@0.55",
                borderw=3,
                bordercolor="black@0.55",
                x=int(width * 0.04),
                y=int(height * 0.90),
            )

        if word_timings:
            ass_path  = output_path.replace(".mp4", ".ass")
            words_per = forge_cfg.get("caption_words_per_frame", 2)
            _write_ass(word_timings, width, height, ass_path, start_after=float(CARD_SHOW_SECONDS), words_per_caption=words_per)
            # Absolute path with escaped colon — safe when output is on a different drive
            ass_ffmpeg = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:")
            video = video.filter("ass", ass_ffmpeg)

        # --- Audio pipeline ---
        audio = _build_audio_stream(audio_path, music_path, duration)

        # --- Single-pass render ---
        (
            ffmpeg
            .output(video, audio, output_path,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="192k",
                ar=44100,
                ac=2,
                pix_fmt="yuv420p",
                r=fps,
                video_bitrate="1500k",
                preset="ultrafast",
                t=duration,
                loglevel="warning",
            )
            .overwrite_output()
            .run()
        )

        if word_timings:
            ass_cleanup = Path(output_path.replace(".mp4", ".ass"))
            if ass_cleanup.exists():
                ass_cleanup.unlink()

    print(f"[composer] Rendered: {output_path} ({duration:.1f}s)")
    return output_path
