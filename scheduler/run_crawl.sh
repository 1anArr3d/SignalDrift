#!/bin/bash
# SignalDrift — crawl to refill queue
# Cron: 6am daily (runs before first forge)

cd /opt/signaldrift || exit 1

source venv/bin/activate

torsocks python main.py --stage crawl >> logs/pipeline.log 2>&1
