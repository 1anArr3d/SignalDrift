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
from slicer.pool_manager import get_random_clip, consume_clip, PoolEmptyError

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
def _load_all_seen_ids() -> set:
    ids = _load_seen()
    if Path(_SUNSET).exists():
        sunset = _load_json(_SUNSET)
        ids.update(p["post_id"] for p in sunset if "post_id" in p)
    if Path(_CLASSIFIED).exists():
        classified = _load_json(_CLASSIFIED)
        ids.update(p["post_id"] for p in classified if "post_id" in p)
    return ids

def run_crawl(config: dict, all_subs: bool = False) -> list[dict]:
    print("\n=== STAGE: crawl ===")
    raw_posts = reddit_crawler.run(config, all_subs=all_subs)
    cleaned_posts = cleaner.run(raw_posts)

    # Skip posts we've already seen or scored before
    seen_ids = _load_all_seen_ids()
    fresh_posts = [p for p in cleaned_posts if p["post_id"] not in seen_ids]
    skipped = len(cleaned_posts) - len(fresh_posts)
    if skipped:
        print(f"[main] Skipped {skipped} already-seen posts.")

    # Score — only passed posts enter the queue
    passed, failed = score_batch(fresh_posts, config=config)

    # Sunset rejected posts immediately — data preserved, not lost
    if failed:
        failed_slim = [{k: v for k, v in p.items() if k != "body"} for p in failed]
        _sunset_posts(failed_slim)
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
        "body": post.get("body", ""),
        "script": script_result["script"],
        "card_title": script_result.get("card_title", ""),
        "narrator_gender": post.get("score", {}).get("narrator_gender", "neutral"),
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

    audio_path = str(Path(f"output/rendered/{post_id}.mp3"))
    video_path = str(Path(f"output/rendered/{post_id}.mp4"))

    bg_path = get_random_clip()

    narrator_gender = draft.get("narrator_gender", "neutral")
    print(f"[main] Narrator gender: {narrator_gender}")

    # card_title is spoken first, then the script body follows
    card_title = draft.get("card_title") or draft["title"]
    full_tts_text = card_title + " " + draft["script"]

    try:
        tts_result = tts.run(full_tts_text, audio_path, config, narrator_gender=narrator_gender)
    except Exception as e:
        print(f"[main] TTS Error: {e}")
        raise

    # Card disappears after card_title words finish speaking
    card_word_count = len(card_title.split())

    post_info = {
        "title": draft["title"],
        "subreddit": draft["subreddit"],
        "hook": card_title,           # word count used for timing
        "hook_display": card_title,   # text shown on card
    }

    composer.compose(
        audio_path=tts_result["wav_path"],
        output_path=video_path,
        config=config,
        post_info=post_info,
        word_timings=tts_result["word_timings"],
        bg_path=bg_path
    )

    consume_clip(bg_path)

    # Remove intermediate audio file
    Path(audio_path).unlink(missing_ok=True)

    _mark_seen(post_id)

    # Sunset the used post — move out of classified, preserve in archive
    _remove_from_classified(post_id)
    _sunset_posts(
        [{"post_id": post_id, "title": draft["title"], "subreddit": draft["subreddit"],
          "tiktok_tag": draft.get("tiktok_tag", ""), "body": draft.get("body", "")}],
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
    parser.add_argument("--stage", choices=["crawl", "forge"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--all", action="store_true", help="Crawl all subreddits at once")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--post-id", help="Reforge a specific post by ID using its existing queue JSON")
    parser.add_argument("--draft-only", action="store_true", help="Run draft stage only, skip forge")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.post_id:
        queue_path = Path(f"output/queue/{args.post_id}.json")
        if queue_path.exists():
            if args.draft_only:
                print(f"[main] Queue JSON already exists for {args.post_id}. Delete it first to redraft.")
                return
            draft = _load_json(str(queue_path))
            run_forge(draft, config)
            return

        # Search classified
        match = None
        if Path(_CLASSIFIED).exists():
            match = next((p for p in _load_json(_CLASSIFIED) if p["post_id"] == args.post_id), None)

        # Fall back to sunset
        if not match and Path(_SUNSET).exists():
            match = next((p for p in _load_json(_SUNSET) if p["post_id"] == args.post_id), None)
            if match:
                print(f"[main] Found {args.post_id} in sunset — redrafting.")

        if not match:
            print(f"[main] {args.post_id} not found in queue, classified, or sunset.")
            return

        draft = run_draft(match, config)
        if not args.draft_only:
            run_forge(draft, config)
        else:
            print(f"[main] Draft saved to output/queue/{args.post_id}.json — inspect before forging.")
        return

    if args.stage == "crawl":
        run_crawl(config, all_subs=args.all)

    elif args.stage == "forge":
        # Draft then forge the top N scored posts from classified
        seen = _load_seen()
        posts = _load_json(_CLASSIFIED)
        to_process = [p for p in posts if p["post_id"] not in seen]
        to_process = sorted(to_process, key=lambda x: x.get("score", {}).get("overall", 0), reverse=True)[:args.count]
        if not to_process:
            print("[main] No posts available. Run --stage crawl first.")
            return
        for post in to_process:
            try:
                draft = run_draft(post, config)
                run_forge(draft, config)
            except Exception as e:
                print(f"[main] FAILED post {post['post_id']}: {e}")

    else:
        run_pipeline(config, count=args.count)

if __name__ == "__main__":
    main()
