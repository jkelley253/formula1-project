#!/bin/bash
# Run on the existing Amazon Linux 2023 EC2 server after uploading this project.
set -euo pipefail
umask 077
trap 'echo "Driver sync installation failed at line ${LINENO}; the weekly timer has not been enabled by this installer." >&2' ERR

if [[ "$EUID" -ne 0 ]]; then
  echo 'Run with sudo bash scripts/install-ec2-driver-sync.sh' >&2
  exit 1
fi
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for executable in docker systemctl systemd-analyze; do
  command -v "$executable" >/dev/null
done
test -s /etc/formula1-postgres/password
test -f /usr/share/zoneinfo/America/Los_Angeles
docker exec formula1-postgres pg_isready -h 127.0.0.1 -U postgres -d formula1
systemd-analyze calendar 'Mon *-*-* 00:01:00 America/Los_Angeles' >/dev/null

docker build --tag formula1-driver-sync:local --file "$PROJECT_DIR/scripts/ec2-sync/Dockerfile" "$PROJECT_DIR"
install -d -m 700 /etc/formula1-driver-sync
docker run --rm --network host --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source=/etc/formula1-postgres/password,target=/run/secrets/admin-password,readonly \
  --mount type=bind,source=/etc/formula1-driver-sync,target=/config \
  --entrypoint python formula1-driver-sync:local /setup/setup_database.py
chmod 600 /etc/formula1-driver-sync/database.json

install -m 644 "$PROJECT_DIR/scripts/ec2-sync/formula1-driver-sync.service" /etc/systemd/system/
install -m 644 "$PROJECT_DIR/scripts/ec2-sync/formula1-driver-sync.timer" /etc/systemd/system/
systemctl daemon-reload
echo 'Installed. Run a manual sync: sudo systemctl start formula1-driver-sync.service'
echo 'Inspect results: sudo journalctl -u formula1-driver-sync.service -n 30 --no-pager'
echo 'After verification, enable weekly runs: sudo systemctl enable --now formula1-driver-sync.timer'
