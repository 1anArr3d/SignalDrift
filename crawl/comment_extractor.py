"""
comment_extractor.py
Classifies each of the top comments into one of four roles:
  - supporting_evidence
  - counterargument
  - emotional_reaction
  - related_theory

Uses a keyword heuristic — fast, zero-cost, no LLM call needed at this stage.
Output is structured JSON with four labeled buckets.
"""

import re

# Keyword sets that signal each role
_SUPPORT_KEYWORDS = {
    "evidence", "records show", "documented", "police report", "autopsy", "witness",
    "confirmed", "according to", "source", "case file", "investigation", "forensic",
    "timeline", "dna", "identified", "official", "report", "footage", "camera",
    "last seen", "surveillance", "coroner", "toxicology", "found", "discovered",
}

_COUNTER_KEYWORDS = {
    "but", "however", "actually", "wrong", "disagree", "not quite", "incorrect",
    "debunked", "no evidence", "unlikely", "flawed", "misunderstood", "that's not",
    "counter", "opposite", "flaw", "criticism", "problem with", "issue with",
    "doesn't make sense", "doesn't add up", "holes in", "contradiction",
    "alternative explanation", "not convinced", "simpler explanation",
}

_EMOTIONAL_KEYWORDS = {
    "wow", "mind blown", "terrifying", "scary", "incredible", "insane", "creepy",
    "disturbing", "haunting", "chilling", "gives me chills", "can't sleep",
    "goosebumps", "speechless", "heartbreaking", "tragic", "devastating",
    "can't believe", "this is why", "i feel sick", "horrifying", "unsettling",
}

_THEORY_KEYWORDS = {
    "what if", "maybe", "perhaps", "could be", "theory", "hypothesis", "speculate",
    "imagine", "suppose", "i think", "my theory", "possibility", "i believe",
    "cover up", "cover-up", "they knew", "someone knows", "inside job",
    "connected to", "pattern", "not a coincidence", "hidden", "suppressed",
    "ancient", "portal", "dimensional", "government", "classified", "secret",
    "ufo", "uap", "paranormal", "supernatural", "conspiracy",
}


def _classify(body: str) -> str:
    text = body.lower()

    scores = {
        "supporting_evidence": _score(text, _SUPPORT_KEYWORDS),
        "counterargument": _score(text, _COUNTER_KEYWORDS),
        "emotional_reaction": _score(text, _EMOTIONAL_KEYWORDS),
        "related_theory": _score(text, _THEORY_KEYWORDS),
    }

    # Pick the highest score; default to related_theory on a tie
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "related_theory"
    return best


def _score(text: str, keywords: set) -> int:
    return sum(1 for kw in keywords if kw in text)


def extract_and_classify(cleaned_post: dict) -> dict:
    """
    Takes a cleaned post dict and returns the same dict with a new
    'classified_comments' field containing the four-bucket structure.
    """
    buckets: dict[str, list] = {
        "supporting_evidence": [],
        "counterargument": [],
        "emotional_reaction": [],
        "related_theory": [],
    }

    for comment in cleaned_post.get("top_comments", []):
        role = _classify(comment["body"])
        buckets[role].append(comment)

    return {
        **cleaned_post,
        "classified_comments": buckets,
    }


def run(cleaned_posts: list[dict]) -> list[dict]:
    """Entry point called by main.py."""
    result = [extract_and_classify(p) for p in cleaned_posts]
    print(f"[comment_extractor] Classified comments for {len(result)} posts.")
    return result


if __name__ == "__main__":
    import json

    with open("output/cleaned_posts.json") as f:
        cleaned = json.load(f)

    result = run(cleaned)
    with open("output/classified_posts.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {len(result)} posts to output/classified_posts.json")
