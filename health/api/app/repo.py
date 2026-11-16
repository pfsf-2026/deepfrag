"""Data access. Plain SQL through psycopg3; every function takes user_id first.

Routers and AI tools both go through here, so authorization lives in one place:
no function in this module reads or writes a row without `user_id` in the WHERE.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import conn, jsonb
from .observations import to_canonical
from .schemas import MealIn, MedicationIn, MedicationLogIn, ObservationIn, WorkoutIn

_SIMPLE_TABLES = {"conditions", "allergies", "providers", "encounters", "observations", "meals", "workouts", "medications", "insights", "documents"}
_JSON_COLUMNS = {"meta", "items", "goals", "preferences", "follow_ups", "data", "extracted"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _params(values: dict[str, Any]) -> dict[str, Any]:
    return {k: (jsonb(v) if k in _JSON_COLUMNS and v is not None else v) for k, v in values.items()}


# ---- profile ---------------------------------------------------------------

def get_profile(user_id: int) -> dict[str, Any]:
    with conn() as c:
        row = c.execute(
            "SELECT p.*, u.display_name, u.email FROM profiles p JOIN users u ON u.id = p.user_id WHERE p.user_id = %s",
            (user_id,),
        ).fetchone()
        if row is None:
            c.execute("INSERT INTO profiles (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            row = c.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,)).fetchone()
    return dict(row)


def update_profile(user_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    if fields:
        sets = ", ".join(f"{k} = %({k})s" for k in fields)
        with conn() as c:
            c.execute(
                f"UPDATE profiles SET {sets}, updated_at = now() WHERE user_id = %(user_id)s",
                {**_params(fields), "user_id": user_id},
            )
    return get_profile(user_id)


# ---- observations ----------------------------------------------------------

def insert_observation(user_id: int, o: ObservationIn, document_id: int | None = None) -> dict[str, Any]:
    value, unit = (to_canonical(o.kind, o.value, o.unit) if o.value is not None else (None, o.unit))
    with conn() as c:
        row = c.execute(
            """INSERT INTO observations (user_id, kind, value, unit, value_text, observed_at, source, document_id, meta)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, kind, observed_at, source) WHERE source <> 'manual'
               DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit, value_text = EXCLUDED.value_text, meta = EXCLUDED.meta
               RETURNING *""",
            (user_id, o.kind, value, unit, o.value_text, o.observed_at or _now(), o.source, document_id, jsonb(o.meta)),
        ).fetchone()
    return dict(row)


def list_observations(user_id: int, kind: str | None, since: datetime, limit: int = 500) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT * FROM observations
               WHERE user_id = %s AND observed_at >= %s AND (%s::text IS NULL OR kind = %s)
               ORDER BY observed_at DESC LIMIT %s""",
            (user_id, since, kind, kind, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def latest_observations(user_id: int) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT DISTINCT ON (kind) * FROM observations
               WHERE user_id = %s ORDER BY kind, observed_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def summarize_observations(user_id: int, kind: str, since: datetime) -> dict[str, Any]:
    with conn() as c:
        row = c.execute(
            """SELECT count(*) AS n, min(value) AS min, max(value) AS max, avg(value) AS mean,
                      percentile_cont(0.5) WITHIN GROUP (ORDER BY value) AS median,
                      min(observed_at) AS first_at, max(observed_at) AS last_at,
                      (array_agg(value ORDER BY observed_at DESC))[1] AS latest,
                      (array_agg(unit ORDER BY observed_at DESC))[1] AS unit
               FROM observations WHERE user_id = %s AND kind = %s AND observed_at >= %s AND value IS NOT NULL""",
            (user_id, kind, since),
        ).fetchone()
        daily = c.execute(
            """SELECT date_trunc('day', observed_at)::date AS day, avg(value) AS mean, sum(value) AS total, count(*) AS n
               FROM observations WHERE user_id = %s AND kind = %s AND observed_at >= %s AND value IS NOT NULL
               GROUP BY 1 ORDER BY 1""",
            (user_id, kind, since),
        ).fetchall()
    out = dict(row)
    out["kind"] = kind
    out["daily"] = [dict(d) for d in daily]
    return out


# ---- meals / workouts ------------------------------------------------------

def insert_meal(user_id: int, m: MealIn) -> dict[str, Any]:
    items = [i.model_dump() for i in m.items]
    # Totals default to the sum of the items when not given explicitly.
    def total(field: str) -> float | None:
        explicit = getattr(m, field)
        if explicit is not None:
            return explicit
        vals = [i[field] for i in items if i.get(field) is not None]
        return sum(vals) if vals else None
    with conn() as c:
        row = c.execute(
            """INSERT INTO meals (user_id, eaten_at, description, items, calories, protein_g, carbs_g, fat_g, fiber_g, source, meta)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (user_id, m.eaten_at or _now(), m.description, jsonb(items), total("calories"), total("protein_g"),
             total("carbs_g"), total("fat_g"), total("fiber_g"), m.source, jsonb(m.meta)),
        ).fetchone()
    return dict(row)


def list_meals(user_id: int, since: datetime, limit: int = 500) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM meals WHERE user_id = %s AND eaten_at >= %s ORDER BY eaten_at DESC LIMIT %s",
            (user_id, since, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_workout(user_id: int, w: WorkoutIn) -> dict[str, Any]:
    with conn() as c:
        row = c.execute(
            """INSERT INTO workouts (user_id, started_at, duration_min, kind, distance_km, calories, avg_hr, notes, source, meta)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, started_at, source) WHERE source <> 'manual'
               DO UPDATE SET duration_min = EXCLUDED.duration_min, kind = EXCLUDED.kind, distance_km = EXCLUDED.distance_km,
                             calories = EXCLUDED.calories, avg_hr = EXCLUDED.avg_hr, meta = EXCLUDED.meta
               RETURNING *""",
            (user_id, w.started_at or _now(), w.duration_min, w.kind, w.distance_km, w.calories, w.avg_hr, w.notes, w.source, jsonb(w.meta)),
        ).fetchone()
    return dict(row)


def list_workouts(user_id: int, since: datetime, limit: int = 500) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM workouts WHERE user_id = %s AND started_at >= %s ORDER BY started_at DESC LIMIT %s",
            (user_id, since, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---- medications -----------------------------------------------------------

def insert_medication(user_id: int, m: MedicationIn, document_id: int | None = None) -> dict[str, Any]:
    with conn() as c:
        row = c.execute(
            """INSERT INTO medications (user_id, name, dose, route, frequency, reason, prescriber, started_on, stopped_on, active, document_id, meta)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (user_id, m.name, m.dose, m.route, m.frequency, m.reason, m.prescriber, m.started_on, m.stopped_on,
             m.active, document_id, jsonb(m.meta)),
        ).fetchone()
    return dict(row)


def list_medications(user_id: int, active_only: bool = True) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT m.*, (SELECT max(taken_at) FROM medication_logs l WHERE l.medication_id = m.id AND NOT l.skipped) AS last_taken_at
               FROM medications m WHERE m.user_id = %s AND (NOT %s OR m.active) ORDER BY m.active DESC, m.name""",
            (user_id, active_only),
        ).fetchall()
    return [dict(r) for r in rows]


def update_medication(user_id: int, med_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        fields = {"active": True}
    sets = ", ".join(f"{k} = %({k})s" for k in fields)
    with conn() as c:
        row = c.execute(
            f"UPDATE medications SET {sets}, updated_at = now() WHERE id = %(id)s AND user_id = %(user_id)s RETURNING *",
            {**_params(fields), "id": med_id, "user_id": user_id},
        ).fetchone()
    return dict(row) if row else None


def log_medication(user_id: int, med_id: int, entry: MedicationLogIn) -> dict[str, Any] | None:
    with conn() as c:
        owned = c.execute("SELECT 1 FROM medications WHERE id = %s AND user_id = %s", (med_id, user_id)).fetchone()
        if not owned:
            return None
        row = c.execute(
            "INSERT INTO medication_logs (medication_id, taken_at, skipped, note) VALUES (%s, %s, %s, %s) RETURNING *",
            (med_id, entry.taken_at or _now(), entry.skipped, entry.note),
        ).fetchone()
    return dict(row)


# ---- generic helpers for the small tables ----------------------------------

def list_simple(table: str, user_id: int, order: str = "id DESC", limit: int = 500) -> list[dict[str, Any]]:
    assert table in _SIMPLE_TABLES
    with conn() as c:
        rows = c.execute(f"SELECT * FROM {table} WHERE user_id = %s ORDER BY {order} LIMIT %s", (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def insert_simple(table: str, user_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    assert table in _SIMPLE_TABLES
    fields = {k: v for k, v in fields.items() if v is not None}
    cols = ["user_id", *fields]
    placeholders = ", ".join(f"%({c})s" for c in cols)
    with conn() as c:
        row = c.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) RETURNING *",
            {**_params(fields), "user_id": user_id},
        ).fetchone()
    return dict(row)


def get_row(table: str, row_id: int, user_id: int) -> dict[str, Any] | None:
    assert table in _SIMPLE_TABLES
    with conn() as c:
        row = c.execute(f"SELECT * FROM {table} WHERE id = %s AND user_id = %s", (row_id, user_id)).fetchone()
    return dict(row) if row else None


def delete_row(table: str, row_id: int, user_id: int) -> bool:
    assert table in _SIMPLE_TABLES
    with conn() as c:
        cur = c.execute(f"DELETE FROM {table} WHERE id = %s AND user_id = %s", (row_id, user_id))
        return cur.rowcount > 0


# ---- documents -------------------------------------------------------------

def insert_document(user_id: int, **fields: Any) -> dict[str, Any]:
    cols = ["user_id", *fields]
    placeholders = ", ".join(f"%({c})s" for c in cols)
    with conn() as c:
        row = c.execute(
            f"""INSERT INTO documents ({', '.join(cols)}) VALUES ({placeholders})
                ON CONFLICT (user_id, sha256) DO UPDATE SET filename = EXCLUDED.filename
                RETURNING *, (xmax = 0) AS inserted""",
            {**_params(fields), "user_id": user_id},
        ).fetchone()
    return dict(row)


def update_document(doc_id: int, user_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    sets = ", ".join(f"{k} = %({k})s" for k in fields)
    with conn() as c:
        row = c.execute(
            f"UPDATE documents SET {sets} WHERE id = %(id)s AND user_id = %(user_id)s RETURNING *",
            {**_params(fields), "id": doc_id, "user_id": user_id},
        ).fetchone()
    return dict(row) if row else None


def search_documents(user_id: int, query: str, limit: int = 10) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT id, filename, kind, document_date, provider_name, status, summary, uploaded_at
               FROM documents WHERE user_id = %s
                 AND (filename ILIKE %s OR summary ILIKE %s OR provider_name ILIKE %s OR extracted::text ILIKE %s)
               ORDER BY document_date DESC NULLS LAST, uploaded_at DESC LIMIT %s""",
            (user_id, f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---- chat ------------------------------------------------------------------

def create_thread(user_id: int, title: str | None) -> dict[str, Any]:
    with conn() as c:
        row = c.execute("INSERT INTO chat_threads (user_id, title) VALUES (%s, %s) RETURNING *", (user_id, title)).fetchone()
    return dict(row)


def get_thread(user_id: int, thread_id: int) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM chat_threads WHERE id = %s AND user_id = %s", (thread_id, user_id)).fetchone()
    return dict(row) if row else None


def list_threads(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM chat_threads WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s", (user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def thread_messages(thread_id: int) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT id, role, content, created_at FROM chat_messages WHERE thread_id = %s ORDER BY id", (thread_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def append_message(thread_id: int, role: str, content: Any) -> None:
    with conn() as c:
        c.execute("INSERT INTO chat_messages (thread_id, role, content) VALUES (%s, %s, %s)", (thread_id, role, jsonb(content)))
        c.execute("UPDATE chat_threads SET updated_at = now() WHERE id = %s", (thread_id,))


# ---- insights --------------------------------------------------------------

def list_insights(user_id: int, include_dismissed: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            """SELECT * FROM insights WHERE user_id = %s AND (%s OR dismissed_at IS NULL)
               ORDER BY CASE severity WHEN 'urgent' THEN 0 WHEN 'attention' THEN 1 ELSE 2 END, created_at DESC LIMIT %s""",
            (user_id, include_dismissed, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_insight(user_id: int, insight_id: int, column: str) -> dict[str, Any] | None:
    assert column in ("acknowledged_at", "dismissed_at")
    with conn() as c:
        row = c.execute(
            f"UPDATE insights SET {column} = now() WHERE id = %s AND user_id = %s RETURNING *", (insight_id, user_id)
        ).fetchone()
    return dict(row) if row else None
