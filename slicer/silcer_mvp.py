import subprocess
import os
import glob
import json

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(SLICER_DIR, "input")
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")

_DEFAULT_CHUNK_LENGTH = 90  # seconds — 1 minute 30


def get_video_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def slice_file(input_file: str, chunk_length: int = _DEFAULT_CHUNK_LENGTH):
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_folder = os.path.join(POOL_FOLDER, base_name)
    os.makedirs(output_folder, exist_ok=True)

    print(f"\n[slicer] ── {os.path.basename(input_file)}")

    duration = get_video_duration(input_file)
    num_chunks = int(duration // chunk_length)
    print(f"  [info] Duration: {duration:.0f}s — {num_chunks} chunks")

    for i in range(num_chunks):
        start = i * chunk_length
        out_path = os.path.join(output_folder, f"chunk_{i:03d}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(chunk_length),
            "-i", input_file,
            "-vf", "scale=-1:1920,crop=1080:1920",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an", out_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, capture_output=False)
        if result.returncode != 0:
            print(f"  [warn] chunk_{i:03d}.mp4 failed (ffmpeg exit {result.returncode})")
        else:
            print(f"  [extract] chunk_{i:03d}.mp4  ({start}s – {start + chunk_length}s)")

    print(f"  [done] {num_chunks} clips -> {output_folder}\n")


def run(config: dict = None):
    chunk_length = _DEFAULT_CHUNK_LENGTH
    if config:
        chunk_length = config.get("slicer", {}).get("chunk_length", _DEFAULT_CHUNK_LENGTH)

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
        slice_file(f, chunk_length)

    print("[slicer] All files processed.")


if __name__ == "__main__":
    run()
