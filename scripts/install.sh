#!/usr/bin/env bash
set -eu
cd /workspace/Cheng-Future-Value
python -m venv .venv
.venv/bin/python -m pip install --requirement requirements.lock
.venv/bin/python -m pip install --no-deps -e .
mkdir -p data/raw data/processed data/logs
# Preserve the current investigation's request budget in a fresh checkout.
if [ ! -f data/logs/requests.jsonl ]; then
    cp reports/evidence/requests.jsonl data/logs/requests.jsonl
fi
.venv/bin/python -m pip check
