# Demo passes in the cloud (Cloud Run jobs)

Demo passes (`tools/mvd_features/*_pass.py`, `extract.py`) run in Cloud Run, not on a Mac.
Code: `tools/cloud_pass/`. Project `deepfrag-prod`, region `us-central1`.

## Pieces
| What | Where |
|---|---|
| Canonical feature DB (was `data/mvd_features.sqlite` on the MacBook) | `gs://deepfrag-mvd/db/mvd_features.sqlite` |
| Demo cache (hub demos fetched once, then read from here) | `gs://deepfrag-mvd/demos/<sha[:3]>/<sha>.mvd.gz` |
| One run's manifest, seed DB and per-task results (deleted after 30 days) | `gs://deepfrag-mvd/runs/<run_id>/` |
| Image (qw-analyze cross-compiled from `~/Projects/mvd_analyzer` + the pass scripts) | `.../cloud-run-source-deploy/demo-pass`, built by `tools/cloud_pass/build.sh` |
| Sharded job, 2 vCPU / 4 GiB per task, up to 50 at once | Cloud Run job `demo-pass` |
| Nightly job, 4 vCPU / 8 GiB, one task | Cloud Run job `demo-nightly`, Cloud Scheduler `demo-nightly` at 09:00 UTC |
| Service account of both jobs (bucket only) | `deepfrag-passes@` |

## On demand
Run from the dev VM (`deepfrag-devbox`), where pulling and pushing the 2.4 GB DB is free:

```bash
python3 tools/cloud_pass/submit.py run --since 2025-06-01 --mode 4on4 --map dm3 --passes quad_track --tasks 50
python3 tools/cloud_pass/submit.py run --manifest m.json --passes extract,items,quad_track
python3 tools/cloud_pass/submit.py pull          # canonical DB -> data/mvd_features.sqlite
```

`run` pulls the canonical DB, writes a seed (the run's `games` rows + `map_items_xyz`), uploads
manifest + seed, starts `demo-pass` with one task per slice, then merges every shard back. Merging
replaces, per game (and per `source` where a table has one), what the canonical DB held, so a pass
can be re-run safely. The upload is refused if the DB changed meanwhile (the nightly job); run
`submit.py merge <run_id>` again then. Passes do not skip games the canonical DB already has: a run
recomputes every game in its manifest.

## Nightly
`run_shard.py nightly` downloads the canonical DB, lists hub games (4on4 and 1on1) of the last
`NIGHTLY_HOURS` (36) it has not seen, runs every pass on them in place and uploads the DB.
`extract.py` keeps only the NA hosts in its `ALLOWED` list (The-Den, la.quake.world, Mom's Basement,
ny.quake.world); DeepFrag's own servers are not on the hub, so their games are not in it.

## A new pass
Read `$MVD_FEATURES_DB` and `$QW_ANALYZE`, fetch demos with `demo_fetch.fetch_mvd(sha, tmp)`, add the
pass to `tools/cloud_pass/passes.py`, rebuild the image (`build.sh`) and update both jobs to the new
image (`gcloud run jobs update demo-pass --image ...:latest`, same for `demo-nightly`).

## Cost
Cloud Run bills per vCPU-second and GiB-second while tasks run; the monthly free tier covers about
180,000 vCPU-seconds. Measured runs are below.

Measured 2026-10-26:
| Run | Wall time | Task time | Cost (before free tier) |
|---|---|---|---|
| `quad_track`, 1,088 NA fours games, 50 tasks of 2 vCPU | 2 min 20 s (2 min 53 s with submit) | 3,586 task-s = 7,172 vCPU-s | about $0.16 |
| Nightly, 139 hub games (25 NA kept), all six passes, 4 vCPU | 8 min 10 s, of which ~1 min is the DB down/up | ~490 s = 1,960 vCPU-s | about $0.05 |
| Merge of the 50 shards into the canonical DB (on the VM) | 86 s | — | free |
