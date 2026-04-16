"""
dashboard/app.py — SignalDrift Desktop Dashboard

Native Qt window. No browser, no localhost.

Usage:
    python dashboard/app.py
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
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMenu, QSystemTrayIcon,
    QTextEdit, QVBoxLayout, QWidget,
)

ROOT = Path(__file__).resolve().parent.parent
# When frozen by PyInstaller, __file__ is in a temp dir — use the exe's location instead
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent.parent
LOG_BUFFER: collections.deque = collections.deque(maxlen=200)
LAST_RUNS: dict = {}
JOB_STATUS: dict = {}

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
DARK_BG  = "#0a0a0f"
CARD_BG  = "#13131f"
BORDER   = "#1f1f35"
TEXT     = "#e0e0e0"
MUTED    = "#6b7280"
ACCENT   = "#6366f1"
GREEN    = "#4ade80"
BLUE     = "#60a5fa"
RED      = "#f87171"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT};
    font-family: 'Courier New';
}}
QLabel {{ color: {TEXT}; background: transparent; }}
QTextEdit {{
    background-color: {CARD_BG};
    color: #9ca3af;
    border: 1px solid {BORDER};
    border-radius: 8px;
    font-family: 'Courier New';
    font-size: 11px;
    padding: 8px;
}}
QScrollBar:vertical {{
    background: {CARD_BG}; width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; }}
QMenu {{
    background-color: {CARD_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{ background-color: {ACCENT}; }}
"""

# ---------------------------------------------------------------------------
# Scheduler jobs
# ---------------------------------------------------------------------------

def _log(line: str):
    ts = datetime.now().strftime("%H:%M:%S")
    LOG_BUFFER.append(f"[{ts}] {line}")
    print(line)


def _run(cmd: list, job_name: str):
    JOB_STATUS[job_name] = "running"
    LAST_RUNS[job_name] = datetime.now()
    _log(f"[scheduler] Starting {job_name}...")
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        for line in (result.stdout + result.stderr).splitlines():
            _log(line)
        JOB_STATUS[job_name] = "failed" if result.returncode != 0 else "ok"
    except Exception as e:
        _log(f"[scheduler] ERROR: {e}")
        JOB_STATUS[job_name] = "failed"


def run_crawl():
    threading.Thread(
        target=_run,
        args=([sys.executable, str(ROOT / "main.py"), "--stage", "crawl"], "run_crawl"),
        daemon=True,
    ).start()


def run_pipeline():
    def _job():
        time.sleep(random.randint(60, 600))
        _run([sys.executable, str(ROOT / "main.py"), "--stage", "forge", "--count", "1"], "run_pipeline")
    threading.Thread(target=_job, daemon=True).start()


def run_compilation():
    threading.Thread(
        target=_run,
        args=([sys.executable, str(ROOT / "compile.py")], "run_compilation"),
        daemon=True,
    ).start()


schedule.every().day.at("06:00").do(run_crawl)
schedule.every().day.at("07:00").do(run_pipeline)
schedule.every().day.at("12:00").do(run_pipeline)
schedule.every().day.at("17:00").do(run_pipeline)
schedule.every().day.at("20:00").do(run_pipeline)
schedule.every().day.at("22:00").do(run_compilation)


def _scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(30)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _card() -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        f"background-color: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px;"
    )
    return frame


def _label(text: str, size: int = 13, color: str = TEXT, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    font = QFont("Courier New", size)
    font.setBold(bold)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return lbl


BADGE_COLORS = {
    "ok":      (GREEN, "#14532d"),
    "running": (BLUE,  "#1c3a5e"),
    "failed":  (RED,   "#4c1d1d"),
    "idle":    (MUTED, BORDER),
}


def _badge_style(status: str) -> str:
    fg, bg = BADGE_COLORS.get(status, (MUTED, BORDER))
    return (
        f"color: {fg}; background-color: {bg}; border-radius: 4px; "
        f"padding: 2px 6px; font-size: 11px; border: none;"
    )


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"border: none; border-top: 1px solid {BORDER};")
    return line


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

JOB_DEFS = [
    ("run_crawl",       "Crawl",       "06:00 AM"),
    ("run_pipeline",    "Pipeline",    "07:00 AM"),
    ("run_pipeline",    "Pipeline",    "12:00 PM"),
    ("run_pipeline",    "Pipeline",    "05:00 PM"),
    ("run_pipeline",    "Pipeline",    "08:00 PM"),
    ("run_compilation", "Compilation", "10:00 PM"),
]


class SignalDriftWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SignalDrift")
        self.setMinimumSize(560, 720)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.addWidget(_label("SignalDrift", 18, "#ffffff", bold=True))
        self._time_lbl = _label("", 10, MUTED)
        header.addStretch()
        header.addWidget(self._time_lbl)
        root_layout.addLayout(header)

        # Stats
        stats_grid = QGridLayout()
        stats_grid.setSpacing(12)
        stats_grid.setColumnStretch(0, 1)
        stats_grid.setColumnStretch(1, 1)

        pool_card = _card()
        pl = QVBoxLayout(pool_card)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.addWidget(_label("POOL", 8, MUTED))
        self._pool_stat = _label("—", 28, "#ffffff", bold=True)
        pl.addWidget(self._pool_stat)
        pl.addWidget(_label("background clips ready", 9, MUTED))
        stats_grid.addWidget(pool_card, 0, 0)

        rendered_card = _card()
        rl = QVBoxLayout(rendered_card)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.addWidget(_label("PENDING COMPILATION", 8, MUTED))
        self._rendered_stat = _label("—", 28, "#ffffff", bold=True)
        rl.addWidget(self._rendered_stat)
        rl.addWidget(_label("shorts in output/rendered", 9, MUTED))
        stats_grid.addWidget(rendered_card, 0, 1)

        root_layout.addLayout(stats_grid)

        # Jobs card
        jobs_card = _card()
        jl = QVBoxLayout(jobs_card)
        jl.setContentsMargins(16, 14, 16, 14)
        jl.setSpacing(0)
        jl.addWidget(_label("JOBS", 8, MUTED))
        jl.addSpacing(10)

        self._job_rows: list[tuple[str, QLabel, QLabel]] = []
        for i, (fn_name, display, sched_time) in enumerate(JOB_DEFS):
            row = QHBoxLayout()
            row.setSpacing(8)

            left = QVBoxLayout()
            left.setSpacing(2)
            left.addWidget(_label(display, 11))
            left.addWidget(_label(f"next: {sched_time}", 9, MUTED))

            badge = QLabel("idle")
            badge.setFixedWidth(64)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(_badge_style("idle"))

            last_lbl = _label("never", 9, MUTED)
            last_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row.addLayout(left)
            row.addStretch()
            row.addWidget(badge)
            row.addWidget(last_lbl)

            self._job_rows.append((fn_name, badge, last_lbl))
            jl.addLayout(row)
            if i < len(JOB_DEFS) - 1:
                jl.addSpacing(4)
                jl.addWidget(_divider())
                jl.addSpacing(4)

        root_layout.addWidget(jobs_card)

        # Logs card
        logs_card = _card()
        ll = QVBoxLayout(logs_card)
        ll.setContentsMargins(16, 14, 16, 14)
        ll.addWidget(_label("RECENT LOGS", 8, MUTED))
        ll.addSpacing(6)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMinimumHeight(200)
        ll.addWidget(self._log_view)
        root_layout.addWidget(logs_card)

        # Tray + timer
        self._setup_tray()
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(10_000)
        self._refresh()

    # ------------------------------------------------------------------
    def _setup_tray(self):
        px = QPixmap(32, 32)
        px.fill(QColor(0, 0, 0, 0))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(99, 102, 241))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.end()

        self._tray = QSystemTrayIcon(QIcon(px), self)
        self._tray.setToolTip("SignalDrift")

        menu = QMenu()
        open_act = QAction("Open Dashboard", self)
        open_act.triggered.connect(self._show_window)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(open_act)
        menu.addSeparator()
        menu.addAction(quit_act)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda r: self._show_window()
            if r == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self._tray.show()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "SignalDrift",
            "Still running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ------------------------------------------------------------------
    def _refresh(self):
        self._time_lbl.setText(datetime.now().strftime("%b %d  %I:%M %p"))

        pool = len(glob.glob(str(ROOT / "slicer/background_pool/**/*.mp4"), recursive=True))
        rendered = len(glob.glob(str(ROOT / "output/rendered/*.mp4")))
        self._pool_stat.setText(str(pool))
        self._rendered_stat.setText(str(rendered))

        for fn_name, badge, last_lbl in self._job_rows:
            status = JOB_STATUS.get(fn_name, "idle")
            last = LAST_RUNS.get(fn_name)
            badge.setText(status)
            badge.setStyleSheet(_badge_style(status))
            last_lbl.setText(last.strftime("%I:%M %p") if last else "never")

        logs = list(LOG_BUFFER)
        html_lines = []
        for line in logs:
            lo = line.lower()
            if "===" in line:
                color = BLUE
            elif any(w in lo for w in ("done", "complete", "uploaded", "ok")):
                color = GREEN
            elif any(w in lo for w in ("fail", "error")):
                color = RED
            else:
                color = "#9ca3af"
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(f'<span style="color:{color};">{escaped}</span>')

        self._log_view.setHtml(
            f'<div style="font-family:\'Courier New\'; font-size:11px; background:{CARD_BG};">'
            + "<br>".join(html_lines)
            + "</div>"
        )
        sb = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    _log(f"[dashboard] ROOT = {ROOT}")
    _log("[dashboard] SignalDrift started.")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = SignalDriftWindow()
    window.show()
    sys.exit(app.exec())
