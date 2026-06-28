#!/usr/bin/env bash
set -euo pipefail
cd /opt/skladbase
sudo -u skladbase git pull --ff-only
sudo -u skladbase venv/bin/pip install -q -r requirements.txt asyncpg
sudo -u skladbase bash -c 'cd frontend/app && npm ci && npm run build'
sudo -u skladbase venv/bin/alembic upgrade head
sudo systemctl restart skladbase-web skladbase-scheduler
