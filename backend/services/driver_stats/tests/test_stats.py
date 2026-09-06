from decimal import Decimal
import pytest

from driver_stats_service.domain.stats import calculate, normalize_result, session_stats, outcome


def result(*, year=2026, round=1, kind="grand_prix", status="Finished", position="1", text="1", grid="1", points="25"):
    return normalize_result({"season": str(year), "round": str(round)},
                            {"Driver": {"driverId": "test_driver"}, "position": position, "positionText": text,
                             "grid": grid, "points": points, "status": status, "laps": "50"}, kind)


@pytest.mark.parametrize("status,text,expected", [
    ("Finished", "1", "finished"), ("+1 Lap", "5", "finished"), ("Lapped", "15", "finished"),
    ("Engine", "R", "dnf"), ("Collision", "9", "dnf"), ("Retired", "R", "dnf"),
    ("Engine", "W", "non_start"), ("Did not start", "R", "non_start"),
    ("Withdrew", "W", "non_start"), ("Did not qualify", "F", "non_start"),
    ("Disqualified", "D", "disqualified"), ("Excluded", "E", "disqualified"),
    ("Not classified", "R", "unknown"), ("Unfamiliar new status", "R", "unknown"), (None, "1", "unknown"),
])
def test_outcome(status, text, expected):
    assert outcome(status, text) == expected


def test_gp_sprint_points_and_championship_separation():
    rows = [result(year=2025, points="12.5"), result(round=1), result(round=2, kind="sprint", points="8")]
    standings = [{"season": 2025, "position": 1, "points": Decimal("12.5"), "completed": True},
                 {"season": 2026, "position": 1, "points": Decimal("30"), "completed": False}]
    season, career = calculate(rows, standings, 2026)
    assert season["grand_prix_wins"] == season["sprint_wins"] == 1
    assert season["total_wins"] == 2
    assert season["total_points"] == 30  # Championship adjustment, not 25+8.
    assert career["total_points"] == Decimal("42.5")
    assert career["grand_prix_points"] == Decimal("37.5")
    assert career["world_championships"] == 1
    assert career["grand_prix_best_finish_count"] == 2


def test_retirements_classification_nonstarts_and_grid_zero():
    rows = [result(), result(round=2, status="Collision", position="9", text="9", grid="0", points="0"),
            result(round=3, status="Did not start", text="W", grid="2", points="0"),
            result(round=4, status="Disqualified", text="D", grid="3", points="0")]
    stats = session_stats(rows)
    assert stats["entries"] == 4
    assert stats["finishes"] == stats["dnfs"] == stats["wins"] == 1
    assert stats["top_10_finishes"] == 2
    assert stats["best_grid"] == stats["best_grid_count"] == 1


def test_missing_data_is_not_zero_and_no_sprints_is_zero():
    stats = session_stats([result(status=None, grid=None)])
    assert stats["finishes"] is stats["dnfs"] is stats["pole_starts"] is None
    assert stats["best_grid_count"] is None
    empty = session_stats([])
    assert empty["entries"] == empty["wins"] == empty["dnfs"] == 0
    assert empty["best_finish"] is None and empty["best_finish_count"] == 0


@pytest.mark.parametrize("value", ["NaN", "Infinity", True])
def test_invalid_points_rejected(value):
    with pytest.raises(ValueError):
        result(points=value)
