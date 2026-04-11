"""
scorer.py

Scores incoming Reddit posts on their potential as a first-person TikTok script.
Uses Claude Haiku for cost efficiency — runs on every crawled post before it
enters classified_posts.json.

Scoring criteria (each 1–10):
  - first_person_fit  : how naturally it reads as "I" narration
  - story_payoff      : strength of the ending moment / final image
  - condensability    : can the core be told in 150–250 words
  - emotional_hook    : dread, shock, disbelief — does it make you feel something

Pass threshold: overall >= 6.5
"""

import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_CLIENT = None
PASS_THRESHOLD = 7.5
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are a content evaluator for a horror storytelling TikTok channel.
Your job is to score Reddit posts on their potential as a short first-person narrated script (150–250 words).
Be critical. Most posts should not pass. Only score high if the story is genuinely compelling and tightly structured.
Always return valid JSON only. No markdown, no explanation outside the JSON."""

USER_PROMPT_TEMPLATE = """\
Score this Reddit post on its potential as a first-person TikTok horror script.

Title: {title}
Body: {body}

Score each criterion 1–10:
- first_person_fit: how naturally it becomes "I" narration
- story_payoff: strength of the final moment or reveal
- condensability: can the core be told in 150–250 words without losing tension
- emotional_hook: dread, shock, disbelief on first read

Return only this JSON:
{{
  "first_person_fit": <int>,
  "story_payoff": <int>,
  "condensability": <int>,
  "emotional_hook": <int>,
  "overall": <float, average of the four>,
  "verdict": "pass" or "fail",
  "reason": "<one sentence>"
}}

verdict is "pass" if overall >= 7.5, otherwise "fail"."""


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _CLIENT


def score_post(post: dict) -> dict:
    """
    Score a single post. Returns the post dict with a 'score' key added.
    Posts that fail get score['verdict'] == 'fail' and are excluded from the queue.
    """
    title = post.get("title", "")
    # Truncate body to 1500 chars — Haiku doesn't need the full text to judge quality
    body = post.get("body", "")[:1500]

    prompt = USER_PROMPT_TEMPLATE.format(title=title, body=body)

    try:
        client = _get_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if model wraps response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if not raw:
            raise ValueError(f"Empty response from model. Full content: {message.content}")
        result = json.loads(raw)
    except Exception as e:
        print(f"  [scorer] Error on '{title[:50]}': {e}")
        # On failure, let the post through with a neutral score rather than blocking the pipeline
        result = {
            "first_person_fit": 5, "story_payoff": 5,
            "condensability": 5, "emotional_hook": 5,
            "overall": 5.0, "verdict": "fail",
            "reason": "Scorer error — skipped."
        }

    post["score"] = result
    verdict = result.get("verdict", "fail")
    overall = result.get("overall", 0)
    print(f"  [scorer] {verdict.upper()} ({overall:.1f}) — {post['title'][:60]}")
    return post


def score_batch(posts: list) -> tuple[list, list]:
    """
    Score a list of posts. Returns (passed, failed) as two separate lists.
    Both lists contain the full post dicts with 'score' attached.
    """
    passed, failed = [], []
    print(f"[scorer] Scoring {len(posts)} posts...")
    for post in posts:
        scored = score_post(post)
        if scored["score"].get("verdict") == "pass":
            passed.append(scored)
        else:
            failed.append(scored)
    print(f"[scorer] {len(passed)} passed / {len(failed)} failed")
    return passed, failed
