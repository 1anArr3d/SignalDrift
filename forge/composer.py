import random
import subprocess
import textwrap
from pathlib import Path
import ffmpeg
from PIL import Image, ImageDraw, ImageFont
import shutil

# Constants
_FONT_FILE = "C:/Windows/Fonts/arial.ttf"
_MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
_TEMP_DIR = Path("output/temp")

def _seconds_to_ass_time(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _write_ass(word_timings: list[dict], width: int, height: int, path: str, start_threshold: float):
    header = (
        f"[Script Info]\nPlayResX: {width}\nPlayResY: {height}\n\n"
        f"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Outline, Alignment\n"
        f"Style: Default,Bahnschrift,{width//7},&H00FFFFFF,4,5\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Text\n"
    )

    words = [w for w in word_timings if w['start'] >= start_threshold]
    events = []

    for i, curr in enumerate(words):
        start = _seconds_to_ass_time(curr['start'])
        end_val = words[i+1]['start'] if i < len(words) - 1 else curr['end'] + 1.0
        end = _seconds_to_ass_time(end_val)
        text = curr['word'].upper().strip().replace('"', '')
        events.append(f"Dialogue: 0,{start},{end},Default,{{\\an5\\pos({width//2},{height//2})}}{text}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))

def _get_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    return float(subprocess.check_output(cmd).decode().strip())

def _render_hook_card(post_info: dict, width: int, height: int, output_path: str, label: str = "[ STORY ]"):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    hook_text = post_info.get("hook", post_info.get("title", ""))
    wrapped = textwrap.fill(hook_text, width=20)
    lines = wrapped.split("\n")

    try:
        font       = ImageFont.truetype("C:/Windows/Fonts/cour.ttf", 72)
        font_label = ImageFont.truetype("C:/Windows/Fonts/cour.ttf", 32)
    except:
        font = font_label = ImageFont.load_default()

    line_h  = 90
    block_h = len(lines) * line_h
    y_start = (height - block_h) // 2 - 60

    pad_x, pad_y = 60, 60
    box_x0 = 60
    box_x1 = width - 60
    box_y0 = y_start - pad_y - 60
    box_y1 = y_start + block_h + pad_y

    # White card
    draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=(255, 255, 255, 230))

    # Dark border
    draw.rectangle([box_x0, box_y0, box_x1, box_y1], outline=(20, 20, 20, 255), width=3)

    label_w = draw.textlength(label, font_label)
    draw.text(((width - label_w) // 2, box_y0 + 14), label, font=font_label, fill=(20, 20, 20, 255))

    # Dark line under label
    draw.rectangle([box_x0 + 30, box_y0 + 54, box_x1 - 30, box_y0 + 57], fill=(20, 20, 20, 180))

    # Dark text
    for i, line in enumerate(lines):
        line_w = draw.textlength(line, font)
        x = (width - line_w) // 2
        y = y_start + i * line_h
        draw.text((x, y), line, font=font, fill=(20, 20, 20, 255))

    img.save(output_path)

def compose(audio_path: str, output_path: str, config: dict, post_info: dict,
            word_timings: list, bg_path: str = None) -> str:
    _TEMP_DIR.mkdir(parents=True, exist_ok=True)
    duration = _get_duration(audio_path)
    ass_path, card_path = str(_TEMP_DIR / "temp.ass"), str(_TEMP_DIR / "card.png")

    # 1. Timing — card disappears after both hook sentences finish (full hook_timing_text)
    hook_text = post_info.get("hook", post_info.get("title", ""))
    hook_words = len(hook_text.split())
    title_end = word_timings[hook_words - 1]['end'] if len(word_timings) >= hook_words else 4.0

    # 2. Assets — card displays only first sentence so viewers can't read ahead
    niche = config.get("brand", {}).get("niche", "storytelling")
    card_label = "[ AITA ]" if niche == "drama" else "[ STORY ]"
    display_post_info = {**post_info, "hook": post_info.get("hook_display", hook_text)}

    _write_ass(word_timings, 1080, 1920, ass_path, start_threshold=title_end)
    _render_hook_card(display_post_info, 1080, 1920, card_path, label=card_label)

    # 3. Background clip
    if bg_path:
        bg = ffmpeg.input(bg_path, stream_loop=-1, t=duration)
    else:
        bg = ffmpeg.input("color=c=0x0a0a0f:s=1080x1920:r=30", f="lavfi", t=duration)

    # 4. Filter chain
    video = (
        bg.filter('scale', -2, 1920).filter('crop', 1080, 1920).filter('vignette', angle='0.5')
        .overlay(ffmpeg.input(card_path), enable=f'lte(t,{title_end})')
        .filter('ass', filename=ass_path)
    )

    # 5. Audio — narration + optional ambient music
    narration = ffmpeg.input(audio_path)
    music_files = list(_MUSIC_DIR.glob("*.mp3")) + list(_MUSIC_DIR.glob("*.wav"))
    if music_files:
        music = ffmpeg.input(str(random.choice(music_files)), stream_loop=-1, t=duration)
        audio = ffmpeg.filter([narration, music], 'amix', inputs=2, duration='first', weights='1 0.08')
        print(f"[composer] Music mixed in at 12% volume.")
    else:
        audio = narration

    # 6. Export
    try:
        ffmpeg.output(video, audio, output_path,
                      vcodec='libx264', acodec='aac', pix_fmt='yuv420p'
                      ).overwrite_output().run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        print(f"FFMPEG ERROR: {e.stderr.decode()}")
    finally:
        shutil.rmtree(_TEMP_DIR, ignore_errors=True)

    return output_path