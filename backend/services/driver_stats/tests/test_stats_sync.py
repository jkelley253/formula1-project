from decimal import Decimal

import pytest

from driver_stats_service.application.sync import run_sync
from driver_stats_service.infrastructure.jolpica import UpstreamError


class FakeClient:
    def __init__(self):
        self.calls = []
        self.empty = False
        self.broken = False

    def schedule(self, year):
        return [{"season": str(year), "round": "1", "date": f"{year}-01-01", "time": "13:00:00Z"}]

    def standings(self, year, *, round=None):
        return [] if self.empty else [({"season": str(year), "round": "1"},
            {"Driver": {"driverId": "test_driver"}, "position": "1", "positionText": "1", "points": "25"})]

    def use_cache(self, run_id):
        self.calls.append(("cache", run_id))

    def collect(self, path, *args):
        return [{"season": "2025"}, {"season": "2026"}] if "seasons" in path else []

    def results(self, path, kind):
        self.calls.append((path, kind))
        if self.broken:
            raise UpstreamError("Failed page")
        if kind == "sprint":
            return []
        years = [2025, 2026] if path.startswith("drivers/") else [int(path.split('/')[0])]
        return [({"season": str(year), "round": "1"},
            {"Driver": {"driverId": "test_driver"}, "position": "1", "positionText": "1", "grid": "1", "points": "25", "status": "Finished"}) for year in years]


class FakeStore:
    def __init__(self):
        self.published = []
        self.done = set()
        self.failed = False
        self.existing = False

    def begin_run(self, *args, **kwargs):
        return "run", self.done.copy()

    def has_history(self, *args):
        return self.existing

    def history(self, *args):
        return [], []

    def publish(self, *args, **kwargs):
        self.published.append((args, kwargs))

    def finish(self, run_id, error=None):
        self.failed = error is not None


def test_new_driver_backfilled_before_publish():
    store = FakeStore()
    result = run_sync(FakeClient(), store, season=2026)
    assert result["driver_count"] == 1
    args, kwargs = store.published[0]
    assert kwargs["rebuild"]
    assert {r["season"] for r in args[3]} == {2025, 2026}
    assert args[5][1]["total_points"] == Decimal(50)


def test_failed_fetch_preserves_good_snapshot():
    client, store = FakeClient(), FakeStore()
    client.broken = True
    with pytest.raises(UpstreamError):
        run_sync(client, store, season=2026)
    assert not store.published  # Bootstrap validation can fail before a run starts.


def test_resume_skips_published_drivers():
    client, store = FakeClient(), FakeStore()
    store.done.add("test_driver")
    assert run_sync(client, store, season=2026, resume=True)["driver_count"] == 1
    assert not store.published
    assert not any(path.startswith("drivers/") for path, _ in client.calls)


def test_preseason_skips_without_erasing_old_data():
    client, store = FakeClient(), FakeStore()
    client.empty = True
    assert run_sync(client, store, season=2026)["outcome"] == "skipped"
    assert not store.published


def test_current_standings_are_pinned_to_published_race_round():
    client, store = FakeClient(), FakeStore()
    original = client.standings
    requested = []
    def standings(year, *, round=None):
        requested.append((year, round))
        return original(year, round=round)
    client.standings = standings
    run_sync(client, store, season=2026)
    assert (2026, 1) in requested
    assert (2026, None) not in requested


def test_practice_only_seasons_do_not_require_championship_records():
    client, store = FakeClient(), FakeStore()
    def collect(path, *args):
        if "seasons" in path:
            pytest.fail("Driver seasons can include practice-only appearances")
        return []
    client.collect = collect
    assert run_sync(client, store, season=2026)["outcome"] == "success"
