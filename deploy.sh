#!/usr/bin/env bash
#
# Deploy the Django backend to a DigitalOcean droplet.
#
# Edit the variables below, then run: ./deploy.sh
#
set -euo pipefail

# --- Server config (edit these) ---
DEPLOY_HOST=""                          # e.g. 164.92.x.x or api.yourdomain.com
DEPLOY_USER="root"
DEPLOY_PATH="/var/www/eld-trip-be"
SSH_KEY=""                              # leave empty to use your default SSH key
SERVICE_NAME="eld-trip-be"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -z "$DEPLOY_HOST" ]]; then
  echo "Error: Set DEPLOY_HOST at the top of deploy.sh before running."
  exit 1
fi

SSH_ARGS=()
RSYNC_SSH="ssh"
if [[ -n "$SSH_KEY" ]]; then
  SSH_ARGS=(-i "$SSH_KEY")
  RSYNC_SSH="ssh -i ${SSH_KEY}"
fi

RSYNC_EXCLUDES=(
  --exclude 'env/'
  --exclude 'venv/'
  --exclude '.git/'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude 'db.sqlite3'
)

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"

echo "==> Syncing code to ${REMOTE}:${DEPLOY_PATH}"
rsync -avz --delete -e "$RSYNC_SSH" "${RSYNC_EXCLUDES[@]}" \
  ./ "${REMOTE}:${DEPLOY_PATH}/"

echo "==> Installing dependencies and applying migrations"
ssh "${SSH_ARGS[@]}" "$REMOTE" bash -s <<EOF
set -euo pipefail
cd "${DEPLOY_PATH}"

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn

python manage.py migrate --noinput

if python manage.py help collectstatic &>/dev/null; then
  python manage.py collectstatic --noinput 2>/dev/null || true
fi

if systemctl is-active --quiet "${SERVICE_NAME}"; then
  sudo systemctl restart "${SERVICE_NAME}"
elif systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
  sudo systemctl start "${SERVICE_NAME}"
else
  echo "Warning: systemd service '${SERVICE_NAME}' not found. Start gunicorn manually."
fi
EOF

echo "==> Deploy complete: ${REMOTE}:${DEPLOY_PATH}"
