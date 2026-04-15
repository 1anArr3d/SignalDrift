"""
playwright_scraper.py

Scrapes YouTube video URLs into video_queue.txt (no login required).
yt-dlp uses cookies exported from your real Chrome browser for downloads.

Usage:
    python slicer/playwright_scraper.py          # scrape URLs into queue
"""
import sys
from pathlib import Path

SLICER_DIR = Path(__file__).resolve().parent
QUEUE_FILE  = SLICER_DIR / "video_queue.txt"

DEFAULT_QUERIES = [
    "satisfying workers compilation",
    "oddly satisfying compilation",
    "relaxing satisfying video compilation",
    "satisfying skills compilation",
    "satisfying construction compilation",
    "satisfying cleaning compilation",
    "satisfying food compilation",
    "oddly satisfying videos",
]

# YouTube search filter: videos over 4 minutes
LONG_VIDEO_FILTER = "EgIQAQ%3D%3D"


def _load_queue() -> list:
    if QUEUE_FILE.exists():
        lines = QUEUE_FILE.read_text().strip().splitlines()
        return [l.strip() for l in lines if l.strip()]
    return []


def _save_queue(urls: list):
    QUEUE_FILE.write_text("\n".join(urls))


def scrape_urls(queries: list = None, count_per_query: int = 15) -> int:
    """
    Scrape YouTube search results and append new video URLs to video_queue.txt.
    Returns number of new URLs added.
    """
    from playwright.sync_api import sync_playwright

    if queries is None:
        queries = DEFAULT_QUERIES

    existing = set(_load_queue())
    new_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()

        for query in queries:
            print(f"[scraper] Searching: {query}")
            search_url = (
                f"https://www.youtube.com/results"
                f"?search_query={query.replace(' ', '+')}"
                f"&sp={LONG_VIDEO_FILTER}"
            )
            try:
                page.goto(search_url, timeout=20000)
                page.wait_for_selector("ytd-video-renderer", timeout=15000)
                # Scroll to trigger lazy-loading of more results
                page.evaluate("window.scrollBy(0, 1500)")
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[scraper] Failed to load results for '{query}': {e}")
                continue

            hrefs = page.eval_on_selector_all(
                "a[href*='/watch?v=']",
                "els => els.map(e => e.getAttribute('href'))"
            )
            added = 0
            for href in hrefs:
                if "/watch?v=" in href:
                    full_url = "https://www.youtube.com" + href.split("&")[0]
                    if full_url not in existing:
                        new_urls.append(full_url)
                        existing.add(full_url)
                        added += 1
                        if added >= count_per_query:
                            break
            print(f"[scraper] Got {added} new URLs from '{query}'")

        context.close()
        browser.close()

    all_urls = _load_queue() + new_urls
    _save_queue(all_urls)
    print(f"[scraper] Added {len(new_urls)} URLs. Queue now has {len(all_urls)}.")
    return len(new_urls)


def pop_url() -> str | None:
    """Remove and return the next URL from the queue. Returns None if empty."""
    urls = _load_queue()
    if not urls:
        return None
    url = urls.pop(0)
    _save_queue(urls)
    return url


def queue_size() -> int:
    return len(_load_queue())


if __name__ == "__main__":
    scrape_urls()
