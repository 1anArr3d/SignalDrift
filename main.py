import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
import yaml

# Stage imports
from crawl import reddit_crawler, cleaner
from draft import script_agent
from forge import tts, composer

def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

_SEEN_LOG = "output/seen_posts.json"

# --- JSON Helpers ---
def _save_json(data, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _load_seen() -> set:
    if not Path(_SEEN_LOG).exists(): return set()
    return set(_load_json(_SEEN_LOG))

def _mark_seen(post_id: str) -> None:
    seen = list(_load_seen())
    if post_id not in seen:
        seen.append(post_id)
        _save_json(sorted(seen), _SEEN_LOG)

# ---------------------------------------------------------------------------
# Stage: crawl
# ---------------------------------------------------------------------------
def run_crawl(config: dict) -> list[dict]:
    print("\n=== STAGE: crawl ===")
    raw_posts = reddit_crawler.run(config)
    cleaned_posts = cleaner.run(raw_posts)
    _save_json(cleaned_posts, "output/classified_posts.json")
    print(f"[main] Crawl complete. {len(cleaned_posts)} posts saved.")
    return cleaned_posts

# ---------------------------------------------------------------------------
# Stage: draft
# ---------------------------------------------------------------------------
def run_draft(post: dict, config: dict) -> dict:
    print(f"\n=== STAGE: draft [{post['post_id']}] ===")
    
    # Matching the new script_agent expectations
    ctx = {
        "title": post["title"],
        "body": post["body"],
        "subreddit": post["subreddit"],
        "post_id": post["post_id"]
    }

    script_result = script_agent.run(ctx, config)

    draft_output = {
        "post_id": post["post_id"],
        "subreddit": post["subreddit"],
        "title": post["title"],
        "script": script_result["script"], # This should now be the string of the story
    }

    queue_path = f"output/queue/{post['post_id']}.json"
    _save_json(draft_output, queue_path)
    return draft_output

# ---------------------------------------------------------------------------
# Stage: forge
# ---------------------------------------------------------------------------
def run_forge(draft: dict, config: dict) -> str:
    start_time = time.time()
    print(f"\n=== STAGE: forge [{draft['post_id']}] ===")

    post_id = draft["post_id"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Define paths
    audio_path = str(Path(f"output/rendered/{post_id}_{timestamp}.mp3"))
    video_path = str(Path(f"output/rendered/{post_id}_{timestamp}.mp4"))

    # 1. TTS & Alignment
    try:
        tts_result = tts.run(draft["script"], audio_path, config)
    except Exception as e:
        print(f"[main] TTS Error: {e}")
        raise

    # 2. Composition
    post_info = {
        "title": draft["title"],
        "subreddit": draft["subreddit"]
    }
    
    composer.compose(
        audio_path=tts_result["wav_path"],
        output_path=video_path,
        config=config,
        post_info=post_info,
        word_timings=tts_result["word_timings"]
    )

    _mark_seen(post_id)
    print(f"[main] Video complete: {video_path} ({time.time()-start_time:.1f}s)")
    return video_path

# ---------------------------------------------------------------------------
# Orchestration Logic
# ---------------------------------------------------------------------------
def run_pipeline(config: dict, limit: int = 5) -> None:
    # 1. Crawl
    posts = run_crawl(config)
    seen = _load_seen()
    
    # 2. Filter & Sort
    to_process = [p for p in posts if p["post_id"] not in seen]
    to_process = sorted(to_process, key=lambda x: x.get("score", 0), reverse=True)[:limit]

    if not to_process:
        print("[main] No new posts to process.")
        return

    # 3. Process
    for post in to_process:
        try:
            draft = run_draft(post, config)
            run_forge(draft, config)
        except Exception as e:
            print(f"[main] FAILED post {post['post_id']}: {e}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["crawl", "draft", "forge"])
    parser.add_argument("--post-id")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.post_id:
        posts = _load_json("output/classified_posts.json")
        match = next((p for p in posts if p["post_id"] == args.post_id), None)
        if match:
            draft = run_draft(match, config)
            run_forge(draft, config)
    elif args.stage == "forge":
        queue = list(Path("output/queue").glob("*.json"))[:args.limit]
        for p in queue:
            run_forge(_load_json(str(p)), config)
    else:
        run_pipeline(config, limit=args.limit)

if __name__ == "__main__":
    main()