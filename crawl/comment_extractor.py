"""
comment_extractor.py
Classifies each top comment into one of four roles:
  - supporting_evidence
  - counterargument
  - emotional_reaction
  - related_theory

Keyword sets are niche-specific. Niche is read from config["farm"]["niche"].
Supported niches: unsolved_mysteries, first_person_horror
"""

# ---------------------------------------------------------------------------
# Keyword sets per niche
# ---------------------------------------------------------------------------

_KEYWORDS = {
    "unsolved_mysteries": {
        "supporting_evidence": {
            "evidence", "records show", "documented", "police report", "autopsy",
            "witness", "confirmed", "according to", "source", "case file",
            "investigation", "forensic", "timeline", "dna", "identified", "official",
            "report", "footage", "camera", "last seen", "surveillance", "coroner",
            "toxicology", "found", "discovered",
        },
        "counterargument": {
            "but", "however", "actually", "wrong", "disagree", "not quite",
            "incorrect", "debunked", "no evidence", "unlikely", "flawed",
            "misunderstood", "that's not", "counter", "opposite", "flaw",
            "criticism", "problem with", "issue with", "doesn't make sense",
            "doesn't add up", "holes in", "contradiction", "alternative explanation",
            "not convinced", "simpler explanation",
        },
        "emotional_reaction": {
            "wow", "mind blown", "terrifying", "scary", "incredible", "insane",
            "creepy", "disturbing", "haunting", "chilling", "gives me chills",
            "can't sleep", "goosebumps", "speechless", "heartbreaking", "tragic",
            "devastating", "can't believe", "i feel sick", "horrifying", "unsettling",
        },
        "related_theory": {
            "what if", "maybe", "perhaps", "could be", "theory", "hypothesis",
            "speculate", "imagine", "suppose", "i think", "my theory", "possibility",
            "i believe", "cover up", "cover-up", "they knew", "someone knows",
            "inside job", "connected to", "pattern", "not a coincidence", "hidden",
            "suppressed", "government", "classified", "secret", "ufo", "uap",
            "paranormal", "supernatural", "conspiracy",
        },
    },

    "first_person_horror": {
        # Corroborating detail: comments that add context, ask clarifying questions,
        # or share similar personal experiences — signals the story feels real
        "supporting_evidence": {
            "this happened to me", "same thing", "i believe you", "this is real",
            "similar experience", "i've heard", "this makes sense", "not the first time",
            "documented", "reported", "police", "called the cops", "checked",
            "verified", "i looked it up", "this is actually", "can confirm",
        },
        # Scepticism: doubting the story, calling it out as fiction or exaggerated
        "counterargument": {
            "didn't happen", "not real", "fake", "made up", "fiction", "creative writing",
            "r/nosleep", "this is nosleep", "sure jan", "i doubt", "hard to believe",
            "inconsistent", "plot hole", "doesn't add up", "suspicious", "convenient",
            "too perfect", "too coincidental", "exaggerated", "ragebait",
        },
        # Raw emotional response — high engagement signal for short-form video
        "emotional_reaction": {
            "oh my god", "omg", "i'm shaking", "that gave me chills", "nope",
            "nope nope nope", "absolutely not", "i would have died", "i'm scared",
            "can't sleep now", "thanks i hate it", "goosebumps", "horrifying",
            "terrifying", "nightmare fuel", "this is my worst fear", "ran chills",
            "so creepy", "genuinely scared", "disturbing", "unsettling", "haunting",
            "traumatizing", "freaked out", "this made my skin crawl",
        },
        # Speculation about what really happened — drives engagement question hooks
        "related_theory": {
            "what if", "maybe", "could have been", "i think", "my theory",
            "sounds like", "reminds me of", "similar to", "pattern", "not a coincidence",
            "stalker", "predator", "paranormal", "ghost", "entity", "demon",
            "sleep paralysis", "carbon monoxide", "intruder", "someone was watching",
            "someone broke in", "followed", "targeted", "they knew where you lived",
            "this isn't random", "too specific to be random",
        },
    },
}

# Fallback for unknown niches — use unsolved_mysteries sets
_DEFAULT_NICHE = "unsolved_mysteries"


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def _score(text: str, keywords: set) -> int:
    return sum(1 for kw in keywords if kw in text)


def _classify(body: str, keyword_sets: dict) -> str:
    text   = body.lower()
    scores = {role: _score(text, kws) for role, kws in keyword_sets.items()}
    best   = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "related_theory"


def extract_and_classify(cleaned_post: dict, niche: str) -> dict:
    keyword_sets = _KEYWORDS.get(niche, _KEYWORDS[_DEFAULT_NICHE])
    buckets: dict[str, list] = {role: [] for role in keyword_sets}

    for comment in cleaned_post.get("top_comments", []):
        role = _classify(comment["body"], keyword_sets)
        buckets[role].append(comment)

    return {**cleaned_post, "classified_comments": buckets}


def run(cleaned_posts: list[dict], config: dict | None = None) -> list[dict]:
    """Entry point called by main.py."""
    niche  = (config or {}).get("farm", {}).get("niche", _DEFAULT_NICHE)
    result = [extract_and_classify(p, niche) for p in cleaned_posts]
    print(f"[comment_extractor] Classified comments for {len(result)} posts.")
    return result
