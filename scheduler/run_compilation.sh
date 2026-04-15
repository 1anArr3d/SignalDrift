#!/bin/bash
# SignalDrift — long-form compilation
# Runs daily, skips if fewer than 6 Shorts are ready

cd /opt/signaldrift || exit 1

source venv/bin/activate

python compile.py >> logs/compilation.log 2>&1
