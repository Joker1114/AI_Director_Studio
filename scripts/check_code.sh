#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/api"
python -m compileall -q app tests migrations
python -m pytest -q
python -m alembic -h >/dev/null
