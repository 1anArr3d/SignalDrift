"""
title_generator.py
LLM call #3 in the draft pipeline.
Given the script hook and theory topic, generates 5 ranked title variations
optimised for curiosity gap and click-through on short-form platforms.

Output schema:
[
  {"rank": 1, "title": "...", "rationale": "..."},
  ...
]
"""

import json
import os
import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are a short-form video title specialist for true crime and unsolved mysteries \
content on Facebook Reels, TikTok, and Pinterest.

Great titles for this niche:
- Lead with the most shocking or unresolved element of the case
- Name the subject (person or event) when it adds weight — specificity wins
- Are 6–12 words long
- Use a curiosity gap — make the viewer need to know what happened
- Lean clickbait but stay truthful — never imply something that isn't in the case
- Avoid ALL CAPS, excessive punctuation, and emoji
- Do not start with "Discover", "Find out", or "You won't believe"
- Strong openers: "She vanished...", "He was found...", "30 years later...", \
  "No one can explain...", "The case that..."

You output ONLY valid JSON. No prose, no markdown, no code fences.
"""

_USER_TEMPLATE = """\
Generate 5 ranked title variations for a short-form unsolved mysteries video.

CASE TOPIC: {topic}
HOOK (first line of the script): {hook}

Output a JSON array of 5 objects, ranked best to worst:
[
  {{"rank": 1, "title": "...", "rationale": "one sentence why this works"}},
  ...
]
"""


def generate_titles(script: dict, context: dict, config: dict) -> dict:
    """
    Args:
        script:  Output of script_agent (the 'script' sub-dict).
        context: Output of context_builder.build_context.
        config:  Parsed config.yaml dict.

    Returns:
        Dict with 'titles' key containing ranked list.
    """
    topic = context["the_theory"]["title"]
    hook = script.get("hook", "")

    prompt = _USER_TEMPLATE.format(topic=topic, hook=hook)

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=config["llm"]["model"],
        max_tokens=config["llm"]["max_tokens"],
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    titles = json.loads(raw)
    # Normalise: OpenAI may wrap the array in a key like {"titles": [...]}
    if isinstance(titles, dict):
        titles = next(iter(titles.values()))
    return {"titles": titles}


def run(script: dict, context: dict, config: dict) -> dict:
    """Entry point called by main.py."""
    result = generate_titles(script, context, config)
    print(f"[title_generator] Generated {len(result['titles'])} title variations.")
    return result


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    test_script = {
        "hook": "We might be the only intelligent life in the entire galaxy.",
        "body": "placeholder",
        "counterargument_acknowledgment": "placeholder",
        "conclusion": "placeholder",
        "cta": "placeholder",
    }
    test_ctx = {
        "the_theory": {"title": "The Great Filter is behind us", "post_id": "test_001"},
    }

    result = run(test_script, test_ctx, cfg)
    for t in result["titles"]:
        print(f"{t['rank']}. {t['title']} — {t['rationale']}")
