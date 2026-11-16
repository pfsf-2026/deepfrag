"""Tools the assistant can call. `build_tools(user_id)` returns a fresh list bound
to one user by closure, so a tool can never cross users and nothing depends on
thread or context state (the chat generator is resumed on different threads).

Return values are JSON strings: the model reads them as tool_result text.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from anthropic import beta_tool

from .. import repo
from ..observations import KINDS
from ..schemas import InsightIn, MealIn, MealItem, MedicationIn, ObservationIn, WorkoutIn

def _json(value: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return str(o)
    return json.dumps(value, default=default, ensure_ascii=False)


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 3660)))


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_tools(user_id: int) -> list[Any]:
    """Assistant tools bound to one user."""

    @beta_tool
    def get_profile() -> str:
        """Get the owner's profile: birth date, sex, height, timezone, goals, preferences (units, diet), notes."""
        return _json(repo.get_profile(user_id))


    @beta_tool
    def list_observation_kinds() -> str:
        """List the canonical observation kinds (code, label, unit, category) the app understands, e.g. weight, bp_systolic, steps, sleep_hours, ldl, hba1c."""
        return _json([k.__dict__ for k in KINDS.values()])


    @beta_tool
    def latest_readings() -> str:
        """Most recent reading of every observation kind the owner has (vitals, body, labs, activity, sleep). Start here for a quick picture."""
        return _json(repo.latest_observations(user_id))


    @beta_tool
    def query_observations(kind: str, days: int = 30, limit: int = 200) -> str:
        """Raw readings of one kind over the last N days, newest first.

        Args:
            kind: observation code, e.g. weight, heart_rate, bp_systolic, glucose, steps, sleep_hours, ldl.
            days: how far back to look.
            limit: max rows.
        """
        return _json(repo.list_observations(user_id, kind=kind, since=_since(days), limit=min(limit, 2000)))


    @beta_tool
    def summarize_observations(kind: str, days: int = 30) -> str:
        """Stats for one kind over the last N days: count, min, max, mean, median, latest, plus per-day mean and total.

        Args:
            kind: observation code (see list_observation_kinds).
            days: window in days.
        """
        return _json(repo.summarize_observations(user_id, kind, since=_since(days)))


    @beta_tool
    def log_observation(kind: str, value: float, unit: str | None = None, observed_at: str | None = None, note: str | None = None) -> str:
        """Record a measurement: weight, blood pressure (log systolic and diastolic as two calls), glucose, mood, water, etc.

        Args:
            kind: observation code.
            value: numeric value.
            unit: unit as the owner said it (kg, lb, mmHg, mg/dL, ...); converted to canonical.
            observed_at: ISO 8601 time; defaults to now.
            note: optional free text stored in meta.
        """
        row = repo.insert_observation(
            user_id,
            ObservationIn(kind=kind, value=value, unit=unit, observed_at=_parse_dt(observed_at), source="assistant",
                          meta={"note": note} if note else {}),
        )
        return _json(row)


    @beta_tool
    def list_meals(days: int = 7) -> str:
        """Meals logged in the last N days with items and macro totals.

        Args:
            days: window in days.
        """
        return _json(repo.list_meals(user_id, since=_since(days)))


    @beta_tool
    def log_meal(description: str, items: list[dict[str, Any]] | None = None, eaten_at: str | None = None,
                 calories: float | None = None, protein_g: float | None = None, carbs_g: float | None = None,
                 fat_g: float | None = None, fiber_g: float | None = None) -> str:
        """Log a meal. Provide per-item estimates when you can; totals default to the sum of items.

        Args:
            description: short description, e.g. "2 eggs, toast with butter, black coffee".
            items: list of {name, qty, calories, protein_g, carbs_g, fat_g, fiber_g}.
            eaten_at: ISO 8601 time; defaults to now.
            calories: total kcal, if you prefer to give totals directly.
            protein_g: total protein grams.
            carbs_g: total carbohydrate grams.
            fat_g: total fat grams.
            fiber_g: total fiber grams.
        """
        meal = MealIn(
            description=description, eaten_at=_parse_dt(eaten_at), items=[MealItem(**i) for i in (items or [])],
            calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, fiber_g=fiber_g, source="assistant",
        )
        return _json(repo.insert_meal(user_id, meal))


    @beta_tool
    def list_workouts(days: int = 30) -> str:
        """Workouts in the last N days.

        Args:
            days: window in days.
        """
        return _json(repo.list_workouts(user_id, since=_since(days)))


    @beta_tool
    def log_workout(kind: str, duration_min: float | None = None, started_at: str | None = None, distance_km: float | None = None,
                    calories: float | None = None, avg_hr: float | None = None, notes: str | None = None) -> str:
        """Log a workout.

        Args:
            kind: run | walk | cycle | strength | swim | hiit | yoga | other.
            duration_min: minutes.
            started_at: ISO 8601 start; defaults to now.
            distance_km: distance in km (convert miles).
            calories: kcal if known.
            avg_hr: average heart rate.
            notes: free text.
        """
        w = WorkoutIn(kind=kind, duration_min=duration_min, started_at=_parse_dt(started_at), distance_km=distance_km,
                      calories=calories, avg_hr=avg_hr, notes=notes, source="assistant")
        return _json(repo.insert_workout(user_id, w))


    @beta_tool
    def list_medications(active_only: bool = True) -> str:
        """Medications with dose, frequency, reason, prescriber and when each was last logged as taken.

        Args:
            active_only: false to include stopped medications.
        """
        return _json(repo.list_medications(user_id, active_only=active_only))


    @beta_tool
    def add_medication(name: str, dose: str | None = None, frequency: str | None = None, reason: str | None = None,
                       route: str | None = None, prescriber: str | None = None, started_on: str | None = None) -> str:
        """Add a medication or supplement to the active list.

        Args:
            name: drug or supplement name.
            dose: e.g. "10 mg".
            frequency: e.g. "once daily, morning".
            reason: what it is for.
            route: oral | topical | injection | inhaled | other.
            prescriber: who prescribed it.
            started_on: ISO date.
        """
        m = MedicationIn(name=name, dose=dose, frequency=frequency, reason=reason, route=route, prescriber=prescriber,
                         started_on=date.fromisoformat(started_on) if started_on else None)
        return _json(repo.insert_medication(user_id, m))


    @beta_tool
    def list_conditions_and_allergies() -> str:
        """Conditions (active, resolved, monitoring, family history) and allergies."""
        return _json({
            "conditions": repo.list_simple("conditions", user_id, order="created_at DESC"),
            "allergies": repo.list_simple("allergies", user_id, order="substance"),
        })


    @beta_tool
    def list_providers_and_encounters() -> str:
        """The owner's doctors/providers and past visits (encounters) with follow-ups."""
        return _json({
            "providers": repo.list_simple("providers", user_id, order="name"),
            "encounters": repo.list_simple("encounters", user_id, order="occurred_at DESC", limit=50),
        })


    @beta_tool
    def search_documents(query: str) -> str:
        """Find uploaded medical documents by words in their filename, summary, provider or extracted content.

        Args:
            query: a word or phrase, e.g. "lipid", "Dr. Patel", "MRI".
        """
        return _json(repo.search_documents(user_id, query))


    @beta_tool
    def get_document(document_id: int) -> str:
        """Full extracted content and summary of one uploaded document.

        Args:
            document_id: id from search_documents.
        """
        row = repo.get_row("documents", document_id, user_id)
        if row is None:
            return _json({"error": "no such document"})
        row.pop("storage_key", None)
        return _json(row)


    @beta_tool
    def list_insights() -> str:
        """Open items on the owner's Today screen: briefings, nudges, anomalies, upcoming items, reminders, questions."""
        return _json(repo.list_insights(user_id))


    @beta_tool
    def create_insight(kind: str, title: str, body: str, severity: str = "info", due_at: str | None = None) -> str:
        """File an item onto the owner's Today screen so it is not lost after this chat.

        Args:
            kind: nudge | anomaly | anticipation | reminder | question.
            title: under 60 characters.
            body: the detail, under 400 characters.
            severity: info | attention | urgent.
            due_at: ISO 8601 time for reminders.
        """
        ins = InsightIn(kind=kind, title=title, body=body, severity=severity, due_at=_parse_dt(due_at))  # type: ignore[arg-type]
        fields = ins.model_dump()
        fields["data"] = {"source": "assistant"}
        return _json(repo.insert_simple("insights", user_id, fields))

    return [get_profile, list_observation_kinds, latest_readings, query_observations, summarize_observations, log_observation, list_meals, log_meal, list_workouts, log_workout, list_medications, add_medication, list_conditions_and_allergies, list_providers_and_encounters, search_documents, get_document, list_insights, create_insight]


WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}
