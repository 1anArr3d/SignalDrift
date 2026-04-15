"""
fetch.py

Download a YouTube video into slicer/input/ for slicing.
Supports direct URL or search query via yt-dlp.

Usage:
    python slicer/fetch.py <url>
    python slicer/fetch.py --search "satisfying workers compilation"
"""

import sys
import json
import subprocess
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent / "input"
FETCHED_LOG = Path(__file__).resolve().parent / "fetched_ids.json"


def _load_fetched() -> set:
    if FETCHED_LOG.exists():
        return set(json.loads(FETCHED_LOG.read_text()))
    return set()


def _save_fetched(ids: set):
    FETCHED_LOG.write_text(json.dumps(sorted(ids), indent=2))


def fetch(url_or_query: str, is_search: bool = False) -> bool:
    """Download a video. Returns True on success."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched = _load_fetched()

    if is_search:
        # Use yt-dlp search — pick longest result not already fetched
        target = f"ytsearch5:{url_or_query}"
    else:
        target = url_or_query

    # Get video ID first to check against fetched log
    info_cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json", "--no-playlist",
        "--match-filter", "duration > 3600",  # prefer videos over 1 hour
        target
    ]

    try:
        result = subprocess.run(info_cmd, capture_output=True, text=True, check=True)
        # May return multiple JSON lines for search results
        for line in result.stdout.strip().splitlines():
            try:
                info = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid_id = info.get("id")
            if vid_id and vid_id not in fetched:
                # Found a new one — download it
                dl_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", str(INPUT_DIR / "%(title)s.%(ext)s"),
                    f"https://www.youtube.com/watch?v={vid_id}"
                ]
                print(f"[fetch] Downloading: {info.get('title', vid_id)}")
                subprocess.run(dl_cmd, check=True)
                fetched.add(vid_id)
                _save_fetched(fetched)
                print(f"[fetch] Done. Logged ID {vid_id}")
                return True

        print("[fetch] No new videos found for query.")
        return False

    except subprocess.CalledProcessError as e:
        print(f"[fetch] Error: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python slicer/fetch.py <url>")
        print("       python slicer/fetch.py --search \"satisfying workers compilation\"")
        sys.exit(1)

    if sys.argv[1] == "--search":
        query = " ".join(sys.argv[2:])
        fetch(query, is_search=True)
    else:
        fetch(sys.argv[1], is_search=False)


if __name__ == "__main__":
    main()
