"""Document ingestion: a PDF or image goes to Claude once, comes back as a typed
ExtractedDocument, and is fanned out into observations, medications,
conditions and an encounter. The raw extraction is kept on the document row.
"""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .. import repo
from ..config import settings
from ..observations import KINDS
from ..schemas import ConditionIn, MedicationIn, ObservationIn
from .client import client
from .prompts import EXTRACT_SYSTEM

log = logging.getLogger("health.ingest")

CANONICAL_LAB_KINDS = [k.code for k in KINDS.values() if k.category in ("lab", "vital", "body")]


class LabResult(BaseModel):
    name: str = Field(description="test name exactly as printed")
    value: float | None = Field(description="numeric value; null if qualitative")
    value_text: str | None = Field(description="qualitative result or the printed value when not numeric")
    unit: str | None
    reference_range: str | None
    flag: str | None = Field(description="H, L, HH, LL, A or null")
    canonical_kind: str | None = Field(description="one of the provided canonical codes, or null")
    collected_at: str | None = Field(description="ISO 8601 date or datetime of collection if printed")


class Medication(BaseModel):
    name: str
    dose: str | None
    frequency: str | None
    route: str | None
    reason: str | None
    status: Literal["new", "continued", "changed", "stopped", "unknown"]


class Diagnosis(BaseModel):
    name: str
    status: Literal["active", "resolved", "monitoring", "history", "rule_out"]
    icd10: str | None


class FollowUp(BaseModel):
    what: str
    due: str | None = Field(description="ISO date or a phrase like 'in 3 months'")


class Vital(BaseModel):
    canonical_kind: str = Field(description="weight, bp_systolic, bp_diastolic, heart_rate, body_temperature, spo2, bmi, height... ")
    value: float
    unit: str | None


class ExtractedDocument(BaseModel):
    kind: Literal["lab_report", "visit_note", "imaging", "prescription", "discharge", "insurance", "other"]
    document_date: str | None = Field(description="ISO date of the visit/collection/report")
    provider_name: str | None
    facility: str | None
    patient_name: str | None
    summary: str = Field(description="3-6 plain-language sentences a patient would want: what was done, key findings, what happens next")
    key_findings: list[str] = Field(description="short bullet-style findings, including anything flagged abnormal")
    lab_results: list[LabResult]
    vitals: list[Vital]
    medications: list[Medication]
    diagnoses: list[Diagnosis]
    follow_ups: list[FollowUp]


def extract(path: Path, media_type: str) -> ExtractedDocument:
    data = base64.standard_b64encode(path.read_bytes()).decode()
    if media_type == "application/pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    elif media_type.startswith("image/"):
        block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    else:
        text = path.read_text(errors="replace")
        block = {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text}}

    response = client().messages.parse(
        model=settings.fast_model,
        max_tokens=16000,
        system=EXTRACT_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                block,
                {"type": "text", "text": "Canonical codes for lab_results.canonical_kind and vitals: "
                                         + ", ".join(CANONICAL_LAB_KINDS) + ".\nExtract this document."},
            ],
        }],
        output_format=ExtractedDocument,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the model declined to process this document")
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError("no structured output returned")
    return parsed


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date() if "T" in value else date.fromisoformat(value[:10])
    except ValueError:
        return None


def process_document(user_id: int, doc_id: int) -> None:
    """Run extraction for one document and write results. Safe to re-run."""
    doc = repo.get_row("documents", doc_id, user_id)
    if doc is None:
        return
    repo.update_document(doc_id, user_id, {"status": "processing", "error": None})
    try:
        path = settings.data_dir / doc["storage_key"]
        ex = extract(path, doc["media_type"])
        doc_date = _parse_date(ex.document_date)
        observed_default = datetime.combine(doc_date or doc["uploaded_at"].date(), time(12, 0), tzinfo=timezone.utc)

        # Re-runs: drop what this document produced before, then write fresh.
        from ..db import conn
        with conn() as c:
            c.execute("DELETE FROM observations WHERE document_id = %s AND user_id = %s", (doc_id, user_id))
            c.execute("DELETE FROM medications WHERE document_id = %s AND user_id = %s", (doc_id, user_id))
            c.execute("DELETE FROM conditions WHERE document_id = %s AND user_id = %s", (doc_id, user_id))
            c.execute("DELETE FROM encounters WHERE document_id = %s AND user_id = %s", (doc_id, user_id))

        for lab in ex.lab_results:
            kind = lab.canonical_kind if lab.canonical_kind in KINDS else "lab:" + lab.name.strip().lower().replace(" ", "_")
            when = lab.collected_at
            observed_at = observed_default
            if when:
                try:
                    dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
                    observed_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            repo.insert_observation(user_id, ObservationIn(
                kind=kind, value=lab.value, unit=lab.unit, value_text=lab.value_text, observed_at=observed_at,
                source=f"document:{doc_id}",
                meta={"name": lab.name, "reference_range": lab.reference_range, "flag": lab.flag},
            ), document_id=doc_id)
        for v in ex.vitals:
            if v.canonical_kind in KINDS:
                repo.insert_observation(user_id, ObservationIn(
                    kind=v.canonical_kind, value=v.value, unit=v.unit, observed_at=observed_default,
                    source=f"document:{doc_id}", meta={}), document_id=doc_id)
        for m in ex.medications:
            repo.insert_medication(user_id, MedicationIn(
                name=m.name, dose=m.dose, frequency=m.frequency, route=m.route, reason=m.reason,
                prescriber=ex.provider_name, started_on=doc_date if m.status == "new" else None,
                stopped_on=doc_date if m.status == "stopped" else None, active=m.status != "stopped",
                meta={"status_in_document": m.status}), document_id=doc_id)
        for d in ex.diagnoses:
            status = {"active": "active", "resolved": "resolved", "monitoring": "monitoring",
                      "history": "resolved", "rule_out": "monitoring"}[d.status]
            fields = ConditionIn(name=d.name, status=status, meta={"icd10": d.icd10, "as_stated": d.status}).model_dump()  # type: ignore[arg-type]
            fields["document_id"] = doc_id
            repo.insert_simple("conditions", user_id, fields)
        repo.insert_simple("encounters", user_id, {
            "occurred_at": observed_default, "kind": ex.kind, "provider_name": ex.provider_name,
            "summary": ex.summary, "follow_ups": [f.model_dump() for f in ex.follow_ups], "document_id": doc_id,
        })
        repo.update_document(doc_id, user_id, {
            "status": "processed", "kind": ex.kind, "document_date": doc_date, "provider_name": ex.provider_name,
            "summary": ex.summary, "extracted": ex.model_dump(), "processed_at": datetime.now(timezone.utc),
        })
    except Exception as e:  # noqa: BLE001
        log.exception("document %s failed", doc_id)
        repo.update_document(doc_id, user_id, {"status": "failed", "error": f"{type(e).__name__}: {e}"[:2000]})
