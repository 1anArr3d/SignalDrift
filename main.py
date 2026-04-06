"""
main.py
SignalDrift pipeline orchestrator.

Runs the full pipeline end to end for one farm:
  crawl -> sense -> draft -> forge -> output

Each stage can be run independently for debugging by passing --stage.

Usage:
  python main.py                        # full pipeline
  python main.py --stage crawl          # crawl only
  python main.py --stage sense          # sense only (uses cached crawl output)
  python main.py --stage draft          # draft only (uses cached sense output)
  python main.py --stage forge          # forge only (uses cached draft output)
  python main.py --post-id <id>         # run draft+forge for a single post ID
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Stage imports
from crawl import reddit_crawler, cleaner, comment_extractor
from sense import chunker, embedder
from draft import context_builder, stance_agent, script_agent, title_generator
from forge import tts


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _save_json(data, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Stage: crawl
# ---------------------------------------------------------------------------

def run_crawl(config: dict) -> list[dict]:
    print("\n=== STAGE: crawl ===")
    raw_posts = reddit_crawler.run(config)
    cleaned_posts = cleaner.run(raw_posts)
    classified_posts = comment_extractor.run(cleaned_posts)

    _save_json(classified_posts, "output/classified_posts.json")
    print(f"[main] Crawl complete. {len(classified_posts)} posts saved.")
    return classified_posts


# ---------------------------------------------------------------------------
# Stage: sense
# ---------------------------------------------------------------------------

def run_sense(classified_posts: list[dict], config: dict) -> None:
    print("\n=== STAGE: sense ===")
    chunks = chunker.run(classified_posts, config)
    embedder.run(chunks, config)
    print("[main] Sense complete. Chunks embedded into Qdrant.")


# ---------------------------------------------------------------------------
# Stage: draft (single post)
# ---------------------------------------------------------------------------

def run_draft(post: dict, config: dict) -> dict:
    print(f"\n=== STAGE: draft [{post['post_id']}] ===")

    ctx = context_builder.run(post, config)
    stance = stance_agent.run(ctx, config)
    script_result = script_agent.run(ctx, stance, config)
    titles = title_generator.run(script_result["script"], ctx, config)

    draft_output = {
        "post_id": post["post_id"],
        "subreddit": post["subreddit"],
        "context": ctx,
        "stance": stance,
        "script": script_result["script"],
        "titles": titles["titles"],
    }

    queue_path = f"output/queue/{post['post_id']}.json"
    _save_json(draft_output, queue_path)
    print(f"[main] Draft saved to queue: {queue_path}")
    return draft_output


# ---------------------------------------------------------------------------
# Stage: forge (single draft)
# ---------------------------------------------------------------------------

def run_forge(draft: dict, config: dict) -> str:
    print(f"\n=== STAGE: forge [{draft['post_id']}] ===")

    post_id = draft["post_id"]
    script = draft["script"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path = f"output/rendered/{post_id}_{timestamp}.mp3"

    tts_result = tts.run(script, audio_path, config)
    print(f"[main] Audio complete: {tts_result['wav_path']}")
    return tts_result["wav_path"]


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(config: dict, limit: int = 5) -> None:
    """
    Run the full pipeline. Processes up to `limit` posts through draft+forge.
    limit defaults to the weekly target (5).
    """
    # Crawl
    classified_posts = run_crawl(config)
    if not classified_posts:
        print("[main] No qualifying posts found. Exiting.")
        return

    # Sense — index all posts into Qdrant
    run_sense(classified_posts, config)

    # Draft + Forge — pick top posts by engagement signal
    top_posts = sorted(
        classified_posts,
        key=lambda p: p["score"] * p["upvote_ratio"],
        reverse=True,
    )[:limit]

    rendered = []
    for post in top_posts:
        try:
            draft = run_draft(post, config)
            final_mp4 = run_forge(draft, config)
            rendered.append(final_mp4)
        except Exception as e:
            print(f"[main] ERROR processing post {post['post_id']}: {e}")
            continue

    print(f"\n=== PIPELINE COMPLETE ===")
    print(f"Rendered {len(rendered)} video(s):")
    for path in rendered:
        print(f"  {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SignalDrift pipeline")
    parser.add_argument(
        "--stage",
        choices=["crawl", "sense", "draft", "forge"],
        default=None,
        help="Run a single pipeline stage",
    )
    parser.add_argument(
        "--post-id",
        default=None,
        help="Run draft+forge for a single post ID from classified_posts.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max number of videos to produce per run (default: 5)",
    )
    parser.add_argument(
        "--draft-only",
        action="store_true",
        help="Run draft stage only — skip TTS and video rendering",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.post_id:
        posts = _load_json("output/classified_posts.json")
        match = next((p for p in posts if p["post_id"] == args.post_id), None)
        if not match:
            print(f"Post ID {args.post_id} not found in output/classified_posts.json")
            sys.exit(1)
        draft = run_draft(match, config)
        if not args.draft_only:
            run_forge(draft, config)
        return

    if args.stage == "crawl":
        run_crawl(config)

    elif args.stage == "sense":
        posts = _load_json("output/classified_posts.json")
        run_sense(posts, config)

    elif args.stage == "draft":
        posts = _load_json("output/classified_posts.json")
        for post in posts[:args.limit]:
            run_draft(post, config)

    elif args.stage == "forge":
        queue_dir = Path("output/queue")
        drafts = sorted(queue_dir.glob("*.json"))[:args.limit]
        for draft_path in drafts:
            draft = _load_json(str(draft_path))
            run_forge(draft, config)

    else:
        run_pipeline(config, limit=args.limit)


if __name__ == "__main__":
    main()
