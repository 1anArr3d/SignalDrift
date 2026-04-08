import re

# Minimalist cleaning: Just remove the stuff that breaks TTS or confuses the LLM
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_BRACKET_RE = re.compile(r"\[|\]") # Remove [ and ] often used in links

def clean_text(text: str) -> str:
    if not text: return ""
    # Remove URLs
    text = _URL_RE.sub("", text)
    # Remove excessive markdown characters
    text = text.replace("#", "").replace("*", "").replace(">", "")
    # Standardize whitespace
    text = " ".join(text.split())
    return text.strip()

def run(raw_posts: list[dict]) -> list[dict]:
    cleaned = []
    for p in raw_posts:
        cleaned.append({
            "post_id": p["post_id"],
            "subreddit": p["subreddit"],
            "title": clean_text(p["title"]),
            "body": clean_text(p["body"]),
            "score": p["score"],
            "upvote_ratio": p["upvote_ratio"],
            "created_utc": p["created_utc"]
        })
    print(f"[cleaner] Cleaned {len(cleaned)} posts.")
    return cleaned