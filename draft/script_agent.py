import anthropic
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

# --- THE PROMPTS ---

_SYSTEM_PROMPT = """\
You are a First-Person Storyteller. Your goal is to write scripts that trick a TTS engine into sounding terrified.

━━━ THE VOICE ━━━
- Use 'Spoken English' and contractions.
- TOTAL BAN on AI-isms: "Little did I know", "shivers", "spooky", "spiraled".
- NO NAMES: Use roles like "The coworker," "The kid," "The toddler."

━━━ EMOTIONAL ENCODING ━━━
- THE GASP: Use double dashes (—) for shocks. (e.g., "The door opened—it was him.")
- THE HEAVY BREATH: Use triple dots (...) between realizations to slow down the TTS.
- IMPACT: Use single-word sentences for intensity.

━━━ THE FINAL STING (CRITICAL) ━━━
- The last sentence MUST be a 'Hard Drop'. Short. Under 5 words.
- Do NOT end on "ing" words (counting, looking, waiting) as they sound like they are trailing off.
- End on 'Closed' sounds that force a pitch drop: "Gone.", "Dead.", "Now.", "Dark.", "Mine."
- No trailing thoughts. No "But..." endings.
"""

def write_script_claude(context: dict, config: dict) -> dict:
    story = context.get("the_theory") or context
    body_text = story.get("body", "")
    source_word_count = len(body_text.split())
    max_words = min(240, max(150, int(source_word_count * 0.45))) 

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)
    
    response = client.messages.create(
        model="claude-sonnet-4-6", 
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user", 
                "content": f"Return a JSON object with the key 'full_script'. Adapt this story into a visceral script under {max_words} words. Use ellipses (...) and dashes (—). \n\nTITLE: {story['title']}\nBODY: {body_text[:12000]}"
            }
        ]
    )
    
    raw_content = response.content[0].text.strip()
    
    # Handle markdown blocks if Claude includes them
    if "```json" in raw_content:
        match = re.search(r'```json\s*(.*?)\s*```', raw_content, re.DOTALL)
        if match:
            raw_content = match.group(1)
    
    return json.loads(raw_content)

def run(ctx: dict, config: dict) -> dict:
    print(f"[script_agent_claude] Crafting visceral script for: {ctx.get('title')}")
    
    try:
        result = write_script_claude(ctx, config)
        full_text = result.get("full_script", "").strip()
    except Exception as e:
        print(f"Error in Claude Script Agent: {e}")
        return {
            "post_id": ctx.get("post_id"), 
            "script": "The headcount is wrong. I count eight kids, but the roster only says five. They're staring at me. I need to leave now ."
        }

    # THE HARD-DROP EXECUTIONER
    sentences = [s.strip() for s in full_text.split('.') if s.strip()]
    
    if sentences:
        last_s = sentences[-1].lower()
        # Kill any trailing AI-isms or "Hope" endings
        banned_ends = ["but", "hope", "maybe", "if only", "we'll see"]
        if any(last_s.endswith(word) or last_s.startswith(word) for word in banned_ends):
            sentences.pop()
            
    full_text = ". ".join(sentences).strip()
    
    # --- THE FINAL INFLECTION HACK ---
    # Strip any trailing punctuation
    full_text = full_text.rstrip(".").rstrip("-").rstrip("!").rstrip("...")
    
    # Add a space before the final period. 
    # This 'isolated' period forces OpenAI/Shimmer to drop her pitch to a 'dead end'.
    full_text += " ." 

    return {
        "post_id": ctx.get("post_id"),
        "script": full_text
    }