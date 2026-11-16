"""Pydantic request/response models shared by routers and the AI tools."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    birth_date: date | None = None
    sex: Literal["male", "female", "other"] | None = None
    height_cm: float | None = None
    timezone: str | None = None
    goals: list[dict[str, Any]] | None = None
    preferences: dict[str, Any] | None = None
    notes: str | None = None


class ObservationIn(BaseModel):
    kind: str = Field(description="snake_case code, e.g. weight, bp_systolic, steps, ldl")
    value: float | None = None
    unit: str | None = None
    value_text: str | None = None
    observed_at: datetime | None = None
    source: str = "manual"
    meta: dict[str, Any] = Field(default_factory=dict)


class MealItem(BaseModel):
    name: str
    qty: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None


class MealIn(BaseModel):
    description: str
    eaten_at: datetime | None = None
    items: list[MealItem] = Field(default_factory=list)
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    source: str = "manual"
    meta: dict[str, Any] = Field(default_factory=dict)


class WorkoutIn(BaseModel):
    kind: str
    started_at: datetime | None = None
    duration_min: float | None = None
    distance_km: float | None = None
    calories: float | None = None
    avg_hr: float | None = None
    notes: str | None = None
    source: str = "manual"
    meta: dict[str, Any] = Field(default_factory=dict)


class MedicationIn(BaseModel):
    name: str
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    reason: str | None = None
    prescriber: str | None = None
    started_on: date | None = None
    stopped_on: date | None = None
    active: bool = True
    meta: dict[str, Any] = Field(default_factory=dict)


class MedicationLogIn(BaseModel):
    taken_at: datetime | None = None
    skipped: bool = False
    note: str | None = None


class ConditionIn(BaseModel):
    name: str
    status: Literal["active", "resolved", "monitoring", "family_history"] = "active"
    onset_date: date | None = None
    resolved_date: date | None = None
    notes: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AllergyIn(BaseModel):
    substance: str
    reaction: str | None = None
    severity: Literal["mild", "moderate", "severe"] | None = None


class ProviderIn(BaseModel):
    name: str
    specialty: str | None = None
    practice: str | None = None
    phone: str | None = None
    portal_url: str | None = None
    notes: str | None = None


class EncounterIn(BaseModel):
    occurred_at: datetime
    kind: str | None = None
    provider_id: int | None = None
    provider_name: str | None = None
    summary: str | None = None
    follow_ups: list[dict[str, Any]] = Field(default_factory=list)


class InsightIn(BaseModel):
    kind: Literal["briefing", "nudge", "anomaly", "anticipation", "reminder", "question"]
    title: str
    body: str
    severity: Literal["info", "attention", "urgent"] = "info"
    due_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ChatIn(BaseModel):
    message: str
    thread_id: int | None = None
