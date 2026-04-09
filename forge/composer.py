import os
import random
import subprocess
import textwrap
from pathlib import Path
import ffmpeg
from PIL import Image, ImageDraw, ImageFont

# Constants
_FONT_FILE = "C:/Windows/Fonts/arial.ttf"
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "slicer" / "background_pool"
_TEMP_DIR = Path("output/temp")

def _seconds_to_ass_time(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _write_ass(word_timings: list[dict], width: int, height: int, path: str, start_threshold: float):
    # Leaner font scaling (width//10) to prevent edge-clipping
    header = (
        f"[Script Info]\nPlayResX: {width}\nPlayResY: {height}\n\n"
        f"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Outline, Alignment\n"
        f"Style: Default,Bahnschrift,{width//10},&H00FFFFFF,6,5\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Text\n"
    )
    
    words = [w for w in word_timings if w['start'] >= start_threshold]
    events = []
    
    for i, curr in enumerate(words):
        start = _seconds_to_ass_time(curr['start'])
        # Hold the word until the next one starts
        end_val = words[i+1]['start'] if i < len(words) - 1 else curr['end'] + 1.0
        end = _seconds_to_ass_time(end_val)
        text = curr['word'].upper().strip().replace('"', '')
        events.append(f"Dialogue: 0,{start},{end},Default,{{\\an5\\pos({width//2},{height//2})}}{text}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))

def _get_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    return float(subprocess.check_output(cmd).decode().strip())

def _render_reddit_card(post_info: dict, width: int, height: int, output_path: str):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    card_w, card_h = int(width * 0.9), 450
    x0, y0 = (width - card_w) // 2, int(height * 0.35)
    
    draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=20, fill=(26, 26, 27, 255))
    
    try:
        f_sub, f_title, f_meta = ImageFont.truetype(_FONT_FILE, 30), ImageFont.truetype(_FONT_FILE, 45), ImageFont.truetype(_FONT_FILE, 25)
    except:
        f_sub = f_title = f_meta = ImageFont.load_default()

    subreddit = f"r/{post_info.get('subreddit', 'nosleep')}"
    draw.text((x0 + 40, y0 + 40), subreddit, font=f_sub, fill="white")
    draw.text((x0 + 40 + draw.textlength(subreddit, f_sub) + 15, y0 + 45), "• 12h", font=f_meta, fill=(129, 131, 132))
    
    wrapped_title = textwrap.fill(post_info.get("title", ""), width=30)
    draw.multiline_text((x0 + 40, y0 + 100), wrapped_title, font=f_title, fill="white", spacing=12)
    draw.text((x0 + 40, y0 + 380), "▲ 14.2k ▼", font=f_sub, fill=(129, 131, 132))
    draw.text((x0 + 250, y0 + 380), "💬 842 Comments", font=f_sub, fill=(129, 131, 132))
    img.save(output_path)

def compose(audio_path: str, output_path: str, config: dict, post_info: dict, word_timings: list) -> str:
    _TEMP_DIR.mkdir(parents=True, exist_ok=True)
    duration = _get_duration(audio_path)
    ass_path, card_path = str(_TEMP_DIR / "temp.ass"), str(_TEMP_DIR / "card.png")

    # 1. Timing
    title_words = len(post_info.get("title", "").split())
    title_end = word_timings[title_words - 1]['end'] if len(word_timings) >= title_words else 4.0

    # 2. Assets
    _write_ass(word_timings, 1080, 1920, ass_path, start_threshold=title_end) 
    _render_reddit_card(post_info, 1080, 1920, card_path)

    # 3. Background
    bg_pool = [str(f) for f in _ASSETS_DIR.glob("*.mp4")]
    bg = ffmpeg.input(random.choice(bg_pool), stream_loop=-1, t=duration) if bg_pool else ffmpeg.input("color=c=0x0a0a0f:s=1080x1920:r=30", f="lavfi", t=duration)
    
    # 4. Filter Chain
    video = (
        bg.filter('scale', -2, 1920).filter('crop', 1080, 1920).filter('vignette', angle='0.5')
        .overlay(ffmpeg.input(card_path), enable=f'lte(t,{title_end})')
        .filter('ass', filename=ass_path)
    )

    # 5. Audio & Export (CLEAN: No background music mixing)
    try:
        ffmpeg.output(video, ffmpeg.input(audio_path), output_path, vcodec='libx264', acodec='aac', pix_fmt='yuv420p').overwrite_output().run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        print(f"FFMPEG ERROR: {e.stderr.decode()}")
    return output_path