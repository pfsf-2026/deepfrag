# Bot pathing & decision methodology (DeepFrag / FragBot)

Origin: distilled from Veritasium × 2swap, *"Google Maps is unreasonably fast"*
(pathfinding: BFS → Dijkstra → A\* → bidirectional → contraction hierarchies),
adapted to QuakeWorld bots. Watch it before touching this if the terms below are
unfamiliar.

## The core idea we're stealing

Google can't precompute everything (64M nodes → 8 petabytes), so it uses
*contraction hierarchies*: heavy one-time preprocessing of the static road graph
(rank nodes by importance via nested dissection, add **shortcut edges**) → sub-
millisecond queries. The tradeoff dial is **preprocessing time vs query time**.

**QW maps are tiny** (a few hundred meaningful waypoints, not 64M). So we go to
the FAR "preprocess everything" end of that dial — the end Google can't afford:

> Precompute **all-pairs shortest travel-time** once per map. Runtime routing is
> then an **O(1) table lookup**. Skip CH entirely; it's overkill at our scale.

## The five transfers

1. **Preprocess-heavy, query-cheap.** Bake the navmesh + all-pairs next-hop table
   + chokepoints + trick-edge traces ONCE per map, offline. Ship the table. The
   bot never runs Dijkstra at runtime.

2. **Trick jumps ARE shortcut edges** (the key unlock). A CH shortcut encodes a
   fast path skipping intermediate nodes. An RL-jump low→mega, an LG-jump, a
   bunny route — each is a weighted shortcut edge carrying:
   - traversal time,
   - the **.qwd trace** to execute it (from our replay engine),
   - required weapons (RL/LG) + ammo,
   - a risk/cost (RL self-damage, exposure).
   This is what unifies **pathing + .qwd movement + positioning** into ONE
   weighted graph. The .qwd library is not just for demos — it's the edge set.

3. **Don't trust a Euclidean heuristic.** The video shows A\*'s travel-time
   heuristic (dist ÷ max_speed) is a weak underestimate and a tuned Dijkstra
   often beats A\* on time. In QW it's worse — teleporters + verticality + jumps
   make straight-line distance wildly wrong. Fix: use the **precomputed all-pairs
   table as a perfect heuristic** → optimal AND instant. (At our scale we just
   read the table; A\* is unnecessary.)

4. **Dynamic cost layers = item timers + threat field.** Google reruns shortcut
   weights on traffic updates. Ours:
   - **item respawn timers** — an edge toward mega only has value when mega is up;
   - **threat field** — nodes near the opponent's likely position (from VYA) get a
     cost penalty (the video notes Minecraft mobs use A\* with "extra penalties
     for dangerous zones").
   So the bot optimizes a **highest-VALUE path**, not shortest:
   `maximize Σ(item value picked up) − (time) − (threat exposure)`.

5. **Importance cuts → map chokepoints.** The small node-cuts that split the
   graph in half (Mississippi bridges) map to QW **chokepoints/connectors** —
   where fights concentrate and where a bot should hold/ambush. For the
   positioning brain, not just routing.

## Building the graph (per map)

Nodes:
- item locations (RA/YA/mega/RL/GL/LG/SNG/quad) from the BSP entity lump,
- key tactical positions (chokes, sniper spots),
- **sampled origins from our human .qwd traces** — a human walked these, so they
  are guaranteed-walkable nodes with real timing.

Edges:
- sequential .qwd trace points → walkable edges with measured traversal time
  (frame count × frametime). Using human demos AS the graph means edges are
  provably traversable, not guessed.
- **trick-jump shortcut edges** from the replay library (each = trace + cost +
  item/risk requirements).

Then: all-pairs Dijkstra → a `next_hop[from][to]` table + `time[from][to]`.

## Runtime loop (the bot)

```
each decision tick:
  for each item node i:
    value[i] = base_value(i) * available_now(i, timers)        # 0 if on cooldown
             - threat_cost(path_to(i))                          # VYA threat field
    score[i] = value[i] / time[me_node][i]                     # value per second
  goal = argmax score
  next = next_hop[me_node][goal]
  if edge(me_node,next) is a trick shortcut: replay its .qwd trace (puppet)
  else: steer toward next waypoint (set desired_angle + forward; native locomotion)
  on reaching a node: me_node = node
```

Phase 2 v1 (item-running brain) implements value-by-timer routing. Threat field +
fighting (LG/RL aim, dodge) layer on top in v2, reusing the same graph.

## Scale note / honesty

We deliberately do NOT implement contraction hierarchies, nested dissection, or
A\* — they solve a scale problem (millions of nodes) we don't have. The valuable
transfer is conceptual: preprocess-everything, trick-jumps-as-shortcut-edges,
heuristic-admissibility caveat, dynamic cost layers, chokepoint importance.

First target map: **dm6** (compact, item-dense, no moving platforms, we already
have trick traces + .bot + replay rig there).
