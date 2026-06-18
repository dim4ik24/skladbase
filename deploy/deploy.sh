#!/usr/bin/env bash
set -euo pipefail

cd /opt/skladbase

git pull --ff-only

venv/bin/pip install -q -r requirements.txt asyncpg

(cd frontend/app && npm ci && npm run build)

venv/bin/alembic upgrade head

sudo systemctl restart skladbase-web skladbase-scheduler
