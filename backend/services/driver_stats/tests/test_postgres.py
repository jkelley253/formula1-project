"""Only runs on an explicitly supplied disposable database without our schema."""

import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
import pytest

from driver_stats_service.application.sync import run_sync
from driver_stats_service.infrastructure.postgres import Store, read_profile, DriverNotFound, StatsUnavailable
from test_stats_sync import FakeClient


@pytest.fixture(scope="module")
def database():
    dsn = os.getenv("DRIVER_STATS_TEST_DSN")
    if not dsn:
        pytest.skip("Set DRIVER_STATS_TEST_DSN to a disposable PostgreSQL database")
    settings = conninfo_to_dict(dsn)
    with psycopg.connect(**settings, autocommit=True) as conn:
        if conn.execute("SELECT to_regnamespace('driver_stats')").fetchone()[0]:
            pytest.fail("Refusing to overwrite an existing driver_stats schema")
        conn.execute((Path(__file__).parents[1] / "sql/001_create_driver_stats.sql").read_text())
    yield settings
    with psycopg.connect(**settings, autocommit=True) as conn:
        conn.execute("DROP SCHEMA driver_stats CASCADE")


def test_pipeline_repeat_corrections_resume_and_rollback(database):
    client = FakeClient()
    with Store(database) as store:
        first = run_sync(client, store, season=2026)
        initial = read_profile("test_driver", settings=database, season=2026)
        assert initial["career_stats"]["grand_prix"]["wins"] == 2
        assert initial["career_stats"]["sprint"]["entries"] == 0
        assert store.conn.execute("SELECT count(*) AS n FROM driver_stats.results").fetchone()["n"] == 2
        run_sync(FakeClient(), store, season=2026)
        assert store.conn.execute("SELECT count(*) AS n FROM driver_stats.results").fetchone()["n"] == 2
        assert store.has_history("test_driver", 2026)
        assert not store.has_history("test_driver", 2027)
        current = read_profile("test_driver", settings=database, season=2026)
        with pytest.raises(ValueError):
            store.publish(first["run_id"], "test_driver", 2026, [], [], ({"bad_column": 1}, {}), rebuild=True)
        assert read_profile("test_driver", settings=database, season=2026) == current
        assert store.conn.execute("SELECT count(*) AS n FROM driver_stats.results").fetchone()["n"] == 2
        with pytest.raises(RuntimeError, match="Another"):
            with Store(database):
                pass
        with pytest.raises(DriverNotFound):
            read_profile("unknown", settings=database, season=2026)
        with pytest.raises(StatsUnavailable):
            read_profile("test_driver", settings=database, season=2027)
        # Rebuild from corrected upstream data; no duplicate entries.
        corrected = FakeClient()
        original = corrected.results
        def correction(path, kind):
            pairs = original(path, kind)
            for _, row in pairs:
                row.update(position="2", positionText="2", points="18")
            return pairs
        corrected.results = correction
        run_sync(corrected, store, season=2026, mode="rebuild")
        profile = read_profile("test_driver", settings=database, season=2026)
        assert profile["career_stats"]["grand_prix"]["wins"] == 0
        assert profile["career_stats"]["grand_prix"]["best_finish"] == {"position": 2, "count": 2}


def test_reader_and_writer_privileges(database):
    with psycopg.connect(**database, autocommit=True) as conn:
        for role in ("stats_test_reader", "stats_test_writer"):
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                pytest.fail("Refusing to change an existing test role")
        conn.execute("CREATE ROLE stats_test_reader")
        conn.execute("CREATE ROLE stats_test_writer")
        try:
            conn.execute("GRANT USAGE ON SCHEMA driver_stats TO stats_test_reader,stats_test_writer")
            conn.execute("GRANT SELECT ON driver_stats.standings,driver_stats.season_stats,driver_stats.career_stats TO stats_test_reader")
            conn.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA driver_stats TO stats_test_writer")
            conn.execute("SET ROLE stats_test_reader")
            assert conn.execute("SELECT count(*) FROM driver_stats.career_stats").fetchone()[0] == 1
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("DELETE FROM driver_stats.career_stats")
            conn.execute("RESET ROLE")
            conn.execute("SET ROLE stats_test_writer")
            conn.execute("UPDATE driver_stats.career_stats SET total_wins=total_wins")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("CREATE TABLE driver_stats.forbidden (id int)")
            conn.execute("RESET ROLE")
        finally:
            conn.execute("RESET ROLE")
            conn.execute("DROP OWNED BY stats_test_reader,stats_test_writer")
            conn.execute("DROP ROLE stats_test_reader,stats_test_writer")
