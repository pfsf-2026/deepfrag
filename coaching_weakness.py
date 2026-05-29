#!/usr/bin/env python3
"""Weakness-detection engine — ranks coaching levers from the metric aggregate.

Deterministic: takes the aggregate from coaching.aggregate() and produces an
ordered list of "levers" (the things to fix), each with the gap, the evidence,
and a confidence. The LLM narrates this — it never invents the diagnosis.

Two baselines per lever:
  - SELF (win-state): compare the player's loss-state to their OWN win-state.
    The strongest signal ("when you win you do X; when you lose you don't").
    Only available if the player has both wins and losses in the window.
  - BENCHMARK (tier): compare to elite-player anchors (derived 2026-05-29 from
    speedball/sane/bogojoker recent wins). Used when there's no win-state, or
    to show absolute ceiling.

Lever value = how much this metric separates wins from losses (self) or how far
below benchmark (tier), normalized so they're rankable on one scale.
"""
from __future__ import annotations

# Elite 1on1 anchors (mean of top players' recent matches, 2026-05-29).
# higher_better=True means a higher value is good.
BENCHMARKS_1ON1 = {
    "ra_control":     {"label": "Red Armor control", "elite": 0.66, "higher_better": True, "fmt": "pct"},
    "stack_at_kill":  {"label": "Stack at your kills", "elite": 194, "higher_better": True, "fmt": "num"},
    "pct_stacked":    {"label": "% time stacked", "elite": 0.76, "higher_better": True, "fmt": "pct"},
    "restack_sec":    {"label": "Restack time after death", "elite": 8.0, "higher_better": False, "fmt": "sec"},
    "enemy_stack_at_my_death": {"label": "Enemy stack when you die", "elite": 120, "higher_better": False, "fmt": "num"},
}

# Map a benchmark key -> how to pull win/loss/all from the aggregate.
def _extract(agg: dict):
    ic = agg.get("item_control", {})
    return {
        "ra_control":   agg_split(ic.get("ra", {})),
        "stack_at_kill": agg.get("stack_at_kill", {}),
        "pct_stacked":  agg.get("pct_stacked", {}),
        "restack_sec":  agg.get("restack_avg_sec", {}),
        "enemy_stack_at_my_death": agg.get("enemy_stack_at_my_death", {}),
    }


def agg_split(d: dict) -> dict:
    # item_control entries already use win/loss/all keys
    return {"win": d.get("win"), "loss": d.get("loss"), "all": d.get("all")}


def _fmt(v, kind):
    if v is None:
        return "—"
    if kind == "pct":
        return f"{round(v * 100)}%"
    if kind == "sec":
        return f"{v:.1f}s"
    return f"{round(v)}"


def detect(agg: dict, mode: str = "1on1") -> dict:
    """Return {levers: [...], has_win_baseline: bool, summary_stat: {...}}."""
    if mode != "1on1":
        # Team-mode benchmarks not derived yet.
        return {"levers": [], "has_win_baseline": False,
                "note": f"coaching benchmarks only calibrated for 1on1 (mode={mode})"}

    data = _extract(agg)
    has_win = (agg.get("wins", 0) > 0 and agg.get("losses", 0) > 0)
    levers = []

    for key, bm in BENCHMARKS_1ON1.items():
        d = data.get(key, {})
        win, loss, allv = d.get("win"), d.get("loss"), d.get("all")
        hb = bm["higher_better"]

        # SELF gap: how much better is win-state than loss-state?
        self_gap = None
        if has_win and win is not None and loss is not None:
            self_gap = (win - loss) if hb else (loss - win)  # positive = wins are "better"

        # BENCHMARK gap: how far is the player's typical (all, or loss if no win) from elite?
        ref = allv if allv is not None else loss
        bench_gap = None
        if ref is not None:
            bench_gap = (bm["elite"] - ref) if hb else (ref - bm["elite"])  # positive = below elite

        # Skip levers we can't evaluate at all.
        if self_gap is None and bench_gap is None:
            continue

        # Normalize to a 0-100ish priority. Self-gap dominates when present
        # (it's the strongest signal); benchmark gap is the fallback / ceiling.
        # Express each as a fraction of the elite value so they're comparable.
        base = abs(bm["elite"]) or 1
        self_score = (self_gap / base) if self_gap is not None else 0
        bench_score = (bench_gap / base) if bench_gap is not None else 0
        # Only count gaps in the "needs improvement" direction (positive).
        priority = max(self_score, 0) * 1.5 + max(bench_score, 0)  # weight self higher

        levers.append({
            "key": key,
            "label": bm["label"],
            "fmt": bm["fmt"],
            "win": _fmt(win, bm["fmt"]) if has_win else None,
            "loss": _fmt(loss, bm["fmt"]) if has_win else None,
            "you": _fmt(ref, bm["fmt"]),
            "elite": _fmt(bm["elite"], bm["fmt"]),
            "self_gap": round(self_gap, 3) if self_gap is not None else None,
            "below_benchmark": (bench_gap is not None and bench_gap > 0),
            "priority": round(priority, 3),
        })

    levers.sort(key=lambda x: x["priority"], reverse=True)
    return {
        "levers": levers,
        "has_win_baseline": has_win,
        "matches_analyzed": agg.get("matches_analyzed", 0),
        "record": {"wins": agg.get("wins", 0), "losses": agg.get("losses", 0)},
    }
