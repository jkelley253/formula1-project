# Driver stats microservice

## Summary

Build `driver_stats` as an independently deployable service with **one new API Lambda**, a **weekly EC2 sync job**, and **new tables in the existing PostgreSQL database**.

Users click a driver’s name in the standings to open a shareable profile displaying existing driver information, current-season stats, and career stats. Profiles cover current-season participants, including substitutes who appear in the season standings.

## Driver page and stat definitions

Use the existing site styling. Show a back link, driver identity information from the existing drivers API, season year, and last successful update time. Below that, display **Current season** followed by **Career**, each grouped into overall, Grand Prix, and sprint sections.

| Section | Displayed statistics |
|---|---|
| Season overall | Championship position, season points, total races won, total DNFs |
| Season Grand Prix | Races completed, points earned, wins, podiums, pole starts, top-10 finishes, DNFs |
| Season Sprint | Races completed, points earned, wins, podiums, pole starts, top-10 finishes, DNFs |
| Career overall | Career points, total races won, total DNFs, world championships |
| Career Grand Prix | Entries, finishes, points earned, wins, podiums, pole starts, top-10 finishes, best finish and its count, best grid position and its count, DNFs |
| Career Sprint | Entries, finishes, points earned, wins, podiums, pole starts, top-10 finishes, best finish and its count, best grid position and its count, DNFs |

Calculation rules:

- **Entries:** one entry per driver result record, including recorded non-starts. Explain this definition beside the metric.
- **Completed/finished:** provider-reported finishes, including lapped finishers. Retirements count as DNFs.
- **DNFs:** retirements and accidents; exclude non-starts, withdrawals, failures to qualify, and disqualifications. Preserve these other outcomes internally.
- **Wins, podiums, top-10s, and best finishes:** use classified finishing positions; exclude disqualified and unclassified results. A classified retirement can therefore count toward a finishing-position statistic and DNF.
- **Poles:** label **“Pole starts (grid P1)”** and count result records with grid position 1. Exclude grid 0 from best-grid calculations.
- **Best positions:** display, for example, `1 (32)`; keep position and occurrence count separate in the API.
- **Points:** GP and sprint points come from their respective results. Overall season points use championship standings; career points sum season standings, including the current season. Explain any difference from result-point sums caused by championship adjustments.
- **Combined wins/DNFs:** add the GP and sprint values.
- **Championships:** count first place in final standings of completed seasons.
- **Unavailable data:** display “Unavailable,” never a fabricated zero. Show zero when complete data establishes no occurrences.

No portraits, race-results table, historical-driver directory, season selector, or telemetry in v1.

## Service, storage, and API

Create `backend/services/driver_stats` using the existing Python workspace, application/domain/infrastructure separation, shared HTTP helpers, and service-local SAM build pattern.

**Runtime**

- One read-only Lambda behind its own API Gateway HTTP API.
- One containerized EC2 job for ingestion and aggregation, with separate manual backfill and refresh commands.
- Dedicated database reader and writer roles; the writer owns only the new service’s tables.
- Lambda accesses PostgreSQL privately using the existing networking pattern. EC2 handles upstream requests.

**Storage**

Create a service-owned `driver_stats` PostgreSQL schema:

| Table | Key and contents |
|---|---|
| `results` | Primary key `(driver_id, season, round, session_type)`; GP/sprint result position, classification text, grid, decimal points, laps, source status, normalized outcome, source payload, and fetch timestamp |
| `standings` | Primary key `(driver_id, season)`; championship position, points, source round, completed-season flag, and fetch timestamp |
| `season_stats` | Primary key `(driver_id, season)`; typed columns for the season metrics, completeness metadata, and successful update timestamp |
| `career_stats` | Primary key `driver_id`; typed columns for career metrics, best-position occurrence counts, through-season marker, completeness metadata, and successful update timestamp |
| `sync_runs` | Run ID, start/end timestamps, outcome, progress/checkpoint information, counts, and sanitized failure details |

Use `TEXT` for driver IDs, integers for counts and positions, `NUMERIC` for points, and timezone-aware timestamps. Keep metric columns explicit; use JSON only for source payloads and operational/completeness metadata.

Link `driver_id` logically to the existing `public.drivers.drivers_id`, which is Jolpica’s stable identifier. Do not link by name or number, introduce cross-service foreign keys, or let this service modify driver records.

**Public interface**

Add `GET /api/driver-stats/{driver_id}` returning:

- `driver_id`, `season`, `updated_at`, and data completeness information.
- `season_stats`, containing `overall`, `grand_prix`, and `sprint`.
- `career_stats`, containing the same groups.
- Numeric metrics; nullable unavailable values; `{position, count}` for best positions.

Return `400` for malformed IDs, `404` for drivers outside the supported roster, `503` for stats awaiting initial population, and `502` for database failures. Serve the last successful snapshot after refresh failures, exposing its actual timestamp.

Add `VITE_DRIVER_STATS_API_BASE_URL`. Preserve the existing drivers endpoint contract. Use hash routing such as `/#/drivers/hamilton` so direct links and reloads work with current S3 hosting. Fetch both APIs on a direct profile visit; handle their loading and failure states independently.

## Data source and weekly refresh

Use Jolpica’s free public API directly:

| Source | Purpose |
|---|---|
| `/{season}/driverstandings.json` | Current roster, season points and position; historical final standings for career points and championships |
| `/drivers/{id}/results.json` | Career Grand Prix history |
| `/drivers/{id}/sprint.json` | Career sprint history |
| Season-filtered results and sprints | Weekly current-season refresh |
| `/status.json` and race schedules | Status interpretation and determining completed seasons |

Jolpica documents the necessary [race result fields](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/results.md), [sprint fields](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/sprint.md), and [standings fields](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/driverStandings.md). Its documented status changes require explicit handling of both historical and newer labels. [Status documentation](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/status.md).

- Resolve and pin the season at run start; derive membership from that season’s standings rather than all retained `public.drivers` rows.
- Backfill complete GP/sprint history and historical standings for each supported driver before publishing their career summary.
- Schedule Monday at **00:15 America/Los_Angeles**, after the existing 00:01 standings job. Allow manual runs and prevent overlapping executions.
- Refresh the entire current season weekly to pick up corrections. Backfill new participants automatically; provide an explicit historical rebuild command.
- Paginate every collection with `limit=100`, following response totals. Use a custom User-Agent and configurable throttling, initially one request per second and at most 450 per rolling hour. Respect `Retry-After` and checkpoint long backfills. [Pagination documentation](https://github.com/jolpica/jolpica-f1/blob/main/docs/README.md), [rate limits](https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md).
- Stage and validate complete source batches before replacing stored results. Publish season and career aggregates together per driver in a transaction.
- Failed or truncated requests must not erase good data or publish partial career totals. Unknown statuses make affected metrics unavailable and produce a diagnostic.
- Preserve prior-season data at rollover, but do not present it as current-season data. Before new-season standings exist, show an awaiting-data state.

No additional provider or FastF1 dependency is needed for the agreed grid-based metrics. Any later supplementary source must address a demonstrated gap and satisfy the requested free-access and accuracy requirements.

## Validation and rollout

- Test all calculations using fixtures covering GP/sprint separation, fractional points, lapped finishes, classified retirements, DNS, DSQ, unknown statuses, grid 0, repeated best positions, and seasons before sprint racing.
- Test championship counting against completed seasons, including an ongoing championship leader.
- Test pagination, throttling, retries, interrupted backfills, newcomer backfills, corrected results, and season rollover.
- Use disposable PostgreSQL integration tests for uniqueness, repeatable refreshes, atomic publication, rollback, and reader/writer permissions.
- Verify API contracts and profile loading, unavailable/zero states, errors, direct links, browser navigation, keyboard access, and mobile layout.
- Run backend tests, SAM validation/build, and frontend lint/build. Reconcile selected drivers’ summaries against the underlying source records.
- Deploy tables and EC2 tooling first; complete backfill and verify a repeated refresh. Deploy the API, then frontend links, then enable the weekly timer.
- Log sync outcomes, duration, coverage, and failures; use the existing systemd journal and Lambda CloudWatch monitoring pattern.
- Roll back by removing profile links and disabling the new timer/API deployment; retain stored data and the existing standings service.
