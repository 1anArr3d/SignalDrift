import subprocess
import os
import glob
import json

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(SLICER_DIR, "input")
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")

CHUNK_LENGTH = 90  # seconds — 1 minute 30


def get_video_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def slice_file(input_file: str):
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_folder = os.path.join(POOL_FOLDER, base_name)
    os.makedirs(output_folder, exist_ok=True)

    print(f"\n[slicer] ── {os.path.basename(input_file)}")

    duration = get_video_duration(input_file)
    num_chunks = int(duration // CHUNK_LENGTH)
    print(f"  [info] Duration: {duration:.0f}s — {num_chunks} chunks")

    for i in range(num_chunks):
        start = i * CHUNK_LENGTH
        out_path = os.path.join(output_folder, f"chunk_{i:03d}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(CHUNK_LENGTH),
            "-i", input_file,
            "-vf", "scale=-1:1920,crop=1080:1920",
            "-c:v", "h264_amf", "-quality", "speed",
            "-an", out_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  [extract] chunk_{i:03d}.mp4  ({start}s – {start + CHUNK_LENGTH}s)")

    print(f"  [done] {num_chunks} clips -> {output_folder}\n")


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
