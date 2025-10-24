#!/usr/bin/env bash
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp -n .env.example .env || true
echo "Edit .env to add your TELEGRAM_BOT_TOKEN, then run:"
echo "source .venv/bin/activate && python bot.py"
