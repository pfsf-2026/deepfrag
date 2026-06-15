#!/usr/bin/env python3
"""
FragBot tracker — turn bot demos into a human-likeness evidence table.

Pipeline (per the komodo lab pattern, but scored on DeepFrag human-likeness
dials instead of raw bunnyhop speed / KTX combat):

  demo(s).mvd  ->  qw-analyze (buckets 13ms + full)  ->  dials.compute_card
              ->  append to runs/ledger.json (deltas vs previous run by label)
              ->  render out/<run_id>.html  (Xantam-style table)

Usage:
  ./score_bot.py score --demo A.mvd [--demo B.mvd ...] --mode 1on1|2on2|4on4 \
      [--roster roster.json] [--run-id ID] [--label "fragbot-v1 @ frogbot-10"]

  roster.json (optional) maps demo player-name -> metadata:
    {"/ bro": {"label":"frogbot-10","build":"frogbot","skill":10,"team":"red","tracked":true},
     "fragbot": {"label":"fragbot-v1","build":"fragbot-v1","skill":null,"team":"blue","tracked":true}}
  Without a roster: every bot (has a skill field) is tracked; label = name.

Multiple --demo files are pooled into ONE run card per player (stable 1v1 cards;
or the set of maps in a 4on4 session).

Env: MVDA_BSP_DIR must point at a BSP dir (height/RJ/airborne dials need it).
     QW_ANALYZE overrides the qw-analyze binary path (default: ./qw-analyze).
"""
import argparse, json, os, subprocess, sys, tempfile, datetime, statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
import dials  # noqa: E402

QW = os.environ.get("QW_ANALYZE", str(HERE / "qw-analyze"))
LEDGER = HERE / "runs" / "ledger.json"
OUT = HERE / "out"

# dials shown in the evidence table, in order. (name, header, lower_is_more_human)
DIAL_COLS = [
    ("humanlikeness", "Human%", False),
    ("coupling_52ms", "Coupling", False),
    ("rocketjumps_min", "RJ/min", False),
    ("airborne_pct", "Air%", False),
    ("strafe_aim_fast", "Strafe-aim", False),
    ("speed_median", "Speed", False),
    ("lg_pct", "LG%", True),
    ("sg_pct", "SG%", True),
    ("reaction_acq_ms", "React ms", True),
    ("frags", "Frags", False),
    ("deaths", "Deaths", False),
    ("dmg_eff", "Eff", False),
]


def run_qw(demo, cache):
    """Produce buckets + full JSON for a demo, cached by basename."""
    base = Path(demo).name
    bpath = cache / f"{base}.buckets.json"
    fpath = cache / f"{base}.full.json"
    if not bpath.exists():
        with open(bpath, "w") as f:
            subprocess.run([QW, "-view", "buckets", "-bucket", "13ms",
                            "-fields", "pos,view,vel,hgt", demo], stdout=f, check=True)
    if not fpath.exists():
        with open(fpath, "w") as f:
            subprocess.run([QW, "-view", "full", demo], stdout=f, check=True)
    return str(bpath), str(fpath)


def pool_cards(cards):
    """Pool per-demo cards into one run card by combining RAW samples — not by
    averaging per-demo rates (which would let a tiny demo skew everything)."""
    out = {"player": cards[0]["player"], "mode": cards[0]["mode"],
           "is_bot": cards[0].get("is_bot"), "skill": cards[0].get("skill"),
           "demos": len(cards)}
    # coupling: concatenate raw (heading-turn, view-turn) pairs, then one Pearson
    for key in ("coupling_13ms", "coupling_52ms"):
        hh, vv = [], []
        for c in cards:
            ph, pv = c.get("_" + key, ([], []))
            hh += ph; vv += pv
        r = dials._pearson(hh, vv)
        out[key] = round(r, 3) if r is not None else None
    # airborne: sum air / sum alive frames
    air = sum(c.get("_air", (0, 0))[0] for c in cards)
    alive = sum(c.get("_air", (0, 0))[1] for c in cards)
    out["airborne_pct"] = round(100 * air / alive, 1) if alive else None
    # accuracy: sum hits / sum attacks per weapon
    for key in ("sg_pct", "lg_pct", "rl_pct"):
        a = sum(c.get("_acc", {}).get(key, (0, 0))[0] for c in cards)
        h = sum(c.get("_acc", {}).get(key, (0, 0))[1] for c in cards)
        out[key] = round(100 * h / a, 1) if a else None
    # strafe-aim: sum fast / sum total damage
    saf = sum(c.get("_sa", (0, 0))[0] for c in cards)
    sat = sum(c.get("_sa", (0, 0))[1] for c in cards)
    out["strafe_aim_fast"] = round(100 * saf / sat, 1) if sat else None
    # rocket-jumps: sum count / sum seconds
    rj = sum(c.get("_rj", (0, 0))[0] for c in cards)
    secs = sum(c.get("_rj", (0, 0))[1] for c in cards)
    out["rocketjumps"] = rj
    out["rocketjumps_min"] = round(rj / (secs / 60.0), 2) if secs else None
    # speed: median of all per-frame speeds
    allspd = [s for c in cards for s in c.get("_speeds", [])]
    out["speed_median"] = round(dials._median(allspd)) if allspd else None
    # reaction: median of all confirmed acquisitions
    allr = [r for c in cards for r in c.get("_react", [])]
    out["reaction_acq_ms"] = dials._median(allr)
    out["reaction_samples"] = len(allr)
    # damage / frags: sum, then derive efficiency
    dg = sum(c.get("dmg_given", 0) or 0 for c in cards)
    dt = sum(c.get("dmg_taken", 0) or 0 for c in cards)
    out["dmg_given"], out["dmg_taken"] = dg, dt
    out["dmg_eff"] = round(dg / dt, 2) if dt else None
    for k in ("frags", "deaths"):
        v = [c[k] for c in cards if c.get(k) is not None]
        out[k] = sum(v) if v else None
    pg = [c["ping"] for c in cards if c.get("ping") is not None]
    out["ping"] = round(statistics.mean(pg)) if pg else None
    return out


def build_run(demos, mode, roster, run_id, label):
    cache = Path(tempfile.gettempdir()) / "fragbot_cache"
    cache.mkdir(exist_ok=True)
    # per player: list of per-demo cards
    by_player = {}
    map_names = []
    for demo in demos:
        bpath, fpath = run_qw(demo, cache)
        d = dials.load(bpath, fpath)
        map_names.append(d["full"].get("match", {}).get("map") or d["full"].get("demoInfo", {}).get("map"))
        names = {p["name"] for p in d["full"].get("demoInfo", {}).get("players", [])}
        for nm in names:
            meta = roster.get(nm, {})
            if roster and not meta.get("tracked", False):
                continue
            card = dials.compute_card(d, nm, mode)
            if "error" in card:
                continue
            by_player.setdefault(nm, []).append(card)
    players = []
    for nm, cards in by_player.items():
        meta = roster.get(nm, {})
        if not roster and not cards[0].get("is_bot"):
            continue  # default: only track bots
        pooled = pool_cards(cards)
        pooled["label"] = meta.get("label") or nm
        pooled["build"] = meta.get("build") or ("frogbot" if pooled.get("skill") is not None else "?")
        pooled["team"] = meta.get("team")
        pooled["role"] = meta.get("role")
        pooled["humanlikeness"] = dials.humanlikeness(pooled)["overall"]
        players.append(pooled)
    players.sort(key=lambda p: (p.get("team") or "", -(p.get("humanlikeness") or 0)))
    return {
        "run_id": run_id,
        "label": label,
        "mode": mode,
        "maps": sorted({m for m in map_names if m}),
        "demos": [Path(x).name for x in demos],
        "players": players,
    }


def attach_deltas(run, ledger):
    """For each player, compute deltas vs the most recent prior run's same label."""
    prev = None
    for r in reversed(ledger):
        if r["mode"] == run["mode"]:
            prev = r
            break
    prev_by_label = {p["label"]: p for p in prev["players"]} if prev else {}
    for p in run["players"]:
        pv = prev_by_label.get(p["label"])
        p["deltas"] = {}
        if not pv:
            continue
        for k, _, _ in DIAL_COLS:
            a, b = p.get(k), pv.get(k)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                p["deltas"][k] = round(a - b, 3)
    run["prev_run_id"] = prev["run_id"] if prev else None
    return run


def fmt(name, v):
    if v is None:
        return "—"
    b = dials.BANDS.get(name)
    if b:
        return b["fmt"].format(v)
    if name == "humanlikeness":
        return str(v)
    if isinstance(v, float):
        return f"{v:.2f}" if name == "dmg_eff" else f"{v:.0f}"
    return str(v)


def render_html(run):
    rows = []
    for p in run["players"]:
        tc = {"red": "#c0392b", "blue": "#2471c7"}.get((p.get("team") or "").lower(), "#555")
        bg = {"red": "#fdecea", "blue": "#eaf1fb"}.get((p.get("team") or "").lower(), "#fff")
        cells = []
        for name, _hdr, lower_human in DIAL_COLS:
            v = p.get(name)
            d = (p.get("deltas") or {}).get(name)
            dtxt = ""
            if d is not None and d != 0:
                # color = raw movement only (not a quality judgement) — matches Xantam's note
                col = "#1a9850" if d > 0 else "#c0392b"
                sign = "+" if d > 0 else ""
                dval = f"{d:+.3f}".rstrip("0").rstrip(".") if isinstance(d, float) else f"{sign}{d}"
                dtxt = f"<div style='font-size:10px;color:{col}'>{dval}</div>"
            hl = ""
            if name == "humanlikeness" and isinstance(v, (int, float)):
                shade = int(255 - min(v, 99) * 1.6)
                hl = f"background:rgb({shade},255,{shade});font-weight:700"
            cells.append(f"<td style='text-align:center;{hl}'>{fmt(name, v)}{dtxt}</td>")
        rows.append(
            f"<tr style='background:{bg}'>"
            f"<td style='border-left:4px solid {tc};font-weight:600'>{p['label']}"
            f"<div style='font-size:10px;color:#888'>{p.get('build','')}"
            f"{' · skill '+str(p['skill']) if p.get('skill') is not None else ''}</div></td>"
            + "".join(cells) + "</tr>")
    head = "".join(f"<th style='text-align:center;font-size:11px'>{h}</th>" for _, h, _ in DIAL_COLS)
    return f"""<!doctype html><meta charset=utf-8>
<title>FragBot Evidence — {run['run_id']}</title>
<body style="font-family:-apple-system,Segoe UI,sans-serif;margin:24px;color:#222">
<h1 style="margin:0">FragBot Human-Likeness Evidence</h1>
<p style="color:#666;margin:4px 0 2px">Run <b>{run['run_id']}</b> · {run['label'] or ''} · mode <b>{run['mode']}</b>
 · maps {', '.join(run['maps']) or '?'} · {len(run['demos'])} demo(s)</p>
<p style="color:#888;font-size:12px;margin:0 0 16px">Delta = change vs previous run (same bot label).
Color shows raw movement only — not a quality judgement. Human% = weighted closeness to the human band
(coupling/RJ/strafe-aim weighted highest); 99 = squarely human, ~0 = stock frogbot.</p>
<table style="border-collapse:collapse;width:100%;font-size:13px">
<thead><tr style="border-bottom:2px solid #ccc"><th style='text-align:left'>Bot / build</th>{head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p style="color:#aaa;font-size:11px;margin-top:18px">Source: DeepFrag dial battery (qw-analyze v33) ·
docs/bot_dials_and_calibration.md · frogbot baseline coupling ~0.03, human 0.29–0.47.</p>
</body>"""


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--demo", action="append", required=True)
    s.add_argument("--mode", default="1on1")
    s.add_argument("--roster")
    s.add_argument("--run-id")
    s.add_argument("--label", default="")
    a = ap.parse_args()

    roster = json.load(open(a.roster)) if a.roster else {}
    run_id = a.run_id or datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    ledger = json.load(open(LEDGER)) if LEDGER.exists() else []

    run = build_run(a.demo, a.mode, roster, run_id, a.label)
    run = attach_deltas(run, ledger)
    ledger.append(run)
    LEDGER.parent.mkdir(exist_ok=True)
    json.dump(ledger, open(LEDGER, "w"), indent=1)
    OUT.mkdir(exist_ok=True)
    html_path = OUT / f"{run_id}.html"
    html_path.write_text(render_html(run))

    print(f"run {run_id}: {len(run['players'])} bots, mode {a.mode}, maps {run['maps']}")
    for p in run["players"]:
        print(f"  {p['label']:16} HL={p['humanlikeness']:>3}  "
              f"coup={fmt('coupling_52ms', p.get('coupling_52ms'))}  "
              f"RJ={fmt('rocketjumps_min', p.get('rocketjumps_min'))}  "
              f"air={fmt('airborne_pct', p.get('airborne_pct'))}  "
              f"LG={fmt('lg_pct', p.get('lg_pct'))}  SG={fmt('sg_pct', p.get('sg_pct'))}")
    print(f"HTML: {html_path}")
    print(f"ledger: {LEDGER} ({len(ledger)} runs)")


if __name__ == "__main__":
    main()
