# SignalDrift — MVP Reference

Automated pipeline that crawls Reddit AITA/drama posts, generates first-person narrated scripts, synthesizes TTS audio with word-level timing, and renders captioned 1080x1920 MP4s for TikTok/Shorts.

---

## Pipeline Stages

```
crawl → score → draft → forge → post
```

| Stage | Entry point | What it does |
|-------|-------------|--------------|
| crawl | `crawl/reddit_crawler.py` | Pulls top+hot from AITAH/AmItheAsshole/relationship_advice, deduplicates |
| score | `crawl/scorer.py` | Rule pre-filter (score, ratio, length) then single Claude micro-call; failures go to sunset archive |
| draft | `draft/script_agent.py` | Claude Sonnet writes 240–260 word first-person drama script + card_title |
| forge | `forge/tts.py` + `forge/composer.py` | Azure TTS (NancyNeural) with SSML breaks → captioned MP4 with background clip + ambient music |

---

## Running the Pipeline

```bash
# Full run (crawl + score + draft + forge), 1 video
python main.py

# Produce N videos in one run
python main.py --count 5

# Crawl only (refresh classified_posts.json)
python main.py --stage crawl

# Forge only from existing queue
python main.py --stage forge --count 3

# Draft only — inspect before forging
python main.py --post-id <post_id> --draft-only

# Forge a specific post by ID
python main.py --post-id <post_id>
```

---

## Slicer

Processes raw footage into a pool of 90-second background clips.

```bash
# Drop .mp4 files into slicer/input/ then run:
python slicer/silcer_mvp.py
```

**How it works:**
1. Reads duration of each input file
2. Cuts into 90-second chunks — no motion analysis, no pixel sampling
3. Chunks saved to `slicer/background_pool/`

**Pool rotation:** Each forge picks a random clip and deletes it after use. Raises `PoolEmptyError` when pool is empty — re-run the slicer to refill.

**Background content:** Use royalty-free or low-enforcement footage (satisfying/oddly satisfying compilations, ambient b-roll). Avoid anything owned by large media companies (e.g. TheSoul Publishing / Five Minute Crafts) — Content ID will flag it on YouTube Shorts over 60s.

---

## Config

`config.yaml` controls all tunable parameters:

```yaml
brand:
  name: "FirstPerson"
  niche: "drama"

farm:
  subreddits:
    - name: "AITAH"
      min_score: 500
      tier: "primary"
    - name: "AmItheAsshole"
      min_score: 500
      tier: "primary"
    - name: "relationship_advice"
      min_score: 300
      tier: "secondary"

tts:
  engine: "azure"
  voice: "en-US-NancyNeural"       # female (default)
  voice_male: "en-US-EricNeural"   # routed by narrator_gender from scorer
  rate: "28%"
  pitch: "+0st"
```

---

## Data Files

| File | Purpose |
|------|---------|
| `output/classified_posts.json` | Scored posts available for drafting |
| `output/queue/<post_id>.json` | Drafted scripts ready to forge |
| `output/seen_posts.json` | All processed post IDs (dedup) |
| `output/sunset_posts.json` | Archive of every post — scored, rejected, and used |

---

## Assets

| Path | Contents |
|------|----------|
| `assets/music/` | Ambient music loops mixed under narration at 8% volume |
| `slicer/input/` | Drop raw footage here before slicing |
| `slicer/background_pool/` | Processed 90s clips ready for forge |

---

## Video Structure

Each rendered video follows this structure:

1. **Card** — white card with `[ AITA ]` label, displays the `card_title` question
2. **Narration reads card_title aloud** — card stays up until it finishes
3. **Card drops** — word-by-word captions take over
4. **Story body** — 240–260 words, first-person drama
5. **CTA** — `"What do you think?"` with emphasis break at the end

---

## Performance Tracking

Every rendered video includes a `tiktok_tag` (`#sd<post_id>`) printed at forge time.

Add this tag to the TikTok description. When you pull analytics later, join on the tag to link views/saves/watch time back to the source post in `sunset_posts.json`.

---

## Environment Variables (`.env`)

```
ANTHROPIC_API_KEY=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=
```

---

## Roadmap

### Near-term
- **Auto-post** — push rendered MP4s to TikTok/Shorts via API on a schedule
- **Performance tracker** — log every rendered video: word count, narrator gender, posting time → `output/performance_log.json`

### Data
- **TikTok metric ingestion** — pull views, saves, watch time and join on `#sd<post_id>` tag
- **Post classifier** — once 50–100 videos have metrics, replace heuristic scorer with a data-driven one

### Scale
- **Multi-account / multi-niche** — only prompts + subreddit config swap between farms; pipeline stays identical
- **Batch scheduling** — cron to run `python main.py --count 5` daily automatically
