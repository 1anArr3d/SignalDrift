"""
reddit_crawler.py
Pulls posts from configured subreddits.

Two modes:
  - public (default): uses Reddit's unauthenticated JSON endpoints, no API key needed
  - praw: uses PRAW with credentials from .env (switch via USE_PRAW=true in .env)
"""

import json
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_HEADERS = {"User-Agent": os.environ.get("REDDIT_USER_AGENT", "SignalDrift/1.0")}


def fetch_posts(config: dict) -> list[dict]:
    farm_cfg = config["farm"]
    crawl_cfg = config["crawl"]

    min_ratio = crawl_cfg["min_upvote_ratio"]
    min_comments = crawl_cfg["min_comments"]
    top_comments_count = crawl_cfg["top_comments_count"]

    results = []

    for sub_name in farm_cfg["subreddits"]:
        url = f"https://www.reddit.com/r/{sub_name}/hot.json?limit=50"
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code in (403, 404):
            print(f"[crawl] Skipping r/{sub_name} — {resp.status_code}")
            continue
        resp.raise_for_status()
        posts = resp.json()["data"]["children"]

        for child in posts:
            p = child["data"]
            if p.get("upvote_ratio", 0) < min_ratio:
                continue
            if p.get("num_comments", 0) < min_comments:
                continue
            if not p.get("is_self") and not p.get("selftext"):
                continue

            # Skip megathreads, meta posts, weekly threads
            title_lower = p.get("title", "").lower()
            if any(kw in title_lower for kw in (
                "meta monday", "what are you", "weekly thread", "daily thread",
                "write your own", "weekly discussion", "monthly thread",
                "off topic", "mod post", "mod announcement",
            )):
                continue

            # Require a substantive body (at least 100 chars of actual content)
            body = p.get("selftext", "")
            if len(body.strip()) < 100:
                continue

            top_comments = _pull_top_comments(sub_name, p["id"], top_comments_count)
            time.sleep(2)  # be polite

            results.append({
                "post_id": p["id"],
                "subreddit": sub_name,
                "title": p.get("title", ""),
                "body": p.get("selftext", ""),
                "upvote_ratio": p.get("upvote_ratio", 0),
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "created_utc": int(p.get("created_utc", 0)),
                "top_comments": top_comments,
            })

        time.sleep(2)

    return results


def _pull_top_comments(sub_name: str, post_id: str, count: int) -> list[dict]:
    url = f"https://www.reddit.com/r/{sub_name}/comments/{post_id}.json?limit=50&sort=top"
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code in (429, 503):
            wait = 15 * (attempt + 1)
            print(f"[crawl] {resp.status_code} on {post_id}, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code in (403, 404):
            return []
        resp.raise_for_status()
        break
    else:
        print(f"[crawl] Skipping comments for {post_id} — server unavailable.")
        return []

    comments = []
    try:
        listing = resp.json()[1]["data"]["children"]
        for child in listing:
            c = child.get("data", {})
            body = c.get("body", "")
            if not body or body in ("[deleted]", "[removed]"):
                continue
            comments.append({
                "comment_id": c.get("id", ""),
                "author": c.get("author", "[deleted]"),
                "body": body,
                "score": c.get("score", 0),
            })
    except (IndexError, KeyError):
        pass

    return sorted(comments, key=lambda x: x["score"], reverse=True)[:count]


def run(config: dict) -> list[dict]:
    """Entry point called by main.py."""
    posts = fetch_posts(config)
    print(f"[crawl] Fetched {len(posts)} qualifying posts.")
    return posts


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    # Quick test: just r/UnresolvedMysteries with real thresholds
    cfg["farm"]["subreddits"] = ["UnresolvedMysteries"]

    posts = run(cfg)
    os.makedirs("output", exist_ok=True)
    with open("output/raw_posts.json", "w") as f:
        json.dump(posts[:1], f, indent=2)
    print(f"Wrote 1 post to output/raw_posts.json")
