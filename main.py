import argparse
import time
from datetime import datetime
from pathlib import Path
import yaml

# Stage imports
from crawl import reddit_crawler
from crawl.scorer import score_batch
from draft import script_agent
from forge import tts, composer
from slicer.pool_manager import get_random_clip, consume_clip, PoolEmptyError
from publish import youtube_uploader, drive_uploader
import store

def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Stage: crawl
# ---------------------------------------------------------------------------
def run_crawl(config: dict) -> list[dict]:
    print("\n=== STAGE: crawl ===")
    raw_posts = reddit_crawler.run(config)

    seen_ids = store.get_all_known_ids()
    fresh_posts = [p for p in raw_posts if p["post_id"] not in seen_ids]
    skipped = len(raw_posts) - len(fresh_posts)
    if skipped:
        print(f"[main] Skipped {skipped} already-seen posts.")

    passed, failed = score_batch(fresh_posts, config=config)

    if failed:
        store.insert_rejected(failed)
        print(f"[main] {len(failed)} posts failed scoring → rejected.")

    store.insert_queued(passed)
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
    store.save_draft(
        post["post_id"],
        script=script_result["script"],
        card_title=script_result.get("card_title", ""),
    )

    return {
        "post_id": post["post_id"],
        "subreddit": post["subreddit"],
        "title": post["title"],
        "body": post.get("body", ""),
        "script": script_result["script"],
        "card_title": script_result.get("card_title", ""),
        "narrator_gender": post.get("narrator_gender", "neutral"),
    }

# ---------------------------------------------------------------------------
# Stage: forge
# ---------------------------------------------------------------------------
def run_forge(draft: dict, config: dict) -> str:
    start_time = time.time()
    print(f"\n=== STAGE: forge [{draft['post_id']}] ===")

    post_id = draft["post_id"]
    audio_path = str(Path(f"output/rendered/{post_id}.wav"))
    video_path = str(Path(f"output/rendered/{post_id}.mp4"))

    try:
        bg_path = get_random_clip(config)
    except PoolEmptyError as e:
        print(f"[main] {e}")
        raise

    narrator_gender = draft.get("narrator_gender", "neutral")
    print(f"[main] Narrator gender: {narrator_gender}")

    card_title = draft.get("card_title") or draft["title"]
    full_tts_text = card_title + " " + draft["script"]

    try:
        tts_result = tts.run(full_tts_text, audio_path, config, narrator_gender=narrator_gender)
    except Exception as e:
        print(f"[main] TTS Error: {e}")
        raise

    post_info = {
        "title": draft["title"],
        "subreddit": draft["subreddit"],
        "hook": card_title,
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
    Path(audio_path).unlink(missing_ok=True)

    print(f"[main] Video complete: {video_path} ({time.time()-start_time:.1f}s)")

    description = (
        f"{card_title}\n\n"
        "#aita #aitah #amitheassholeforreal #amitheasshole #redditstories #reddit #redditdrama "
        "#storytime #storytelling #truestory #firstperson #confession #drama #relationships "
        "#relationship #relationshipadvice #family #familydrama #toxic #revenge #pettythings "
        "#fyp #foryou #foryoupage #viral #trending #shorts #shortsviral #youtubeshorts"
    )
    tags = [
        "aita", "aitah", "amitheasshole", "amitheassholeforreal",
        "reddit", "redditstories", "redditdrama", "askreddit",
        "storytime", "storytelling", "truestory", "confession", "firstperson",
        "drama", "relationships", "relationship", "relationshipadvice",
        "family", "familydrama", "toxic", "revenge",
        "fyp", "foryou", "viral", "trending", "shorts", "youtubeshorts"
    ]
    youtube_uploader.upload(video_path, title=f"{card_title} #Shorts", description=description, tags=tags)

    drive_cfg = config.get("drive", {})
    if drive_cfg.get("enabled", False):
        try:
            drive_uploader.upload(
                video_path,
                filename=f"{post_id}.mp4",
                folder_id=drive_cfg.get("folder_id")
            )
        except Exception as e:
            print(f"[main] Drive upload failed (video still on YouTube): {e}")

    store.mark_used(post_id, used_at=datetime.now().isoformat())

    Path(video_path).unlink(missing_ok=True)
    print(f"[main] Cleaned up {video_path}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["crawl", "forge"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--post-id", help="Redraft/reforge a specific post by ID")
    parser.add_argument("--draft-only", action="store_true", help="Run draft stage only, skip forge")
    args = parser.parse_args()

    config = load_config(args.config)
    store.init()

    if args.post_id:
        post = store.get_post(args.post_id)
        if not post:
            print(f"[main] {args.post_id} not found in database.")
            return

        if post["status"] == "used":
            print(f"[main] Found {args.post_id} in archive — redrafting.")

        draft = run_draft(post, config)
        if not args.draft_only:
            run_forge(draft, config)
        else:
            print(f"[main] Draft saved for {args.post_id} — inspect before forging.")
        return

    if args.stage == "crawl":
        run_crawl(config)

    elif args.stage == "forge":
        posts = store.get_queued()
        to_process = posts[:args.count]
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
        run_crawl(config)
        posts = store.get_queued()
        to_process = posts[:args.count]
        if not to_process:
            print("[main] No new posts to process.")
            return
        for post in to_process:
            try:
                draft = run_draft(post, config)
                run_forge(draft, config)
            except Exception as e:
                print(f"[main] FAILED post {post['post_id']}: {e}")

if __name__ == "__main__":
    main()
