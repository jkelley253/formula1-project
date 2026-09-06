#!/bin/bash
set -euo pipefail
exec docker run --rm --network host --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source=/etc/formula1-driver-stats/database.json,target=/run/secrets/database.json,readonly \
  --mount type=bind,source=/var/lib/formula1-driver-stats,target=/state \
  formula1-driver-stats:local "$@"
