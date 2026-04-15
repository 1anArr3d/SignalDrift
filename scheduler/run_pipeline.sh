#!/bin/bash
# SignalDrift — daily shorts pipeline
# Cron: 7am, 11am, 2pm, 6pm

cd /opt/signaldrift || exit 1

source venv/bin/activate

python main.py --stage forge --count 1 >> logs/pipeline.log 2>&1
