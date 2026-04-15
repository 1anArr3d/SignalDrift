"""
schedule.py — local scheduler for SignalDrift

Replaces cron when running on your PC instead of a server.
Uploads go out from your residential IP automatically.

Usage:
    python scheduler/schedule.py

Keep this running in a terminal. Ctrl+C to stop.
"""

import random
import subprocess
import sys
import time
from pathlib import Path

import schedule

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list):
    print(f"\n[scheduler] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(ROOT))


def run_crawl():
    _run([sys.executable, "main.py", "--stage", "crawl"])


def run_pipeline():
    # Random 1–10 min jitter so uploads don't look perfectly scheduled
    time.sleep(random.randint(60, 600))
    _run([sys.executable, "main.py", "--stage", "forge", "--count", "1"])


def run_compilation():
    _run([sys.executable, "compile.py"])


# All times are your local system time (CST)
schedule.every().day.at("06:00").do(run_crawl)
schedule.every().day.at("07:00").do(run_pipeline)
schedule.every().day.at("12:00").do(run_pipeline)
schedule.every().day.at("17:00").do(run_pipeline)
schedule.every().day.at("20:00").do(run_pipeline)
schedule.every().day.at("22:00").do(run_compilation)

if __name__ == "__main__":
    print("[scheduler] SignalDrift local scheduler running.")
    print("[scheduler] Uploads use your residential IP.")
    print("[scheduler] Ctrl+C to stop.\n")
    while True:
        schedule.run_pending()
        time.sleep(30)
