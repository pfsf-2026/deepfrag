"""Apple Health export importer.

Health app > profile > Export All Health Data gives a zip with export.xml, often
hundreds of MB. This streams it with iterparse, keeps only the record types the
app knows, sums per-day the kinds that are cumulative (steps, energy), keeps
point kinds (weight, HR, BP) per sample but thinned to at most one per 5 minutes,
and bulk-inserts with ON CONFLICT so a re-import is idempotent.

Sleep comes from HKCategoryTypeIdentifierSleepAnalysis intervals, summed per
night (asleep states only) and stored as sleep_hours on the wake-up date.
Workouts come from <Workout> elements.
"""
from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from xml.etree import ElementTree as ET

from .db import conn, jsonb
from .observations import APPLE_TYPES, to_canonical

SOURCE = "apple_health"
POINT_THIN = timedelta(minutes=5)

WORKOUT_KINDS = {
    "HKWorkoutActivityTypeRunning": "run", "HKWorkoutActivityTypeWalking": "walk", "HKWorkoutActivityTypeHiking": "walk",
    "HKWorkoutActivityTypeCycling": "cycle", "HKWorkoutActivityTypeSwimming": "swim",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "strength", "HKWorkoutActivityTypeFunctionalStrengthTraining": "strength",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "hiit", "HKWorkoutActivityTypeYoga": "yoga",
    "HKWorkoutActivityTypeElliptical": "cardio", "HKWorkoutActivityTypeRowing": "cardio", "HKWorkoutActivityTypeStairClimbing": "cardio",
}
ASLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisAsleep", "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore", "HKCategoryValueSleepAnalysisAsleepDeep", "HKCategoryValueSleepAnalysisAsleepREM",
}


def _dt(s: str) -> datetime:
    # export format: "2026-03-04 07:15:22 -0500"
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def _open_export(data: bytes | BinaryIO) -> BinaryIO:
    raw = data if isinstance(data, bytes) else data.read()
    if raw[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in zf.namelist() if n.endswith("export.xml") and "export_cda" not in n), None)
        if name is None:
            raise ValueError("zip has no export.xml")
        return io.BytesIO(zf.read(name))
    return io.BytesIO(raw)


def parse(data: bytes | BinaryIO) -> dict[str, Any]:
    """Return {"observations": [...], "workouts": [...], "counts": {...}} ready for insert."""
    stream = _open_export(data)
    sums: dict[tuple[str, str], float] = defaultdict(float)       # (kind, day) -> total
    sum_units: dict[str, str] = {}
    points: dict[str, list[tuple[datetime, float, str]]] = defaultdict(list)
    sleep: dict[str, float] = defaultdict(float)                    # wake date -> hours
    workouts: list[dict[str, Any]] = []
    seen_types: dict[str, int] = defaultdict(int)

    for _, el in ET.iterparse(stream, events=("end",)):
        if el.tag == "Record":
            rtype = el.get("type", "")
            seen_types[rtype] += 1
            if rtype == "HKCategoryTypeIdentifierSleepAnalysis":
                if el.get("value") in ASLEEP_VALUES:
                    start, end = _dt(el.get("startDate")), _dt(el.get("endDate"))
                    sleep[end.date().isoformat()] += (end - start).total_seconds() / 3600.0
            elif rtype in APPLE_TYPES:
                kind, mult, agg = APPLE_TYPES[rtype]
                try:
                    value = float(el.get("value")) * mult
                except (TypeError, ValueError):
                    el.clear(); continue
                unit = el.get("unit") or ""
                value, unit = to_canonical(kind, value, unit)
                when = _dt(el.get("startDate"))
                if agg == "sum":
                    sums[(kind, when.date().isoformat())] += value
                    sum_units[kind] = unit
                else:
                    points[kind].append((when, value, unit))
            el.clear()
        elif el.tag == "Workout":
            kind = WORKOUT_KINDS.get(el.get("workoutActivityType", ""), "other")
            start = _dt(el.get("startDate"))
            dur = el.get("duration")
            stats = {s.get("type"): s for s in el.findall("WorkoutStatistics")}
            def stat(t: str) -> float | None:
                s = stats.get(t)
                if s is None:
                    return None
                v = s.get("sum") or s.get("average")
                return float(v) if v else None
            dist = stat("HKQuantityTypeIdentifierDistanceWalkingRunning") or stat("HKQuantityTypeIdentifierDistanceCycling") \
                or (float(el.get("totalDistance")) if el.get("totalDistance") else None)
            dist_unit = el.get("totalDistanceUnit") or "km"
            if dist is not None and dist_unit == "mi":
                dist *= 1.609344
            workouts.append({
                "started_at": start, "duration_min": float(dur) if dur else None, "kind": kind,
                "distance_km": dist, "calories": stat("HKQuantityTypeIdentifierActiveEnergyBurned")
                    or (float(el.get("totalEnergyBurned")) if el.get("totalEnergyBurned") else None),
                "avg_hr": stat("HKQuantityTypeIdentifierHeartRate"),
                "meta": {"apple_type": el.get("workoutActivityType"), "source_name": el.get("sourceName")},
            })
            el.clear()

    observations: list[dict[str, Any]] = []
    for (kind, day), total in sums.items():
        observations.append({"kind": kind, "value": round(total, 3), "unit": sum_units[kind],
                             "observed_at": datetime.fromisoformat(day + "T12:00:00+00:00"), "meta": {"aggregate": "daily_sum"}})
    for day, hours in sleep.items():
        observations.append({"kind": "sleep_hours", "value": round(hours, 2), "unit": "h",
                             "observed_at": datetime.fromisoformat(day + "T08:00:00+00:00"), "meta": {"aggregate": "nightly_sum"}})
    for kind, samples in points.items():
        samples.sort()
        last: datetime | None = None
        for when, value, unit in samples:
            if last is not None and when - last < POINT_THIN:
                continue
            last = when
            observations.append({"kind": kind, "value": value, "unit": unit, "observed_at": when, "meta": {}})

    return {"observations": observations, "workouts": workouts,
            "counts": {"record_types_seen": dict(seen_types), "observations": len(observations), "workouts": len(workouts)}}


def import_into(user_id: int, parsed: dict[str, Any]) -> dict[str, int]:
    obs_rows = [(user_id, o["kind"], o["value"], o["unit"], o["observed_at"], SOURCE, jsonb(o["meta"])) for o in parsed["observations"]]
    w_rows = [(user_id, w["started_at"], w["duration_min"], w["kind"], w["distance_km"], w["calories"], w["avg_hr"], SOURCE, jsonb(w["meta"]))
              for w in parsed["workouts"]]
    with conn() as c:
        with c.cursor() as cur:
            cur.executemany(
                """INSERT INTO observations (user_id, kind, value, unit, observed_at, source, meta)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, kind, observed_at, source) WHERE source <> 'manual'
                   DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit, meta = EXCLUDED.meta""",
                obs_rows,
            )
            cur.executemany(
                """INSERT INTO workouts (user_id, started_at, duration_min, kind, distance_km, calories, avg_hr, source, meta)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, started_at, source) WHERE source <> 'manual'
                   DO UPDATE SET duration_min = EXCLUDED.duration_min, kind = EXCLUDED.kind, distance_km = EXCLUDED.distance_km,
                                 calories = EXCLUDED.calories, avg_hr = EXCLUDED.avg_hr, meta = EXCLUDED.meta""",
                w_rows,
            )
    return {"observations": len(obs_rows), "workouts": len(w_rows)}


def import_file(user_id: int, path: Path) -> dict[str, Any]:
    parsed = parse(path.read_bytes())
    written = import_into(user_id, parsed)
    return {**parsed["counts"], "written": written}
