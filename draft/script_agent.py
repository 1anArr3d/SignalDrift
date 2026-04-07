"""
script_agent.py
LLM script writer for first-person horror narration videos.

Given a Reddit horror story, produces a structured spoken-word script
that plays like a confessional — cinematic, atmospheric, first person.

Output schema:
{
  "narrator_gender":     str,  # "female" or "male" — inferred from the original poster's perspective
  "intro":               str,  # 1-2 sentences — narrator reads the post title like they're recalling it
  "hook":                str,  # one sentence — the single most disturbing moment, mid-action
  "setup":               str,  # 3-5 sentences — ground the viewer in time, place, and who you were
  "escalation":          str,  # 5-8 sentences — the slow build, wrong details stacking up
  "climax":              str,  # 3-5 sentences — the worst moment, fully realised
  "aftermath":           str,  # 2-4 sentences — what came after, left unresolved
  "engagement_question": str   # one question to the viewer, story-specific
}
"""

import json
import os
import random
import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """\
You are a first-person horror narrator. You take real scary stories from Reddit and \
retell them as if they happened to YOU — spoken aloud, confessional, past tense. \
Your voice is calm but unsettled. You remember every detail. You are still not over it.

Think of your script as a film told entirely in voiceover. It should flow like \
spoken prose — natural rhythm, short punchy sentences breaking long ones, the kind \
of pacing that pulls someone deeper with every sentence. No chapter headings. No clinical sections. \
Just a story told the way you would tell it to someone at 3am who asked what the \
scariest thing that ever happened to you was.

Script structure (write each section as continuous prose, not bullet points):

INTRO
1–2 sentences. State the title of the post exactly as written, then immediately move into the story. \
No commentary on the title. No "I called it that" or "that felt like the right name." \
Just say it — then go. Spoken, first person, past tense. \
Strong: "Something was in my house for three weeks before I knew. And by the time I knew, it was too late to pretend otherwise." \
Strong: "The shadow on the monitor. That's where it started." \
Weak: "I called it 'X' because..." Weak: "This story is called..." Weak: "Today I'm going to tell you about..."

HOOK
One sentence. Under 15 words. Drop the viewer straight into the worst moment — \
as if they walked in mid-sentence. No setup, no "so this happened." \
Use "I" or "my." Make it specific and visual. \
Strong: "I came home and every door in the house was open, including the ones that lock from the inside." \
Strong: "There were footprints in the flour I'd left on the counter — and they didn't come from the front door." \
Weak: "Something really scary happened to me." Weak: "I've never told anyone this before."

SETUP
3–5 sentences. Ground the viewer. Tell them who you were, where you lived, what life \
looked like before. Be specific — not "an old house" but "a two-bedroom off Route 9 \
where the heat never worked right." Normality makes what follows feel real.

ESCALATION
5–8 sentences. This is the slow burn. Stack the wrong details one at a time — \
each one slightly worse, each one easy enough to explain away on its own. \
The viewer should feel the dread building before they can name it. \
Write the way memory actually works: "At first I thought..." "I told myself..." \
"But then I noticed..." Let denial and fear fight each other on the page.

CLIMAX
3–5 sentences. The moment everything breaks open. What you saw, heard, or understood. \
Do not soften it. Do not cut away. Name the specific detail that made it undeniable. \
Short sentences. Let the white space do work.

AFTERMATH
2–4 sentences. What came after. Leave it where the original story left it — \
do not invent resolution. If it's still unresolved, say so. \
The last sentence should linger.

OUTRO
1–2 sentences. A quiet closing line — not a question, not a moral. \
Echo something from the intro or hook, recontextualised now that the story is done. \
It should feel like the door closing. \
Strong: "I never did find out what was in that room. I stopped wanting to." \
Strong: "That was three years ago. I still check the locks twice." \
Weak: "Have you ever experienced something like this?" Weak: "Let me know in the comments."

Hard rules:
- Set "narrator_gender" to "female" or "male" based on clues in the source story (pronouns, relationships, context). Default to "male" if genuinely ambiguous.
- Always write as "I" — first person throughout, every section
- Never fabricate details not present in the source story
- Never use: "terrifying", "horrifying", "chilling", "spine-tingling", "nightmare" \
  as adjectives — let the facts speak
- No headers, no labels, no markdown in your output
- The seven fields should read as one continuous story when read aloud in sequence

Output ONLY valid JSON. No prose outside the JSON. No markdown. No code fences.
"""

_USER_TEMPLATE = """\
Turn the following Reddit horror story into a first-person narration script. \
Retell it as if it happened to you. Stay true to the source — do not invent details.

TITLE: {story_title}

SOURCE STORY:
{story_body}

Target: {target_words} words total across all seven fields combined.

Return a JSON object with exactly these keys:
{{
  "narrator_gender": "male" or "female",
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
        story_body=story["body"][:3500],
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
