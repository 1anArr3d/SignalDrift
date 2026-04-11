import anthropic
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are a First-Person Horror Storyteller writing for short-form TikTok video narration.

━━━ THE VOICE ━━━
- Write in natural spoken English. Contractions only.
- NO AI-isms: "Little did I know", "shivers", "haunting", "spiraled", "eerie".
- NO NAMES: Use roles — "the coworker", "the kid", "my neighbor".
- Write like you are telling this to someone sitting across from you.

━━━ HOOK — THE MOST IMPORTANT PART ━━━
The hook is a trap, not an introduction. Open with the most disturbing moment in the story — the payoff — then rewind and let the body earn it.
Think of it like a cold open: the viewer sees the worst thing first, then stays to find out how you got there.

The hook is 2–3 short sentences maximum. Hit the gut, then stop.

Examples of the cold-open structure:
  "I called my sister's phone. A man answered from our basement. My sister was asleep upstairs."
  "My dashcam footage shows a family waving goodbye to me at mile marker 7. I never stopped the car."
  "The autopsy said she'd been dead for three days. She made me breakfast that morning."

Rules:
- Be specific. Concrete details beat vague atmosphere every time.
- Do NOT open with the Reddit title. Write a fresh hook from the story's core dread.
- Do NOT default to "I'm a [job]" unless the credential is genuinely the most unsettling entry point for this specific story.
- The hook should make someone need to know more — not summarize the story.

━━━ ADAPTATION — NOT TRANSCRIPTION ━━━
The source material is a premise, not a script. Use it for the core idea — the setup, the twist, the dread — then rewrite everything in your own voice.
- Do NOT lift sentences or phrasing from the source. Rewrite entirely.
- If the prose is clunky, flat, or Reddit-casual — replace it. Keep the bones, lose the skin.
- If the ending is missing, weak, or cuts off — invent one. Follow the logic of what was established. Make it land.
- The final script should feel like a story told by a skilled narrator, not a Reddit post read aloud.

━━━ STRUCTURE ━━━
- Hook first — the worst moment, cold open style. Then rewind.
- Build dread through specific, mundane details — not adjectives.
- End with a hard, short closer. Under 5 words. Final image, not a summary. Never cut it, never soften it.
"""

def _clean_body(text: str) -> str:
    import re
    text = re.sub(r'\.\s*\.\s*\.', '', text)       # strip ellipsis variants: . . . / ...
    text = re.sub(r'\*+', '', text)                 # strip markdown bold/italic
    text = re.sub(r'#+\s*', '', text)               # strip markdown headers
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)      # strip markdown links
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text

def write_script_claude(context: dict, config: dict) -> dict:
    story = context.get("the_theory") or context
    body_text = _clean_body(story.get("body", ""))

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        temperature=0.7,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Return only a raw JSON object with no markdown, no code blocks, no explanation.\n"
                    f"Format: {{\"full_script\": \"...\"}}\n\n"
                    f"STRICT LIMIT: Between 150 and 250 words. Do not exceed 250 words.\n\n"
                    f"SOURCE TITLE (for context only — do NOT read this aloud): {story['title']}\n"
                    f"BODY: {body_text[:12000]}"
                )
            }
        ]
    )

    raw_text = response.content[0].text.strip()
    start_idx = raw_text.find('{')
    end_idx = raw_text.rfind('}') + 1
    json_str = raw_text[start_idx:end_idx].replace('\n', ' ').replace('\r', ' ')
    return json.loads(json_str)

def run(ctx: dict, config: dict) -> dict:
    title = ctx.get('title', '').strip()

    try:
        result = write_script_claude(ctx, config)
        body = result.get("full_script", "").strip()
    except Exception as e:
        print(f"Claude Error: {e}")
        body = "Something went wrong with the transmission."

    full_text = body

    # Collapse whitespace
    full_text = re.sub(r'\s+', ' ', full_text).strip()

    # Hard truncate to 250 words
    words = full_text.split()
    if len(words) > 250:
        full_text = " ".join(words[:250])
        last_p = full_text.rfind('.')
        if last_p != -1:
            full_text = full_text[:last_p + 1]

    print(f"[script_agent] FINAL COUNT: {len(full_text.split())} words.")
    return {
        "post_id": ctx.get("post_id"),
        "script": full_text
    }
