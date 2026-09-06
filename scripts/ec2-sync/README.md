# Run the driver sync on the existing EC2 server

This is the selected low-cost deployment: a short-lived Docker container on
the PostgreSQL EC2 server, started by systemd every Monday at **00:01
America/Los_Angeles**. A manual start uses the same service. No new Lambda,
NAT gateway, private endpoint, or Secrets Manager secret is required.

The EC2 server and its PostgreSQL container must remain running. Normal EC2,
disk, public-IP, and applicable data-transfer charges still apply. This job
adds a container image on disk and brief CPU/memory usage; it creates no new
hourly-billed AWS network resources.

## Deployment verified September 5, 2026

Installed on the existing EC2 host listed below. Two live sync runs succeeded;
the second confirmed **23 rows and 23 unique driver IDs** in `formula1.public.drivers`.
The timer is enabled. Its next run at verification was September 7, 2026 at
07:01 UTC (00:01 Pacific). The November calendar check returned 08:01 UTC,
confirming the intended daylight saving adjustment. All 43 backend tests passed.

For this installed server, use **Manually update drivers** below to run it now;
you do not need to repeat installation. The remaining setup instructions are
provided for reproduction and future updates.

## What the installer changes

Run the installer on the existing Amazon Linux 2023 server prepared by
[`ec2-postgres-user-data.sh`](../ec2-postgres-user-data.sh). It:

1. Builds `formula1-driver-sync:local` using Python 3.12 and locked dependencies.
2. Uses the existing bootstrap password file to access the `formula1` database.
3. Creates `public.drivers` if missing, using the shared SQL schema.
4. Creates the dedicated `driver_sync_ec2` login and grants only database
   connection, schema usage, and table SELECT/INSERT/UPDATE privileges.
5. Generates a random password and stores its connection configuration in
   `/etc/formula1-driver-sync/database.json` (directory 700, file 600).
6. Installs `formula1-driver-sync.service` and `formula1-driver-sync.timer`.

On a first install the timer remains disabled until you enable it after the
manual checks below. On updates, the installer preserves the timer's existing
enabled state. Reruns reuse credentials and do not rotate an existing role.
They do not migrate an incompatible existing table. The bootstrap PostgreSQL
container, its superuser password, and the test database are preserved.

The old Lambda handler and SAM resources remain available, with sync disabled
by default. Keep `EnableDriverSync=false` in SAM while using the EC2 schedule
to avoid two schedulers writing the same table. The HTTP response contract is
unchanged; the API now reads PostgreSQL through a separate read-only role. See
the [API reader guide](../drivers-api/README.md).

## Upload from your Mac

These commands package an explicit set of files. Do not upload the entire
repository or its private SSH key. The Docker build also uses an allowlist in
`Dockerfile.dockerignore` to exclude credentials and unrelated files.

From your Mac:

```bash
cd /Users/jacksonkelley/Documents/GitHub/formula1-project

COPYFILE_DISABLE=1 tar --exclude='__pycache__' --exclude='*.pyc' \
  -czf /tmp/formula1-driver-sync.tar.gz \
  backend/pyproject.toml backend/uv.lock backend/README.md \
  backend/packages/lambda-common/pyproject.toml \
  backend/packages/lambda-common/src \
  backend/services/drivers/pyproject.toml \
  backend/services/drivers/src backend/services/drivers/sql \
  backend/services/driver_stats/pyproject.toml \
  scripts/ec2-sync scripts/install-ec2-driver-sync.sh

scp -i ./formula1-db-key.pem /tmp/formula1-driver-sync.tar.gz \
  ec2-user@ec2-34-220-66-15.us-west-2.compute.amazonaws.com:/home/ec2-user/

ssh -i ./formula1-db-key.pem \
  ec2-user@ec2-34-220-66-15.us-west-2.compute.amazonaws.com
```

Confirm the current EC2 public DNS first if the instance has been stopped or
recreated. This upload does not require committing code or granting EC2 access
to your GitHub account.

## Install on EC2

At the EC2 shell:

```bash
mkdir -p ~/formula1-driver-sync
tar -xzf ~/formula1-driver-sync.tar.gz -C ~/formula1-driver-sync
cd ~/formula1-driver-sync
sudo bash scripts/install-ec2-driver-sync.sh
```

The existing EC2 internet route is used for the image build and Jolpica calls.
The job uses Docker host networking and accesses PostgreSQL at localhost:5432;
no new public PostgreSQL ingress rule is necessary. The runtime receives only
the application configuration file, mounted read-only. It never receives the
bootstrap administrator password or Docker socket.

The installer targets `formula1` and the existing container's host port 5432.
It refuses to take over an existing `driver_sync_ec2` role if its credential
file is missing, and fails if saved credentials no longer authenticate.
Restore the matching file or deliberately repair that role as administrator;
do not delete the application database or rerun the PostgreSQL bootstrap to fix it.

## Manually update drivers

On EC2:

```bash
sudo systemctl start formula1-driver-sync.service
sudo journalctl -u formula1-driver-sync.service -n 30 --no-pager
sudo systemctl show formula1-driver-sync.service -p Result -p ExecMainStatus
```

Successful nonempty runs log `outcome: success` and the number of drivers.
The service becomes inactive after finishing; that is normal for a one-shot
job. `Result=success` and `ExecMainStatus=0` indicate successful execution.
An empty upstream response logs `skipped` and preserves the table.

Inspect the application data:

```bash
sudo docker exec formula1-postgres psql -U postgres -d formula1 \
  -c 'SELECT drivers_id, drivers_current_position, drivers_current_total_points, updated_at FROM public.drivers ORDER BY drivers_current_position;'
```

Run the service a second time and verify that the same driver IDs are updated
without duplicate rows. The writer commits the batch atomically and retains
drivers absent from later responses.

After installation, you can also start an update directly from your Mac:

```bash
ssh -i ./formula1-db-key.pem \
  ec2-user@ec2-34-220-66-15.us-west-2.compute.amazonaws.com \
  'sudo systemctl start formula1-driver-sync.service'
```

## Enable Monday's schedule

After a successful manual run, on EC2:

```bash
sudo systemctl enable --now formula1-driver-sync.timer
systemctl list-timers formula1-driver-sync.timer --all
systemd-analyze calendar 'Mon *-*-* 00:01:00 America/Los_Angeles'
```

The timer explicitly uses Pacific time and follows daylight saving changes.
EC2 can keep its system timezone at UTC; `list-timers` may display UTC times.
During Pacific daylight time, Monday 00:01 is Monday 07:01 UTC; during standard
time it is 08:01 UTC.

`Persistent=true` catches up once if a scheduled time was missed while the
timer/server was stopped. It fetches the latest standings, not a historical
snapshot for each missed week. systemd does not launch a second copy when the
same service is already running. Manual starts do not change the weekly schedule.

Failures exit nonzero and are logged without credential-bearing exception
messages. systemd retries after 30 seconds, limited to three starts per ten
minutes. Each attempt has a two-minute timeout and the container is stopped
on cleanup. There is no email/SNS alarm in this setup; inspect the service
journal for failures. To retry after hitting the start limit:

```bash
sudo systemctl reset-failed formula1-driver-sync.service
sudo systemctl start formula1-driver-sync.service
```

## Pause, update, and remove scheduling

Pause future scheduled runs, while retaining manual triggering:

```bash
sudo systemctl disable --now formula1-driver-sync.timer
```

For an update, pause the timer, wait for any active service run to finish, upload
the new package, and rerun the installer. Manually verify the result, then
enable the timer again. Do not run multiple installers at once. Enabling a
persistent timer may immediately catch up on a missed schedule.

The installer does not modify or delete existing data rows. To stop using this
feature, disable its timer; the database, application credentials, and container
image remain for an intentional cleanup or rollback later.

## Verification and references

Local unit tests cover configuration, success/empty/failure outcomes, sanitized
logs, and bypassing AWS secret access. The PostgreSQL integration tests cover
upserts and rollback. Docker smoke checks exercise the packaged entrypoint and
repeated application-role setup against a disposable PostgreSQL 18 server.

- [Existing database testing instructions](../../notes/test_ec2_db.md)
- [Driver service documentation](../../backend/services/drivers/README.md)
- [Docker host networking](https://docs.docker.com/engine/network/drivers/host/)
- [systemd timer behavior](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
