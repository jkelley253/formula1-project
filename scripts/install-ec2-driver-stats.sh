#!/bin/bash
set -euo pipefail
umask 077
if [[ "$EUID" -ne 0 ]]; then
  echo 'Run with sudo bash scripts/install-ec2-driver-stats.sh' >&2
  exit 1
fi
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test -s /etc/formula1-postgres/password
systemd-analyze calendar 'Mon *-*-* 00:15:00 America/Los_Angeles' >/dev/null
docker exec formula1-postgres pg_isready -U postgres -d formula1
docker build -t formula1-driver-stats:local -f "$PROJECT_DIR/scripts/driver-stats/Dockerfile" "$PROJECT_DIR"
install -d -m 700 /etc/formula1-driver-stats /var/lib/formula1-driver-stats
docker run --rm --network host --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source=/etc/formula1-postgres/password,target=/run/secrets/admin-password,readonly \
  --mount type=bind,source=/etc/formula1-driver-stats,target=/config \
  --entrypoint python formula1-driver-stats:local /setup/setup_database.py
chmod 600 /etc/formula1-driver-stats/*.json
install -m 644 "$PROJECT_DIR/scripts/driver-stats/formula1-driver-stats.service" /etc/systemd/system/
install -m 644 "$PROJECT_DIR/scripts/driver-stats/formula1-driver-stats.timer" /etc/systemd/system/
install -m 755 "$PROJECT_DIR/scripts/driver-stats/run-sync.sh" /usr/local/bin/formula1-driver-stats
systemctl daemon-reload
echo 'Installed. Run: sudo formula1-driver-stats backfill --resume'
echo 'After verification: sudo systemctl enable --now formula1-driver-stats.timer'
