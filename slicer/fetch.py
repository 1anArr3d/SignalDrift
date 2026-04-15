"""
fetch.py

Downloads the next video from the URL queue into slicer/input/.
Queue is populated by playwright_scraper.py.

Usage:
    python slicer/fetch.py        # download next URL from queue
"""

import sys
import subprocess
from pathlib import Path

INPUT_DIR    = Path(__file__).resolve().parent / "input"
COOKIES_FILE = Path(__file__).resolve().parent / "yt_cookies.txt"


def fetch_next(config: dict = None) -> bool:
    """
    Pop the next URL from the queue and download it to slicer/input/.
    Refills the queue via playwright_scraper if empty.
    Returns True on success.
    """
    from slicer.playwright_scraper import pop_url, scrape_urls, queue_size

    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    url = pop_url()
    if url is None:
        print("[fetch] Queue empty — running scraper to refill...")
        queries = config.get("slicer", {}).get("search_queries") if config else None
        scrape_urls(queries=queries)
        url = pop_url()
        if url is None:
            print("[fetch] Scraper returned no URLs.")
            return False

    cookies_arg = ["--cookies", str(COOKIES_FILE)] if COOKIES_FILE.exists() else []

    print(f"[fetch] Downloading: {url}")
    dl_cmd = [
        sys.executable, "-m", "yt_dlp",
        *cookies_arg,
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(INPUT_DIR / "%(title)s.%(ext)s"),
        url
    ]
    try:
        subprocess.run(dl_cmd, check=True)
        print(f"[fetch] Done. {queue_size()} URLs remaining in queue.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[fetch] Download failed: {e}")
        return False


if __name__ == "__main__":
    fetch_next()
