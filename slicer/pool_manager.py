import os
import glob
import random

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")


class PoolEmptyError(Exception):
    pass


def get_random_clip() -> str:
    """Return a random chunk from background_pool/. Raises PoolEmptyError if empty."""
    clips = glob.glob(os.path.join(POOL_FOLDER, "**", "chunk_*.mp4"), recursive=True)
    if not clips:
        raise PoolEmptyError(
            "[pool] No clips found in background_pool/. "
            "Drop footage in slicer/input/ and run: python slicer/silcer_mvp.py"
        )
    return random.choice(clips)


def consume_clip(clip_path: str):
    """Delete a clip after it has been successfully used in a render."""
    if os.path.exists(clip_path):
        os.remove(clip_path)
        print(f"[pool] Consumed: {os.path.basename(clip_path)}")
