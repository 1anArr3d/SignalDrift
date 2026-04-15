"""
schedule.py — SignalDrift local scheduler + dashboard

Runs the pipeline on your PC and serves a status dashboard at http://localhost:5000

Usage:
    python scheduler/schedule.py

Ctrl+C to stop.
"""

import collections
import glob
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import schedule
from flask import Flask

ROOT = Path(__file__).resolve().parent.parent
LOG_BUFFER = collections.deque(maxlen=100)
LAST_RUNS = {}
JOB_STATUS = {}  # "ok" | "running" | "failed"

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>SignalDrift</title>
  <meta http-equiv="refresh" content="30">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Courier New', monospace; background: #0a0a0f; color: #e0e0e0; padding: 30px; }
    h1 { color: #fff; font-size: 1.6rem; margin-bottom: 4px; }
    .sub { color: #6b7280; font-size: 0.85rem; margin-bottom: 24px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
    .card { background: #13131f; border: 1px solid #1f1f35; border-radius: 10px; padding: 18px; }
    .card h2 { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
    .stat { font-size: 2rem; color: #fff; font-weight: bold; }
    .stat-label { font-size: 0.8rem; color: #6b7280; margin-top: 2px; }
    .job { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #1f1f35; }
    .job:last-child { border-bottom: none; }
    .job-name { font-size: 0.9rem; color: #e0e0e0; }
    .job-meta { font-size: 0.8rem; color: #6b7280; text-align: right; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
    .ok { background: #14532d; color: #4ade80; }
    .running { background: #1c3a5e; color: #60a5fa; }
    .failed { background: #4c1d1d; color: #f87171; }
    .idle { background: #1f1f35; color: #6b7280; }
    .logs { background: #13131f; border: 1px solid #1f1f35; border-radius: 10px; padding: 18px; }
    .logs h2 { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
    .log-line { font-size: 0.78rem; color: #9ca3af; padding: 2px 0; white-space: pre-wrap; word-break: break-all; }
    .log-line.stage { color: #60a5fa; }
    .log-line.done { color: #4ade80; }
    .log-line.err { color: #f87171; }
    .refresh { color: #374151; font-size: 0.75rem; margin-top: 16px; text-align: right; }
  </style>
</head>
<body>
  <h1>SignalDrift</h1>
  <div class="sub">Auto-refreshes every 30s &nbsp;·&nbsp; {{ now }}</div>

  <div class="grid">
    <div class="card">
      <h2>Pool</h2>
      <div class="stat">{{ pool }}</div>
      <div class="stat-label">background clips ready</div>
    </div>
    <div class="card">
      <h2>Pending Compilation</h2>
      <div class="stat">{{ rendered }}</div>
      <div class="stat-label">shorts in output/rendered</div>
    </div>
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>Jobs</h2>
    {% for job in jobs %}
    <div class="job">
      <div>
        <div class="job-name">{{ job.name }}</div>
        <div class="job-meta">next: {{ job.next }}</div>
      </div>
      <div style="text-align:right;">
        <span class="badge {{ job.status_class }}">{{ job.status }}</span>
        <div class="job-meta">{{ job.last }}</div>
      </div>
    </div>
    {% endfor %}
  </div>

  <div class="logs">
    <h2>Recent Logs</h2>
    {% for line in logs %}
    <div class="log-line {% if '===' in line %}stage{% elif 'Done' in line or 'complete' in line %}done{% elif 'FAIL' in line or 'Error' in line or 'ERROR' in line %}err{% endif %}">{{ line }}</div>
    {% endfor %}
  </div>

  <div class="refresh">Last loaded: {{ now }}</div>
</body>
</html>
"""


@app.route("/")
def dashboard():
    from flask import render_template_string

    pool = len(glob.glob(str(ROOT / "slicer/background_pool/**/*.mp4"), recursive=True))
    rendered = len(glob.glob(str(ROOT / "output/rendered/*.mp4")))

    jobs_data = []
    for job in schedule.jobs:
        name = getattr(job.job_func, "__name__", str(job.job_func))
        last_run = LAST_RUNS.get(name)
        status = JOB_STATUS.get(name, "idle")
        jobs_data.append({
            "name": name.replace("run_", "").replace("_", " ").title(),
            "next": job.next_run.strftime("%I:%M %p") if job.next_run else "—",
            "last": last_run.strftime("%I:%M %p") if last_run else "never",
            "status": status,
            "status_class": status,
        })

    return render_template_string(
        DASHBOARD_HTML,
        pool=pool,
        rendered=rendered,
        jobs=jobs_data,
        logs=list(reversed(list(LOG_BUFFER)))[:40],
        now=datetime.now().strftime("%b %d %I:%M %p"),
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def _run(cmd: list, job_name: str):
    JOB_STATUS[job_name] = "running"
    LAST_RUNS[job_name] = datetime.now()
    _log(f"[scheduler] Starting {job_name}...")
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT),
            capture_output=True, text=True
        )
        for line in (result.stdout + result.stderr).splitlines():
            _log(line)
        JOB_STATUS[job_name] = "failed" if result.returncode != 0 else "ok"
    except Exception as e:
        _log(f"[scheduler] ERROR: {e}")
        JOB_STATUS[job_name] = "failed"


def _log(line: str):
    LOG_BUFFER.append(line)
    print(line)


def run_crawl():
    _run([sys.executable, "main.py", "--stage", "crawl"], "run_crawl")


def run_pipeline():
    time.sleep(random.randint(60, 600))
    _run([sys.executable, "main.py", "--stage", "forge", "--count", "1"], "run_pipeline")


def run_compilation():
    _run([sys.executable, "compile.py"], "run_compilation")


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

schedule.every().day.at("06:00").do(run_crawl)
schedule.every().day.at("07:00").do(run_pipeline)
schedule.every().day.at("12:00").do(run_pipeline)
schedule.every().day.at("17:00").do(run_pipeline)
schedule.every().day.at("20:00").do(run_pipeline)
schedule.every().day.at("22:00").do(run_compilation)

if __name__ == "__main__":
    print("[scheduler] SignalDrift starting...")
    print("[scheduler] Dashboard → http://localhost:5000")
    print("[scheduler] Ctrl+C to stop.\n")

    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()

    while True:
        schedule.run_pending()
        time.sleep(30)
