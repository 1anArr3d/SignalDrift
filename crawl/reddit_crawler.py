import os
import json
import time
import requests
from pathlib import Path

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

OUTPUT_DIR = Path(__file__).parent.parent / "output"
SEEN_PATH = OUTPUT_DIR / "seen_posts.json"
CRAWL_STATE_PATH = OUTPUT_DIR / "crawl_state.json"


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_seen() -> set:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text()))
    return set()


def _load_crawl_state(secondaries: list) -> dict:
    if CRAWL_STATE_PATH.exists():
        return json.loads(CRAWL_STATE_PATH.read_text())
    return {"secondary_index": 0}


def _save_crawl_state(state: dict):
    OUTPUT_DIR.mkdir(exist_ok=True)
    CRAWL_STATE_PATH.write_text(json.dumps(state, indent=2))


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_sort(sub: str, sort: str) -> list:
    """Fetch posts from a subreddit by sort. Paginates through all results for top/year."""
    all_children = []
    after = None

    while True:
        if sort == "top":
            url = f"https://www.reddit.com/r/{sub}/top.json?limit=100&t=year"
        else:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=100"

        if after:
            url += f"&after={after}"

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            if resp.status_code == 429:
                print(f"[crawl] Rate limited on r/{sub}/{sort}. Sleeping 30s...")
                time.sleep(30)
                continue
            resp.raise_for_status()
            data = resp.json().get("data", {})
            children = data.get("children", [])
            all_children.extend(children)
            after = data.get("after")
        except Exception as e:
            print(f"[crawl] Failed r/{sub}/{sort}: {e}")
            break

        # Stop if no more pages or not paginating hot
        if not after or sort != "top":
            break

        time.sleep(1)

    return all_children


def _filter_post(p: dict, min_score: int, min_ratio: float,
                 skip_keywords: list, seen: set) -> bool:
    """Return True if post passes all quality gates."""
    if p.get("id") in seen:
        return False
    if not p.get("is_self"):
        return False
    if p.get("score", 0) < min_score:
        return False
    if p.get("upvote_ratio", 0) < min_ratio:
        return False
    if len(p.get("selftext", "")) < 200:
        return False
    if p.get("stickied"):
        return False
    title = p.get("title", "").lower()
    if any(kw.lower() in title for kw in skip_keywords):
        return False
    return True


def _scrape_sub(sub_cfg: dict, crawl_cfg: dict, seen: set) -> list:
    """Scrape top+hot for one subreddit, dedup between sorts, apply filters."""
    name = sub_cfg["name"]
    min_score = sub_cfg.get("min_score", 100)
    min_ratio = crawl_cfg.get("min_upvote_ratio", 0.8)
    skip_keywords = crawl_cfg.get("skip_title_keywords", [])

    print(f"[crawl] r/{name} — top/week + hot...")

    top_children = _fetch_sort(name, "top")
    time.sleep(1)
    hot_children = _fetch_sort(name, "hot")

    # Merge, dedup by post id within this fetch
    seen_this_fetch = set()
    merged = []
    for child in top_children + hot_children:
        p = child["data"]
        if p["id"] not in seen_this_fetch:
            seen_this_fetch.add(p["id"])
            merged.append(p)

    results = []
    for p in merged:
        if _filter_post(p, min_score, min_ratio, skip_keywords, seen):
            results.append({
                "post_id": p["id"],
                "subreddit": name,
                "title": p["title"],
                "body": p["selftext"],
                "score": p["score"],
                "upvote_ratio": p["upvote_ratio"],
                "created_utc": p["created_utc"],
            })

    print(f"[crawl] r/{name} → {len(results)} new posts")
    return results


# ── Main entry ────────────────────────────────────────────────────────────────

def fetch_posts(config: dict, all_subs: bool = False) -> list:
    crawl_cfg = config["crawl"]
    sub_list = config["farm"]["subreddits"]

    primaries = [s for s in sub_list if s.get("tier") == "primary"]
    secondaries = [s for s in sub_list if s.get("tier") == "secondary"]

    seen = _load_seen()
    state = _load_crawl_state(secondaries)

    if all_subs:
        subs_to_crawl = primaries + secondaries
        print(f"[crawl] Mode: ALL ({len(subs_to_crawl)} subreddits)")
    else:
        subs_to_crawl = list(primaries)
        if secondaries:
            idx = state.get("secondary_index", 0) % len(secondaries)
            subs_to_crawl.append(secondaries[idx])
            print(f"[crawl] Secondary this run: r/{secondaries[idx]['name']} ({idx + 1}/{len(secondaries)})")
            state["secondary_index"] = (idx + 1) % len(secondaries)
            _save_crawl_state(state)

    results = []
    for sub_cfg in subs_to_crawl:
        results.extend(_scrape_sub(sub_cfg, crawl_cfg, seen))
        time.sleep(2)

    print(f"[crawl] Total new posts this run: {len(results)}")
    return results


def run(config: dict, all_subs: bool = False) -> list:
    return fetch_posts(config, all_subs=all_subs)
