import anthropic
import json
import os
import re
from dotenv import load_dotenv


load_dotenv()

_SYSTEM_PROMPT = """\
You are a First-Person Drama Narrator writing for short-form TikTok video narration.

━━━ THE VOICE ━━━
- Write in natural spoken English. Contractions only. Short sentences. Vary rhythm — mix a long one with two short punchy ones.
- NO AI-isms: "spiraled", "at the end of the day", "toxic", "boundaries", "gaslit", "unpacked", "processed", "healing", "it hit me", "I realized in that moment", "navigate", "journey", "valid", "rewind", "let me take you back", "so let's go back".
- NO NAMES: Use roles — "my sister", "my boss", "my boyfriend's mom".
- Write like you're venting to a friend who's about to lose their mind on your behalf.
- If the source uses censored words (f***, s***, a**, b****), write the actual word. Never write asterisks.
- Use natural spoken pauses: em-dashes for interruptions, a beat before key details. Let the story breathe.

━━━ STRUCTURE ━━━
- Drop straight into the story. No hook — that is handled separately.
- NEVER open with "so rewind", "let me rewind", "so let me take you back", "rewind to", "let me explain", or any meta-framing. Start mid-scene.
- Each sentence in the body makes the other person look worse than the last. Concrete actions only — not character judgements.
- End with a short hard closer. Under 8 words. The most damning detail — not a summary, not a repeat of the hook.
- Stay faithful to the source. Do not add events or people not in the source.

━━━ VERIFY BEFORE RETURNING ━━━
1. No hook written — story starts mid-scene, not with an opener.
2. Closer: under 8 words, explicit, does NOT repeat anything from the opener.
3. Any proper names? Replace with roles.
4. Any invented details? Remove them.
"""


def write_script_claude(context: dict, config: dict) -> dict:
    body_text = context.get("body", "")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    r = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        temperature=0.7,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Write a TikTok drama script from this source. 240–260 words total.\n\n"
                f"SOURCE TITLE: {context['title']}\n"
                f"SOURCE BODY: {body_text[:12000]}\n\n"
                f"Also return a card_title: an 'Am I the asshole for...' question. "
                f"If the title already starts with AITA/AITAH, rewrite it as 'Am I the asshole for [rest of title]'. "
                f"If not, derive what the AITA question would be from context. Keep it under 12 words after 'for'.\n\n"
                f"Return raw JSON only: {{\"script\": \"...\", \"card_title\": \"Am I the asshole for ...\"}}"
            )
        }]
    )

    raw = r.content[0].text.strip()
    s, e = raw.find('{'), raw.rfind('}') + 1
    parsed = json.loads(raw[s:e].replace('\n', ' ').replace('\r', ' '))
    return {"full_script": parsed["script"].strip(), "card_title": parsed.get("card_title", "").strip()}


def run(ctx: dict, config: dict) -> dict:
    try:
        result = write_script_claude(ctx, config)
    except anthropic.APIStatusError as e:
        if e.status_code in (402, 429) and "credit" in str(e).lower():
            raise RuntimeError("Anthropic credit balance too low — top up at console.anthropic.com") from e
        raise
    body = result.get("full_script", "").strip()
    card_title = result.get("card_title", "")

    full_text = body
    full_text = re.sub(r'\s+', ' ', full_text).strip()

    words = full_text.split()
    if len(words) > 260:
        full_text = " ".join(words[:220])
        last_p = full_text.rfind('.')
        if last_p != -1:
            full_text = full_text[:last_p + 1]

    print(f"[script_agent] FINAL COUNT: {len(full_text.split())} words.")
    return {
        "post_id": ctx.get("post_id"),
        "script": full_text,
        "card_title": card_title,
    }
