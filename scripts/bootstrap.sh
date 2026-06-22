#!/usr/bin/env sh
# Bootstrap a NowLens environment: apply migrations, create the Qdrant
# collection, and (optionally) seed demo data.
#
# Usage:
#   ./scripts/bootstrap.sh           # migrate + bootstrap Qdrant
#   ./scripts/bootstrap.sh --demo    # also run scripts/seed_demo.py
#
# Honors the standard NOWLENS_* environment variables (or a local .env loaded
# by the application). Run from the repository root.

set -eu

DEMO=0
if [ "${1:-}" = "--demo" ]; then
  DEMO=1
fi

echo "==> Applying database migrations (alembic upgrade head)"
alembic upgrade head

echo "==> Ensuring the Qdrant collection exists (nowlens bootstrap)"
nowlens bootstrap

if [ "$DEMO" -eq 1 ]; then
  echo "==> Seeding demo data (scripts/seed_demo.py)"
  python scripts/seed_demo.py
fi

echo "==> Done. Try:  nowlens ask \"How do I model incidents in ITSM?\""
