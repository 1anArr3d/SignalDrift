import subprocess
import os
import glob
import json
import statistics

from PIL import Image, ImageChops, ImageStat

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(SLICER_DIR, "input")
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")

CHUNK_LENGTH = 180       # seconds per output clip
SAMPLE_FPS = 1           # frames per second for motion analysis
THUMB_W, THUMB_H = 64, 36
MOTION_PERCENTILE = 30   # bottom 30th percentile = adaptive floor per video
MIN_SEGMENT_DURATION = 30  # drop segments shorter than this (seconds)
MERGE_GAP = 10           # merge segments within this many seconds of each other


def get_video_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def analyze_motion(input_file: str) -> list:
    """
    Sample video at 1fps via ffmpeg pipe, compute per-second motion scores
    using PIL frame differencing. Returns list of floats (0.0–1.0).
    Each video uses its own baseline — no global threshold.
    """
    frame_size = THUMB_W * THUMB_H
    cmd = [
        "ffmpeg", "-hwaccel", "auto",
        "-i", input_file,
        "-vf", f"fps={SAMPLE_FPS},scale={THUMB_W}:{THUMB_H}",
        "-f", "rawvideo", "-pix_fmt", "gray", "-"
    ]
    print(f"  [analyze] Sampling motion at {SAMPLE_FPS}fps — may take a few minutes for long files...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    prev_frame = None
    scores = []

    while True:
        raw = proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break
        curr_img = Image.frombytes("L", (THUMB_W, THUMB_H), raw)
        if prev_frame is not None:
            diff = ImageChops.difference(curr_img, prev_frame)
            score = ImageStat.Stat(diff).mean[0] / 255.0
            scores.append(score)
        prev_frame = curr_img

    proc.wait()
    print(f"  [analyze] {len(scores)} seconds sampled.")
    return scores


def find_good_segments(scores: list) -> list:
    """
    Compute an adaptive floor from this video's own distribution (p30).
    Find segments of sustained motion above that floor, merge nearby gaps,
    and drop anything too short to be useful.
    Returns list of (start_sec, end_sec) tuples.
    """
    if len(scores) < 2:
        return []

    threshold = statistics.quantiles(scores, n=100)[MOTION_PERCENTILE - 1]
    print(f"  [analyze] Adaptive floor (p{MOTION_PERCENTILE}): {threshold:.4f}")

    good = [s >= threshold for s in scores]

    # Build raw segments from good windows
    segments = []
    in_seg = False
    seg_start = 0
    for i, is_good in enumerate(good):
        if is_good and not in_seg:
            seg_start = i
            in_seg = True
        elif not is_good and in_seg:
            segments.append([float(seg_start), float(i)])
            in_seg = False
    if in_seg:
        segments.append([float(seg_start), float(len(good))])

    # Merge segments within MERGE_GAP seconds — avoids over-fragmentation
    merged = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] <= MERGE_GAP:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)

    # Drop segments too short to yield a full chunk
    final = [(s, e) for s, e in merged if e - s >= MIN_SEGMENT_DURATION]
    return final


def extract_chunks(input_file: str, segments: list, output_folder: str) -> int:
    """
    For each good segment, slice into CHUNK_LENGTH clips with AMF hardware encoding.
    Returns total chunk count.
    """
    os.makedirs(output_folder, exist_ok=True)
    chunk_idx = 0

    for seg_start, seg_end in segments:
        seg_duration = seg_end - seg_start
        num_chunks = int(seg_duration // CHUNK_LENGTH)

        for i in range(num_chunks):
            start = seg_start + i * CHUNK_LENGTH
            out_path = os.path.join(output_folder, f"chunk_{chunk_idx:03d}.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start), "-t", str(CHUNK_LENGTH),
                "-i", input_file,
                "-vf", "scale=-1:1920,crop=1080:1920",
                "-c:v", "h264_amf", "-quality", "speed",
                "-an", out_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  [extract] chunk_{chunk_idx:03d}.mp4  ({start:.0f}s – {start + CHUNK_LENGTH:.0f}s)")
            chunk_idx += 1

    return chunk_idx


def slice_file(input_file: str):
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_folder = os.path.join(POOL_FOLDER, base_name)

    print(f"\n[slicer] ── {os.path.basename(input_file)}")

    duration = get_video_duration(input_file)
    print(f"  [info] Duration: {duration / 3600:.2f}h")

    scores = analyze_motion(input_file)
    segments = find_good_segments(scores)

    total_good = sum(e - s for s, e in segments)
    print(f"  [segments] {len(segments)} good segments — {total_good / 60:.1f} min usable")

    count = extract_chunks(input_file, segments, output_folder)
    print(f"  [done] {count} clips → {output_folder}\n")


def run():
    if not os.path.exists(INPUT_FOLDER):
        os.makedirs(INPUT_FOLDER)
        print("[slicer] Created slicer/input/ — drop footage there and re-run.")
        return

    mp4_files = glob.glob(os.path.join(INPUT_FOLDER, "*.mp4"))
    if not mp4_files:
        print("[slicer] No .mp4 files found in slicer/input/.")
        return

    print(f"[slicer] Found {len(mp4_files)} file(s).\n")
    for f in sorted(mp4_files):
        slice_file(f)

    print("[slicer] All files processed.")


if __name__ == "__main__":
    run()
