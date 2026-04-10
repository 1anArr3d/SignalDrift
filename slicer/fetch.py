"""
Download a YouTube video into slicer/input/ for slicing.

Usage:
    python slicer/fetch.py <url>
"""

import sys
import subprocess
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent / "input"

def main():
    if len(sys.argv) < 2:
        print("Usage: python slicer/fetch.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(INPUT_DIR / "%(title)s.%(ext)s"),
        url
    ]

    print(f"[fetch] Downloading to {INPUT_DIR}")
    subprocess.run(cmd, check=True)
    print(f"[fetch] Done. Run: python slicer/silcer_mvp.py")

if __name__ == "__main__":
    main()
