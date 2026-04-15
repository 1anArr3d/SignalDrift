import os
import glob
import random
import sys
from pathlib import Path

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")


class PoolEmptyError(Exception):
    pass


def _clip_count() -> int:
    return len(glob.glob(os.path.join(POOL_FOLDER, "**", "chunk_*.mp4"), recursive=True))


def _replenish(config: dict):
    """Download a new video and slice it into the pool."""
    import random as _random
    from slicer.fetch import fetch
    from slicer.silcer_mvp import run as slice_run

    queries = config.get("slicer", {}).get("search_queries", ["satisfying compilation"])
    query = _random.choice(queries)
    print(f"[pool] Pool low — fetching: \"{query}\"")

    success = fetch(query, is_search=True)
    if success:
        slice_run(config)
        print(f"[pool] Replenished. Pool now has {_clip_count()} clips.")
    else:
        print("[pool] Replenish failed — no new videos found.")


def get_random_clip(config: dict = None) -> str:
    """Return a random clip. Auto-replenishes if pool is below threshold."""
    if config:
        threshold = config.get("slicer", {}).get("replenish_threshold", 10)
        count = _clip_count()
        if count < threshold:
            print(f"[pool] {count} clips remaining (threshold: {threshold}) — replenishing...")
            _replenish(config)

    clips = glob.glob(os.path.join(POOL_FOLDER, "**", "chunk_*.mp4"), recursive=True)
    if not clips:
        raise PoolEmptyError(
            "[pool] No clips in background_pool/ and replenish failed. "
            "Drop footage in slicer/input/ and run: python slicer/silcer_mvp.py"
        )
    return random.choice(clips)


def consume_clip(clip_path: str):
    """Delete a clip after it has been used in a render."""
    if os.path.exists(clip_path):
        os.remove(clip_path)
        print(f"[pool] Consumed: {os.path.basename(clip_path)}")
