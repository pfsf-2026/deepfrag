from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_profile_roundtrip(client):
    r = client.put("/api/profile", json={"height_cm": 180.5, "timezone": "America/New_York", "goals": [{"kind": "weight", "target": 80, "unit": "kg"}]})
    assert r.status_code == 200
    p = client.get("/api/profile").json()
    assert float(p["height_cm"]) == 180.5 and p["timezone"] == "America/New_York" and p["goals"][0]["target"] == 80


def test_observations_convert_and_summarize(client):
    now = datetime.now(timezone.utc)
    for i, lb in enumerate([190.0, 189.2, 188.6]):
        r = client.post("/api/observations", json={"kind": "weight", "value": lb, "unit": "lb", "observed_at": (now - timedelta(days=2 - i)).isoformat()})
        assert r.status_code == 201, r.text
        assert r.json()["unit"] == "kg"
    rows = client.get("/api/observations", params={"kind": "weight", "days": 7}).json()
    assert len(rows) == 3 and abs(float(rows[0]["value"]) - 188.6 * 0.45359237) < 1e-6
    s = client.get("/api/observations/summary", params={"kind": "weight", "days": 7}).json()
    assert s["n"] == 3 and len(s["daily"]) == 3 and float(s["min"]) < float(s["max"])
    latest = client.get("/api/observations/latest").json()
    assert any(r["kind"] == "weight" for r in latest)
    # value or value_text required
    assert client.post("/api/observations", json={"kind": "urine_protein"}).status_code == 422


def test_meal_totals_from_items(client):
    r = client.post("/api/meals", json={
        "description": "oats and eggs",
        "items": [{"name": "oats", "calories": 150, "protein_g": 5}, {"name": "2 eggs", "calories": 140, "protein_g": 12}],
    })
    assert r.status_code == 201
    m = r.json()
    assert float(m["calories"]) == 290 and float(m["protein_g"]) == 17 and m["fat_g"] is None
    assert len(client.get("/api/meals").json()) >= 1


def test_workouts_medications_conditions(client):
    assert client.post("/api/workouts", json={"kind": "run", "duration_min": 32, "distance_km": 5.2}).status_code == 201
    med = client.post("/api/medications", json={"name": "Atorvastatin", "dose": "10 mg", "frequency": "nightly"}).json()
    assert med["active"] is True
    log = client.post(f"/api/medications/{med['id']}/log", json={}).json()
    assert log["medication_id"] == med["id"]
    meds = client.get("/api/medications").json()
    assert meds[0]["last_taken_at"] is not None
    stopped = client.patch(f"/api/medications/{med['id']}", json={"name": "Atorvastatin", "active": False}).json()
    assert stopped["active"] is False
    assert client.get("/api/medications").json() == []
    assert len(client.get("/api/medications", params={"active_only": "false"}).json()) == 1
    c = client.post("/api/conditions", json={"name": "Hyperlipidemia", "meta": {"icd10": "E78.5"}}).json()
    assert c["meta"]["icd10"] == "E78.5"
    assert client.post("/api/allergies", json={"substance": "penicillin", "severity": "severe"}).status_code == 201
    assert client.delete(f"/api/conditions/{c['id']}").status_code == 204
    assert client.delete(f"/api/conditions/{c['id']}").status_code == 404


def test_insights_lifecycle(client):
    r = client.post("/api/insights", json={"kind": "reminder", "title": "Repeat lipid panel", "body": "Due in March", "severity": "attention"})
    assert r.status_code == 201
    iid = r.json()["id"]
    assert any(i["id"] == iid for i in client.get("/api/insights").json())
    assert client.post(f"/api/insights/{iid}/dismiss").status_code == 200
    assert not any(i["id"] == iid for i in client.get("/api/insights").json())
    assert any(i["id"] == iid for i in client.get("/api/insights", params={"include_dismissed": "true"}).json())


def test_document_upload_dedupes_and_queues(client, monkeypatch):
    calls = []
    import app.routers.documents as docs
    monkeypatch.setattr(docs, "process_document", lambda uid, did: calls.append((uid, did)))
    pdf = b"%PDF-1.4 fake"
    r = client.post("/api/documents", files={"file": ("labs.pdf", pdf, "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "pending" and "storage_key" not in doc
    r2 = client.post("/api/documents", files={"file": ("labs-copy.pdf", pdf, "application/pdf")})
    assert r2.json()["id"] == doc["id"]
    assert calls and calls[0] == (1, doc["id"])
    assert client.post("/api/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
    f = client.get(f"/api/documents/{doc['id']}/file")
    assert f.status_code == 200 and f.content == pdf
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204


def test_chat_without_api_key_reports_error(client):
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200
    events = [l for l in r.text.split("\n\n") if l.startswith("data:")]
    assert events[0].startswith('data: {"type": "thread"')
    assert "error" in events[-1]
    threads = client.get("/api/chat/threads").json()
    assert threads and threads[0]["title"] == "hi"
    t = client.get(f"/api/chat/threads/{threads[0]['id']}").json()
    assert t["messages"][0] == {**t["messages"][0], "role": "user", "text": "hi"}


def test_auth_token_enforced(client, monkeypatch):
    monkeypatch.setenv("HEALTH_APP_TOKEN", "s3cret")
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/profile", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/profile", headers={"Authorization": "Bearer s3cret"}).status_code == 200
