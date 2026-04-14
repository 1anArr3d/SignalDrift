"""
scorer.py

Lightweight hybrid scorer. Rule-based pre-filter first (free), then a single
Claude call only for posts that pass rules. One sentence verdict, no rubric.
"""

import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_CLIENT = None
MODEL = "claude-haiku-4-5-20251001"
SKIP_KEYWORDS = ["update", "part 2", "mod post", "announcement", "repost"]

SYSTEM_PROMPT = """\
You are a TikTok content filter. Decide if a Reddit post makes a good short drama script.
Return JSON only. No explanation outside the JSON."""

USER_PROMPT = """\
Title: {title}
Body: {body}

Does this make a good 200-word TikTok drama script? Is the conflict clear and the other person clearly in the wrong?
Return: {{"verdict": "pass" or "fail", "narrator_gender": "male" or "female" or "neutral"}}"""


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _CLIENT


def _narrator_gender_fallback(post: dict) -> str:
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

    sub_name = post.get("subreddit", "")
    min_score = 200
    if config:
        for s in config.get("farm", {}).get("subreddits", []):
            if s["name"].lower() == sub_name.lower():
                min_score = s.get("min_score", 200)
                break

    # ── Rule pre-filter (free) ────────────────────────────────────────────────
    fail_reason = None
    if reddit_score < min_score:
        fail_reason = f"score {reddit_score} < {min_score}"
    elif upvote_ratio < 0.8:
        fail_reason = f"ratio {upvote_ratio:.2f} < 0.80"
    elif len(body) < 300:
        fail_reason = "body too short"
    elif any(kw in title for kw in SKIP_KEYWORDS):
        fail_reason = "skip keyword"

    if fail_reason:
        post["score"] = {"verdict": "fail", "overall": 4.0, "reason": fail_reason,
                         "narrator_gender": _narrator_gender_fallback(post)}
        print(f"  [scorer] FAIL (rules) — {post['title'][:60]}")
        return post

    # ── Claude micro-call (only for rule-passers) ─────────────────────────────
    try:
        client = _get_client()
        r = client.messages.create(
            model=MODEL, max_tokens=60, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_PROMPT.format(
                title=post.get("title", ""), body=body[:800]
            )}]
        )
        raw = r.content[0].text.strip()
        s, e = raw.find('{'), raw.rfind('}') + 1
        result = json.loads(raw[s:e])
        verdict = result.get("verdict", "fail")
        narrator_gender = result.get("narrator_gender", "female")
    except Exception as ex:
        print(f"  [scorer] Claude error: {ex} — letting through")
        verdict = "pass"
        narrator_gender = _narrator_gender_fallback(post)

    post["score"] = {"verdict": verdict, "overall": 8.0 if verdict == "pass" else 4.0,
                     "narrator_gender": narrator_gender}
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
