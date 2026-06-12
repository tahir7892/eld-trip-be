#!/usr/bin/env bash
#
# Deploy the Django backend.
#
# On the server (after git pull):
#   cd /opt/eld-trip-be && ./deploy.sh
#
# From your Mac (push code via rsync):
#   Set DEPLOY_HOST below, then ./deploy.sh
#
set -euo pipefail

# --- Remote deploy config (only needed when running from your Mac) ---
DEPLOY_HOST=""                          # droplet IP or SSH host alias
DEPLOY_USER="root"
DEPLOY_PATH="/opt/eld-trip-be"
SSH_KEY=""                              # leave empty to use your default SSH key
SERVICE_NAME="eld-trip-be"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

deploy_on_server() {
  local app_dir="$1"
  cd "$app_dir"

  echo "==> Deploying in ${app_dir}"

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
    systemctl restart "${SERVICE_NAME}"
  elif systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    systemctl start "${SERVICE_NAME}"
  else
    echo "Warning: systemd service '${SERVICE_NAME}' not found. Start gunicorn manually."
  fi

  echo "==> Deploy complete"
}

# On-server: git pull already updated the code; just install, migrate, restart.
if [[ -z "$DEPLOY_HOST" || "${1:-}" == "--local" ]]; then
  deploy_on_server "$SCRIPT_DIR"
  exit 0
fi

# From Mac: rsync code to the droplet, then run server steps over SSH.
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
  "$SCRIPT_DIR/" "${REMOTE}:${DEPLOY_PATH}/"

echo "==> Running deploy on server"
ssh "${SSH_ARGS[@]}" "$REMOTE" "cd ${DEPLOY_PATH} && ./deploy.sh --local"

echo "==> Remote deploy complete: ${REMOTE}:${DEPLOY_PATH}"
