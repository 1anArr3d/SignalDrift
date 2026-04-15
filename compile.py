"""
compile.py

Stitches all rendered Shorts from output/rendered/ into a long-form compilation
and uploads to YouTube. Deletes the clips after a successful upload.

Runs daily via cron — skips if fewer than MIN_CLIPS are ready.

Usage:
    python compile.py
    python compile.py --config config.yaml
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

import yaml

RENDERED_DIR = Path("output/rendered")
COUNTER_FILE = Path("output/compilation_count.txt")
MIN_CLIPS = 6  # wait until at least 6 Shorts are ready (~1.5 days)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _next_number() -> int:
    n = int(COUNTER_FILE.read_text().strip()) if COUNTER_FILE.exists() else 0
    n += 1
    COUNTER_FILE.write_text(str(n))
    return n


def _stitch(clips: list[Path], output_path: Path):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for clip in clips:
            f.write(f"file '{clip.resolve()}'\n")
        concat_file = f.name

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    Path(concat_file).unlink()


def run(config: dict):
    clips = sorted(RENDERED_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)

    if len(clips) < MIN_CLIPS:
        print(f"[compile] Only {len(clips)} clip(s) ready — need {MIN_CLIPS}. Skipping.")
        return

    print(f"[compile] Stitching {len(clips)} clips...")

    n = _next_number()
    output_path = Path(f"output/compilation_{n}.mp4")

    _stitch(clips, output_path)
    print(f"[compile] Stitched → {output_path}")

    from publish import youtube_uploader

    title = f"Reddit AITA Compilation #{n} — {len(clips)} Stories"
    description = (
        f"Reddit AITA compilation — {len(clips)} stories back to back.\n\n"
        "#aita #aitah #redditstories #storytelling #redditcompilation "
        "#redditdrama #storytime #drama #relationships"
    )
    tags = [
        "aita", "aitah", "redditstories", "storytelling", "redditcompilation",
        "redditdrama", "storytime", "drama", "relationships",
    ]

    youtube_uploader.upload(str(output_path), title=title, description=description, tags=tags)

    for clip in clips:
        clip.unlink(missing_ok=True)
    output_path.unlink(missing_ok=True)
    print(f"[compile] Done. Compilation #{n} posted and clips cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    run(load_config(args.config))
