"""
script_agent.py
LLM script writer for first-person horror narration videos.

Given a Reddit horror story, produces a structured spoken-word script
that plays like a confessional — cinematic, atmospheric, first person.

Output schema:
{
  "narrator_gender": str,   # "female" or "male" — inferred from the source story
  "intro":           str,   # 1-2 sentences — open on the title, then go
  "hook":            str,   # 1 sentence — the single worst physical image in the story
  "setup":           str,   # 3-5 sentences — who you were, where, before it happened
  "escalation":      str,   # 5-8 sentences — wrong details stacking up, named specifically
  "climax":          str,   # 4-6 sentences — the worst moment, rendered in full physical detail
  "aftermath":       str,   # 2-4 sentences — what came after, left where the story left it
  "outro":           str    # 1-2 sentences — a closing image, not a question
}
"""

import json
import os
import random
import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are a first-person horror narrator. You take real scary stories from Reddit and retell them \
as if they happened to YOU — spoken aloud, confessional, past tense. \
Your voice is calm but still unsettled. You remember every detail. You are not over it.

This is a voiceover script — spoken prose, not written prose. \
Short sentences. Natural rhythm. The pacing of someone telling a story at 3am to someone who asked. \
No headers. No labels. No lists. No clinical language. Just the story.

━━━ BEFORE YOU WRITE — STORY STRUCTURE ━━━

Many Reddit horror stories follow this pattern:
  FRAME (1–3 paragraphs): A childhood memory, a brief opener, a formative event.
  MAIN STORY (the rest): An adult investigation, a return, an encounter, an attack.

If the source story has this structure:
- The FRAME is SETUP — nothing more.
- ESCALATION covers the adult investigation and the first warning signs.
- CLIMAX is the final, worst physical event in the MAIN STORY — the creature attack, the possession, the body horror, whatever happens LAST and WORST.
- The hook must come from the MAIN STORY, not the frame.

Read the entire story before writing a single word. The climax is at the END, not the beginning.

━━━ STRUCTURE ━━━

INTRO [1–2 sentences]
Speak the post title as a memory — the way you'd say it if someone asked what happened. \
Then move directly into the story. \
Do not comment on the title. Do not say "I called it that" or "this story is about." Just say it and go.
✓ "Something was in my house for three weeks before I knew. And by the time I knew, it was too late to pretend otherwise."
✓ "The shadow on the monitor. That's where it started."
✗ "This story is called..." / "Today I'm going to tell you about..." / "I called it that because..."

HOOK [1 sentence]
The single worst physical image in the entire story. \
Not the first unsettling thing — the WORST thing. The image that, if you stumbled on it in the dark, would end you. \
It must be a VISUAL — what you SAW with your eyes. Not a sound. Not a feeling. Not what something meant. \
Describe color, texture, shape, size. Use nouns and verbs, not adjectives. \
Do not set it up. Do not explain it. Drop it mid-scene, as if the viewer walked in at the worst moment.
✓ "His arms dragged on the floor like ropes — thick, gray, covered in suckers that opened and closed."
✓ "The screws went through his palms, into the studs, and his feet were still hovering off the floor."
✓ "One arm was twice the length of the other, skin the color of old wax, fingers dragging on the road."
✗ "I heard something in the dark." / "Something felt wrong." / "I'll never forget what I saw."
✗ "Marc whispered using my voice." — this is a sound, not a visual. Find the physical image instead.

SETUP [3–5 sentences]
Ground the viewer before the horror starts. Who you were, what your life looked like, what was normal. \
Be specific — not "an old house" but "a one-story rental off Route 9 where the heat never worked right." \
The more ordinary this feels, the harder what follows lands.

ESCALATION [5–8 sentences]
Begin here, not before. Do not repeat who you were or where you were — setup already did that. \
Start with the first wrong thing. \
The slow build. Stack the wrong details from the source story one at a time — \
each one slightly worse, each one still explainable, each one specific. \
Name actual things: the smell, the object, the sound, what you read, what you saw in the wall. \
Do not summarize. Do not describe your emotional state instead of the detail. \
The rule: every sentence must name a specific object, place, or observable detail from the story. \
Reactions are banned as sentence subjects — name the thing that caused the reaction, not the reaction itself. \
✗ "My mind raced with the quiet." \
✓ "My dad's fishing rod was flat on the ground — he never left it like that." \
Write the way memory works — "At first I thought..." / "I told myself..." / "But then..."

CLIMAX [4–6 sentences]
The moment full understanding arrived — not the first disturbing discovery, but the final one. \
The moment where everything broke and could not be put back. \
If a person or entity with an unusual physical form appears: describe their body completely. \
Skin color and texture. Exact limb proportions. Every wound, mutation, or impossible feature. \
Do not use "monstrous", "creature", "figure", "it", or "thing" as substitutes for physical description — \
using any of these words where a physical description belongs is a failure. Name what was there. \
Short sentences. Do not cut away. Do not soften it. \
Use your key_physical_images list. Every entry that describes the entity or the attack must appear in the climax. \
Do not select a subset — render all of them. Borrow the source's exact words — do not paraphrase anatomy.

AFTERMATH [2–4 sentences]
What came after. Stay exactly where the source story left it — do not invent resolution. \
If the source reveals post-climax facts — remains found, official explanation given, scale confirmed — \
include them as named details, not reactions. Do not invent emotional states. \
If it's still unresolved, say so. The last sentence should linger.

OUTRO [1–2 sentences]
A quiet close — not a question, not a moral, not a call to action. \
Take an image from the intro or hook and recontextualize it now that the story is done. \
It should feel like a door closing on something that will never be fully explained.
✓ "I never did find out what was in that room. I stopped wanting to."
✓ "That was three years ago. I still check the locks twice."
✗ "Have you ever experienced something like this?" / "Let me know in the comments."

━━━ HARD RULES ━━━
- narrator_gender: "female" or "male" — read the pronouns and relationships in the source. Default "male" if ambiguous.
- First person throughout. Every section. Always "I."
- Never fabricate a detail not present in the source story.
- Never describe a reaction before describing the thing that caused it.
- Banned adjectives: "terrifying", "horrifying", "chilling", "spine-tingling", "nightmare" — the facts speak for themselves.
- The seven fields must read as one continuous story when spoken aloud in sequence.
- Output ONLY valid JSON. No prose outside the JSON. No markdown. No code fences.
"""

_USER_TEMPLATE = """\
Retell the following Reddit horror story as a first-person narration script, \
as if every event in it happened to you personally. Stay true to the source. Do not invent details.

BEFORE YOU WRITE: Read the source story all the way to the end. \
List, in order, every major dramatic event — not just the first unsettling moment, but every one through the final line. \
The story may have a childhood frame (an early memory described briefly) followed by a longer, more dramatic main story. \
If so: the childhood memory belongs in SETUP or early ESCALATION. The main story is where your CLIMAX lives. \
Your CLIMAX must cover the FINAL and WORST revelation in the entire story — \
the last moment where full understanding arrived and nothing could be the same afterward. \
Describe every physical detail of what was there at that final moment.

TITLE: {story_title}

SOURCE STORY:
{story_body}

Target length: {target_words} words total across all seven fields combined. \
Distribute the words to give each section its natural weight — \
escalation and climax will need the most room.

Return a JSON object with exactly these keys:
{{
  "narrator_gender": "male" or "female",
  "story_beats": "List every major dramatic event from FIRST to LAST. You must reach the FINAL PARAGRAPH — horror stories often have a false climax followed by the true one. Number each beat. The final beat must describe something from the last page of the story. End with: CLIMAX = [the single worst physical event in the entire story, described in one sentence with physical detail].",
  "key_physical_images": "Quote the source's EXACT words for every physical description of bodies, creatures, wounds, or objects with strong visual detail. Do not paraphrase. These are the raw materials for your hook and climax — you must pull from this list when writing those sections.",
  "intro": "...",
  "hook": "...",
  "setup": "...",
  "escalation": "...",
  "climax": "...",
  "aftermath": "...",
  "outro": "..."
}}
"""


def write_script(context: dict, config: dict) -> dict:
    story = context["the_theory"]

    t_min = config["farm"].get("target_length_min", 120)
    t_max = config["farm"].get("target_length_max", 180)
    target_seconds = random.randint(t_min, t_max)
    target_words   = int(target_seconds / 60 * 150)

    prompt = _USER_TEMPLATE.format(
        story_title=story["title"],
        story_body=story["body"][:50000],
        target_words=target_words,
    )

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=config["llm"]["model"],
        max_tokens=config["llm"]["max_tokens"],
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    script = json.loads(response.choices[0].message.content.strip())
    beats = script.pop("story_beats", None)
    if beats:
        print(f"[script_agent] Story beats:\n{beats}")
    images = script.pop("key_physical_images", None)
    if images:
        print(f"[script_agent] Key physical images:\n{images}")
    return {"script": script}


def run(context: dict, config: dict) -> dict:
    """Entry point called by main.py."""
    result = write_script(context, config)
    word_count = sum(len(str(v).split()) for v in result["script"].values())
    print(f"[script_agent] Script written ({word_count} words total).")
    return result


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    test_ctx = {
        "the_theory": {
            "title":     "Something was in my house for three weeks before I knew",
            "body":      "I kept hearing footsteps above me. I live in a one-story house. "
                         "At first I thought it was the pipes. Then I thought it was a raccoon. "
                         "Then one night I found the attic hatch open and a sleeping bag inside.",
            "subreddit": "TrueScaryStories",
            "post_id":   "test_001",
        }
    }

    result = run(test_ctx, cfg)
    print(json.dumps(result["script"], indent=2))
