#!/bin/bash
# EC2 user data for Amazon Linux 2023 x86_64, including reference AMI:
# al2023-ami-2023.12.20260831.0-kernel-6.18-x86_64
set -euo pipefail
umask 077
trap 'echo "PostgreSQL bootstrap failed at line ${LINENO}" >&2' ERR

POSTGRES_IMAGE='postgres:18'
POSTGRES_DB='formula1'
CONTAINER_NAME='formula1-postgres'
VOLUME_NAME='formula1-postgres-data'
SECRET_DIR='/etc/formula1-postgres'
PASSWORD_FILE="${SECRET_DIR}/password"

if [[ "$EUID" -ne 0 ]]; then
  echo 'Run as root (EC2 user data runs as root automatically).' >&2
  exit 1
fi

dnf install -y docker openssl
systemctl enable --now docker

# Keep the same password on reruns; never print it in cloud-init logs.
install -d -m 700 "$SECRET_DIR"
if [[ ! -s "$PASSWORD_FILE" ]]; then
  openssl rand -hex 32 > "$PASSWORD_FILE"
fi
chmod 600 "$PASSWORD_FILE"

# Preserve an existing container and database when manually rerunning user data.
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  docker start "$CONTAINER_NAME"
else
  docker pull "$POSTGRES_IMAGE"
  docker volume create "$VOLUME_NAME"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --publish 0.0.0.0:5432:5432 \
    --env POSTGRES_DB="$POSTGRES_DB" \
    --env POSTGRES_USER=postgres \
    --env POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password \
    --env POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 \
    --mount "type=bind,source=${PASSWORD_FILE},target=/run/secrets/postgres-password,readonly" \
    --mount "type=volume,source=${VOLUME_NAME},target=/var/lib/postgresql" \
    --health-cmd='pg_isready -h 127.0.0.1 -U postgres -d "$POSTGRES_DB"' \
    --health-interval=10s \
    --health-timeout=5s \
    --health-retries=12 \
    --health-start-period=30s \
    --log-opt max-size=10m \
    --log-opt max-file=3 \
    "$POSTGRES_IMAGE" postgres -c 'listen_addresses=*'
fi

# TCP readiness avoids treating the temporary initialization server as ready.
for ((attempt = 1; attempt <= 60; attempt++)); do
  if docker exec "$CONTAINER_NAME" \
    pg_isready -h 127.0.0.1 -U postgres -d "$POSTGRES_DB" >/dev/null 2>&1; then
    echo 'PostgreSQL is ready on host port 5432. Database: formula1.'
    exit 0
  fi
  sleep 5
done

echo "PostgreSQL did not become ready. Inspect: docker logs ${CONTAINER_NAME}" >&2
exit 1
