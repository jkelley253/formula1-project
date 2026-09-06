# Driver stats installation and operations

This adds the driver stats schema, two application roles, one API Lambda, and
an EC2 Docker job. It uses the existing PostgreSQL server and does not change
the standings API contract or its timer. The separate feature plan is
[driver_stats_feature.md](../../driver_stats_feature.md).

## Deployment verified September 6, 2026

- Stack: `formula1-driver-stats-service`, `us-west-2`, `CREATE_COMPLETE`.
- API base: `https://s4uacl7c5h.execute-api.us-west-2.amazonaws.com`.
- Site: [formula1project.com](http://formula1project.com/); select any driver name.
- All 23 current-driver profiles populated from 4,330 unique GP/sprint results.
  Repeated refreshes preserved the result count. The existing drivers API still
  returns 23 drivers.
- The systemd refresh succeeded, and the timer is enabled. Its next scheduled
  run is September 7 at 07:15 UTC (00:15 Pacific). The November check resolves
  to November 2 at 08:15 UTC, confirming the daylight-saving adjustment.
- Validation: 94 backend tests including disposable PostgreSQL integration tests;
  11 frontend tests; frontend lint/build; SAM validation/build; repeatable Docker
  database setup; live checks of every profile, error responses, CORS, and the
  published HTML/JS/CSS. Hamilton and Lindblad wins/grid-P1 totals were also
  reconciled with separate filtered source queries.
- Interactive visual browser inspection was unavailable in the execution session.
- Lambda uses the account's unreserved concurrency pool. An optional reservation
  was removed because the account quota could not accommodate it. The failed
  initial stack was fully rolled back and removed before the successful deployment.
- Previous frontend assets were retained. The previous entry page was saved
  locally at `/private/tmp/formula1-frontend-before-driver-stats-index.html` for rollback.

## Package and install

From the repository root, package only the required source files:

```bash
COPYFILE_DISABLE=1 tar --exclude=__pycache__ --exclude='*.pyc' \
  -czf /tmp/formula1-driver-stats.tar.gz \
  backend/pyproject.toml backend/uv.lock backend/README.md \
  backend/packages/lambda-common/pyproject.toml backend/packages/lambda-common/src \
  backend/services/drivers/pyproject.toml \
  backend/services/driver_stats/pyproject.toml backend/services/driver_stats/src \
  backend/services/driver_stats/sql scripts/driver-stats scripts/install-ec2-driver-stats.sh
scp -i ./formula1-db-key.pem /tmp/formula1-driver-stats.tar.gz ec2-user@<verified-host>:/home/ec2-user/
```

On EC2:

```bash
mkdir -p ~/formula1-driver-stats
tar -xzf ~/formula1-driver-stats.tar.gz -C ~/formula1-driver-stats
cd ~/formula1-driver-stats
sudo bash scripts/install-ec2-driver-stats.sh
sudo formula1-driver-stats backfill --resume
```

The installer builds `formula1-driver-stats:local`, applies the new schema, and
saves writer/reader credentials in `/etc/formula1-driver-stats` with restrictive
permissions. Reruns authenticate existing roles rather than rotate credentials.
Keep the saved files; an existing role without its credential file requires
deliberate administrator repair. The installer does not enable the new timer.

Backfill may take several minutes or pause for the rolling API budget. It is
checkpointed per driver, with upstream pages saved under
`/var/lib/formula1-driver-stats/<run-id>`. `--resume` reuses a failed/interrupted
run only when mode, season, source round, and roster match. Published drivers
are skipped. Plain commands start a fresh run. Both a host file lock and a
PostgreSQL advisory lock prevent overlapping executions.

## Deploy API and frontend

From the repository root, after the backfill is verified:

```bash
backend/.venv/bin/python scripts/deploy-driver-stats-api.py \
  --instance-id <verified-instance-id> --ssh-host <verified-host> \
  --key ./formula1-db-key.pem --execute
```

Omit `--execute` to prepare a reviewable change set. Execute that exact prepared
change set in CloudFormation when ready. The helper verifies the running host,
uses strict SSH host-key checking, and passes passwords through the SDK in
memory. It uses the existing SAM artifact bucket and supplies a private database
address, database security group, and subnet. No new NAT gateway is needed.

Retrieve the `DriverStatsApiBaseUrl` stack output from
`formula1-driver-stats-service` in `us-west-2`. Build the frontend with that value:

```bash
cd frontend
npm test
npm run lint
VITE_DRIVER_STATS_API_BASE_URL=https://<stats-api-host> npm run build
aws s3 sync dist/ s3://formula1project.com
```

Upload hashed assets before publishing the new `index.html` if applying the
deployment manually. Keep previous hashed assets for rollback and open tabs.
The checked-in frontend `.env.production` supplies the deployed public endpoint
for ordinary builds. Override it when deploying against another stats stack.
The existing `VITE_API_BASE_URL` still controls the separate identity API.

## Refresh, schedule, and rebuild

```bash
sudo formula1-driver-stats refresh
sudo formula1-driver-stats rebuild --resume
sudo systemctl enable --now formula1-driver-stats.timer
sudo systemctl list-timers formula1-driver-stats.timer --all
systemd-analyze calendar 'Mon *-*-* 00:15:00 America/Los_Angeles'
```

`refresh` re-fetches all current-season results and automatically backfills new
drivers. `backfill` and `rebuild` both re-fetch career history; the separate names
describe initial installation versus historical corrections. Do not routinely
rebuild every week. On year rollover, refresh rebuilds career histories once.

The timer runs Mondays at 00:15 Pacific and follows daylight saving changes.
Its persistent setting catches up after a missed run. The one-shot service
allows up to three hours for backfills/rate limiting and retries failures after
60 seconds, at most three starts in three hours. It is normally inactive after
successful completion. A retry resumes the same matching run.

## Verify and monitor

```bash
sudo systemctl start formula1-driver-stats.service
sudo journalctl -u formula1-driver-stats.service -n 40 --no-pager
sudo systemctl show formula1-driver-stats.service -p Result -p ExecMainStatus
sudo docker exec formula1-postgres psql -U postgres -d formula1 \
  -c 'SELECT outcome,driver_count,started_at,ended_at,error_type FROM driver_stats.sync_runs ORDER BY started_at DESC LIMIT 5'
sudo docker exec formula1-postgres psql -U postgres -d formula1 \
  -c 'SELECT driver_id,through_season,total_points,total_wins,world_championships,updated_at FROM driver_stats.career_stats ORDER BY driver_id'
```

Run refresh twice and verify stable result counts and no duplicate composite
keys. Compare a veteran and newcomer against source records. Unknown statuses
appear in completeness metadata; review and test their mapping before changing
the classifier. An upstream failure leaves published profiles intact.

API Lambda logs have 30-day retention. Monitor CloudWatch Errors/Throttles and
the systemd journal; there is no new SNS/email alarm. Check the page's update
timestamp. The website displays a notice after eight days without a new snapshot.

Successful-run cache directories can be removed after verification when disk
space needs reclaiming. Retain `request-times.json`, `sync.lock`, and any active
or resumable run's directory. Never remove cache files while a sync is running.

## Update and rollback

Disable the stats timer and wait for an active job to finish before updating its
image or schema. Upload the new allowlisted package, rerun the installer, run a
manual refresh, then re-enable the timer. Versioned administrator SQL is needed
for future schema changes; the initial installer does not migrate incompatible tables.

Rollback by restoring the previous frontend `index.html`, disabling
`formula1-driver-stats.timer`, and removing the stats API stack if desired.
Keep the new tables and credentials for recovery. Do not remove or alter the
existing PostgreSQL instance, public driver table, or standings service.
