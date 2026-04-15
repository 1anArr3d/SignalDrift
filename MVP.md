# SignalDrift — MVP Reference

Automated pipeline that crawls Reddit AITA/drama posts, generates first-person narrated scripts, synthesizes TTS audio with word-level timing, and renders captioned 1080x1920 MP4s for YouTube Shorts / TikTok.

---

## Pipeline Stages

```
crawl → score → draft → forge → upload
```

| Stage | Entry point | What it does |
|-------|-------------|--------------|
| crawl | `crawl/reddit_crawler.py` | Pulls top+hot from configured subreddits, deduplicates against SQLite |
| score | `crawl/scorer.py` | Rule pre-filter (score, ratio, length, title keywords) then Claude micro-call; assigns `narrator_gender` |
| draft | `draft/script_agent.py` | Claude Sonnet writes 240–260 word first-person drama script + `card_title` |
| forge | `forge/tts.py` + `forge/composer.py` | Azure TTS with SSML breaks → captioned MP4 with background clip |
| upload | `publish/youtube_uploader.py` + `publish/drive_uploader.py` | Posts to YouTube Shorts; mirrors to Google Drive for cross-posting |

---

## Running the Pipeline

```bash
# Full run (crawl + score + draft + forge), 1 video
python main.py

# Produce N videos in one run
python main.py --count 5

# Crawl only (fill queue)
python main.py --stage crawl

# Forge only from existing queue
python main.py --stage forge --count 3

# Draft only — inspect script before forging
python main.py --post-id <post_id> --draft-only

# Redraft + forge a specific post by ID
python main.py --post-id <post_id>
```

---

## Slicer / Background Pool

Background clips are auto-downloaded via yt-dlp when the pool drops below `replenish_threshold`.

```bash
# Manual replenish (or drop .mp4s into slicer/input/ and run):
python slicer/silcer_mvp.py
```

**How it works:**
1. `pool_manager.py` checks clip count before each forge
2. Below threshold → `fetch.py` downloads from configured `search_queries` via yt-dlp
3. `silcer_mvp.py` slices downloads into `chunk_length`-second chunks → `slicer/background_pool/`
4. Each forge picks a random clip and deletes it after use

**Content guidance:** Use royalty-free or low-enforcement footage (satisfying/oddly satisfying compilations, ambient b-roll). Avoid anything owned by large media companies (e.g. TheSoul Publishing / Five Minute Crafts) — Content ID flags it on Shorts over 60s.

---

## Config (`config.yaml`)

```yaml
farm:
  subreddits:
    - name: "AITAH"
      min_score: 500
    - name: "AmItheAsshole"
      min_score: 500

tts:
  engine: "azure"
  voice_male: "en-US-EricNeural"
  voice_female: "en-US-NancyNeural"   # routed by narrator_gender from scorer
  rate: "28%"
  pitch: "+0st"
  cta: "What do you think?"

slicer:
  replenish_threshold: 3
  chunk_length: 90
  search_queries:
    - "satisfying workers compilation"

drive:
  enabled: true
  folder_id: "<your-drive-folder-id>"
```

---

## Persistence

All state is stored in `output/signaldrift.db` (SQLite). Status flow:

```
queued → drafted → used
               ↘ rejected
```

| Status | Meaning |
|--------|---------|
| `queued` | Passed scoring, waiting to draft+forge |
| `drafted` | Draft saved, ready to forge |
| `used` | Forged and uploaded |
| `rejected` | Failed scoring |

---

## Assets

| Path | Contents |
|------|----------|
| `assets/music/` | Ambient music loops mixed under narration |
| `slicer/input/` | Drop raw footage here for manual slicing |
| `slicer/background_pool/` | Processed clips ready for forge |

---

## Video Structure

1. **Hook card** — displays the `card_title` AITA question while narration reads it aloud
2. **Body** — 240–260 words, first-person drama, word-by-word captions
3. **CTA** — `"What do you think?"` with pitch/rate change at the end

---

## Environment Variables (`.env`)

```
ANTHROPIC_API_KEY=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
```

---

## Server Deployment (Ubuntu)

```bash
git clone <repo> /opt/signaldrift
cd /opt/signaldrift
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Copy auth tokens from local machine
scp token.json drive_token.json user@server:/opt/signaldrift/
scp client_secret.json user@server:/opt/signaldrift/

# Update composer.font_path in config.yaml for Linux fonts
# e.g. /usr/share/fonts/truetype/courier-prime/CourierPrime-Regular.ttf
```

Cron schedules are in `scheduler/crontab.txt`.

---

## Roadmap

### Near-term
- **TikTok API** — apply for developer access (gated); post alongside YouTube automatically
- **Facebook cross-post** — via Drive mirror

### Compilation pipeline
- **Daily long-form** — stitch that day's Shorts into a single upload
- One pipeline feeds the other

### Spanish channel
- Same pipeline, separate config — Spanish prompts, Azure Spanish neural voice, Spanish AITA subreddits
- `python main.py --config config_es.yaml`

### Data
- **Post classifier** — once 50–100 videos have metrics, replace heuristic scorer with a data-driven one

### Scale
- **Multi-niche / multi-account** — only prompts + subreddit config swap between farms
