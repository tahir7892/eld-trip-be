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

install_systemd_service() {
  local app_dir="$1"
  local unit_src="${app_dir}/deploy/${SERVICE_NAME}.service"
  local unit_dst="/etc/systemd/system/${SERVICE_NAME}.service"

  if [[ ! -f "$unit_src" ]]; then
    return 1
  fi

  sed "s|__APP_DIR__|${app_dir}|g" "$unit_src" > "$unit_dst"
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
}

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

  if ! systemctl cat "${SERVICE_NAME}" &>/dev/null; then
    if install_systemd_service "$app_dir"; then
      echo "==> Installed systemd service ${SERVICE_NAME}"
    fi
  fi

  if systemctl cat "${SERVICE_NAME}" &>/dev/null; then
    systemctl restart "${SERVICE_NAME}"
    echo "==> Service status:"
    systemctl status "${SERVICE_NAME}" --no-pager -l || true
  else
    echo "Warning: systemd service '${SERVICE_NAME}' not found. Start gunicorn manually:"
    echo "  ${app_dir}/venv/bin/gunicorn --bind 0.0.0.0:8000 config.wsgi:application"
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
