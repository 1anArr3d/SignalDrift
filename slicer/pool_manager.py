import os
import glob
import random
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

SLICER_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_FOLDER = os.path.join(SLICER_DIR, "background_pool")


class PoolEmptyError(Exception):
    pass


def _clip_count() -> int:
    return len(glob.glob(os.path.join(POOL_FOLDER, "**", "chunk_*.mp4"), recursive=True))


def _send_low_pool_alert(count: int, threshold: int):
    """Send email alert when pool is low. Requires ALERT_EMAIL_* vars in .env."""
    smtp_host = os.getenv("ALERT_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("ALERT_SMTP_PORT", "587"))
    smtp_user = os.getenv("ALERT_SMTP_USER", "")
    smtp_pass = os.getenv("ALERT_SMTP_PASS", "")
    to_addr   = os.getenv("ALERT_EMAIL_TO", smtp_user)

    if not smtp_user or not smtp_pass:
        print("[pool] Email alert skipped — ALERT_SMTP_USER / ALERT_SMTP_PASS not set.")
        return

    msg = MIMEText(
        f"SignalDrift background pool is low: {count} clips remaining (threshold: {threshold}).\n\n"
        f"Add footage to slicer/input/ and run:\n"
        f"  python slicer/silcer_mvp.py\n\n"
        f"Or scp .mp4 files directly into slicer/background_pool/"
    )
    msg["Subject"] = f"[SignalDrift] Background pool low ({count} clips)"
    msg["From"] = smtp_user
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"[pool] Alert sent to {to_addr}")
    except Exception as e:
        print(f"[pool] Alert email failed: {e}")


def _replenish(config: dict):
    """Download next video from queue, slice it into the pool."""
    from slicer.fetch import fetch_next
    from slicer.silcer_mvp import run as slice_run

    print("[pool] Replenishing from URL queue...")
    success = fetch_next(config)
    if success:
        slice_run(config)
        print(f"[pool] Replenished. Pool now has {_clip_count()} clips.")
    else:
        print("[pool] Replenish failed — queue empty or no session. Sending alert...")
        _send_low_pool_alert(_clip_count(), config.get("slicer", {}).get("replenish_threshold", 10) if config else 10)


def get_random_clip(config: dict = None) -> str:
    """Return a random clip. Auto-replenishes from URL queue if pool is below threshold."""
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
