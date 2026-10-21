# Travel times between key rooms on the TB4 maps

*Seconds from entering one room to entering the other, measured from recent NA fours through the demo parser's room trails, for runs **without a rocket jump**. Each cell is **fast / typical**: fast = the 10th percentile of runs that actually went from one room to the other in one life (done well; stairs, lifts and teleporters included), typical = the median. Where players also rocket-jump the pair, **RJ n** follows: the fast time with a rocket jump (the player's own rocket splash during the run). A cell in *italics* is an estimate for a pair nobody ran directly (shortest chain of typical legs). Built by `tools/mvd_features/research_2026_10/route_times_build.py` and written by `map_route_json.py` (2026-10-21); the Game Report uses the same table for its clocks and perfect-timing lines, RJ times only when the player has rockets and a stack.*


## dm3

| from \ to | quad | red | YA | RL | LG | SNG mega | hill mega | Pent room | tele | RA tunnel | lifts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **quad** | · | 4 / 10 (RJ 6) | 3 / 6 (RJ 6) | 4 / 8 (RJ 8) | 5 / 10 (RJ 11) | 10 / 15 (RJ 11) | 0 / 3 (RJ 1) | 3 / 8 (RJ 7) | 7 / 14 (RJ 8) | 2 / 8 (RJ 4) | 3 / 13 (RJ 8) |
| **red** | 6 / 11 (RJ 5) | · | 9 / 15 (RJ 14) | 12 / 17 | 11 / 18 | 10 / 14 (RJ 8) | 7 / 13 (RJ 7) | 13 / 17 (RJ 20) | 6 / 9 (RJ 6) | 5 / 16 (RJ 9) | 16 / 22 (RJ 19) |
| **YA** | 3 / 7 (RJ 5) | 7 / 14 (RJ 11) | · | 3 / 7 (RJ 5) | 4 / 9 | 12 / 19 (RJ 16) | 5 / 12 (RJ 8) | 3 / 7 (RJ 5) | 1 / 18 (RJ 14) | 7 / 14 (RJ 9) | 3 / 10 (RJ 7) |
| **RL** | 10 / 16 (RJ 13) | 13 / 20 | 7 / 12 (RJ 8) | · | 4 / 7 | 7 / 19 | 6 / 11 (RJ 15) | 8 / 15 (RJ 13) | 1 / 15 | 8 / 14 (RJ 16) | 2 / 17 (RJ 17) |
| **LG** | 10 / 17 (RJ 13) | 13 / 17 | 7 / 13 (RJ 13) | 3 / 7 | · | 15 / 20 | 4 / 8 (RJ 8) | 5 / 10 | 1 / 15 | 7 / 11 | 9 / 15 (RJ 15) |
| **SNG mega** | 5 / 12 (RJ 7) | 7 / 11 (RJ 6) | 8 / 17 (RJ 10) | 9 / 15 | 9 / 14 | · | 6 / 11 (RJ 11) | 9 / 16 (RJ 14) | 1 / 3 (RJ 1) | 8 / 14 (RJ 14) | 15 / 22 (RJ 15) |
| **hill mega** | 7 / 14 (RJ 1) | 8 / 12 (RJ 5) | 8 / 15 (RJ 5) | 4 / 6 (RJ 5) | 3 / 5 | 8 / 12 (RJ 9) | · | 8 / 13 (RJ 13) | 5 / 9 (RJ 8) | 1 / 3 (RJ 1) | 1 / 17 (RJ 18) |
| **Pent room** | 10 / 18 (RJ 6) | 16 / 20 (RJ 13) | 11 / 17 (RJ 13) | 9 / 18 (RJ 12) | 6 / 12 | 15 / 18 (RJ 18) | 10 / 15 (RJ 9) | · | 14 / 20 (RJ 18) | 14 / 16 (RJ 13) | 2 / 6 (RJ 2) |
| **tele** | 2 / 3 (RJ 3) | 4 / 7 (RJ 5) | 5 / 8 (RJ 6) | 7 / 12 (RJ 14) | 7 / 12 (RJ 11) | 1 / 3 (RJ 2) | 2 / 5 (RJ 5) | 6 / 11 (RJ 13) | · | 5 / 12 (RJ 6) | 5 / 13 (RJ 13) |
| **RA tunnel** | 6 / 12 (RJ 7) | 6 / 8 (RJ 3) | 9 / 16 (RJ 15) | 5 / 7 (RJ 7) | 4 / 6 (RJ 6) | 6 / 10 (RJ 11) | 1 / 1 (RJ 1) | 10 / 16 (RJ 17) | 4 / 6 (RJ 5) | · | 12 / 18 (RJ 19) |
| **lifts** | 3 / 3 (RJ 3) | 5 / 10 (RJ 9) | 6 / 12 (RJ 12) | 6 / 13 (RJ 10) | 6 / 12 (RJ 16) | 6 / 12 (RJ 16) | 3 / 4 (RJ 5) | 1 / 4 (RJ 2) | 9 / 14 (RJ 12) | 3 / 11 (RJ 7) | · |

## dm2

| from \ to | quad | back RA/mega | secret RA | big YA | tele YA | high RL | low RL | GL mega | tele | NG | water |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **quad** | · | 1 / 16 (RJ 10) | 7 / 13 (RJ 8) | 2 / 8 (RJ 3) | 6 / 10 (RJ 8) | 3 / 4 (RJ 3) | 5 / 13 (RJ 8) | 7 / 14 (RJ 7) | 3 / 7 (RJ 5) | 2 / 4 (RJ 3) | 5 / 16 (RJ 10) |
| **back RA/mega** | 7 / 16 (RJ 9) | · | 7 / 14 (RJ 8) | 3 / 7 (RJ 4) | 10 / 16 (RJ 11) | 12 / 19 (RJ 8) | 4 / 9 (RJ 7) | 17 / 18 (RJ 7) | 8 / 15 (RJ 12) | 8 / 14 (RJ 10) | 9 / 17 (RJ 10) |
| **secret RA** | 4 / 13 (RJ 4) | 1 / 12 (RJ 15) | · | 5 / 12 (RJ 13) | 5 / 10 (RJ 10) | 8 / 14 (RJ 8) | 5 / 10 (RJ 9) | 11 / 18 (RJ 14) | 4 / 7 (RJ 7) | 2 / 3 (RJ 2) | 1 / 2 (RJ 2) |
| **big YA** | 4 / 14 (RJ 3) | 6 / 11 (RJ 7) | 8 / 12 (RJ 10) | · | 7 / 12 (RJ 11) | 9 / 15 (RJ 3) | 3 / 5 (RJ 4) | 10 / 16 (RJ 4) | 5 / 9 (RJ 7) | 3 / 6 (RJ 5) | 7 / 14 (RJ 11) |
| **tele YA** | 5 / 9 (RJ 6) | 1 / 12 (RJ 16) | 9 / 17 (RJ 12) | 2 / 8 (RJ 4) | · | 2 / 3 (RJ 3) | 4 / 12 (RJ 10) | 3 / 7 (RJ 5) | 1 / 4 (RJ 1) | 6 / 11 (RJ 7) | 1 / 13 (RJ 12) |
| **high RL** | 2 / 4 (RJ 4) | 1 / 17 (RJ 13) | 9 / 15 (RJ 11) | 4 / 10 (RJ 6) | 8 / 14 (RJ 11) | · | 5 / 13 (RJ 10) | 5 / 10 (RJ 7) | 5 / 11 (RJ 9) | 4 / 8 (RJ 5) | 6 / 17 (RJ 10) |
| **low RL** | 9 / 16 (RJ 9) | 3 / 5 (RJ 4) | 3 / 5 (RJ 4) | 4 / 10 (RJ 8) | 8 / 15 (RJ 10) | 10 / 17 (RJ 12) | · | 13 / 21 (RJ 14) | 6 / 13 (RJ 11) | 5 / 10 (RJ 8) | 5 / 9 (RJ 7) |
| **GL mega** | 7 / 10 (RJ 6) | 11 / 16 (RJ 10) | 12 / 20 (RJ 14) | 2 / 4 (RJ 4) | 10 / 15 (RJ 15) | 4 / 5 (RJ 5) | 5 / 9 (RJ 6) | · | 9 / 13 (RJ 12) | 6 / 11 (RJ 8) | 7 / 20 (RJ 18) |
| **tele** | 7 / 12 (RJ 8) | 1 / 16 (RJ 15) | 9 / 16 (RJ 13) | 5 / 11 (RJ 6) | 1 / 3 (RJ 2) | 4 / 6 (RJ 5) | 7 / 13 (RJ 7) | 5 / 9 (RJ 6) | · | 3 / 10 (RJ 6) | 7 / 16 (RJ 11) |
| **NG** | 2 / 12 (RJ 2) | 7 / 12 (RJ 10) | 4 / 7 (RJ 6) | 3 / 10 (RJ 7) | 3 / 7 (RJ 7) | 5 / 10 (RJ 5) | 4 / 7 (RJ 6) | 7 / 12 (RJ 11) | 2 / 2 (RJ 3) | · | 1 / 10 (RJ 6) |
| **water** | 3 / 11 (RJ 2) | 6 / 10 (RJ 11) | 1 / 7 (RJ 12) | 4 / 9 (RJ 8) | 4 / 8 (RJ 6) | 6 / 11 (RJ 5) | 4 / 7 (RJ 7) | 8 / 12 (RJ 12) | 2 / 3 (RJ 4) | 0 / 1 (RJ 1) | · |

## e1m2

| from \ to | quad | YA | RL | mega | GA | GL | door | crossing | start | spikes |
|---|---|---|---|---|---|---|---|---|---|---|
| **quad** | · | 5 / 9 (RJ 7) | 11 / 20 | 7 / 12 | 10 / 14 | 2 / 5 (RJ 3) | 7 / 14 | 4 / 12 (RJ 16) | 14 / 16 | *~11* |
| **YA** | 7 / 13 (RJ 10) | · | 7 / 13 (RJ 10) | 11 / 19 (RJ 11) | 2 / 7 (RJ 4) | 2 / 6 (RJ 4) | 4 / 11 (RJ 6) | 6 / 14 (RJ 10) | 5 / 16 (RJ 12) | 3 / 11 (RJ 9) |
| **RL** | 7 / 12 (RJ 12) | 10 / 16 (RJ 11) | · | 7 / 12 (RJ 7) | 10 / 18 (RJ 13) | 8 / 12 (RJ 9) | 6 / 14 (RJ 13) | 4 / 6 (RJ 4) | 6 / 10 (RJ 11) | 10 / 16 (RJ 19) |
| **mega** | 7 / 13 (RJ 7) | 9 / 14 (RJ 11) | 8 / 15 | · | 6 / 14 (RJ 10) | 6 / 10 (RJ 7) | 3 / 8 (RJ 10) | 1 / 4 (RJ 2) | 9 / 10 | 8 / 16 (RJ 20) |
| **GA** | 7 / 15 (RJ 13) | 6 / 11 (RJ 8) | 3 / 6 (RJ 4) | 7 / 14 (RJ 10) | · | 8 / 15 (RJ 11) | 2 / 2 (RJ 2) | 3 / 8 (RJ 7) | 3 / 7 (RJ 11) | 3 / 6 (RJ 5) |
| **GL** | 3 / 9 (RJ 6) | 2 / 4 (RJ 4) | 10 / 16 (RJ 9) | 8 / 16 (RJ 11) | 5 / 9 (RJ 7) | · | 7 / 11 (RJ 10) | 4 / 12 (RJ 8) | 1 / 14 (RJ 17) | 1 / 13 (RJ 8) |
| **door** | 5 / 9 (RJ 6) | 6 / 10 (RJ 7) | 5 / 8 (RJ 7) | 5 / 8 (RJ 5) | 2 / 3 (RJ 2) | 5 / 10 (RJ 10) | · | 1 / 2 (RJ 1) | 4 / 7 (RJ 7) | 4 / 6 (RJ 4) |
| **crossing** | 3 / 6 (RJ 5) | 6 / 10 (RJ 8) | 7 / 13 (RJ 15) | 3 / 4 (RJ 3) | 4 / 12 (RJ 9) | 4 / 6 (RJ 5) | 1 / 3 (RJ 2) | · | 1 / 12 | 5 / 12 (RJ 6) |
| **start** | 10 / 18 | 8 / 11 (RJ 11) | 4 / 5 (RJ 4) | 11 / 18 (RJ 20) | 4 / 6 (RJ 5) | 10 / 16 (RJ 17) | 4 / 7 (RJ 4) | 5 / 11 (RJ 6) | · | 5 / 8 (RJ 9) |
| **spikes** | 8 / 17 | 2 / 3 (RJ 3) | 7 / 12 | 10 / 17 | 4 / 8 (RJ 9) | 5 / 9 (RJ 6) | 3 / 6 (RJ 5) | 4 / 10 (RJ 6) | 5 / 13 | · |

## schloss

| from \ to | quad | pent | red | tower YA | Cat YA | tower RL | Cat RL | yard mega | cemetery mega | cemetery tele | Cat SSG |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **quad** | · | 3 / 7 (RJ 6) | 9 / 16 (RJ 11) | 4 / 10 (RJ 4) | 2 / 5 (RJ 4) | 3 / 8 (RJ 5) | 1 / 1 (RJ 1) | 3 / 6 (RJ 5) | 4 / 11 (RJ 8) | 7 / 14 (RJ 10) | 3 / 9 (RJ 5) |
| **pent** | 4 / 10 (RJ 5) | · | 8 / 13 (RJ 8) | 4 / 8 (RJ 7) | 5 / 14 (RJ 9) | 1 / 10 (RJ 11) | 5 / 12 (RJ 7) | 1 / 2 (RJ 1) | 4 / 12 (RJ 12) | 1 / 13 (RJ 12) | 1 / 16 (RJ 10) |
| **red** | 9 / 14 (RJ 9) | 7 / 12 (RJ 8) | · | 6 / 12 (RJ 7) | 10 / 16 (RJ 11) | 4 / 9 (RJ 5) | 6 / 12 (RJ 9) | 4 / 10 (RJ 3) | 3 / 6 (RJ 3) | 3 / 8 (RJ 4) | 5 / 9 (RJ 7) |
| **tower YA** | 2 / 4 (RJ 4) | 2 / 6 (RJ 2) | 8 / 13 (RJ 9) | · | 6 / 9 (RJ 7) | 1 / 2 (RJ 1) | 3 / 8 (RJ 6) | 2 / 5 (RJ 2) | 6 / 12 (RJ 8) | 3 / 9 (RJ 5) | 6 / 13 (RJ 9) |
| **Cat YA** | 3 / 9 (RJ 6) | 6 / 14 (RJ 9) | 10 / 17 (RJ 10) | 5 / 14 (RJ 7) | · | 6 / 13 (RJ 9) | 1 / 4 (RJ 2) | 5 / 13 (RJ 8) | 4 / 10 (RJ 8) | 7 / 16 (RJ 11) | 3 / 8 (RJ 4) |
| **tower RL** | 4 / 7 (RJ 5) | 4 / 11 (RJ 7) | 7 / 13 (RJ 10) | 1 / 3 (RJ 2) | 7 / 12 (RJ 8) | · | 5 / 11 (RJ 8) | 4 / 10 (RJ 7) | 4 / 10 (RJ 7) | 2 / 4 (RJ 4) | 7 / 14 (RJ 8) |
| **Cat RL** | 1 / 2 (RJ 2) | 5 / 13 (RJ 8) | 7 / 15 (RJ 9) | 6 / 12 (RJ 8) | 1 / 2 (RJ 2) | 5 / 12 (RJ 8) | · | 5 / 11 (RJ 8) | 3 / 7 (RJ 4) | 6 / 14 (RJ 8) | 1 / 3 (RJ 2) |
| **yard mega** | 5 / 10 (RJ 3) | 0 / 1 (RJ 1) | 6 / 9 (RJ 6) | 6 / 12 (RJ 5) | 9 / 12 (RJ 7) | 6 / 10 (RJ 8) | 6 / 12 (RJ 6) | · | 5 / 10 (RJ 7) | 7 / 13 (RJ 10) | 6 / 13 (RJ 8) |
| **cemetery mega** | 4 / 10 (RJ 6) | 4 / 12 (RJ 5) | 4 / 7 (RJ 5) | 7 / 13 (RJ 4) | 5 / 10 (RJ 7) | 5 / 10 (RJ 2) | 3 / 5 (RJ 4) | 3 / 8 (RJ 6) | · | 4 / 8 (RJ 1) | 1 / 3 (RJ 1) |
| **cemetery tele** | 4 / 8 (RJ 6) | 5 / 11 (RJ 8) | 3 / 8 (RJ 6) | 2 / 3 (RJ 2) | 8 / 13 (RJ 10) | 1 / 1 (RJ 1) | 6 / 10 (RJ 7) | 5 / 10 (RJ 6) | 1 / 4 (RJ 2) | · | 4 / 9 (RJ 4) |
| **Cat SSG** | 3 / 4 (RJ 3) | 6 / 14 (RJ 10) | 5 / 10 (RJ 6) | 7 / 14 (RJ 10) | 3 / 5 (RJ 4) | 6 / 11 (RJ 6) | 1 / 2 (RJ 1) | 5 / 11 (RJ 8) | 1 / 2 (RJ 2) | 5 / 11 (RJ 5) | · |
