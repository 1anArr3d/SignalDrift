import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
import yaml

# Stage imports
from crawl import reddit_crawler, cleaner
from crawl.scorer import score_batch
from draft import script_agent
from forge import tts, composer
from slicer.pool_manager import preflight_check, get_next_clip, consume_clip, PoolEmptyError

def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

_SEEN_LOG      = "output/seen_posts.json"
_CLASSIFIED    = "output/classified_posts.json"
_SUNSET        = "output/sunset_posts.json"

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

# --- Sunset helpers ---
def _load_sunset() -> list:
    if not Path(_SUNSET).exists(): return []
    return _load_json(_SUNSET)

def _sunset_posts(posts: list, used_at: str = None, video_path: str = None) -> None:
    """Append posts to sunset_posts.json, preserving all data + metadata."""
    archive = _load_sunset()
    for post in posts:
        entry = dict(post)
        if used_at:
            entry["used_at"] = used_at
        if video_path:
            entry["video_path"] = video_path
        archive.append(entry)
    _save_json(archive, _SUNSET)

def _remove_from_classified(post_id: str) -> None:
    """Remove a post from classified_posts.json after it has been used."""
    if not Path(_CLASSIFIED).exists():
        return
    posts = _load_json(_CLASSIFIED)
    remaining = [p for p in posts if p["post_id"] != post_id]
    _save_json(remaining, _CLASSIFIED)

# ---------------------------------------------------------------------------
# Stage: crawl
# ---------------------------------------------------------------------------
def run_crawl(config: dict) -> list[dict]:
    print("\n=== STAGE: crawl ===")
    raw_posts = reddit_crawler.run(config)
    cleaned_posts = cleaner.run(raw_posts)

    # Score — only passed posts enter the queue
    passed, failed = score_batch(cleaned_posts)

    # Sunset rejected posts immediately — data preserved, not lost
    if failed:
        _sunset_posts(failed)
        print(f"[main] {len(failed)} posts failed scoring → sunset_posts.json")

    _save_json(passed, _CLASSIFIED)
    print(f"[main] Crawl complete. {len(passed)} posts queued.")
    return passed

# ---------------------------------------------------------------------------
# Stage: draft
# ---------------------------------------------------------------------------
def run_draft(post: dict, config: dict) -> dict:
    print(f"\n=== STAGE: draft [{post['post_id']}] ===")

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
        "script": script_result["script"],
        "tiktok_tag": f"#sd{post['post_id']}",   # tag for performance tracking
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

    audio_path = str(Path(f"output/rendered/{post_id}_{timestamp}.mp3"))
    video_path = str(Path(f"output/rendered/{post_id}_{timestamp}.mp4"))

    # Get next background clip from rotation pool
    bg_path = get_next_clip()

    try:
        tts_result = tts.run(draft["script"], audio_path, config)
    except Exception as e:
        print(f"[main] TTS Error: {e}")
        raise

    post_info = {
        "title": draft["title"],
        "subreddit": draft["subreddit"]
    }

    composer.compose(
        audio_path=tts_result["wav_path"],
        output_path=video_path,
        config=config,
        post_info=post_info,
        word_timings=tts_result["word_timings"],
        bg_path=bg_path
    )

    # Consume the clip after successful render
    consume_clip(bg_path)

    _mark_seen(post_id)

    # Sunset the used post — move out of classified, preserve in archive
    _remove_from_classified(post_id)
    _sunset_posts(
        [{"post_id": post_id, "title": draft["title"], "subreddit": draft["subreddit"],
          "tiktok_tag": draft.get("tiktok_tag", "")}],
        used_at=datetime.now().isoformat(),
        video_path=video_path
    )

    print(f"[main] Video complete: {video_path} ({time.time()-start_time:.1f}s)")
    print(f"[main] TikTok tag: {draft.get('tiktok_tag', '')}")
    return video_path

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_pipeline(config: dict, count: int = 1) -> None:
    try:
        preflight_check()
    except PoolEmptyError as e:
        print(e)
        return

    posts = run_crawl(config)
    seen = _load_seen()

    to_process = [p for p in posts if p["post_id"] not in seen]
    to_process = sorted(to_process, key=lambda x: x.get("score", {}).get("overall", 0), reverse=True)[:count]

    if not to_process:
        print("[main] No new posts to process.")
        return

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
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.post_id:
        posts = _load_json(_CLASSIFIED)
        match = next((p for p in posts if p["post_id"] == args.post_id), None)
        if match:
            draft = run_draft(match, config)
            run_forge(draft, config)
    elif args.stage == "crawl":
        run_crawl(config)
    elif args.stage == "forge":
        queue = list(Path("output/queue").glob("*.json"))[:args.count]
        for p in queue:
            run_forge(_load_json(str(p)), config)
    else:
        run_pipeline(config, count=args.count)

if __name__ == "__main__":
    main()
