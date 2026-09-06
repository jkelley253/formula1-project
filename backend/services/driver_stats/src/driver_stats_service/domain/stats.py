"""Pure calculations. Unknown source data never becomes a made-up zero."""

from decimal import Decimal
import re

DRIVER_ID = re.compile(r"[a-z0-9_]{1,80}\Z")
SESSION_TYPES = ("grand_prix", "sprint")
COUNTS = ("entries", "finishes", "wins", "podiums", "pole_starts", "top_10_finishes", "dnfs")
METRICS = (*COUNTS, "points", "best_finish", "best_finish_count", "best_grid", "best_grid_count")
# Match labels, not unstable historical status IDs. Do not assume every new
# label is a retirement. Ambiguous 'Not classified' also stays unknown.
RETIREMENTS = frozenset("""Accident|Collision|Engine|Gearbox|Transmission|Clutch|Hydraulics|Electrical|Spun off|Radiator|Suspension|Brakes|Differential|Overheating|Mechanical|Tyre|Driver Seat|Puncture|Driveshaft|Retired|Fuel pressure|Front wing|Water pressure|Refuelling|Wheel|Throttle|Steering|Technical|Electronics|Broken wing|Heat shield fire|Exhaust|Oil leak|Wheel rim|Water leak|Fuel pump|Track rod|Oil pressure|Wheel nut|Out of fuel|Pneumatics|Handling|Rear wing|Fire|Wheel bearing|Fuel system|Oil line|Fuel rig|Launch control|Fuel|Power loss|Vibrations|Drivetrain|Ignition|Chassis|Battery|Stalled|Halfshaft|Alternator|Oil pump|Fuel leak|Injection|Distributor|Turbo|Water pump|Fatal accident|Spark plugs|Fuel pipe|Oil pipe|Axle|Water pipe|Magneto|Supercharger|Collision damage|Power Unit|ERS|Brake duct|Seat|Damage|Debris|Undertray|Cooling system""".split("|"))


def integer(value, *, minimum=0):
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError("Invalid integer")
    number = int(value)
    if number < minimum:
        raise ValueError("Integer below minimum")
    return number


def optional_integer(value, *, minimum=0):
    return None if value in (None, "") else integer(value, minimum=minimum)


def points(value):
    if isinstance(value, bool):
        raise ValueError("Invalid points")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Nonfinite points")
    return number


def outcome(status, position_text):
    # Explicit non-start/classification codes take precedence over the reason
    # (a pre-start engine failure must not be counted as a retirement).
    if position_text in ("W", "F") or status in ("Withdrew", "Did not start", "Did not qualify", "Did not prequalify", "107% Rule"):
        return "non_start"
    if position_text in ("D", "E") or status in ("Disqualified", "Excluded"):
        return "disqualified"
    if status in ("Finished", "Lapped") or re.fullmatch(r"\+\d+ Laps?", status or ""):
        return "finished"
    if status in RETIREMENTS:
        return "dnf"
    return "unknown"


def normalize_result(race, result, session_type):
    driver_id = result["Driver"]["driverId"]
    if not DRIVER_ID.fullmatch(driver_id) or session_type not in SESSION_TYPES:
        raise ValueError("Invalid result identity")
    position_text = result["positionText"]
    if not isinstance(position_text, str) or not position_text:
        raise ValueError("Missing classification")
    status = result.get("status")
    if status is not None and not isinstance(status, str):
        raise ValueError("Invalid status")
    return {
        "driver_id": driver_id, "season": integer(race["season"], minimum=1950),
        "round": integer(race["round"], minimum=1), "session_type": session_type,
        "position": integer(result["position"], minimum=1), "position_text": position_text,
        "grid": optional_integer(result.get("grid")), "points": points(result["points"]),
        "laps": optional_integer(result.get("laps")), "source_status": status,
        "outcome": outcome(status, position_text), "source_payload": result,
    }


def best(values):
    if not values:
        return None, 0
    position = min(values)
    return position, values.count(position)


def session_stats(rows):
    classified = [r["position"] for r in rows if r["position_text"].isdigit()
                  and r["outcome"] not in ("disqualified", "non_start")]
    grids = [r["grid"] for r in rows if r["grid"] is not None and r["grid"] > 0]
    result = {
        "entries": len(rows), "finishes": sum(r["outcome"] == "finished" for r in rows),
        "points": sum((r["points"] for r in rows), Decimal(0)),
        "wins": classified.count(1), "podiums": sum(p <= 3 for p in classified),
        "pole_starts": grids.count(1), "top_10_finishes": sum(p <= 10 for p in classified),
        "dnfs": sum(r["outcome"] == "dnf" for r in rows),
    }
    result["best_finish"], result["best_finish_count"] = best(classified)
    result["best_grid"], result["best_grid_count"] = best(grids)
    if any(r["outcome"] == "unknown" for r in rows):
        result["finishes"] = result["dnfs"] = None
    if any(r["grid"] is None for r in rows):
        result["pole_starts"] = result["best_grid"] = result["best_grid_count"] = None
    return result


def calculate(rows, standings, season):
    """Return flat, typed season/career snapshots ready for database storage."""
    current = next(s for s in standings if s["season"] == season)
    snapshots = []
    for scope in ("season", "career"):
        selected = [r for r in rows if r["season"] == season] if scope == "season" else rows
        groups = {kind: session_stats([r for r in selected if r["session_type"] == kind])
                  for kind in SESSION_TYPES}
        flat = {f"{kind}_{key}": value for kind, stats in groups.items() for key, value in stats.items()}
        flat["total_points"] = current["points"] if scope == "season" else sum((s["points"] for s in standings), Decimal(0))
        flat["total_wins"] = sum(g["wins"] for g in groups.values())
        flat["total_dnfs"] = None if any(g["dnfs"] is None for g in groups.values()) else sum(g["dnfs"] for g in groups.values())
        if scope == "season":
            flat["championship_position"] = current["position"]
        else:
            flat["world_championships"] = sum(s["completed"] and s["position"] == 1 for s in standings)
        flat["completeness"] = {
            "unavailable_metrics": sorted(key for key, value in flat.items() if value is None
                                          and not key.endswith(("best_finish", "best_grid"))),
            "unknown_statuses": sorted({r["source_status"] or "Missing status" for r in selected if r["outcome"] == "unknown"}),
        }
        # Best grid being missing across existing entries is different from
        # having no entries. Include it explicitly in coverage metadata.
        for kind in SESSION_TYPES:
            if groups[kind]["best_grid_count"] is None:
                flat["completeness"]["unavailable_metrics"].append(f"{kind}_best_grid")
        snapshots.append(flat)
    return tuple(snapshots)


def api_stats(row, *, career=False):
    def numeric(value):
        return float(value) if isinstance(value, Decimal) else value
    overall = {key: numeric(row[key]) for key in ("total_points", "total_wins", "total_dnfs")}
    overall["world_championships" if career else "championship_position"] = row["world_championships" if career else "championship_position"]
    result = {"overall": overall}
    for kind in SESSION_TYPES:
        group = {key: numeric(row[f"{kind}_{key}"]) for key in (*COUNTS, "points")}
        for metric in ("best_finish", "best_grid"):
            group[metric] = {"position": row[f"{kind}_{metric}"], "count": row[f"{kind}_{metric}_count"]}
        result[kind] = group
    return result
