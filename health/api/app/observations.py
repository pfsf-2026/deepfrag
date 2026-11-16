"""Catalog of observation kinds and the Apple Health identifiers that map to them.

An observation is any single measurement with a time. Keeping one table for
vitals, labs and wearable data means the assistant queries everything the same
way, and a new kind is a dict entry here, not a migration.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    code: str
    label: str
    unit: str          # canonical storage unit
    category: str      # vital | body | activity | sleep | lab | other
    loinc: str | None = None


KINDS: dict[str, Kind] = {k.code: k for k in [
    # body
    Kind("weight", "Weight", "kg", "body", "29463-7"),
    Kind("body_fat_pct", "Body fat", "%", "body", "41982-0"),
    Kind("bmi", "BMI", "kg/m2", "body", "39156-5"),
    Kind("waist_cm", "Waist circumference", "cm", "body", "8280-0"),
    # vitals
    Kind("bp_systolic", "Systolic BP", "mmHg", "vital", "8480-6"),
    Kind("bp_diastolic", "Diastolic BP", "mmHg", "vital", "8462-4"),
    Kind("heart_rate", "Heart rate", "bpm", "vital", "8867-4"),
    Kind("resting_heart_rate", "Resting heart rate", "bpm", "vital", "40443-4"),
    Kind("hrv_sdnn", "HRV (SDNN)", "ms", "vital", "80404-7"),
    Kind("spo2", "Blood oxygen", "%", "vital", "59408-5"),
    Kind("respiratory_rate", "Respiratory rate", "breaths/min", "vital", "9279-1"),
    Kind("body_temperature", "Body temperature", "C", "vital", "8310-5"),
    Kind("glucose", "Blood glucose", "mg/dL", "vital", "2339-0"),
    Kind("vo2_max", "VO2 max", "mL/kg/min", "vital", "60842-2"),
    # activity
    Kind("steps", "Steps", "count", "activity", "55423-8"),
    Kind("active_energy", "Active energy", "kcal", "activity", "41981-2"),
    Kind("basal_energy", "Resting energy", "kcal", "activity"),
    Kind("distance_walk_run", "Walking + running distance", "km", "activity"),
    Kind("exercise_minutes", "Exercise minutes", "min", "activity"),
    Kind("stand_hours", "Stand hours", "h", "activity"),
    Kind("flights_climbed", "Flights climbed", "count", "activity"),
    # sleep
    Kind("sleep_hours", "Sleep", "h", "sleep", "93832-4"),
    Kind("sleep_deep_hours", "Deep sleep", "h", "sleep"),
    Kind("sleep_rem_hours", "REM sleep", "h", "sleep"),
    # labs (common panels; anything else is stored with the lab's own name as kind)
    Kind("hba1c", "HbA1c", "%", "lab", "4548-4"),
    Kind("total_cholesterol", "Total cholesterol", "mg/dL", "lab", "2093-3"),
    Kind("ldl", "LDL cholesterol", "mg/dL", "lab", "13457-7"),
    Kind("hdl", "HDL cholesterol", "mg/dL", "lab", "2085-9"),
    Kind("triglycerides", "Triglycerides", "mg/dL", "lab", "2571-8"),
    Kind("fasting_glucose", "Fasting glucose", "mg/dL", "lab", "1558-6"),
    Kind("creatinine", "Creatinine", "mg/dL", "lab", "2160-0"),
    Kind("egfr", "eGFR", "mL/min/1.73m2", "lab", "62238-1"),
    Kind("alt", "ALT", "U/L", "lab", "1742-6"),
    Kind("ast", "AST", "U/L", "lab", "1920-8"),
    Kind("tsh", "TSH", "mIU/L", "lab", "3016-3"),
    Kind("vitamin_d", "Vitamin D (25-OH)", "ng/mL", "lab", "1989-3"),
    Kind("ferritin", "Ferritin", "ng/mL", "lab", "2276-4"),
    Kind("hemoglobin", "Hemoglobin", "g/dL", "lab", "718-7"),
    Kind("wbc", "White blood cells", "10^3/uL", "lab", "6690-2"),
    Kind("platelets", "Platelets", "10^3/uL", "lab", "777-3"),
    Kind("psa", "PSA", "ng/mL", "lab", "2857-1"),
    Kind("crp", "CRP", "mg/L", "lab", "1988-5"),
    Kind("sodium", "Sodium", "mmol/L", "lab", "2951-2"),
    Kind("potassium", "Potassium", "mmol/L", "lab", "2823-3"),
    # other
    Kind("mood", "Mood (1-5)", "score", "other"),
    Kind("energy", "Energy (1-5)", "score", "other"),
    Kind("pain", "Pain (0-10)", "score", "other"),
    Kind("water_ml", "Water intake", "mL", "other"),
    Kind("caffeine_mg", "Caffeine", "mg", "other"),
    Kind("alcohol_drinks", "Alcoholic drinks", "count", "other"),
]}

# Apple Health export.xml `type` attribute -> (kind, multiplier to canonical unit, aggregate)
# aggregate: "sum" kinds are summed per day on import (steps, energy); "point" kinds are kept per sample.
APPLE_TYPES: dict[str, tuple[str, float, str]] = {
    "HKQuantityTypeIdentifierBodyMass": ("weight", 1.0, "point"),            # export unit kg or lb; see import
    "HKQuantityTypeIdentifierBodyFatPercentage": ("body_fat_pct", 100.0, "point"),
    "HKQuantityTypeIdentifierBodyMassIndex": ("bmi", 1.0, "point"),
    "HKQuantityTypeIdentifierWaistCircumference": ("waist_cm", 1.0, "point"),
    "HKQuantityTypeIdentifierBloodPressureSystolic": ("bp_systolic", 1.0, "point"),
    "HKQuantityTypeIdentifierBloodPressureDiastolic": ("bp_diastolic", 1.0, "point"),
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", 1.0, "point"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_heart_rate", 1.0, "point"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_sdnn", 1.0, "point"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2", 100.0, "point"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiratory_rate", 1.0, "point"),
    "HKQuantityTypeIdentifierBodyTemperature": ("body_temperature", 1.0, "point"),
    "HKQuantityTypeIdentifierBloodGlucose": ("glucose", 1.0, "point"),
    "HKQuantityTypeIdentifierVO2Max": ("vo2_max", 1.0, "point"),
    "HKQuantityTypeIdentifierStepCount": ("steps", 1.0, "sum"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_energy", 1.0, "sum"),
    "HKQuantityTypeIdentifierBasalEnergyBurned": ("basal_energy", 1.0, "sum"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("distance_walk_run", 1.0, "sum"),
    "HKQuantityTypeIdentifierAppleExerciseTime": ("exercise_minutes", 1.0, "sum"),
    "HKQuantityTypeIdentifierAppleStandTime": ("stand_hours", 1.0 / 60.0, "sum"),
    "HKQuantityTypeIdentifierFlightsClimbed": ("flights_climbed", 1.0, "sum"),
    "HKQuantityTypeIdentifierDietaryWater": ("water_ml", 1.0, "sum"),
    "HKQuantityTypeIdentifierDietaryCaffeine": ("caffeine_mg", 1.0, "sum"),
}

# Unit conversions to canonical units, keyed by (kind, source_unit).
UNIT_FACTORS: dict[tuple[str, str], float] = {
    ("weight", "lb"): 0.45359237,
    ("weight", "lbs"): 0.45359237,
    ("weight", "kg"): 1.0,
    ("distance_walk_run", "mi"): 1.609344,
    ("distance_walk_run", "m"): 0.001,
    ("distance_walk_run", "km"): 1.0,
    ("body_temperature", "degF"): None,  # handled in to_canonical (affine)
    ("glucose", "mmol/L"): 18.0182,
    ("stand_hours", "min"): 1.0 / 60.0,
    ("sleep_hours", "min"): 1.0 / 60.0,
}


def to_canonical(kind: str, value: float, unit: str | None) -> tuple[float, str]:
    """Convert a value in `unit` to the kind's canonical unit. Unknown kinds pass through."""
    k = KINDS.get(kind)
    if k is None:
        return value, unit or ""
    if unit is None or unit == k.unit:
        return value, k.unit
    if kind == "body_temperature" and unit in ("degF", "F"):
        return (value - 32.0) * 5.0 / 9.0, "C"
    factor = UNIT_FACTORS.get((kind, unit))
    if factor:
        return value * factor, k.unit
    return value, unit
