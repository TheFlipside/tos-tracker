#!/usr/bin/env bash
set -euo pipefail

# Fetch TOS/privacy pages, commit changes, and push.
# Designed for unattended cron execution.
#
# Usage: ./update.sh
# Cron:  0 6 * * * /home/max/Projects/tos-tracker/update.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

TIMESTAMP="$(date -u '+%Y-%m-%d %H:%M UTC')"

echo "=== TOS Tracker update: ${TIMESTAMP} ==="

python3 fetch.py || true

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "No changes detected."
    exit 0
fi

git add pages/
git commit -m "Update: ${TIMESTAMP}"

if git remote | grep -q .; then
    git push
    echo "Pushed to remote."
else
    echo "No remote configured, skipping push."
fi

echo "Done."
