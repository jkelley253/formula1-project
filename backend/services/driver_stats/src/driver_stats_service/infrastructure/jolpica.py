"""Paginated public Jolpica client with durable cache and request budget."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class UpstreamError(RuntimeError):
    pass


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as file:
        json.dump(value, file)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


class Client:
    def __init__(self, state_dir, *, opener=urlopen, clock=time.time, sleep=time.sleep):
        self.root = Path(state_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache = None
        self.opener, self.clock, self.sleep = opener, clock, sleep
        self.base = os.getenv("STATS_API_BASE_URL", "https://api.jolpi.ca/ergast/f1").rstrip("/")
        self.interval = float(os.getenv("STATS_REQUEST_INTERVAL", "1"))
        self.hourly = int(os.getenv("STATS_REQUESTS_PER_HOUR", "450"))
        if self.interval < 1 or not 1 <= self.hourly <= 450:
            raise ValueError("Unsafe upstream request budget")

    def use_cache(self, run_id):
        self.cache = self.root / run_id
        self.cache.mkdir(exist_ok=True)

    def wait(self, seconds):
        end = self.clock() + max(0, seconds)
        while self.clock() < end:
            self.sleep(min(30, end - self.clock()))

    def throttle(self):
        path = self.root / "request-times.json"
        times = json.loads(path.read_text()) if path.exists() else []
        while True:
            now = self.clock()
            times = [t for t in times if t > now - 3600]
            delay = max(0, (times[-1] + self.interval - now) if times else 0,
                        (times[0] + 3600 - now) if len(times) >= self.hourly else 0)
            if delay <= 0:
                break
            self.wait(delay)
        times.append(self.clock())
        atomic_json(path, times)

    def get(self, path, offset):
        url = f"{self.base}/{path.lstrip('/')}?limit=100&offset={offset}"
        cached = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json") if self.cache else None
        if cached and cached.exists():
            return json.loads(cached.read_text())
        for attempt in range(4):
            self.throttle()
            try:
                request = Request(url, headers={"Accept": "application/json", "User-Agent": "formula1-project-driver-stats/1.0"})
                with self.opener(request, timeout=20) as response:
                    payload = json.load(response)["MRData"]
                if not isinstance(payload, dict):
                    raise ValueError("Malformed response")
                if cached:
                    atomic_json(cached, payload)
                return payload
            except HTTPError as exc:
                if exc.code != 429 and not 500 <= exc.code < 600:
                    raise UpstreamError("Upstream request rejected") from None
                delay = 2 ** attempt
                retry = exc.headers.get("Retry-After") if exc.headers else None
                if retry:
                    try:
                        delay = max(delay, float(retry))
                    except ValueError:
                        try:
                            delay = max(delay, parsedate_to_datetime(retry).timestamp() - self.clock())
                        except (ValueError, TypeError):
                            pass
                if attempt < 3:
                    self.wait(delay)
            except (URLError, TimeoutError, OSError):
                if attempt < 3:
                    self.wait(2 ** attempt)
            except (KeyError, ValueError, TypeError):
                raise UpstreamError("Malformed upstream response") from None
        raise UpstreamError("Upstream retries exhausted")

    def collect(self, path, table, collection, *, nested=None):
        """Totals/offsets count result rows, not outer race/standing groups."""
        offset, expected, output = 0, None, []
        while True:
            payload = self.get(path, offset)
            try:
                total, actual_offset = int(payload["total"]), int(payload["offset"])
                if total < 0 or actual_offset != offset or (expected is not None and total != expected):
                    raise ValueError("Pagination changed")
                expected = total
                groups = payload[table][collection]
                if not isinstance(groups, list):
                    raise ValueError("Invalid collection")
                page = [(group, row) for group in groups for row in group[nested]] if nested else groups
                if offset + len(page) > total or (not page and offset < total):
                    raise ValueError("Truncated pagination")
                output.extend(page)
                offset += len(page)
            except (KeyError, TypeError, ValueError):
                raise UpstreamError("Incomplete upstream collection") from None
            if offset == total:
                return output

    def results(self, path, kind):
        return self.collect(path, "RaceTable", "Races", nested="Results" if kind == "grand_prix" else "SprintResults")

    def standings(self, season, *, round=None):
        prefix = str(season) if round is None else f"{season}/{round}"
        return self.collect(f"{prefix}/driverstandings.json", "StandingsTable", "StandingsLists", nested="DriverStandings")

    def schedule(self, season):
        return self.collect(f"{season}.json", "RaceTable", "Races")


def season_complete(season, source_round, races, now=None):
    now = now or datetime.now(timezone.utc)
    if not races:
        return False
    last = max(races, key=lambda r: int(r["round"]))
    # A date alone isn't enough: the final round must also have standings.
    return (int(last["season"]) == season and source_round >= int(last["round"])
            and datetime.fromisoformat(last["date"] + "T" + last.get("time", "23:59:59Z")) < now)
