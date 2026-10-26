"""Run demo passes in Cloud Run and merge the results into the canonical feature DB.

The canonical DB is gs://deepfrag-mvd/db/mvd_features.sqlite (the nightly job updates it too).
Run this on the dev VM: pulling and pushing the 2.4 GB DB there costs nothing; from a Mac it is
internet egress (about $0.30 a pull).

    # a pass over a manifest (hub_fetch.py output), 50 tasks, merged into the canonical DB
    python3 tools/cloud_pass/submit.py run --manifest m.json --passes extract,quad_track --tasks 50
    # or let the hub pick the games
    python3 tools/cloud_pass/submit.py run --since 2025-09-21 --mode 4on4 --map dm3 --passes quad_track
    python3 tools/cloud_pass/submit.py merge <run_id>     # re-merge a finished run
    python3 tools/cloud_pass/submit.py pull [path]        # canonical DB -> data/mvd_features.sqlite
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

from google.cloud import storage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import passes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUCKET = os.environ.get('DEMO_BUCKET', 'deepfrag-mvd')
CANON = 'db/mvd_features.sqlite'
JOB, REGION = 'demo-pass', 'us-central1'
SEED_TABLES = ['map_items_xyz']   # copied whole into every shard; `games` is copied for the run's ids


def bucket():
    return storage.Client().bucket(BUCKET)


def pull(path=None, gen_out=None):
    path = path or os.path.join(ROOT, 'data', 'mvd_features.sqlite')
    blob = bucket().blob(CANON); blob.reload()
    t0 = time.time(); blob.download_to_filename(path)
    print(f'pulled canonical DB (gen {blob.generation}) to {path} in {time.time() - t0:.0f}s')
    return blob.generation


def seed(canon, ids, out):
    s = sqlite3.connect(out); s.execute('ATTACH ? AS c', (canon,))
    for t in ['games', *SEED_TABLES]:
        ddl = s.execute("SELECT sql FROM c.sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not ddl:
            continue
        s.execute(ddl[0])
        if t == 'games':
            s.execute('CREATE TEMP TABLE want(id INTEGER PRIMARY KEY)'); s.executemany('INSERT INTO want VALUES (?)', [(i,) for i in ids])
            s.execute('INSERT INTO games SELECT * FROM c.games WHERE id IN (SELECT id FROM want)')
        else:
            s.execute(f'INSERT INTO {t} SELECT * FROM c.{t}')
    s.commit(); s.execute('DETACH c'); s.close()


def merge_shard(con, shard):
    """Replace, per game, whatever the canonical DB holds for the games the shard processed."""
    con.execute('ATTACH ? AS s', (shard,))
    for (t, ddl) in con.execute("SELECT name, sql FROM s.sqlite_master WHERE type='table'").fetchall():
        if not con.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (t,)).fetchone():
            con.execute(ddl)
        cols = [r[1] for r in con.execute(f'PRAGMA s.table_info({t})')]
        if t == 'games':
            con.execute('INSERT OR REPLACE INTO main.games SELECT * FROM s.games')
        elif 'game_id' in cols:
            key = 'source, game_id' if 'source' in cols else 'game_id'
            con.execute(f'DELETE FROM main.{t} WHERE ({key}) IN (SELECT DISTINCT {key} FROM s.{t})')
            con.execute(f'INSERT INTO main.{t} SELECT * FROM s.{t}')
        else:
            con.execute(f'INSERT INTO main.{t} SELECT * FROM s.{t} EXCEPT SELECT * FROM main.{t}')
    con.commit(); con.execute('DETACH s')


def merge(run_id):
    b = bucket(); shards = list(b.list_blobs(prefix=f'runs/{run_id}/shards/'))
    with tempfile.TemporaryDirectory() as tmp:
        canon = os.path.join(tmp, 'canon.sqlite'); gen = pull(canon)
        con = sqlite3.connect(canon)
        for blob in shards:
            p = os.path.join(tmp, 'shard.sqlite'); blob.download_to_filename(p); merge_shard(con, p); os.remove(p)
        con.close()
        b.blob(CANON).upload_from_filename(canon, if_generation_match=gen)
    print(f'merged {len(shards)} shards of {run_id} into gs://{BUCKET}/{CANON}')


def run(a):
    names = passes.ordered(a.passes)
    if a.manifest:
        games = json.load(open(a.manifest))
    else:
        out = tempfile.mktemp(suffix='.json')
        cmd = [sys.executable, os.path.join(ROOT, 'tools/mvd_features/hub_fetch.py'), '--since', a.since, '--out', out]
        cmd += ['--mode', a.mode] if a.mode else []; cmd += ['--map', a.map] if a.map else []
        subprocess.run(cmd, check=True); games = json.load(open(out))
    games = [g for g in games if g.get('demo_sha256')]
    if not games:
        sys.exit('no games with demos in the manifest')
    run_id = dt.datetime.utcnow().strftime('%Y%m%d-%H%M%S') + '-' + '-'.join(names)
    tasks = max(1, min(a.tasks, len(games)))
    with tempfile.TemporaryDirectory() as tmp:
        canon = os.path.join(tmp, 'canon.sqlite'); pull(canon)
        sd = os.path.join(tmp, 'seed.sqlite'); seed(canon, [g['id'] for g in games], sd)
        b = bucket()
        b.blob(f'runs/{run_id}/manifest.json').upload_from_string(json.dumps(games))
        b.blob(f'runs/{run_id}/seed.sqlite').upload_from_filename(sd)
    print(f'{run_id}: {len(games)} games, {tasks} tasks, passes {names}', flush=True)
    # '^;^' makes ';' gcloud's separator: PASSES and MODES contain commas
    env = f'^;^RUN=gs://{BUCKET}/runs/{run_id};PASSES={",".join(names)};SOURCE={a.source};MODES={a.modes}'
    t0 = time.time()
    subprocess.run(['gcloud', 'run', 'jobs', 'execute', JOB, '--region', REGION, '--tasks', str(tasks),
                    '--update-env-vars', env, '--wait'], check=True)
    print(f'{run_id}: cloud run finished in {time.time() - t0:.0f}s', flush=True)
    if not a.no_merge:
        merge(run_id)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--passes', required=True, help=f'comma list of {passes.ORDER}')
    r.add_argument('--manifest'); r.add_argument('--since'); r.add_argument('--mode'); r.add_argument('--map')
    r.add_argument('--tasks', type=int, default=50); r.add_argument('--source', default='na')
    r.add_argument('--modes', default='4on4,1on1', help='modes extract keeps')
    r.add_argument('--no-merge', action='store_true')
    m = sub.add_parser('merge'); m.add_argument('run_id')
    p = sub.add_parser('pull'); p.add_argument('path', nargs='?')
    a = ap.parse_args()
    if a.cmd == 'run' and not (a.manifest or a.since):
        ap.error('run needs --manifest or --since')
    {'run': lambda: run(a), 'merge': lambda: merge(a.run_id), 'pull': lambda: pull(a.path)}[a.cmd]()
