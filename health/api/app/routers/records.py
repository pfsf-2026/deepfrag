"""Profile, observations, meals, workouts, medications, conditions, allergies,
providers, encounters: plain CRUD over the user's own rows.

Every handler takes `user_id` from auth and scopes every query by it. The AI
tools in app/ai/tools.py call the same `repo` functions, so the model can never
reach a row a route couldn't.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import repo
from ..auth import UserId
from ..observations import KINDS
from ..schemas import (
    AllergyIn, ConditionIn, EncounterIn, MealIn, MedicationIn, MedicationLogIn,
    ObservationIn, ProfileIn, ProviderIn, WorkoutIn,
)

router = APIRouter(prefix="/api", tags=["records"])


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# ---- profile ---------------------------------------------------------------

@router.get("/profile")
def get_profile(user_id: int = UserId) -> dict[str, Any]:
    return repo.get_profile(user_id)


@router.put("/profile")
def put_profile(body: ProfileIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.update_profile(user_id, body.model_dump(exclude_none=True))


# ---- observations ----------------------------------------------------------

@router.get("/observations/kinds")
def observation_kinds() -> list[dict[str, Any]]:
    return [k.__dict__ for k in KINDS.values()]


@router.get("/observations")
def list_observations(
    kind: str | None = None,
    days: int = Query(30, ge=1, le=3660),
    limit: int = Query(500, ge=1, le=5000),
    user_id: int = UserId,
) -> list[dict[str, Any]]:
    return repo.list_observations(user_id, kind=kind, since=_since(days), limit=limit)


@router.get("/observations/latest")
def latest_observations(user_id: int = UserId) -> list[dict[str, Any]]:
    """Most recent reading of every kind the user has, for the dashboard."""
    return repo.latest_observations(user_id)


@router.get("/observations/summary")
def observation_summary(kind: str, days: int = Query(30, ge=1, le=3660), user_id: int = UserId) -> dict[str, Any]:
    return repo.summarize_observations(user_id, kind, since=_since(days))


@router.post("/observations", status_code=201)
def create_observation(body: ObservationIn, user_id: int = UserId) -> dict[str, Any]:
    if body.value is None and body.value_text is None:
        raise HTTPException(422, "value or value_text is required")
    return repo.insert_observation(user_id, body)


@router.delete("/observations/{obs_id}", status_code=204)
def delete_observation(obs_id: int, user_id: int = UserId) -> None:
    if not repo.delete_row("observations", obs_id, user_id):
        raise HTTPException(404)


# ---- meals -----------------------------------------------------------------

@router.get("/meals")
def list_meals(days: int = Query(14, ge=1, le=3660), user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_meals(user_id, since=_since(days))


@router.post("/meals", status_code=201)
def create_meal(body: MealIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_meal(user_id, body)


@router.delete("/meals/{meal_id}", status_code=204)
def delete_meal(meal_id: int, user_id: int = UserId) -> None:
    if not repo.delete_row("meals", meal_id, user_id):
        raise HTTPException(404)


# ---- workouts --------------------------------------------------------------

@router.get("/workouts")
def list_workouts(days: int = Query(30, ge=1, le=3660), user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_workouts(user_id, since=_since(days))


@router.post("/workouts", status_code=201)
def create_workout(body: WorkoutIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_workout(user_id, body)


@router.delete("/workouts/{workout_id}", status_code=204)
def delete_workout(workout_id: int, user_id: int = UserId) -> None:
    if not repo.delete_row("workouts", workout_id, user_id):
        raise HTTPException(404)


# ---- medications -----------------------------------------------------------

@router.get("/medications")
def list_medications(active_only: bool = True, user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_medications(user_id, active_only=active_only)


@router.post("/medications", status_code=201)
def create_medication(body: MedicationIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_medication(user_id, body)


@router.patch("/medications/{med_id}")
def update_medication(med_id: int, body: MedicationIn, user_id: int = UserId) -> dict[str, Any]:
    row = repo.update_medication(user_id, med_id, body.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(404)
    return row


@router.post("/medications/{med_id}/log", status_code=201)
def log_medication(med_id: int, body: MedicationLogIn, user_id: int = UserId) -> dict[str, Any]:
    row = repo.log_medication(user_id, med_id, body)
    if row is None:
        raise HTTPException(404)
    return row


# ---- conditions / allergies / providers / encounters ----------------------

@router.get("/conditions")
def list_conditions(user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_simple("conditions", user_id, order="created_at DESC")


@router.post("/conditions", status_code=201)
def create_condition(body: ConditionIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_simple("conditions", user_id, body.model_dump())


@router.delete("/conditions/{row_id}", status_code=204)
def delete_condition(row_id: int, user_id: int = UserId) -> None:
    if not repo.delete_row("conditions", row_id, user_id):
        raise HTTPException(404)


@router.get("/allergies")
def list_allergies(user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_simple("allergies", user_id, order="substance")


@router.post("/allergies", status_code=201)
def create_allergy(body: AllergyIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_simple("allergies", user_id, body.model_dump())


@router.delete("/allergies/{row_id}", status_code=204)
def delete_allergy(row_id: int, user_id: int = UserId) -> None:
    if not repo.delete_row("allergies", row_id, user_id):
        raise HTTPException(404)


@router.get("/providers")
def list_providers(user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_simple("providers", user_id, order="name")


@router.post("/providers", status_code=201)
def create_provider(body: ProviderIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_simple("providers", user_id, body.model_dump())


@router.get("/encounters")
def list_encounters(user_id: int = UserId) -> list[dict[str, Any]]:
    return repo.list_simple("encounters", user_id, order="occurred_at DESC")


@router.post("/encounters", status_code=201)
def create_encounter(body: EncounterIn, user_id: int = UserId) -> dict[str, Any]:
    return repo.insert_simple("encounters", user_id, body.model_dump())
