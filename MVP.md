# SignalDrift — MVP Reference

Automated pipeline that crawls Reddit horror stories, generates narrated scripts, synthesizes TTS audio with word-level timing, and renders captioned 1080x1920 MP4s for TikTok.

---

## Pipeline Stages

```
crawl → score → draft → forge → post
```

| Stage | Entry point | What it does |
|-------|-------------|--------------|
| crawl | `crawl/reddit_crawler.py` | Pulls top+hot from Reddit, rotates secondaries, deduplicates |
| score | `crawl/scorer.py` | Haiku scores each post; failures go to sunset archive |
| draft | `draft/script_agent.py` | Claude Sonnet condenses post into 150–250 word first-person script |
| forge | `forge/tts.py` + `forge/composer.py` | Azure TTS with word timing → captioned MP4 with background clip + ambient music |

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

# Forge a specific post by ID
python main.py --post-id <post_id>
```

---

## Slicer

Processes raw gameplay footage into a rotation pool of 3-minute background clips.

```bash
# Drop .mp4 files into slicer/input/ then run:
python slicer/silcer_mvp.py

# Check pool rotation status
python slicer/pool_manager.py
```

**How it works:**
1. Samples footage at 1fps, computes per-second motion scores via PIL frame differencing
2. Each video uses its own adaptive threshold (30th percentile of its own scores)
3. Low-motion segments (menus, cutscenes, loading) are dropped
4. Remaining segments sliced into 180s chunks → `slicer/background_pool/<game>/`

**Pool rotation:** Each video render consumes the next clip in rotation across all game folders. If any game pool hits 0 the run stops.

---

## Config

`config.yaml` controls all tunable parameters:

```yaml
farm:
  subreddits:
    - name: "nosleep"
      min_score: 300
      tier: "primary"        # crawled every run
    - name: "paranormal"
      min_score: 100
      tier: "secondary"      # rotates in one per crawl

crawl:
  min_upvote_ratio: 0.8
  skip_title_keywords: [Update, Part, Announcement, Mod Post]

tts:
  engine: "azure"
  voice: "en-US-EricNeural"
  rate: "21%"
  pitch: "+0st"

video:
  resolution: "1080x1920"
  fps: 30
```

---

## Data Files

| File | Purpose |
|------|---------|
| `output/classified_posts.json` | Scored posts available for drafting |
| `output/queue/<post_id>.json` | Drafted scripts ready to forge |
| `output/seen_posts.json` | All processed post IDs (dedup) |
| `output/sunset_posts.json` | Archive of every post — scored, rejected, and used |
| `output/crawl_state.json` | Secondary subreddit rotation index |
| `slicer/pool_state.json` | Background clip rotation index |

---

## Assets

| Path | Contents |
|------|----------|
| `assets/music/` | Ambient music loops mixed under narration at 12% volume |
| `slicer/input/` | Drop raw gameplay footage here before slicing |
| `slicer/background_pool/` | Processed clips organized by game |

---

## Performance Tracking

Every rendered video includes a `tiktok_tag` (`#sd<post_id>`) printed at forge time.

Add this tag to the TikTok description. When you pull analytics later, join on the tag to link views/saves/watch time back to the source Reddit post in `sunset_posts.json`.

---

## Environment Variables (`.env`)

```
ANTHROPIC_API_KEY=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
```

---

## Roadmap

### Near-term
- **`--post-id` + `--stage forge` bug** — `--post-id` currently bypasses `--stage`, always re-drafts. Needs a one-line fix in `main.py`.
- **Female TTS routing** — scorer already planned to return `narrator_gender`. Route female-narrator stories to a second Azure voice automatically.
- **Gender field in scorer** — add `narrator_gender: male | female | neutral` to `crawl/scorer.py` JSON output.

### Data & ML
- **Performance tracker** — log every rendered video: story category, word count, script score, game used, posting time. Store in `output/performance_log.json`.
- **TikTok metric ingestion** — pull views, saves, watch time and join on `#sd<post_id>` tag to link performance back to source post in `sunset_posts.json`.
- **Post classifier** — once 50–100 videos have metrics, train a logistic regression on text embeddings to predict high/low performer. Replaces the heuristic Haiku scorer with a data-driven one.
- **False positive isolation** — log which game clip was used per video so you can separate "bad story" from "bad clip" in the performance data.

### Scale
- **Synthetic story generation** — feed top-performing scripts as examples to Claude, generate original stories in the same style. Patches the hole when Reddit supply runs thin.
- **Multi-account / multi-niche** — AITAH and space-theory farms planned. Only prompts + subreddit config swap between farms; pipeline stays identical.
- **`--count N` batch scheduling** — cron or scheduled trigger to run `python main.py --count 5` daily at 3pm automatically.

### Slicer
- **Motion threshold tuning per game** — expose `motion_percentile` as a per-subreddit-style config so slow horror games and fast FPS games each use the right floor.
- **Post-slice cleanup** — optionally delete source file from `slicer/input/` after processing to save disk space.
