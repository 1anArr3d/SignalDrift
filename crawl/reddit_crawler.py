import re
import time
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+")


def _clean_text(text: str) -> str:
    if not text: return ""
    text = _URL_RE.sub("", text)
    text = text.replace("#", "").replace("*", "").replace(">", "").replace("[", "").replace("]", "")
    return " ".join(text.split()).strip()


def _fetch_sort(sub: str, sort: str) -> list:
    all_children = []
    after = None

    while True:
        if sort == "top":
            url = f"https://www.reddit.com/r/{sub}/top.json?limit=100&t=month"
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

        if not after or sort != "top":
            break

        time.sleep(1)

    return all_children


def _filter_post(p: dict) -> bool:
    if not p.get("is_self"):
        return False
    if p.get("stickied"):
        return False
    return True


def _scrape_sub(sub_cfg: dict) -> list:
    name = sub_cfg["name"]

    print(f"[crawl] r/{name} — top/month + hot...")

    top_children = _fetch_sort(name, "top")
    time.sleep(1)
    hot_children = _fetch_sort(name, "hot")

    seen_this_fetch = set()
    merged = []
    for child in top_children + hot_children:
        p = child["data"]
        if p["id"] not in seen_this_fetch:
            seen_this_fetch.add(p["id"])
            merged.append(p)

    results = []
    for p in merged:
        if _filter_post(p):
            results.append({
                "post_id": p["id"],
                "subreddit": name,
                "title": _clean_text(p["title"]),
                "body": _clean_text(p["selftext"]),
                "score": p["score"],
                "upvote_ratio": p["upvote_ratio"],
                "created_utc": p["created_utc"],
            })

    print(f"[crawl] r/{name} -> {len(results)} new posts")
    return results


def run(config: dict) -> list:
    subs = config["farm"]["subreddits"]

    results = []
    for sub_cfg in subs:
        results.extend(_scrape_sub(sub_cfg))
        time.sleep(2)

    print(f"[crawl] Total posts fetched: {len(results)}")
    return results
