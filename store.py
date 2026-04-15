"""
store.py — SQLite persistence layer.
Replaces seen_posts.json, classified_posts.json, output/queue/*.json, sunset_posts.json.

Status values:
  queued   — passed scoring, waiting to draft+forge
  drafted  — draft complete, ready to forge
  used     — forged and uploaded
  rejected — failed scoring
"""
import sqlite3
from pathlib import Path

_DB_PATH = "output/signaldrift.db"


def _conn() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id         TEXT PRIMARY KEY,
                subreddit       TEXT,
                title           TEXT,
                body            TEXT,
                upvote_ratio    REAL,
                created_utc     INTEGER,
                narrator_gender TEXT,
                script          TEXT,
                card_title      TEXT,
                status          TEXT DEFAULT 'queued',
                used_at         TEXT
            )
        """)


def get_all_known_ids() -> set:
    with _conn() as c:
        rows = c.execute("SELECT post_id FROM posts").fetchall()
    return {r["post_id"] for r in rows}


def insert_queued(posts: list) -> None:
    """Insert scored/passed posts. Skips duplicates."""
    with _conn() as c:
        for p in posts:
            score = p.get("score", {})
            c.execute("""
                INSERT OR IGNORE INTO posts
                (post_id, subreddit, title, body, upvote_ratio, created_utc, narrator_gender, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
            """, (
                p["post_id"], p["subreddit"], p["title"], p["body"],
                p.get("upvote_ratio"), p.get("created_utc"),
                score.get("narrator_gender", "neutral"),
            ))


def insert_rejected(posts: list) -> None:
    """Store only the ID — enough to prevent re-processing."""
    with _conn() as c:
        for p in posts:
            c.execute(
                "INSERT OR IGNORE INTO posts (post_id, status) VALUES (?, 'rejected')",
                (p["post_id"],)
            )


def get_queued() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM posts WHERE status IN ('queued', 'drafted') ORDER BY rowid ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def save_draft(post_id: str, script: str, card_title: str) -> None:
    with _conn() as c:
        c.execute("""
            UPDATE posts SET script=?, card_title=?, status='drafted'
            WHERE post_id=?
        """, (script, card_title, post_id))


def get_post(post_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM posts WHERE post_id=?", (post_id,)).fetchone()
    return dict(row) if row else None



def mark_used(post_id: str, used_at: str) -> None:
    with _conn() as c:
        c.execute("""
            UPDATE posts SET status='used', used_at=?
            WHERE post_id=?
        """, (used_at, post_id))
