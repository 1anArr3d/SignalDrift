"""
scorer.py — rule-based filter only, no LLM call.
"""

_DEFAULT_SKIP_KEYWORDS = ["update", "part 2", "mod post", "announcement", "repost"]


def _narrator_gender(post: dict) -> str:
    text = (post.get("title", "") + " " + post.get("body", "")).lower()
    f = text.count("(f)") + text.count("(f,") + text.count(" her ") + text.count(" she ")
    m = text.count("(m)") + text.count("(m,") + text.count(" his ") + text.count(" he ")
    if f > m: return "female"
    if m > f: return "male"
    return "female"


def score_post(post: dict, config: dict = None) -> dict:
    title = post.get("title", "").lower()
    body = post.get("body", "")
    reddit_score = post.get("score", 0)
    upvote_ratio = post.get("upvote_ratio", 0)

    min_score = 200
    if config:
        for s in config.get("farm", {}).get("subreddits", []):
            if s["name"].lower() == post.get("subreddit", "").lower():
                min_score = s.get("min_score", 200)
                break

    skip_kws = config.get("crawl", {}).get("skip_title_keywords", _DEFAULT_SKIP_KEYWORDS) if config else _DEFAULT_SKIP_KEYWORDS

    fail_reason = None
    if reddit_score < min_score:
        fail_reason = f"score {reddit_score} < {min_score}"
    elif upvote_ratio < 0.8:
        fail_reason = f"ratio {upvote_ratio:.2f} < 0.80"
    elif len(body) < 300:
        fail_reason = "body too short"
    elif any(kw in title for kw in skip_kws):
        fail_reason = "skip keyword"

    verdict = "fail" if fail_reason else "pass"
    post["score"] = {
        "verdict": verdict,
        "overall": 8.0 if verdict == "pass" else 4.0,
        "narrator_gender": _narrator_gender(post),
        **({"reason": fail_reason} if fail_reason else {})
    }
    print(f"  [scorer] {verdict.upper()} — {post['title'][:60]}")
    return post


def score_batch(posts: list, config: dict = None) -> tuple[list, list]:
    passed, failed = [], []
    print(f"[scorer] Scoring {len(posts)} posts...")
    for post in posts:
        scored = score_post(post, config=config)
        if scored["score"].get("verdict") == "pass":
            passed.append(scored)
        else:
            failed.append(scored)
    print(f"[scorer] {len(passed)} passed / {len(failed)} failed")
    return passed, failed
