"""Refresh a pinned season, backfilling newcomers before publishing profiles."""

from datetime import datetime, timezone
import logging

from driver_stats_service.domain.stats import DRIVER_ID, calculate, integer, normalize_result, points
from driver_stats_service.infrastructure.jolpica import UpstreamError, season_complete

logger = logging.getLogger(__name__)


def standings_rows(pairs, season, schedule):
    rows, seen = [], set()
    for group, value in pairs:
        driver = value["Driver"]["driverId"]
        if not DRIVER_ID.fullmatch(driver) or driver in seen or int(group["season"]) != season:
            raise UpstreamError("Invalid standings identities")
        seen.add(driver)
        source_round = integer(group["round"])
        text = value.get("positionText", "")
        position = integer(value["position"], minimum=1) if text.isdigit() else None
        rows.append({"driver_id": driver, "season": season, "position": position,
                     "points": points(value["points"]), "source_round": source_round,
                     "completed": season_complete(season, source_round, schedule)})
    if len({r["source_round"] for r in rows}) > 1:
        raise UpstreamError("Mixed standings rounds")
    return rows


def result_rows(pairs, kind, *, driver=None, season=None):
    rows, seen = [], set()
    for race, result in pairs:
        row = normalize_result(race, result, kind)
        key = (row["driver_id"], row["season"], row["round"], kind)
        if key in seen or (driver and row["driver_id"] != driver) or (season and row["season"] != season):
            raise UpstreamError("Duplicate or mismatched results")
        seen.add(key)
        rows.append(row)
    return rows


def run_sync(client, store, *, mode="refresh", resume=False, season=None):
    season = season or datetime.now(timezone.utc).year
    # Explicit numeric year: don't relabel last year's standings as current
    # when the current alias falls back during the off-season.
    schedule = client.schedule(season)
    gp = result_rows(client.results(f"{season}/results.json", "grand_prix"), "grand_prix", season=season)
    if not gp:
        return {"outcome": "skipped", "reason": "awaiting_season_results", "driver_count": 0}
    # Jolpica's latest standings round can advance during an upcoming race
    # weekend while points still reflect the previous GP. Request the exact
    # last published race round instead of trusting that latest alias.
    published_round = max(r["round"] for r in gp)
    current = standings_rows(client.standings(season, round=published_round), season, schedule)
    if not current:
        return {"outcome": "skipped", "reason": "awaiting_season_standings", "driver_count": 0}
    run_id, done = store.begin_run(season, mode, current, resume=resume)
    client.use_cache(run_id)
    try:
        client.collect("status.json", "StatusTable", "Status")
        sprint = result_rows(client.results(f"{season}/sprint.json", "sprint"), "sprint", season=season)
        source_round = current[0]["source_round"]
        if gp and max(r["round"] for r in gp) != source_round:
            raise UpstreamError("Standings and race results are from different rounds")
        if source_round and not gp:
            raise UpstreamError("Missing current results")
        # An upcoming sprint can precede its GP standings. Publish only the
        # pinned standings round, keeping all totals on the same snapshot.
        sprint = [r for r in sprint if r["round"] <= source_round]
        historical_standings = {}
        for standing in current:
            driver = standing["driver_id"]
            if driver in done:
                continue
            rebuild = mode in ("backfill", "rebuild") or not store.has_history(driver, season)
            if rebuild:
                results = []
                for kind, endpoint in (("grand_prix", "results"), ("sprint", "sprint")):
                    history = result_rows(client.results(f"drivers/{driver}/{endpoint}.json", kind), kind, driver=driver)
                    results.extend(r for r in history if r["season"] < season)
                # The driver seasons endpoint also includes practice-only
                # appearances (e.g. Antonelli in 2024). Our career definition
                # includes result-listed entries, so derive years from those.
                years = {r["season"] for r in results}
                standings = []
                for year in sorted(years):
                    if year not in historical_standings:
                        historical_standings[year] = standings_rows(client.standings(year), year, client.schedule(year))
                    match = [s for s in historical_standings[year] if s["driver_id"] == driver]
                    if len(match) != 1 or not match[0]["completed"]:
                        raise UpstreamError(f"Historical final standings missing for {driver} in {year}")
                    standings.extend(match)
            else:
                results, standings = store.history(driver, season)
                # Rollover: refresh last season's final standings even if the
                # stored snapshot was captured before its final race.
                for old in list(standings):
                    if not old["completed"]:
                        year = old["season"]
                        if year not in historical_standings:
                            historical_standings[year] = standings_rows(client.standings(year), year, client.schedule(year))
                        final = next((s for s in historical_standings[year] if s["driver_id"] == driver), None)
                        if not final or not final["completed"]:
                            raise UpstreamError("Prior season not final")
                        # A missed end-of-year refresh requires results too.
                        results = [r for r in results if r["season"] != year]
                        for kind, endpoint in (("grand_prix", "results"), ("sprint", "sprint")):
                            results.extend(result_rows(client.results(f"{year}/drivers/{driver}/{endpoint}.json", kind), kind, driver=driver, season=year))
                        standings.remove(old)
                        standings.append(final)
                        rebuild = True
            results.extend(r for r in gp + sprint if r["driver_id"] == driver)
            standings.append(standing)
            snapshots = calculate(results, standings, season)
            store.publish(run_id, driver, season, results, standings, snapshots, rebuild=rebuild)
            if snapshots[1]["completeness"]["unknown_statuses"]:
                logger.warning("Unknown result status for driver %s; affected metrics unavailable", driver)
            done.add(driver)
            logger.info("Published driver %s (%d/%d)", driver, len(done), len(current))
        store.finish(run_id)
        return {"outcome": "success", "run_id": run_id, "driver_count": len(done)}
    except Exception as exc:
        store.finish(run_id, exc)
        raise
