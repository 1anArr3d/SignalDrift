"""
stance_agent.py
LLM call #1 in the draft pipeline.
Given the assembled context object, derives a defensible stance on the theory —
a single paragraph with a stated conclusion and a confidence level.
"""

import json
import os
import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are a true-crime and unsolved mysteries narrator. You cover real cases involving \
real victims — missing persons, unexplained deaths, cold cases — and you treat every \
subject with dignity and respect.

Your tone is:
- Professional and sombre when handling victim details
- Genuinely curious and investigative when exploring what happened
- Measured — you present theories as theories, not conclusions

You never sensationalise suffering. You never name a suspect without established fact. \
You frame unanswered questions as open investigations, not entertainment.
"""

_USER_TEMPLATE = """\
Here is an unsolved mystery case from Reddit that we are turning into a short video.

CASE (title + body):
{theory_title}
{theory_body}

CONFIRMED FACTS from the discussion:
{supporting}

COUNTERARGUMENTS / SKEPTICAL TAKES:
{counter}

THEORIES people have proposed:
{related}

BACKGROUND CONTEXT:
{canon}

ENGAGEMENT SIGNAL:
- Upvote ratio: {upvote_ratio}
- Comments: {num_comments}

Based on all of the above, write ONE paragraph (3–5 sentences) that:
1. Summarises what is confirmed vs. what remains unknown.
2. Notes which theory from the discussion has the most weight behind it, and why.
3. Identifies the single most important unanswered question.

Treat the subject with respect. Output ONLY the paragraph. No headers, no bullet points.
"""


def _format_comments(comments: list[dict], limit: int = 3) -> str:
    if not comments:
        return "None"
    return "\n".join(f"- {c['body'][:200]}" for c in comments[:limit])


def _format_canon(chunks: list[dict]) -> str:
    if not chunks:
        return "None"
    return "\n\n".join(f"[{c['subreddit']}] {c['text'][:300]}" for c in chunks)


def derive_stance(context: dict, config: dict) -> dict:
    """
    Args:
        context: Output of context_builder.build_context.
        config: Parsed config.yaml dict.

    Returns:
        Dict with 'stance_paragraph' and raw 'context' for downstream agents.
    """
    theory = context["the_theory"]
    debate = context["the_debate"]
    canon = context["the_canon"]
    signal = context["the_signal"]

    prompt = _USER_TEMPLATE.format(
        theory_title=theory["title"],
        theory_body=theory["body"][:800],
        supporting=_format_comments(debate.get("supporting_evidence", [])),
        counter=_format_comments(debate.get("counterargument", [])),
        related=_format_comments(debate.get("related_theory", [])),
        canon=_format_canon(canon),
        upvote_ratio=signal["upvote_ratio"],
        num_comments=signal["num_comments"],
    )

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=config["llm"]["model"],
        max_tokens=config["llm"]["max_tokens"],
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    stance = response.choices[0].message.content.strip()
    return {"stance_paragraph": stance}


def run(context: dict, config: dict) -> dict:
    """Entry point called by main.py."""
    result = derive_stance(context, config)
    print(f"[stance_agent] Derived stance ({len(result['stance_paragraph'].split())} words).")
    return result


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    # Minimal test context
    test_ctx = {
        "the_theory": {
            "title": "The Great Filter is behind us — we are the rare survivors",
            "body": "Most civilisations die before multicellular life. We made it. That's the filter.",
            "core_claim": "The Great Filter is behind us.",
            "subreddit": "Fermi",
            "post_id": "test_001",
        },
        "the_debate": {
            "supporting_evidence": [{"body": "The Cambrian explosion took 3.5 billion years to occur — that's the rare step.", "score": 900}],
            "counterargument": [{"body": "We could be the first, not the survivors — the filter may still be ahead.", "score": 600}],
            "related_theory": [],
            "emotional_reaction": [],
        },
        "the_canon": [],
        "the_signal": {"upvote_ratio": 0.92, "num_comments": 312, "score": 4500},
    }

    result = run(test_ctx, cfg)
    print(result["stance_paragraph"])
