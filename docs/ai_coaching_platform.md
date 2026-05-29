---
title: DeepFrag AI Coaching Platform — Design
status: NORTH STAR — design doc, not yet built
---

# DeepFrag AI Coaching Platform

> The whole point of DeepFrag: gather an immense amount of QuakeWorld telemetry,
> then sit an AI coach on top of it for anyone who wants to improve. This doc
> turns that vision into an architecture, grounded in the first real diagnosis
> we ran (Cronus's 20-duel "funk", 2026-05-29) — which proved the data + tooling
> can produce a coach-grade read end-to-end.

## 0. What the Cronus diagnosis proved (the existence proof)

From 20 parsed demos we mechanically derived, with zero human watching:
- **Item control** (RA/MH/Quad pickup share, win vs loss splits)
- **Stack-state at every kill and death** (armor+hp of both players at each frag)
- **Restack time** after death (economy-reset speed)
- **Death heatmaps** overlaid on real map geometry (where you die vs kill)
- **Accuracy** per weapon, win/loss split
- A **single root-cause diagnosis** ("stack problem, not aim problem") + a
  prioritized, specific fix list + a weapon-specific (LG tracking) training plan.

Every one of those is a coaching primitive. The platform is: **compute these
for every player automatically, detect their personal weakness, and deliver it
as natural-language coaching + drills + progress tracking.**

## 1. The coaching primitives (the metric layer)

Each is a function over the MVD bucket/frag/item data we already extract. These
are the "stats a coach would compute by hand," now automatic:

| Primitive | Signal | Coaching question it answers |
|---|---|---|
| **Item Control Index** | share of RA/YA/MH/Quad taken, + timing-vs-respawn | "Are you winning the economy?" |
| **Stack-at-engagement** | your stack vs enemy stack at each kill/death | "Do you fight from strength or desperation?" |
| **Restack efficiency** | sec from death → armor≥50 | "Do you reset after losing a fight, or tilt-feed?" |
| **Tracking efficiency (LG)** | beam-on-target % over fight windows (from 50ms lg-held + positions) | "Is your continuous-aim landing?" |
| **Burst efficiency (RL)** | direct vs splash, accuracy, self-damage | "Is your rocket aim + rocket-jump economy sound?" |
| **Map control / pathing** | time-in-zone, rotation patterns, death clustering | "Are you dying in the same trap repeatedly?" |
| **Tilt detection** | snowball curves — does a stack-loss cascade into a blowout? | "Do you reset emotionally?" |
| **Matchup deltas** | per-opponent splits (Cronus: 1-10 vs BullD0zer, even vs Kingstud) | "Who/what beats you, specifically?" |

## 2. The weakness-detection engine

For a given player, compute every primitive across their recent N games, then
**rank deviations from their own win-state baseline AND from a skill-tier
benchmark.** The biggest gaps = the coaching priorities. (Cronus: RA-control gap
44%→61% and restack 7.2s→4.8s ranked #1; LG-vs-benchmark ranked #2.)

Output is an ordered list of "levers," each with: the metric, the gap, the
win/loss evidence, and a confidence. This is deterministic — the LLM doesn't
invent the diagnosis, it *narrates* a computed one (the key to trustworthy
coaching; see the "don't hallucinate the analysis" principle below).

## 3. The LLM coach layer

The LLM does NOT compute stats. It receives the ranked levers + supporting
numbers + map context as structured input, and produces:
- a plain-language **diagnosis** ("you have a stack problem, not an aim problem")
- a **prioritized fix list** with the *why* (evidence-cited)
- **weapon/mechanic-specific training plans** (e.g. the LG tracking regimen:
  sens drop, KovaaK's tracking scenarios, prediction-tracking, arm-vs-wrist)
- a **drill prescription** tied to detectable metrics so progress is measurable

Prompt-caching the metric schemas + benchmark tables keeps cost low. The coach
is a thin, well-grounded narrator over a deterministic analysis — never a
free-floating "watch the demo and guess."

## 4. Progress tracking (the retention loop)

Every coaching lever maps to a measurable metric. Re-run the engine each session:
- "Your RA control went 44%→58% this week — the #1 fix is working."
- "LG still flat at 24%; the tracking drills haven't moved it. Try the sens drop."
This closes the loop: diagnose → prescribe → measure → re-diagnose. It's also
the engagement hook — players come back to see their lever bars move.

## 5. Delivery surfaces

1. **Profile "Coach" tab** — auto-generated weakness report per player, refreshes
   each sync. Free tier: top lever + headline. Paid: full report + drills + history.
2. **Per-match deep-dive** — "why did I lose THIS one" with the heatmap +
   stack-timeline + the moment-by-moment narration (we built the match deep-dive
   + playback tools already — this is their home).
3. **Chat coach** — ask "why do I lose to BullD0zer?" → it pulls the matchup
   deltas and answers with evidence. (Reuse the Owly chat pattern from the agency
   side.)
4. **Drill tracker** — prescribed drills + the metric each one targets, with the
   trendline.

## 6. Build order (incremental, each step shippable)

1. **Metric layer as API** — `/api/players/{id}/coaching/metrics` computing the
   primitives over recent games (extends the mvd-api pipeline we just used
   manually). [foundation]
2. **Weakness engine** — deterministic lever-ranking on top of the metrics.
3. **LLM narration** — structured levers → coaching text (Claude, prompt-cached).
4. **Coach tab UI** — render the report; free vs paid gating.
5. **Progress tracking** — store metric snapshots per session, show trendlines.
6. **Chat coach + drill tracker** — the engagement/retention layer.

## 7. Why this is defensible

Anyone can show stats. The moat is: (a) the **largest parsed QW telemetry set**
(150k+ matches), (b) **win-state-relative** diagnosis (compare you to *your
winning self*, not just a leaderboard), and (c) a coach that **cites evidence
from your own demos** instead of generic tips. The Cronus run proved all three
are computable today.

## 8. Open questions

- Tracking-efficiency (LG beam-on-target) needs per-50ms beam-held + relative
  angle — confirm the bucket `lg` field + positions are enough, or if we need a
  new mvd-api field (beam target). [likely a small parser addition]
- Benchmark tables per skill tier — derive from the rating tiers we already have.
- Pricing / gating — free headline vs paid depth (ties to the federated-login +
  billing work already on the roadmap).
