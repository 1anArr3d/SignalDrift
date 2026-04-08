import os
import random
import subprocess
import textwrap
from pathlib import Path
import ffmpeg
from PIL import Image, ImageDraw, ImageFont

# Constants
_FONT_FILE = "C:/Windows/Fonts/arial.ttf"
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "backgrounds"
_MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
_TEMP_DIR = Path("output/temp")
CARD_SHOW_SECONDS = 4.0

def _seconds_to_ass_time(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _write_ass(word_timings: list[dict], width: int, height: int, path: str):
    """Generates stationary, single-word captions with no skipping."""
    # Center coordinates
    center_x = width // 2
    center_y = height // 2
    
    header = (
        f"[Script Info]\nPlayResX: {width}\nPlayResY: {height}\n\n"
        f"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Outline, Alignment\n"
        f"Style: Default,Bahnschrift,{width//8},&H00FFFFFF,8,5\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Text\n"
    )
    
    words = [w for w in word_timings if w['start'] >= CARD_SHOW_SECONDS]
    events = []
    
    for i, curr in enumerate(words):
        start = _seconds_to_ass_time(curr['start'])
        
        # Determine the end time: 0.01s BEFORE the next word starts
        if i < len(words) - 1:
            end_val = max(curr['start'] + 0.05, words[i+1]['start'] - 0.01)
        else:
            end_val = curr['end'] + 0.5
            
        end = _seconds_to_ass_time(end_val)
        text = curr['word'].upper().strip().replace('"', '')
        
        # \pos forces it to the exact center, \an5 ensures it anchors from its own center
        events.append(f"Dialogue: 0,{start},{end},Default,{{\\an5\\pos({center_x},{center_y})}}{text}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))

def _get_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    return float(subprocess.check_output(cmd).decode().strip())

def _render_case_panel(post_info: dict, width: int, height: int, output_path: str):
    """Creates the 'Case File' intro graphic."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    card_w, card_h = int(width * 0.9), 400
    x0, y0 = (width - card_w) // 2, int(height * 0.35)
    
    draw.rounded_rectangle([x0, y0, x0+card_w, y0+card_h], radius=15, fill=(15, 15, 20, 230), 
                           outline=(100, 100, 120, 200), width=2)
    
    try:
        f_title, f_sub = ImageFont.truetype(_FONT_FILE, 50), ImageFont.truetype(_FONT_FILE, 35)
    except:
        f_title = f_sub = ImageFont.load_default()

    title = textwrap.fill(post_info.get("title", "Untitled Story"), width=25)
    draw.multiline_text((x0 + 40, y0 + 60), title, font=f_title, fill="white", spacing=10)
    draw.text((x0 + 40, y0 + 320), f"r/{post_info.get('subreddit', 'Horror')}", font=f_sub, fill=(255, 69, 0))
    img.save(output_path)

def compose(audio_path: str, output_path: str, config: dict, post_info: dict, word_timings: list) -> str:
    print(f"[composer] Rendering: {output_path}")
    _TEMP_DIR.mkdir(parents=True, exist_ok=True)
    duration = _get_duration(audio_path)
    ass_file, card_file = "temp_render.ass", str(_TEMP_DIR / "intro.png")

    # 1. Assets
    _write_ass(word_timings, 1080, 1920, ass_file)
    _render_case_panel(post_info, 1080, 1920, card_file)

    # 2. Pick Backgrounds (Ternary selection)
    bg_pool = [str(f) for f in _ASSETS_DIR.glob("*.mp4")]
    ms_pool = [str(f) for f in _MUSIC_DIR.glob("*.mp3")]
    bg_input = random.choice(bg_pool) if bg_pool else "color=c=0x0a0a0f:s=1080x1920:r=30"
    
    # 3. Video Chain (Chained filters)
    video = (
        ffmpeg.input(bg_input, stream_loop=-1, t=duration, f='lavfi' if not bg_pool else None)
        .filter('scale', -2, 1920).filter('crop', 1080, 1920)
        .filter('drawbox', color='black@0.5', t='fill')
        .filter('noise', alls=10, allf='t+u')
    )
    video = ffmpeg.overlay(video, ffmpeg.input(card_file), enable=f'lte(t,{CARD_SHOW_SECONDS})')
    video = video.filter('ass', filename=ass_file)

    # 4. Audio Chain (One-liner mix)
    narration = (
    ffmpeg.input(audio_path).audio
    .filter("compand", points="-80/-80|-20/-20|-15/-10|0/-7", gain=3)
    )
    music = ffmpeg.input(random.choice(ms_pool), stream_loop=-1, t=duration).audio.filter('volume', 0.08) if ms_pool else None
    audio = ffmpeg.filter([narration, music], 'amix', inputs=2, duration='first') if music else narration

    # 5. Execute
    try:
        (ffmpeg.output(video, audio, output_path, vcodec='libx264', acodec='aac', 
                       video_bitrate='2500k', pix_fmt='yuv420p', r=30, preset='veryfast')
         .overwrite_output().run(capture_stdout=True, capture_stderr=True))
    finally:
        if os.path.exists(ass_file): os.remove(ass_file)

    return output_path