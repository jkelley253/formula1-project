"""Persistence owned by driver_stats. No joins or writes to public.drivers."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from driver_stats_service.domain.stats import api_stats


class StatsUnavailable(Exception):
    pass


class DriverNotFound(Exception):
    pass


def connection_settings(*, reader=False):
    if reader:
        config = {"host": os.environ["DRIVER_STATS_DB_HOST"], "port": os.getenv("DRIVER_STATS_DB_PORT", "5432"),
                  "dbname": os.getenv("DRIVER_STATS_DB_NAME", "formula1"), "username": os.environ["DRIVER_STATS_DB_USER"],
                  "password": os.environ["DRIVER_STATS_DB_PASSWORD"]}
    else:
        config = json.loads(Path(os.environ.get("DATABASE_CONFIG_FILE", "/run/secrets/database.json")).read_text())
    if any(not isinstance(config.get(k), str) or not config[k] for k in ("host", "dbname", "username", "password")):
        raise ValueError("Missing database configuration")
    port = int(config.get("port", 5432))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid database port")
    return {"host": config["host"], "port": port, "dbname": config["dbname"], "user": config["username"],
            "password": config["password"], "sslmode": config.get("sslmode", "prefer"), "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=3000" +
                       (" -c default_transaction_read_only=on" if reader else "")}


def read_profile(driver_id, *, settings=None, season=None):
    season = season or datetime.now(timezone.utc).year
    with psycopg.connect(**(settings or connection_settings(reader=True)), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        roster = conn.execute("SELECT driver_id FROM driver_stats.standings WHERE season=%s AND current_roster", (season,)).fetchall()
        if not roster:
            raise StatsUnavailable()
        if driver_id not in {r["driver_id"] for r in roster}:
            raise DriverNotFound()
        current = conn.execute("SELECT * FROM driver_stats.season_stats WHERE driver_id=%s AND season=%s", (driver_id, season)).fetchone()
        career = conn.execute("SELECT * FROM driver_stats.career_stats WHERE driver_id=%s AND through_season=%s", (driver_id, season)).fetchone()
        if not current or not career:
            raise StatsUnavailable()
        return {"driver_id": driver_id, "season": season, "updated_at": min(current["updated_at"], career["updated_at"]),
                "completeness": {"season": current["completeness"], "career": career["completeness"]},
                "season_stats": api_stats(current), "career_stats": api_stats(career, career=True)}


def upsert(conn, table, record, keys):
    """Identifiers are always quoted, values always parameterized."""
    columns = list(record)
    values = [Jsonb(record[k]) if isinstance(record[k], (dict, list)) else record[k] for k in columns]
    statement = sql.SQL("INSERT INTO driver_stats.{} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(sql.Placeholder() for _ in columns), sql.SQL(",").join(map(sql.Identifier, keys)),
        sql.SQL(",").join(sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k)) for k in columns if k not in keys))
    conn.execute(statement, values)


class Store:
    def __init__(self, settings):
        # Autocommit prevents holding idle transactions during API calls; all
        # mutations below have explicit transaction boundaries.
        self.conn = psycopg.connect(**settings, row_factory=dict_row, autocommit=True)

    def __enter__(self):
        if not self.conn.execute("SELECT pg_try_advisory_lock(761234901)").fetchone()["pg_try_advisory_lock"]:
            self.conn.close()
            raise RuntimeError("Another stats sync is running")
        return self

    def __exit__(self, *args):
        self.conn.close()

    def begin_run(self, season, mode, standings, *, resume=False):
        ids = sorted(s["driver_id"] for s in standings)
        source_round = max(s["source_round"] for s in standings)
        if resume:
            previous = self.conn.execute("""SELECT * FROM driver_stats.sync_runs WHERE season=%s AND mode=%s
                AND source_round=%s AND roster_ids=%s AND outcome IN ('running','failed') ORDER BY started_at DESC LIMIT 1""",
                (season, mode, source_round, Jsonb(ids))).fetchone()
            if previous:
                self.conn.execute("UPDATE driver_stats.sync_runs SET outcome='running', error_type=NULL, ended_at=NULL WHERE run_id=%s", (previous["run_id"],))
                return str(previous["run_id"]), set(previous["completed_drivers"])
        run_id = str(uuid4())
        with self.conn.transaction():
            upsert(self.conn, "sync_runs", {"run_id": run_id, "season": season, "mode": mode,
                   "source_round": source_round, "roster_ids": ids, "outcome": "running"}, ("run_id",))
            self.conn.execute("UPDATE driver_stats.standings SET current_roster=FALSE WHERE season=%s", (season,))
            for standing in standings:
                upsert(self.conn, "standings", {**standing, "current_roster": True, "fetched_at": datetime.now(timezone.utc)}, ("driver_id", "season"))
        return run_id, set()

    def has_history(self, driver_id, season):
        # At rollover, rebuild history to include every missed final round or
        # season rather than trusting a possibly old career snapshot.
        return bool(self.conn.execute("SELECT 1 FROM driver_stats.career_stats WHERE driver_id=%s AND through_season=%s", (driver_id, season)).fetchone())

    def history(self, driver_id, before_season):
        results = self.conn.execute("SELECT * FROM driver_stats.results WHERE driver_id=%s AND season<%s", (driver_id, before_season)).fetchall()
        standings = self.conn.execute("SELECT * FROM driver_stats.standings WHERE driver_id=%s AND season<%s", (driver_id, before_season)).fetchall()
        return results, standings

    def publish(self, run_id, driver_id, season, results, standings, snapshots, *, rebuild):
        from driver_stats_service.domain.stats import METRICS, SESSION_TYPES
        now = datetime.now(timezone.utc)
        with self.conn.transaction():
            condition = sql.SQL("") if rebuild else sql.SQL(" AND season=%s")
            args = (driver_id,) if rebuild else (driver_id, season)
            self.conn.execute(sql.SQL("DELETE FROM driver_stats.results WHERE driver_id=%s") + condition, args)
            for result in results:
                if rebuild or result["season"] == season:
                    fields = {k: result[k] for k in ("driver_id", "season", "round", "session_type", "position", "position_text", "grid", "points", "laps", "source_status", "outcome", "source_payload")}
                    upsert(self.conn, "results", {**fields, "fetched_at": now}, ("driver_id", "season", "round", "session_type"))
            if rebuild:
                self.conn.execute("DELETE FROM driver_stats.standings WHERE driver_id=%s AND season<%s", (driver_id, season))
            for standing in standings:
                fields = {k: standing[k] for k in ("driver_id", "season", "position", "points", "source_round", "completed")}
                upsert(self.conn, "standings", {**fields, "current_roster": standing["season"] == season, "fetched_at": now}, ("driver_id", "season"))
            for table, snapshot in zip(("season_stats", "career_stats"), snapshots):
                allowed = {f"{kind}_{metric}" for kind in SESSION_TYPES for metric in METRICS}
                allowed.update(("total_points", "total_wins", "total_dnfs", "championship_position", "world_championships", "completeness"))
                if set(snapshot) - allowed:
                    raise ValueError("Unexpected summary fields")
                career = table == "career_stats"
                upsert(self.conn, table, {**snapshot, "driver_id": driver_id, "through_season" if career else "season": season, "updated_at": now},
                       ("driver_id",) if career else ("driver_id", "season"))
            self.conn.execute("""UPDATE driver_stats.sync_runs SET completed_drivers=completed_drivers || %s::jsonb,
                driver_count=driver_count+1 WHERE run_id=%s""", (Jsonb([driver_id]), run_id))

    def finish(self, run_id, error=None):
        self.conn.execute("UPDATE driver_stats.sync_runs SET outcome=%s, error_type=%s, ended_at=CURRENT_TIMESTAMP WHERE run_id=%s",
                          ("failed" if error else "success", type(error).__name__ if error else None, run_id))
