"""
pool_manager.py

Manages the background clip rotation pool for SignalDrift.

Usage:
    from slicer.pool_manager import get_next_clip, consume_clip, pool_status

    clip_path = get_next_clip()          # get next clip in rotation
    ... render video using clip_path ...
    consume_clip(clip_path)              # delete clip after successful render
"""

import os
import json
import glob

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")
STATE_FILE = os.path.join(SLICER_DIR, "pool_state.json")
LOW_POOL_WARNING = 10


class PoolEmptyError(Exception):
    pass


# ── Internal helpers ──────────────────────────────────────────────────────────

def _scan_pool() -> dict:
    """Return {game_name: [sorted clip paths]} for all games with clips."""
    games = {}
    if not os.path.exists(POOL_FOLDER):
        return games
    for entry in sorted(os.listdir(POOL_FOLDER)):
        full = os.path.join(POOL_FOLDER, entry)
        if os.path.isdir(full):
            clips = sorted(glob.glob(os.path.join(full, "chunk_*.mp4")))
            if clips:
                games[entry] = clips
    return games


def _load_state() -> dict | None:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def init_pool() -> dict:
    """
    Scan background_pool/ and build pool_state.json.
    Preserves existing rotation order if state already exists.
    """
    games = _scan_pool()
    if not games:
        raise PoolEmptyError("No games found in background_pool/. Run the slicer first.")

    existing = _load_state()

    # Preserve existing rotation order, add new games at end, drop missing ones
    rotation = existing["rotation"] if existing else list(games.keys())
    rotation = [g for g in rotation if g in games]
    for g in games:
        if g not in rotation:
            rotation.append(g)

    current_index = existing.get("current_index", 0) if existing else 0
    if current_index >= len(rotation):
        current_index = 0

    state = {
        "rotation": rotation,
        "current_index": current_index,
        "counts": {g: len(clips) for g, clips in games.items()},
    }
    _save_state(state)
    return state


def preflight_check():
    """
    Call at the start of a batch run.
    Stops immediately if any game in the rotation has 0 clips.
    """
    games = _scan_pool()
    state = _load_state() or init_pool()

    for game in state["rotation"]:
        count = len(games.get(game, []))
        if count == 0:
            raise PoolEmptyError(
                f"[pool] STOPPED: '{game}' pool is empty before run started. "
                f"Drop more footage in slicer/input/ and re-run the slicer."
            )
        if count <= LOW_POOL_WARNING:
            print(f"[pool] WARNING: '{game}' is low ({count} clips). Refill soon.")


def get_next_clip() -> str:
    """
    Return the path to the next clip in rotation.
    Does NOT delete the clip — call consume_clip() after a successful render.
    Raises PoolEmptyError if the current game's pool is empty.
    """
    games = _scan_pool()
    state = _load_state() or init_pool()

    rotation = state["rotation"]
    idx = state["current_index"]
    game = rotation[idx]

    clips = games.get(game, [])
    if not clips:
        raise PoolEmptyError(
            f"[pool] STOPPED: '{game}' pool is empty. "
            f"Drop more footage in slicer/input/ and re-run the slicer."
        )

    if len(clips) <= LOW_POOL_WARNING:
        print(f"[pool] WARNING: '{game}' is low ({len(clips)} clips remaining).")

    # Advance rotation for the next call
    state["current_index"] = (idx + 1) % len(rotation)
    _save_state(state)

    return clips[0]


def consume_clip(clip_path: str):
    """
    Delete a clip after it has been successfully used in a render.
    Updates the pool count in state.
    """
    if os.path.exists(clip_path):
        os.remove(clip_path)

    # Update count for the game this clip belonged to
    game = os.path.basename(os.path.dirname(clip_path))
    state = _load_state()
    if state and game in state["counts"]:
        state["counts"][game] = max(0, state["counts"][game] - 1)
        _save_state(state)

    print(f"[pool] Consumed: {os.path.basename(clip_path)} ({game})")


def pool_status():
    """Print a summary of the current pool state."""
    games = _scan_pool()
    state = _load_state()

    if not state:
        print("[pool] No state file found. Run init_pool() or the slicer first.")
        return

    rotation = state["rotation"]
    idx = state["current_index"]
    print(f"\n[pool] Rotation ({len(rotation)} games):")
    for i, game in enumerate(rotation):
        count = len(games.get(game, []))
        marker = " ◀ next" if i == idx else ""
        status = "LOW" if count <= LOW_POOL_WARNING else "OK"
        print(f"  [{status}] {game}: {count} clips{marker}")
    print()


if __name__ == "__main__":
    pool_status()
