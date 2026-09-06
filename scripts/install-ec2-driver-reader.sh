#!/bin/bash
# Prepare API-only credentials using the already-installed EC2 sync image.
set -euo pipefail
umask 077
if [[ "$EUID" -ne 0 ]]; then
  echo 'Run with sudo bash scripts/install-ec2-driver-reader.sh' >&2
  exit 1
fi
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test -s /etc/formula1-postgres/password
test -d /etc/formula1-driver-sync
docker image inspect formula1-driver-sync:local >/dev/null
docker run --rm --network host --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source=/etc/formula1-postgres/password,target=/run/secrets/admin-password,readonly \
  --mount type=bind,source=/etc/formula1-driver-sync,target=/config \
  --mount "type=bind,source=$PROJECT_DIR/scripts/ec2-sync/setup_reader.py,target=/setup_reader.py,readonly" \
  --entrypoint python formula1-driver-sync:local /setup_reader.py
chmod 600 /etc/formula1-driver-sync/reader.json
