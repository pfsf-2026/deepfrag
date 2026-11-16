from __future__ import annotations

import io
import zipfile

from app import apple_health

XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count" startDate="2026-03-04 08:00:00 -0500" endDate="2026-03-04 08:10:00 -0500" value="900"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count" startDate="2026-03-04 09:00:00 -0500" endDate="2026-03-04 09:10:00 -0500" value="1100"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count" startDate="2026-03-05 09:00:00 -0500" endDate="2026-03-05 09:10:00 -0500" value="500"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Scale" unit="lb" startDate="2026-03-04 07:00:00 -0500" endDate="2026-03-04 07:00:00 -0500" value="190"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" startDate="2026-03-04 07:00:00 -0500" endDate="2026-03-04 07:00:00 -0500" value="62"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" startDate="2026-03-04 07:02:00 -0500" endDate="2026-03-04 07:02:00 -0500" value="64"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" startDate="2026-03-04 07:30:00 -0500" endDate="2026-03-04 07:30:00 -0500" value="70"/>
 <Record type="HKQuantityTypeIdentifierOxygenSaturation" sourceName="Watch" unit="%" startDate="2026-03-04 07:00:00 -0500" endDate="2026-03-04 07:00:00 -0500" value="0.97"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" value="HKCategoryValueSleepAnalysisAsleepCore" startDate="2026-03-03 23:00:00 -0500" endDate="2026-03-04 03:00:00 -0500"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" value="HKCategoryValueSleepAnalysisAsleepREM" startDate="2026-03-04 03:00:00 -0500" endDate="2026-03-04 06:30:00 -0500"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" value="HKCategoryValueSleepAnalysisInBed" startDate="2026-03-03 22:30:00 -0500" endDate="2026-03-04 06:45:00 -0500"/>
 <Record type="HKQuantityTypeIdentifierSomethingUnknown" unit="x" startDate="2026-03-04 07:00:00 -0500" endDate="2026-03-04 07:00:00 -0500" value="1"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="31.5" durationUnit="min" totalDistance="3.1" totalDistanceUnit="mi" totalEnergyBurned="320" sourceName="Watch" startDate="2026-03-04 17:00:00 -0500" endDate="2026-03-04 17:31:30 -0500">
   <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" average="152" minimum="110" maximum="171" unit="count/min"/>
 </Workout>
</HealthData>
"""


def _by_kind(parsed, kind):
    return sorted([o for o in parsed["observations"] if o["kind"] == kind], key=lambda o: o["observed_at"])


def test_parse_xml():
    p = apple_health.parse(XML.encode())
    steps = _by_kind(p, "steps")
    assert [s["value"] for s in steps] == [2000.0, 500.0]
    w = _by_kind(p, "weight")[0]
    assert abs(w["value"] - 190 * 0.45359237) < 1e-6 and w["unit"] == "kg"
    hr = _by_kind(p, "heart_rate")
    assert [h["value"] for h in hr] == [62.0, 70.0]          # 07:02 sample thinned (within 5 min of 07:00)
    assert _by_kind(p, "spo2")[0]["value"] == 97.0
    sleep = _by_kind(p, "sleep_hours")
    assert len(sleep) == 1 and abs(sleep[0]["value"] - 7.5) < 1e-6   # InBed excluded
    assert p["workouts"][0]["kind"] == "run"
    assert abs(p["workouts"][0]["distance_km"] - 3.1 * 1.609344) < 1e-6
    assert p["workouts"][0]["avg_hr"] == 152.0 and p["workouts"][0]["calories"] == 320.0
    assert p["counts"]["record_types_seen"]["HKQuantityTypeIdentifierSomethingUnknown"] == 1


def test_parse_zip_and_import_idempotent(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("apple_health_export/export.xml", XML)
        zf.writestr("apple_health_export/export_cda.xml", "<x/>")
    first = client.post("/api/import/apple-health", files={"file": ("export.zip", buf.getvalue(), "application/zip")}).json()
    assert first["written"]["observations"] == first["observations"] > 0 and first["written"]["workouts"] == 1
    again = client.post("/api/import/apple-health", files={"file": ("export.zip", buf.getvalue(), "application/zip")}).json()
    assert again["written"] == first["written"]
    rows = client.get("/api/observations", params={"kind": "steps", "days": 3660}).json()
    assert len(rows) == 2 and all(r["source"] == "apple_health" for r in rows)
    assert sum(w["source"] == "apple_health" for w in client.get("/api/workouts", params={"days": 3660}).json()) == 1
    assert client.post("/api/import/apple-health", files={"file": ("bad.xml", b"<not xml", "text/xml")}).status_code == 422
