"""
cleaner.py
Strips Reddit markdown, removes links, normalises whitespace.
Extracts the core claim from the post body.
Tags output with subreddit, post ID, and unix timestamp.
"""

import re
import time


# Patterns to strip
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")          # [text](url) -> text
_BARE_URL_RE = re.compile(r"https?://\S+")
_MARKDOWN_BOLD_ITALIC = re.compile(r"[*_]{1,3}(.*?)[*_]{1,3}")
_MARKDOWN_CODE = re.compile(r"`{1,3}[^`]*`{1,3}")
_MARKDOWN_HEADER = re.compile(r"^#+\s+", re.MULTILINE)
_MARKDOWN_QUOTE = re.compile(r"^>+\s?", re.MULTILINE)
_MARKDOWN_HR = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
_WHITESPACE = re.compile(r"\s{2,}")


def strip_markdown(text: str) -> str:
    text = _LINK_RE.sub(r"\1", text)
    text = _BARE_URL_RE.sub("", text)
    text = _MARKDOWN_CODE.sub("", text)
    text = _MARKDOWN_BOLD_ITALIC.sub(r"\1", text)
    text = _MARKDOWN_HEADER.sub("", text)
    text = _MARKDOWN_QUOTE.sub("", text)
    text = _MARKDOWN_HR.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


def extract_core_claim(title: str, body: str) -> str:
    """
    Heuristic: the first non-empty sentence of the body is usually the thesis.
    Fall back to title if the body is empty or very short.
    """
    cleaned_body = strip_markdown(body)
    sentences = re.split(r"(?<=[.!?])\s+", cleaned_body)
    substantive = [s for s in sentences if len(s.split()) >= 6]
    if substantive:
        return substantive[0]
    return title


def clean_post(raw: dict) -> dict:
    """
    Takes a raw post dict from reddit_crawler and returns a cleaned dict.
    """
    clean_body = strip_markdown(raw.get("body", ""))
    clean_title = strip_markdown(raw.get("title", ""))

    clean_comments = []
    for c in raw.get("top_comments", []):
        clean_comments.append({
            **c,
            "body": strip_markdown(c["body"]),
        })

    return {
        "post_id": raw["post_id"],
        "subreddit": raw["subreddit"],
        "title": clean_title,
        "body": clean_body,
        "core_claim": extract_core_claim(clean_title, clean_body),
        "upvote_ratio": raw["upvote_ratio"],
        "score": raw["score"],
        "num_comments": raw["num_comments"],
        "created_utc": raw["created_utc"],
        "top_comments": clean_comments,
    }


def run(raw_posts: list[dict]) -> list[dict]:
    """Entry point called by main.py."""
    cleaned = [clean_post(p) for p in raw_posts]
    print(f"[cleaner] Cleaned {len(cleaned)} posts.")
    return cleaned


