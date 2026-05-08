#!/bin/bash
# Auto-deploy: pull latest from GitHub, reinstall deps if needed, restart services.
# Triggered every 5 minutes by subway-deploy.timer (see install-services.sh).
# Safe to run manually: idempotent, exits 0 if already up to date.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Allow root to operate on the user-owned repo without git's "dubious ownership" warning.
git config --global --add safe.directory "$PROJECT_DIR" >/dev/null 2>&1 || true

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch --quiet origin "$BRANCH"

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
    exit 0
fi

echo "Updating $BRANCH: ${LOCAL_HEAD:0:7} -> ${REMOTE_HEAD:0:7}"

CHANGED_FILES="$(git diff --name-only "$LOCAL_HEAD" "$REMOTE_HEAD")"
echo "Changed files:"
echo "$CHANGED_FILES" | sed 's/^/  /'

# Refuse to clobber local edits (e.g. someone hand-edited config.json on the Pi).
git pull --ff-only origin "$BRANCH"

if echo "$CHANGED_FILES" | grep -qE '^server/(package\.json|package-lock\.json)$'; then
    echo "Server deps changed, running npm install..."
    (cd server && npm install --omit=dev)
fi

if echo "$CHANGED_FILES" | grep -qE '^display/requirements\.txt$'; then
    echo "Python deps changed, running pip install..."
    (cd display && pip3 install -r requirements.txt)
fi

# Restart only when code or config changed (skip for README / docs-only updates).
if echo "$CHANGED_FILES" | grep -qE '^(server/|display/|config\.json$)'; then
    echo "Restarting services..."
    systemctl restart subway-server subway-display
else
    echo "No service-affecting files changed, skipping restart"
fi

echo "Deploy complete: ${REMOTE_HEAD:0:7}"
