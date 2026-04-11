"""
rescore.py

Re-scores all posts in classified_posts.json using the current scorer.
Run this once after adding new fields to the scorer prompt.

Usage:
    python rescore.py
"""

import json
from pathlib import Path
from crawl.scorer import score_post

CLASSIFIED = Path("output/classified_posts.json")
SUNSET = Path("output/sunset_posts.json")


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    posts = _load_json(CLASSIFIED)
    print(f"[rescore] {len(posts)} posts to re-score...")

    passed, failed = [], []
    for i, post in enumerate(posts, 1):
        print(f"  [{i}/{len(posts)}]", end=" ")
        scored = score_post(post)
        if scored["score"].get("verdict") == "pass":
            passed.append(scored)
        else:
            failed.append(scored)

    _save_json(passed, CLASSIFIED)
    print(f"\n[rescore] Done. {len(passed)} passed / {len(failed)} failed this re-score.")

    if failed:
        # Append newly failed posts to sunset
        archive = _load_json(SUNSET) if SUNSET.exists() else []
        archive.extend(failed)
        _save_json(archive, SUNSET)
        print(f"[rescore] {len(failed)} posts moved to sunset_posts.json.")


if __name__ == "__main__":
    main()
