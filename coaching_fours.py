#!/usr/bin/env python3
"""4on4 coach — deterministic engine (levels, gates, lever library, ranking,
one-focus prescriptions and their follow-up grading).

Framework agreed with Peter 2026-09-18 (docs/coaching_4on4.md):

  LEVELS   a player's level is the band of his mean "above average" +/- per game
           over his last 40 fours (LEVEL_WINDOW). Bands were mined from the corpus:
           the lever that separates each band from the next is different at every
           step (L1->L2 reds + damage, L2->L3 death rate + even-fight win rate, L3->L4 quads +
           reds, L4->L5 adjusted kills + stacked DDR), which is the whole reason
           to scaffold. Levels are public on profiles (Peter, 2026-09-18).
  GATES    two metrics per level. Target = the lever's typical value AT THE PROMOTION
           LINE (a regression of the lever on above-average across the active pool,
           read off at the next band's lower edge), never easier than the player's own
           level median and never harder than the next level's median. Peter 2026-09-19:
           the next level's median was too high a bar (0 of 36 players passed both
           gates; half of the players already in the next level failed them). Passing
           both over LEVEL_WINDOW games is "ready to move up"; the level itself still
           comes from above-average, so nobody is promoted on a habit stat alone.
  LEVERS   every demo-derived metric with: direction, the levels it is coached at,
           a map exclusion where the map has no such item, the Quake drill, and the
           unit. The coach only ranks levers active at the player's level (plus the
           next level's gates), which keeps L1 advice about surviving and L5 advice
           about leverage.
  BASELINES self (own wins vs own losses), own level median, next level median;
           reds are computed without e1m2 games (no RA there).
  FOCUS    exactly ONE prescription at a time (Peter): lever + numeric target +
           a 10-game window. The next report grades the previous prescription on
           the games played since it was issued before choosing the next focus.

Pure functions over row dicts (one row per player-game, the columns of
fours_advanced_stats) so the whole thing is testable without a database.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone

LEVEL_WINDOW = 40          # games a level is judged on
LEVEL_MIN_GAMES = 15       # fewer -> "unplaced"
ACTIVE_DAYS = 365          # pool for level medians: 15+ games in the last year
FOCUS_WINDOW_GAMES = 10    # a prescription is graded after this many games
MIN_SPLIT = 5              # wins AND losses needed for the self baseline
RA_EXCLUDED_MAPS = {"e1m2"}
MAP_MIN_GAMES = 8          # games on a map before the per-map card / baselines use it

# Armor and power-up inventory per map (counted from the demos, 2026-09-20). Raw counts
# are not comparable across maps — dm2 has two reds and three yellows — so the coach uses
# SHARES for items: your takes divided by everything taken in that game (even split = 1/8).
MAP_ITEMS = {
    "dm3":     {"ra": 1, "ya": 1, "mh": 3, "quad": 1, "pent": 1, "ring": 1, "rl": 1, "lg": 1},
    "dm2":     {"ra": 2, "ya": 3, "mh": 2, "quad": 1, "rl": 2},
    "e1m2":    {"ra": 0, "ya": 1, "ga": 1, "mh": 1, "quad": 1, "rl": 1},
    "schloss": {"ra": 1, "ya": 2, "mh": 2, "quad": 1, "pent": 1, "ring": 1, "rl": 2},
}
# Map-specific drill notes, shown on the per-map "work on this" card when the lever matches.
MAP_NOTES = {
    "dm3":     {"ra_share": "One red, 20-second cycle, in the LG room: the RA and the LG are the same territory. Hold the room, not the item.",
                "quad_pg": "Quad sits below the RA/LG platform: a stacked LG carrier can cover the door from above.",
                "even_win_pct": "The LG decides dm3's even fights; take the shaft when it is up and do not duel an LG with a rocket launcher in the open."},
    "dm2":     {"ra_share": "Two reds: low RL and the tele red. You should never be under 12 percent here; the team that holds both locks the map.",
                "ya_share": "Three yellows on dm2, so stack is cheap: route every respawn through one before you rejoin.",
                "quad_pg": "Quad is in the water room next to big; leave low RL at 24 on the clock and come through the tunnel."},
    "e1m2":    {"ya_share": "No red on e1m2. The single yellow on a 20-second cycle is the armor game; the team that owns it owns the map.",
                "deaths_pm": "Naked deaths are the e1m2 disease: armor or mega before the RL, every spawn.",
                "quad_pg": "Quad is next to the GL room and is the strongest item on the map; be there stacked at spawn or do not be there."},
    "schloss": {"ra_share": "One red in the cellar under RA window. Six or more reds a game is the line between your good games and your bad ones here.",
                "quad_pg": "Quad is two to three seconds from the red area at speed; leave red or tower at 24 on the timer with a yellow on.",
                "ra_on_timer_pct": "The cellar red is contested from the window and the low door; arrive three seconds early with a rocket ready."},
}

LEVELS = [
    {"level": 1, "name": "Survive", "lo": None, "hi": -30, "blurb": "Stop feeding. Get on the map: reds, damage, live longer."},
    {"level": 2, "name": "Stack", "lo": -30, "hi": -10, "blurb": "Die less and die once: reset naked, chain nothing."},
    {"level": 3, "name": "Fight", "lo": -10, "hi": 15, "blurb": "Pick fights from stack, take the quads and reds that decide fours."},
    {"level": 4, "name": "Control", "lo": 15, "hi": 40, "blurb": "Run the map: quad efficiency, red timing, fight only when ahead."},
    {"level": 5, "name": "Carry", "lo": 40, "hi": None, "blurb": "Win fights from stack at volume; your frags come when they matter most."},
]

# Gates to move up FROM a level (target = the lever's value at the promotion line, see pool_baselines).
# 2026-09-18 corpus check: chained-death share is 45% in wins vs 48% in losses within
# a player and has no effect on above-average once deaths/min is held constant, so it
# is NOT a fours lever (it is one in duels). Even-fight win rate climbs 34/44/53/58/65%
# across L1..L5 and is the L2 gate instead. Teamkills per game RISE with level (the
# good players are the stacked ones in the pack), so they are charged per event in
# +/- but never ranked as a player lever.
# 2026-09-20 (Peter): reds are a SHARE of the game's reds, so one-red and two-red maps count the same.
GATES = {1: ["ra_share", "dmg_pm"], 2: ["deaths_pm", "even_win_pct"], 3: ["quad_pg", "ra_share"], 4: ["adj_kills_pm", "sddr"], 5: []}

# The lever library. `levels` = levels at which the lever is coached.
LEVERS = {
    "deaths_pm": {"label": "Deaths per minute", "higher_better": False, "fmt": "num2", "levels": {1, 2, 3},
                  "why": "Every death hands the other team stack and a free respawn timer.",
                  "drill": "Count to three after you lose an exchange before you re-engage: armor first, then the fight. "
                           "On a lockout, spawn and walk away from the fight, not into it."},
    "chained_pct": {"label": "Chained deaths", "higher_better": False, "fmt": "pct", "levels": set(),   # display only in fours (see GATES note)
                    "why": "A chained death is a death within 14 s of the last one after living long enough to have picked something up. It is the tilt loop, and it is the one death habit that is yours rather than the map's.",
                    "drill": "After any death: one item (YA, GA, mega, even shells) before you take damage again. Say 'reset' on comms when you do it."},
    "dmg_pm": {"label": "Damage per minute", "higher_better": True, "fmt": "num0", "levels": {1, 2},
               "why": "Damage is the shot attempts under the frags. Low damage per minute means you are not in the fights at all.",
               "drill": "Fire at range with the RL before you close: two rockets at the doorway beat one point-blank. Keep the LG on dm3 and shoot the walls they hide behind."},
    "ra_share": {"label": "Share of the reds", "higher_better": True, "fmt": "pct", "levels": {1, 2, 3, 4}, "map_excl": RA_EXCLUDED_MAPS,
                 "why": "Your cut of every red armor taken in the game, so a one-red map and a two-red map count the same. An even split among eight players is 12.5 percent; the top group takes 18 to 20.",
                 "drill": "Know the cycle, 20 seconds after the last take. Be moving toward it at 15, on it at 18. If a teammate has it, take the yellow instead and say so."},
    "ya_share": {"label": "Share of the yellows", "higher_better": True, "fmt": "pct", "levels": {1, 2, 3},
                 "why": "Your cut of the yellows taken in the game. Yellows are the cheap stack, 0.6 of a red in the win model, and on e1m2 the only armor there is.",
                 "drill": "Route every respawn through a yellow before you rejoin. Say 'yellow' when you take it so the next man goes elsewhere."},
    "ra_pg": {"label": "Red armors per game", "higher_better": True, "fmt": "num1", "levels": set(), "map_excl": RA_EXCLUDED_MAPS,   # display; the share is the lever
              "why": "The corpus says timing does not separate players, count does. The top group takes nine or ten reds a game, the bottom four to six.",
              "drill": "Learn the red cycle on dm3 and schloss: be moving toward it at 20 s, on it at 25. If a teammate has it, take YA instead and call it."},
    "ra_on_timer_pct": {"label": "Reds taken on the timer", "higher_better": True, "fmt": "pct", "levels": {3, 4, 5}, "map_excl": RA_EXCLUDED_MAPS,
                        "why": "Late reds are contested reds. Everyone is near 60 percent; above it means you are running the cycle rather than reacting to it.",
                        "drill": "Say the red timer out loud when you take it. Arrive three seconds early with a rocket ready for the doorway."},
    "ya_pg": {"label": "Yellow armors per game", "higher_better": True, "fmt": "num1", "levels": set(),   # display; the share is the lever
              "why": "Yellows are the cheap stack: 0.6 of a red in the win model and nobody fights you for them.",
              "drill": "Route every respawn through a yellow before you rejoin. On e1m2 the yellows are the whole armor game."},
    "sddr": {"label": "Stacked damage ratio", "higher_better": True, "fmt": "num2", "levels": {3, 4, 5},
             "why": "Damage dealt over damage taken while you were at 150+ effective HP. It finds the player who fights from stack, and ignores naked chip damage.",
             "drill": "When you are stacked, fight the fight in front of you and finish it. When you drop under 150, leave, restack, come back. Do not spend a red on a 50-50."},
    "adj_kills_pm": {"label": "Adjusted kills per minute", "higher_better": True, "fmt": "num2", "levels": {3, 4, 5},
                     "why": "Frags re-weighted by how hard the fight was at first contact. Killing a stacked RL carrier while naked is three kills; a spawn kill from full red is half a kill.",
                     "drill": "Hunt the carrier, not the spawner. When their RL holder is low after a fight, that is the kill worth three; commit two players to it."},
    "even_win_pct": {"label": "Even-fight win rate", "higher_better": True, "fmt": "pct", "levels": {2, 3, 4, 5},
                     "why": "Fights that started within 60 HP of even. This is the aim-and-movement number; nothing else here measures it.",
                     "drill": "Fifteen minutes a day of RL and LG aim maps, and duel one night a week. This is the only lever that improves outside of fours."},
    "started_behind_pct": {"label": "Fights started from behind", "higher_better": False, "fmt": "pct", "levels": {2, 3, 4},
                           "why": "Share of the fights you opened while 60+ effective HP down. From there you win a fifth of them at best; against an equal player it is the whole margin.",
                           "drill": "Sixty behind means you do not shoot first. Back off, take an item, let them come to your teammate."},
    "quad_contests_pg": {"label": "Quad spawns contested per game", "higher_better": True, "fmt": "num1", "levels": {3, 4},
                         "why": "How many of the twenty quad spawns you were at: within 400 units at any point in the 10 seconds before it spawned, counting the times you died there trying. This is the attendance behind quads per game; conversion is the other half.",
                         "drill": "Call the time when anyone takes it. Leave the armor room at 24 seconds on the timer with a yellow on and be at the door at 27. Five spawns a game contested is the L3 line; the top players contest eight."},
    "quad_conversion": {"label": "Quad conversion", "higher_better": True, "fmt": "pct", "levels": {3, 4, 5},
                        "why": "Of the quad spawns you contested, the share you took. Attendance barely separates levels (about six contested a game at every level); conversion does: 6 percent at L1, 21 at L3, 33 at L5, 43 for the best quad player in the pool.",
                        "drill": "Arrive with a yellow or better and a teammate at the door, and be the one standing on the spot at the spawn, not the one fighting in the room. If you are under 100 when it spawns, let the stacked teammate take it."},
    "quad_pg": {"label": "Quads per game", "higher_better": True, "fmt": "num1", "levels": {3, 4},
                "why": "Quad decides fours. Players who take three or more a game sit a full level above those who take two.",
                "drill": "Own the quad timer: say the spawn time on comms, be there at 5 s before with stack, and have a teammate cover the door."},
    "quad_died_pct": {"label": "Died holding quad", "higher_better": False, "fmt": "pct", "levels": {4, 5},
                      "why": "The corpus norm is dying on 45 percent of quad runs. The frags follow from staying alive; a player who dies on half his runs cannot post a good average.",
                      "drill": "Take quad WITH armor, never naked. Run it toward their spawns with a teammate ahead of you, and leave a fight the moment you drop under 100."},
    "quad_frags_per_full": {"label": "Frags per full quad run", "higher_better": True, "fmt": "num1", "levels": {4, 5},
                            "why": "A full 30-second run averages 3.9 holder frags and nearly as many for the teammates around it.",
                            "drill": "Pre-plan the route before you take it: the two rooms with the most enemies, in order. Teammates funnel, you finish."},
    "tk_pg": {"label": "Teamkills per game", "higher_better": False, "fmt": "num2", "levels": set(),   # display only (rises with level)
              "why": "Killing a teammate holding an RL costs about 3.6 frags of win probability, the mirror image of killing their carrier. The scoreboard charges one.",
              "drill": "No rockets into a room your teammate just entered. Call 'in' before you push a doorway together."},
    "rl_dmg_per_rocket": {"label": "Damage per rocket", "higher_better": True, "fmt": "num0", "levels": {4, 5},
                          "why": "Direct-hit percentage misses most of what a rocket does in fours; splash is most of the damage. Regulars run from the mid 20s to low 40s.",
                          "drill": "Aim at feet and door frames, not chests. One rocket into a crowded room beats three at a strafing target."},
}

OUTCOMES = {
    "above_avg": {"label": "Above average per game", "fmt": "num1"},
    "plus_minus": {"label": "+/- per game", "fmt": "num1"},
    "agi": {"label": "Game Impact Score", "fmt": "num2"},
}


# ── metrics from rows ────────────────────────────────────────────────────────
def _num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _sum(rows, k):
    return sum((_num(r.get(k)) or 0.0) for r in rows)


def metrics(rows: list[dict]) -> dict:
    """Aggregate metrics over a set of player-game rows. None when undefined."""
    rows = [r for r in rows if (_num(r.get("minutes")) or 0) > 5]
    if not rows:
        return {}
    mins = _sum(rows, "minutes"); games = len(rows)
    deaths = _sum(rows, "deaths")
    ra_rows = [r for r in rows if (r.get("map") or "") not in RA_EXCLUDED_MAPS]
    ra = _sum(ra_rows, "take_ra"); ra_t = _sum(ra_rows, "ra_on_timer")
    st_g = _sum(rows, "stacked_given"); st_t = _sum(rows, "stacked_taken")
    g_ra = _sum(rows, "game_ra"); g_ya = _sum(rows, "game_ya"); g_mh = _sum(rows, "game_mh"); g_quad = _sum(rows, "game_quad")
    even_n = _sum(rows, "even_n"); started = _sum(rows, "started")
    qr = _sum(rows, "quad_runs"); qfull = _sum(rows, "quad_full_runs")
    qsp = _sum(rows, "quad_spawns"); qc = _sum(rows, "quad_contests")
    rockets = _sum(rows, "rockets_fired")

    def ratio(a, b, scale=1.0):
        return (a / b * scale) if b else None

    m = {
        "games": games, "minutes": round(mins, 1),
        "wins": sum(1 for r in rows if r.get("win")), "losses": sum(1 for r in rows if not r.get("win")),
        "deaths_pm": ratio(deaths, mins), "chained_pct": ratio(_sum(rows, "chained_real"), deaths),
        "spawn_death_pct": ratio(_sum(rows, "spawn_deaths"), deaths),
        "dmg_pm": ratio(_sum(rows, "dmg"), mins),
        "ra_pg": (ra / len(ra_rows)) if ra_rows else None, "ra_on_timer_pct": ratio(ra_t, ra),
        "ra_share": ratio(_sum(ra_rows, "take_ra"), g_ra), "ya_share": ratio(_sum(rows, "take_ya"), g_ya),
        "mh_share": ratio(_sum(rows, "take_mh"), g_mh), "quad_share": ratio(_sum(rows, "take_quad"), g_quad),
        "ya_pg": _sum(rows, "take_ya") / games,
        "sddr": ratio(st_g, st_t), "adj_kills_pm": ratio(_sum(rows, "adj_kills"), mins),
        "even_win_pct": ratio(_sum(rows, "even_w"), even_n), "even_n": int(even_n),
        "started_behind_pct": ratio(_sum(rows, "started_behind"), started), "started": int(started),
        "quad_pg": _sum(rows, "take_quad") / games,
        # Peter's attendance rule (2026-09-20): within ~400u of the quad at any point in the 10 s before
        # it spawned, deaths there included. Corpus rows carry the 10-s named-zone proxy from quad_contest_pass.py.
        "quad_contests_pg": (qc / games) if qsp else None, "quad_contest_rate": ratio(qc, qsp),
        "quad_conversion": ratio(_sum(rows, "quad_contest_takes"), qc), "quad_contest_died_pg": (_sum(rows, "quad_contest_died") / games) if qsp else None,
        "quad_died_pct": ratio(_sum(rows, "quad_died"), qr), "quad_runs": int(qr),
        "quad_frags_per_full": ratio(_sum(rows, "quad_frags_full"), qfull), "quad_full_runs": int(qfull),
        "tk_pg": _sum(rows, "teamkills") / games, "team_dmg_pg": _sum(rows, "team_dmg") / games,
        "rl_dmg_per_rocket": ratio(_sum(rows, "rl_dmg"), rockets),
        "above_avg": _sum(rows, "above_avg") / games, "plus_minus": _sum(rows, "plus_minus") / games,
        "agi": _sum(rows, "agi") / games,
        "maps": sorted({r.get("map") for r in rows if r.get("map")}),
    }
    return m


def level_for(above_avg_pg: float | None, games: int) -> dict:
    """{level, name, blurb, placed}. Unplaced (level 0) under LEVEL_MIN_GAMES."""
    if above_avg_pg is None or games < LEVEL_MIN_GAMES:
        return {"level": 0, "name": "Unplaced", "blurb": f"Play {LEVEL_MIN_GAMES} fours to get a level.", "placed": False}
    for L in LEVELS:
        if (L["lo"] is None or above_avg_pg >= L["lo"]) and (L["hi"] is None or above_avg_pg < L["hi"]):
            return {**L, "placed": True}
    return {**LEVELS[-1], "placed": True}


# ── pool baselines ───────────────────────────────────────────────────────────
def pool_baselines(players: dict[str, list[dict]]) -> dict:
    """players = {canonical_id: rows (last LEVEL_WINDOW games)}. Returns
    {'levels': {lvl: {'n': k, 'median': {metric: v}}}, 'sd': {metric: v}, 'n': total}."""
    per = {}
    for cid, rows in players.items():
        m = metrics(rows[-LEVEL_WINDOW:])
        if not m or m["games"] < LEVEL_MIN_GAMES:
            continue
        m["level"] = level_for(m["above_avg"], m["games"])["level"]
        per[cid] = m
    keys = list(LEVERS) + list(OUTCOMES)
    levels = _level_tables(per, keys)
    # per-map baselines: each player's metrics on that map (last LEVEL_WINDOW games there, MAP_MIN_GAMES minimum)
    maps = {}
    for mp in MAP_ITEMS:
        perm = {}
        for cid, rows in players.items():
            mr = [r for r in rows if r.get("map") == mp][-LEVEL_WINDOW:]
            if len(mr) < MAP_MIN_GAMES or cid not in per:
                continue
            m = metrics(mr); m["level"] = per[cid]["level"]; perm[cid] = m
        if len(perm) >= 6:
            maps[mp] = {"n": len(perm), "levels": _level_tables(perm, keys)}
    sd = {}
    for k in keys:
        vals = [m[k] for m in per.values() if m.get(k) is not None]
        sd[k] = statistics.pstdev(vals) if len(vals) >= 3 and statistics.pstdev(vals) > 0 else None
    return {"levels": levels, "sd": sd, "n": len(per), "maps": maps}


def _level_tables(per: dict, keys: list) -> dict:
    """{lvl: {'n', 'median': {k: v}, 'line': {k: bar}}} for a set of per-player metric dicts
    (each carrying 'level' and 'above_avg'). The line is the OLS value of each lever at the
    next band's lower edge, clamped between own median and next median."""
    levels = {}
    for lvl in range(1, 6):
        grp = [m for m in per.values() if m["level"] == lvl]
        med = {}
        for k in keys:
            vals = [m[k] for m in grp if m.get(k) is not None]
            med[k] = statistics.median(vals) if vals else None
        levels[lvl] = {"n": len(grp), "median": med}
    # Promotion-line bars
    for L in LEVELS:
        lvl = L["level"]; nxt = next((x for x in LEVELS if x["level"] == lvl + 1), None)
        line = {}
        if nxt is not None and nxt["lo"] is not None:
            edge = float(nxt["lo"])
            for k in LEVERS:
                pts = [(m["above_avg"], m[k]) for m in per.values() if m.get(k) is not None and m.get("above_avg") is not None]
                own_med = levels[lvl]["median"].get(k); nxt_med = levels[lvl + 1]["median"].get(k)
                bar = None
                if len(pts) >= 10:
                    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
                    mx, my = statistics.mean(xs), statistics.mean(ys)
                    vx = sum((x - mx) ** 2 for x in xs)
                    if vx > 0:
                        slope = sum((x - mx) * (y - my) for x, y in pts) / vx
                        bar = my + slope * (edge - mx)
                if bar is None:
                    bar = nxt_med
                hb = LEVERS[k]["higher_better"]
                if bar is not None and own_med is not None:
                    bar = max(bar, own_med) if hb else min(bar, own_med)
                if bar is not None and nxt_med is not None:
                    bar = min(bar, nxt_med) if hb else max(bar, nxt_med)
                line[k] = bar
        levels[lvl]["line"] = line
    return levels


def gate_status(m: dict, level: int, base: dict) -> list[dict]:
    """The player's standing on each gate out of his level."""
    out = []
    nxt = base["levels"].get(level, {}).get("line", {}) if level else {}
    for k in GATES.get(level, []):
        L = LEVERS[k]; you = m.get(k); target = nxt.get(k)
        passed = None
        if you is not None and target is not None:
            passed = you >= target if L["higher_better"] else you <= target
        out.append({"key": k, "label": L["label"], "you": _fmt(you, L["fmt"]), "target": _fmt(target, L["fmt"]),
                    "you_raw": you, "target_raw": target, "passed": passed})
    return out


# ── lever ranking ────────────────────────────────────────────────────────────
def _fmt(v, kind):
    if v is None:
        return "—"
    if kind == "pct":
        return f"{round(v * 100)}%"
    if kind == "num0":
        return f"{v:.0f}"
    if kind == "num1":
        return f"{v:.1f}"
    return f"{v:.2f}"


def _tables(base: dict, level: int, map_: str | None):
    """(own median, line, next median) dicts — per-map when that map has a baseline
    with enough players at this level, else pooled."""
    src = base["levels"]
    if map_ and base.get("maps", {}).get(map_):
        mt = base["maps"][map_]["levels"]
        if mt.get(level, {}).get("n", 0) >= 4 and mt.get(min(level + 1, 5), {}).get("n", 0) >= 2:
            src = mt
    own = src.get(level, {}).get("median", {}) if level else {}
    nxt_lvl = min(level + 1, 5) if level else 0
    nxt_med = src.get(nxt_lvl, {}).get("median", {}) if level else {}
    nxt = src.get(level, {}).get("line", {}) if level and level < 5 else nxt_med
    return own, nxt, nxt_med, (src is not base["levels"])


def rank_levers(rows: list[dict], level: int, base: dict, map_: str | None = None) -> dict:
    """Rank the levers active at this level. Score = distance to the promotion line
    (in pool SDs) + a capped, discounted own win/loss split + a gate bonus.
    `map_` ranks against that map's baselines when they exist.
    Returns {'levers': [...], 'self_split': bool, 'all': m, 'per_map': bool}."""
    m = metrics(rows)
    if not m:
        return {"levers": [], "self_split": False, "all": {}, "per_map": False}
    wins = [r for r in rows if r.get("win")]; losses = [r for r in rows if not r.get("win")]
    split = len(wins) >= MIN_SPLIT and len(losses) >= MIN_SPLIT
    mw = metrics(wins) if split else {}; ml = metrics(losses) if split else {}
    own, nxt, nxt_med, per_map = _tables(base, level, map_)
    active = [k for k, L in LEVERS.items() if (level in L["levels"]) or (k in GATES.get(level, []))]
    out = []
    for k in active:
        L = LEVERS[k]; you = m.get(k); target = nxt.get(k); sd = base["sd"].get(k)
        if you is None or target is None or not sd:
            continue
        sign = 1 if L["higher_better"] else -1
        short = sign * (target - you) / sd            # >0: you are short of the next level
        sgap = 0.0
        if split and mw.get(k) is not None and ml.get(k) is not None:
            sgap = sign * (mw[k] - ml[k]) / sd         # >0: you do it in wins, not in losses
        # Score: distance to the next level's median (in pool SDs) + a capped, discounted
        # own win/loss split, + a bonus for this level's gates. The split is discounted
        # because it is partly game-state (you start more fights from behind when you are
        # losing), and capped so a low-variance lever cannot outrank a wide real gap.
        score = max(short, 0.0) + 0.25 * min(max(sgap, 0.0), 2.0) + (0.5 if k in GATES.get(level, []) else 0.0)
        # evidence: minimum samples for the ratio levers
        n_ok = True
        if k in ("even_win_pct",) and m.get("even_n", 0) < 30: n_ok = False
        if k in ("started_behind_pct",) and m.get("started", 0) < 30: n_ok = False
        if k in ("quad_died_pct", "quad_frags_per_full") and m.get("quad_runs", 0) < 8: n_ok = False
        if k in ("ra_on_timer_pct",) and (m.get("ra_pg") or 0) * m["games"] < 30: n_ok = False
        if k in ("ra_share", "ya_share") and m.get(k) is None: n_ok = False
        if not n_ok:
            continue
        out.append({
            "key": k, "label": L["label"], "you": _fmt(you, L["fmt"]), "you_raw": you,
            "win": _fmt(mw.get(k), L["fmt"]) if split else None, "loss": _fmt(ml.get(k), L["fmt"]) if split else None,
            "level_median": _fmt(own.get(k), L["fmt"]), "target": _fmt(target, L["fmt"]), "target_raw": target,
            "next_median": _fmt(nxt_med.get(k), L["fmt"]),
            "short_sd": round(short, 2), "split_sd": round(sgap, 2), "score": round(score, 2),
            "is_gate": k in GATES.get(level, []), "higher_better": L["higher_better"], "fmt": L["fmt"],
            "why": L["why"], "drill": L["drill"],
        })
    out.sort(key=lambda x: (-x["score"], not x["is_gate"]))
    return {"levers": out, "self_split": split, "all": m, "wins": mw, "losses": ml, "per_map": per_map}


# ── prescriptions ────────────────────────────────────────────────────────────
def _parse_ts(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def grade_prescription(prev: dict | None, rows: list[dict]) -> dict | None:
    """Grade the previous prescription on the games played after it was issued.
    Returns None when there was none; otherwise {status: pending|hit|improved|flat|worse, ...}."""
    if not prev or not prev.get("lever"):
        return None
    k = prev["lever"]; L = LEVERS.get(k)
    if not L:
        return None
    issued = _parse_ts(prev.get("issued_after"))
    since = [r for r in rows if issued and (_parse_ts(r.get("played_at")) or issued) > issued]
    n = len(since); window = int(prev.get("window_games") or FOCUS_WINDOW_GAMES)
    m = metrics(since) if since else {}
    now_v = m.get(k) if m else None
    res = {"lever": k, "label": L["label"], "target": prev.get("target"), "at_issue": prev.get("you"),
           "games_since": n, "window_games": window, "now": now_v, "now_fmt": _fmt(now_v, L["fmt"]),
           "target_fmt": _fmt(prev.get("target"), L["fmt"]), "at_issue_fmt": _fmt(prev.get("you"), L["fmt"]),
           "issued_at": prev.get("issued_at")}
    if n < window:
        res["status"] = "pending"; return res
    y0, tgt = _num(prev.get("you")), _num(prev.get("target"))
    if now_v is None or y0 is None or tgt is None:
        res["status"] = "flat"; return res
    sign = 1 if L["higher_better"] else -1
    gap = sign * (tgt - y0)
    moved = sign * (now_v - y0)
    if sign * (now_v - tgt) >= 0:
        res["status"] = "hit"
    elif gap > 0 and moved >= 0.25 * gap:
        res["status"] = "improved"
    elif gap > 0 and moved <= -0.10 * gap:
        res["status"] = "worse"
    else:
        res["status"] = "flat"
    return res


def choose_focus(ranked: list[dict], prev: dict | None, graded: dict | None, rows: list[dict]) -> dict | None:
    """One focus at a time. Keep the previous one while its window is open;
    otherwise the top-ranked lever (which may be the same one again)."""
    if not ranked:
        return None
    last_played = max((r.get("played_at") for r in rows if r.get("played_at")), default=None)
    if graded and graded["status"] == "pending":
        top = next((l for l in ranked if l["key"] == prev["lever"]), None)
        if top:
            # no games since the prescription yet -> show the at-issue value, not a dash
            now_fmt = graded["now_fmt"] if graded.get("now") is not None else _fmt(_num(prev.get("you")), LEVERS[prev["lever"]]["fmt"])
            return {**prev, "status": "in_progress", "games_since": graded["games_since"], "now_fmt": now_fmt,
                    "label": top["label"], "why": top["why"], "drill": top["drill"]}
    top = ranked[0]
    return {"lever": top["key"], "label": top["label"], "you": top["you_raw"], "you_fmt": top["you"],
            "target": top["target_raw"], "target_fmt": top["target"], "window_games": FOCUS_WINDOW_GAMES,
            "issued_at": datetime.now(timezone.utc).isoformat(), "issued_after": str(last_played) if last_played else None,
            "status": "new", "why": top["why"], "drill": top["drill"], "higher_better": top["higher_better"]}


# ── game cards ───────────────────────────────────────────────────────────────
GAME_KEYS = ["deaths_pm", "dmg_pm", "ra_pg", "sddr", "adj_kills_pm", "quad_pg", "started_behind_pct", "even_win_pct"]


def game_cards(rows: list[dict], n: int = 8) -> list[dict]:
    """Last n games: score + the two levers that most explain the game vs the
    player's own 40-game norm (in SDs of his own game-to-game spread)."""
    rows = sorted([r for r in rows if r.get("played_at")], key=lambda r: str(r["played_at"]))
    if not rows:
        return []
    per_game = [{**metrics([r]), "_r": r} for r in rows[-LEVEL_WINDOW:]]
    sd = {}; mean = {}
    for k in GAME_KEYS:
        vals = [g[k] for g in per_game if g.get(k) is not None]
        if len(vals) >= 5:
            mean[k] = statistics.mean(vals); sd[k] = statistics.pstdev(vals) or None
    cards = []
    for g in per_game[-n:]:
        r = g["_r"]; expl = []
        for k in GAME_KEYS:
            v = g.get(k)
            if v is None or k not in sd or not sd[k]:
                continue
            z = (v - mean[k]) / sd[k]
            good = z > 0 if LEVERS[k]["higher_better"] else z < 0
            expl.append((abs(z), k, good, v))
        expl.sort(reverse=True)
        cards.append({
            "hub_game_id": r.get("hub_game_id"), "played_at": str(r.get("played_at")), "map": r.get("map"), "win": bool(r.get("win")),
            "frags": r.get("frags"), "deaths": r.get("deaths"), "agi": round(_num(r.get("agi")) or 0, 2),
            "above_avg": round(_num(r.get("above_avg")) or 0, 1), "plus_minus": round(_num(r.get("plus_minus")) or 0, 1),
            "explain": [{"key": k, "label": LEVERS[k]["label"], "value": _fmt(v, LEVERS[k]["fmt"]), "good": good} for _, k, good, v in expl[:2]],
        })
    return list(reversed(cards))


# ── the report ───────────────────────────────────────────────────────────────
def map_cards(rows: list[dict], level: int, base: dict, n_cards: int = 4) -> list[dict]:
    """One card per map the player has MAP_MIN_GAMES+ games on (last LEVEL_WINDOW on that
    map): his numbers there, the map's level baseline, and the single "work on this" lever
    ranked against that map's promotion line. The overall focus stays one thing; these say
    what that level's syllabus looks like on each map."""
    if not level:
        return []
    out = []
    for mp in MAP_ITEMS:
        mr = [r for r in rows if r.get("map") == mp][-LEVEL_WINDOW:]
        if len(mr) < MAP_MIN_GAMES:
            continue
        rk = rank_levers(mr, level, base, map_=mp)
        m = rk["all"]
        top = rk["levers"][0] if rk["levers"] else None
        lv_eq = level_for(m.get("above_avg"), m.get("games", 0))
        card = {"map": mp, "games": m.get("games"), "wins": m.get("wins"), "losses": m.get("losses"),
                "above_avg_pg": round(m["above_avg"], 1), "plays_like": lv_eq["level"] if lv_eq["placed"] else None,
                "items": MAP_ITEMS[mp], "per_map_baseline": rk["per_map"],
                "levers": rk["levers"][:4],
                "work_on": None}
        if top:
            note = MAP_NOTES.get(mp, {}).get(top["key"])
            card["work_on"] = {**{k: top[k] for k in ("key", "label", "you", "win", "loss", "level_median", "target", "next_median", "is_gate", "why", "drill")},
                               "map_note": note}
        out.append(card)
    out.sort(key=lambda c: -c["games"])
    return out[:n_cards]


def build_report(rows: list[dict], base: dict, prev: dict | None, display: str) -> dict:
    rows = sorted(rows, key=lambda r: str(r.get("played_at") or ""))
    win_rows = rows[-LEVEL_WINDOW:]
    m = metrics(win_rows)
    lvl = level_for(m.get("above_avg"), m.get("games", 0))
    ranked = rank_levers(win_rows, lvl["level"], base) if lvl["placed"] else {"levers": [], "self_split": False, "all": m}
    graded = grade_prescription(prev, rows)
    focus = choose_focus(ranked["levers"], prev, graded, rows) if lvl["placed"] else None
    gates = gate_status(m, lvl["level"], base) if lvl["placed"] else []
    nxt = base["levels"].get(min(lvl["level"] + 1, 5), {}) if lvl["placed"] else {}
    return {
        "display": display, "mode": "4on4",
        "level": {**lvl, "above_avg_pg": round(m["above_avg"], 1) if m else None, "games": m.get("games", 0),
                  "window": LEVEL_WINDOW, "gates": gates, "ready": bool(gates) and all(g["passed"] for g in gates),
                  "next_level_n": nxt.get("n")},
        "record": {"wins": m.get("wins", 0), "losses": m.get("losses", 0)},
        "metrics": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()} if m else {},
        "levers": ranked["levers"][:6], "self_split": ranked["self_split"],
        "previous": graded, "focus": focus,
        "games": game_cards(rows),
        "maps": map_cards(rows, lvl["level"], base) if lvl["placed"] else [],
        "pool": {"n": base.get("n"), "levels": {k: v["n"] for k, v in base["levels"].items()},
                 "maps": {mp: v["n"] for mp, v in base.get("maps", {}).items()}},
    }
