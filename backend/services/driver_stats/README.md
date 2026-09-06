# Driver stats service

An independently deployed, read-only Lambda serves season and career statistics
from PostgreSQL. A separate EC2 Docker job owns ingestion and calculation.
The approved feature plan remains in [driver_stats_feature.md](../../../driver_stats_feature.md).

Production API: `https://s4uacl7c5h.execute-api.us-west-2.amazonaws.com`.
Deployment and verification details are in the [operations guide](../../../scripts/driver-stats/README.md#deployment-verified-september-6-2026).

## API and frontend

`GET /api/driver-stats/{driver_id}` returns:

```json
{
  "driver_id": "hamilton",
  "season": 2026,
  "updated_at": "2026-09-06T00:00:00+00:00",
  "completeness": {
    "season": {"unavailable_metrics": [], "unknown_statuses": []},
    "career": {"unavailable_metrics": [], "unknown_statuses": []}
  },
  "season_stats": {"overall": {}, "grand_prix": {}, "sprint": {}},
  "career_stats": {"overall": {}, "grand_prix": {}, "sprint": {}}
}
```

The empty groups above abbreviate the response. Overall groups contain
`total_points`, `total_wins`, and `total_dnfs`, plus `championship_position` for
the season or `world_championships` for career. Each format group contains
`entries`, `finishes`, `points`, `wins`, `podiums`, `pole_starts`,
`top_10_finishes`, `dnfs`, `best_finish`, and `best_grid`. Best positions are
objects such as `{"position": 1, "count": 32}`.

Unavailable metrics are `null`. No eligible best result is represented as
`{"position": null, "count": 0}`; unknown best-grid coverage has a null count.
The frontend displays the season and career subsets defined in the feature plan.

Responses use `400` for malformed IDs, `404` for drivers outside the current
roster, `503` before roster/stat population, and `502` for database errors.
Successful snapshots are cached for five minutes; errors use `no-store`.
No request fetches Jolpica or writes to PostgreSQL. Refresh failures preserve
the last published summaries and their timestamps.

The frontend's `.env.production` sets `VITE_DRIVER_STATS_API_BASE_URL` to the
deployed `DriverStatsApiBaseUrl` stack output; override it for another deployment.
The existing `VITE_API_BASE_URL` still selects the drivers service. Both are
embedded at frontend build time. Profiles use `/#/drivers/{driver_id}`, so
S3 does not need a history-routing fallback. The page independently loads
identity and stats, supports retry, and flags snapshots older than eight days.

## Definitions and source coverage

- Entries count driver result records, including recorded non-starts.
- Finishes include lapped finishers. DNFs count known retirement/accident labels;
  non-starts and disqualifications are separate internal outcomes.
- Classified positions count toward wins, podiums, top-10s, and best finishes.
  A classified retirement can also count as a DNF.
- Pole starts mean grid position 1, not an independently credited pole award.
  Grid 0 is excluded from best grid. Missing grids make grid metrics unavailable.
- Session points are summed using decimal arithmetic; overall points use season
  standings, preserving championship adjustments. Career includes current season.
- Championships require final-round standings and a final race date in the past.
- Missing or unknown status labels make finish and DNF totals unavailable,
  with a diagnostic in `completeness`. They are never assumed to be retirements.

Jolpica is the only v1 provider. The adapter supports pagination, a custom User-Agent,
bounded retries, `Retry-After`, durable page checkpoints, and a rolling request budget.
See [results](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/results.md),
[sprints](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/sprint.md),
[standings](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/driverStandings.md),
and [rate limits](https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md).

The job pins the UTC calendar year and explicitly requests standings for the
last published GP round. Jolpica's latest standings can already be labelled
with an upcoming round while its points still reflect the previous race.
Sprint results beyond the pinned GP round wait until that GP is published.
Before first-season results exist, the job skips without relabelling old data.

Current membership comes from those standings, not all retained `public.drivers`
rows. New participants receive a full history backfill before their profile is
published. Year rollover also rebuilds histories, covering missed final rounds
or seasons. Weekly refreshes replace the entire current season; `rebuild` also
refreshes historical corrections. Season and career summaries publish together
per driver; different drivers can finish updating at different times.

Historical years come from GP/sprint result records. The provider's driver-season
directory also lists practice-only appearances, which do not count as race entries.

## Database

Apply `sql/001_create_driver_stats.sql` as administrator or use the EC2 installer.
The schema contains `results`, `standings`, `season_stats`, `career_stats`, and
`sync_runs`. Typed metric columns store summaries; JSON stores source records,
coverage, and run checkpoints. `standings.current_roster` records membership
even before the first summary is ready.

Driver IDs match `public.drivers.drivers_id` logically. There are no cross-service
foreign keys or driver-table mutations. `driver_stats_sync` receives DML only
on this schema's tables. `driver_stats_api` receives SELECT only on standings
and summaries. Application roles cannot create tables. Schema changes remain
administrator migrations; the initial SQL does not migrate incompatible tables.

## Configuration

| Variable | Default / purpose |
|---|---|
| `DRIVER_STATS_DB_HOST` | Required private PostgreSQL host for Lambda |
| `DRIVER_STATS_DB_PORT` | `5432` |
| `DRIVER_STATS_DB_NAME` | `formula1` |
| `DRIVER_STATS_DB_USER` | Required read-only role |
| `DRIVER_STATS_DB_PASSWORD` | Required; deployment helper supplies in memory |
| `CORS_ALLOW_ORIGIN` | SAM parameter; production uses `http://formula1project.com` |
| `DATABASE_CONFIG_FILE` | EC2: `/run/secrets/database.json` |
| `STATS_STATE_DIR` | EC2: `/state`, mounted to durable host storage |
| `STATS_API_BASE_URL` | `https://api.jolpi.ca/ergast/f1` |
| `STATS_REQUEST_INTERVAL` | `1` second minimum |
| `STATS_REQUESTS_PER_HOUR` | `450` maximum; lower when sharing the IP with other jobs |

Lambda uses private DB access and a separate security group, without internet
egress or a NAT gateway. Credentials follow the existing deployment's encrypted
Lambda environment pattern. The EC2 job mounts only its writer credential file.
Installer credentials are never mounted into the application job.

## Verify locally

From `backend/`:

```bash
uv sync --all-packages --dev
uv run pytest
cd services/driver_stats
sam validate --lint
sam build
```

To run PostgreSQL integration tests, set `DRIVER_STATS_TEST_DSN` to a disposable
database without a `driver_stats` schema. Tests refuse an existing schema and
remove only their test schema/roles afterward. The existing standings integration
tests separately use `DRIVER_SYNC_TEST_DSN`.

From `frontend/`, run `npm test`, `npm run lint`, and `npm run build`.
The page tests cover direct links, hash navigation, GP/sprint separation,
unavailable versus zero values, independent API failures, and retry.

See [EC2 installation and deployment](../../../scripts/driver-stats/README.md).
