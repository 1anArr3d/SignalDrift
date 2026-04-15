"""
playwright_scraper.py

Scrapes YouTube video URLs using a saved browser session.
On first run, opens a visible browser for manual login.
Subsequent runs are headless.

Usage:
    python slicer/playwright_scraper.py          # scrape URLs into queue
    python slicer/playwright_scraper.py --login  # force re-login
"""
import json
import sys
from pathlib import Path

SLICER_DIR = Path(__file__).resolve().parent
SESSION_FILE = SLICER_DIR / "yt_session.json"
COOKIES_FILE = SLICER_DIR / "yt_cookies.txt"
QUEUE_FILE   = SLICER_DIR / "video_queue.txt"

DEFAULT_QUERIES = [
    "satisfying workers compilation 1 hour",
    "oddly satisfying compilation 1 hour",
    "relaxing satisfying video compilation 1 hour",
    "satisfying skills compilation 1 hour",
]

# YouTube search filter for videos over 20 minutes
LONG_VIDEO_FILTER = "EgIYAQ%3D%3D"


def _load_queue() -> list:
    if QUEUE_FILE.exists():
        lines = QUEUE_FILE.read_text().strip().splitlines()
        return [l.strip() for l in lines if l.strip()]
    return []


def _save_queue(urls: list):
    QUEUE_FILE.write_text("\n".join(urls))


def _export_cookies(session_path: Path, output_path: Path):
    """Convert Playwright storage_state cookies to Netscape format for yt-dlp."""
    state = json.loads(session_path.read_text())
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in state.get("cookies", []):
        domain = cookie["domain"]
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.get("path", "/")
        secure = "TRUE" if cookie.get("secure", False) else "FALSE"
        expires = int(cookie.get("expires", 0))
        name = cookie["name"]
        value = cookie["value"]
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    output_path.write_text("\n".join(lines))
    print(f"[scraper] Cookies exported to {output_path}")


def scrape_urls(queries: list = None, count_per_query: int = 5, force_login: bool = False) -> int:
    """
    Scrape YouTube video URLs and append to video_queue.txt.
    Returns number of new URLs added.
    """
    from playwright.sync_api import sync_playwright

    if queries is None:
        queries = DEFAULT_QUERIES

    headless = SESSION_FILE.exists() and not force_login
    if not headless:
        print("[scraper] No saved session — opening browser for manual login.")

    existing = set(_load_queue())
    new_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        if SESSION_FILE.exists() and not force_login:
            context = browser.new_context(storage_state=str(SESSION_FILE))
        else:
            context = browser.new_context()

        page = context.new_page()

        if not headless:
            page.goto("https://www.youtube.com")
            print("[scraper] Log into YouTube in the browser window.")
            input("[scraper] Press Enter here after you're logged in...")
            context.storage_state(path=str(SESSION_FILE))
            _export_cookies(SESSION_FILE, COOKIES_FILE)
            print("[scraper] Session saved.")

        for query in queries:
            print(f"[scraper] Searching: {query}")
            url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}&sp={LONG_VIDEO_FILTER}"
            try:
                page.goto(url, timeout=15000)
                page.wait_for_selector("ytd-video-renderer", timeout=10000)
            except Exception as e:
                print(f"[scraper] Failed to load search results for '{query}': {e}")
                continue

            videos = page.query_selector_all("ytd-video-renderer a#video-title")
            added = 0
            for v in videos:
                href = v.get_attribute("href")
                if href and "/watch?v=" in href:
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
    force = "--login" in sys.argv
    scrape_urls(force_login=force)
