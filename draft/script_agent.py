"""
script_agent.py
LLM call #2 in the draft pipeline.
Given the context object and the stance paragraph, outputs a structured
60–90 second video script as JSON.

Output schema:
{
  "hook": str,                          # under 15 words, opening statement
  "body": str,                          # main explanation, 3–4 sentences
  "counterargument_acknowledgment": str, # 1–2 sentences addressing the strongest counter
  "conclusion": str,                    # 1–2 sentences, resolves the tension
  "cta": str                            # 1 sentence call to action
}
"""

import json
import os
import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are a writer for unsolved mysteries short-form videos on Facebook Reels, TikTok, \
and Pinterest. Your audience loves true crime, cold cases, and unexplained disappearances. \
They scroll fast — you have 3 seconds to stop them.

Your scripts follow this formula:
1. HOOK — one sentence, under 12 words. State the core mystery as a plain fact. \
   No adjectives. No dramatic language. No case-specific names or dates. \
   Format: "[Subject] [what happened]." \
   Examples: "A woman vanished and was never found." \
             "He disappeared the night before his wedding." \
             "A family of four went missing without a trace." \
   Wrong: "The chilling disappearance of Christina Plante still haunts investigators." \
   Wrong: "In 1987, a shocking mystery unfolded in rural Louisiana."
2. BODY — stretch out the background. Give full context: who the victim was, the timeline, \
   key events in order, the facts as confirmed. Make the viewer feel like they know this \
   person and understand exactly what happened up to the point it became a mystery. \
   5–7 sentences. Do not rush this section.
3. THEORIES — explicitly name every theory the community has raised and explain each one. \
   Don't just state "some believe X" — briefly explain the reasoning or evidence behind it \
   so a viewer unfamiliar with the case understands why people believe it. \
   "Some believe X because Y. Others point to Z, citing the fact that..." \
   Cover all major theories. 4–6 sentences.
4. COUNTERARGUMENT — 1–2 sentences acknowledging the skeptical take or the official \
   explanation, delivered respectfully.
5. CONCLUSION — 1–2 sentences. Restate what remains unknown. Treat the subject with dignity.
6. ENGAGEMENT QUESTION — end with a direct question to the viewer. Something that invites \
   them to pick a side or share knowledge. "Which theory do you believe?" or \
   "What do you think really happened?" — make it specific to the case.

Rules:
- Always refer to victims by name, not "the victim"
- Never state a theory as fact
- Professional tone throughout — curious and investigative, never exploitative
- Target length: see user prompt for word count

You output ONLY valid JSON. No prose, no markdown, no code fences.
"""

_USER_TEMPLATE = """\
Write a short-form video script about the following unsolved case.

CASE: {theory_title}

POST (full original writeup — use this as your primary source of facts and detail):
{theory_body}

ANALYSIS (editorially guides framing, not facts): {stance_paragraph}

CONFIRMED FACTS from the discussion:
{supporting}

THEORIES FROM THE COMMUNITY:
{theories}

STRONGEST SKEPTICAL TAKE:
{counter}

BACKGROUND CONTEXT (related cases / prior discussion):
{canon}

Target length: {target_words} words total across all fields combined.

Output a JSON object with exactly these fields:
{{
  "hook": "...",
  "body": "...",
  "theories": "...",
  "counterargument_acknowledgment": "...",
  "conclusion": "...",
  "engagement_question": "..."
}}
"""


def _format_comments(comments: list[dict], limit: int = 5) -> str:
    if not comments:
        return "None"
    return "\n".join(f"- {c['body'][:300]}" for c in comments[:limit])


def _format_canon(chunks: list[dict]) -> str:
    if not chunks:
        return "None"
    return "\n\n".join(f"[{c['subreddit']}] {c['text'][:400]}" for c in chunks[:3])


def write_script(context: dict, stance: dict, config: dict) -> dict:
    """
    Args:
        context: Output of context_builder.build_context.
        stance:  Output of stance_agent.run.
        config:  Parsed config.yaml dict.

    Returns:
        Dict with 'script' key containing the parsed JSON script object,
        and 'raw_response' for debugging.
    """
    theory = context["the_theory"]
    debate = context["the_debate"]
    target_seconds = config["farm"]["target_length_seconds"]
    # 150 wpm is a comfortable narration pace
    target_words = int(target_seconds / 60 * 150)

    prompt = _USER_TEMPLATE.format(
        theory_title=theory["title"],
        theory_body=theory["body"][:2500],
        stance_paragraph=stance["stance_paragraph"],
        supporting=_format_comments(debate.get("supporting_evidence", [])),
        theories=_format_comments(debate.get("related_theory", []), limit=5),
        counter=_format_comments(debate.get("counterargument", [])),
        canon=_format_canon(context.get("the_canon", [])),
        target_words=target_words,
    )

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

    # Strip any accidental markdown fences before parsing
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    script = json.loads(raw)
    return {"script": script, "raw_response": raw}


def run(context: dict, stance: dict, config: dict) -> dict:
    """Entry point called by main.py."""
    result = write_script(context, stance, config)
    word_count = sum(
        len(str(v).split()) for v in result["script"].values()
    )
    print(f"[script_agent] Script written ({word_count} words total).")
    return result


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    test_ctx = {
        "the_theory": {
            "title": "The Great Filter is behind us",
            "body": "Most civilisations die before multicellular life.",
            "core_claim": "The Great Filter is behind us.",
            "subreddit": "Fermi",
            "post_id": "test_001",
        },
        "the_debate": {
            "supporting_evidence": [{"body": "Cambrian explosion took 3.5B years.", "score": 900}],
            "counterargument": [{"body": "Filter could still be ahead of us.", "score": 600}],
            "related_theory": [],
            "emotional_reaction": [],
        },
        "the_canon": [],
        "the_signal": {"upvote_ratio": 0.92, "num_comments": 312, "score": 4500},
    }
    test_stance = {
        "stance_paragraph": (
            "The evidence leans toward the Great Filter being behind us, "
            "with eukaryotic life as the rare bottleneck. Confidence: medium. "
            "The most important caveat is that we cannot rule out a second filter ahead."
        )
    }

    result = run(test_ctx, test_stance, cfg)
    print(json.dumps(result["script"], indent=2))
