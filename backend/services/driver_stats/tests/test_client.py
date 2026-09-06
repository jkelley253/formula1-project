from datetime import datetime, timezone
from io import BytesIO
import json
from urllib.error import HTTPError

import pytest

from driver_stats_service.infrastructure.jolpica import Client, UpstreamError, season_complete


def page(total, offset, rows):
    return {"MRData": {"total": str(total), "offset": str(offset), "RaceTable": {"Races": rows}}}


def client(tmp_path, responses):
    now = [10000.0]
    calls = []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return BytesIO(json.dumps(value).encode())
    def sleep(delay):
        now[0] += delay
    return Client(tmp_path, opener=opener, clock=lambda: now[0], sleep=sleep), calls, now


def test_pagination_counts_inner_results_and_reuses_durable_cache(tmp_path):
    c, calls, _ = client(tmp_path, [page(3, 0, [{"Results": [1, 2]}]), page(3, 2, [{"Results": [3]}])])
    c.use_cache("run")
    assert len(c.results("results.json", "grand_prix")) == 3
    assert "offset=2" in calls[1]
    assert len(c.results("results.json", "grand_prix")) == 3
    assert len(calls) == 2


@pytest.mark.parametrize("second", [page(3, 2, []), page(4, 2, [{"Results": [3]}]), page(3, 1, [{"Results": [3]}])])
def test_truncated_or_changing_collections_fail(tmp_path, second):
    c, _, _ = client(tmp_path, [page(3, 0, [{"Results": [1, 2]}]), second])
    with pytest.raises(UpstreamError):
        c.results("results.json", "grand_prix")


def test_retry_after_and_persisted_hourly_budget(tmp_path):
    error = HTTPError("https://example", 429, "throttle", {"Retry-After": "10"}, None)
    c, calls, now = client(tmp_path, [error, page(0, 0, [])])
    c.hourly = 1
    c.results("results.json", "grand_prix")
    assert len(calls) == 2
    assert now[0] >= 13600
    assert json.loads((tmp_path / "request-times.json").read_text()) == [now[0]]


def test_final_round_and_date_required_for_title():
    races = [{"season": "2026", "round": "23", "date": "2026-12-06", "time": "13:00:00Z"}]
    before = datetime(2026, 9, 5, tzinfo=timezone.utc)
    after = datetime(2026, 12, 7, tzinfo=timezone.utc)
    assert not season_complete(2026, 12, races, before)
    assert not season_complete(2026, 22, races, after)
    assert season_complete(2026, 23, races, after)
