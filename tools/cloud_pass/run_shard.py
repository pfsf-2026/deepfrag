"""Cloud Run job entrypoint: run demo passes over one slice of a run's manifest, or the nightly pass.

Shard mode (job `demo-pass`, started by submit.py; one task per slice):
    env RUN=gs://<bucket>/runs/<run_id>, PASSES=extract,quad_track, SOURCE=na, MODES=4on4,1on1
    reads RUN/manifest.json and RUN/seed.sqlite, takes games i::N by id (CLOUD_RUN_TASK_INDEX /
    CLOUD_RUN_TASK_COUNT), runs the passes into a shard DB seeded from seed.sqlite, and uploads it to
    RUN/shards/<i>.sqlite for submit.py to merge.

Nightly mode (job `demo-nightly`, Cloud Scheduler; `run_shard.py nightly`):
    downloads the canonical gs://<bucket>/db/mvd_features.sqlite, lists the hub games of the last
    NIGHTLY_HOURS (default 36) that it has not seen, runs the NIGHTLY passes on them in place and
    uploads the DB back, refusing if someone else replaced it meanwhile.
"""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time

from google.cloud import storage

import passes

APP = os.path.dirname(os.path.abspath(__file__))
MVD = os.environ.get('MVD_FEATURES_DIR', os.path.join(APP, 'mvd_features'))
WORK = '/tmp/work'
BUCKET = os.environ.get('DEMO_BUCKET', 'deepfrag-mvd')
CANON = 'db/mvd_features.sqlite'


def split(uri):
    b, _, k = uri.removeprefix('gs://').partition('/')
    return storage.Client().bucket(b), k


def run_passes(names, db, source, modes):
    env = dict(os.environ, MVD_FEATURES_DB=db, QW_ANALYZE=os.path.join(APP, 'qw-analyze'), DEMO_BUCKET=BUCKET)
    for name in passes.ordered(names):
        cmd = [sys.executable, os.path.join(MVD, passes.argv(name, passes.workers(), source, modes)[0]),
               *passes.argv(name, passes.workers(), source, modes)[1:]]
        print(f'== {name}: {" ".join(cmd[1:])}', flush=True); t0 = time.time()
        subprocess.run(cmd, cwd=WORK, env=env, check=True)
        print(f'== {name} done in {time.time() - t0:.0f}s', flush=True)
        if name == 'extract':
            # extract keeps only its ALLOWED (NA) hosts; quad_track reads the manifest itself and
            # would otherwise tag every other game with this source
            path = os.path.join(WORK, 'manifest_all.json'); con = sqlite3.connect(db)
            kept = {r[0] for r in con.execute('SELECT id FROM games')}; con.close()
            games = [g for g in json.load(open(path)) if g['id'] in kept]
            json.dump(games, open(path, 'w')); print(f'== manifest: {len(games)} games kept by extract', flush=True)


def shard():
    i, n = int(os.environ.get('CLOUD_RUN_TASK_INDEX', 0)), int(os.environ.get('CLOUD_RUN_TASK_COUNT', 1))
    bucket, prefix = split(os.environ['RUN'])
    games = sorted(json.loads(bucket.blob(f'{prefix}/manifest.json').download_as_bytes()), key=lambda g: g['id'])[i::n]
    print(f'task {i}/{n}: {len(games)} games, passes {os.environ["PASSES"]}, {passes.workers()} cpus', flush=True)
    json.dump(games, open(os.path.join(WORK, 'manifest_all.json'), 'w'))
    db = os.path.join(WORK, 'shard.sqlite')
    seed = bucket.blob(f'{prefix}/seed.sqlite')
    if seed.exists():
        seed.download_to_filename(db)
    if games:
        run_passes(os.environ['PASSES'], db, os.environ.get('SOURCE', 'na'), os.environ.get('MODES', '4on4,1on1'))
    sqlite3.connect(db).close()
    bucket.blob(f'{prefix}/shards/{i:04d}.sqlite').upload_from_filename(db)
    print(f'task {i}: uploaded shard', flush=True)


def nightly():
    bucket = storage.Client().bucket(BUCKET); blob = bucket.blob(CANON); blob.reload()
    gen = blob.generation; db = os.path.join(WORK, 'mvd_features.sqlite')
    t0 = time.time(); blob.download_to_filename(db); print(f'canonical DB in {time.time() - t0:.0f}s (gen {gen})', flush=True)
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=int(os.environ.get('NIGHTLY_HOURS', 36)))).strftime('%Y-%m-%dT%H:%M:%S')
    games = []
    for mode in os.environ.get('MODES', '4on4,1on1').split(','):
        out = os.path.join(WORK, f'hub_{mode}.json')
        subprocess.run([sys.executable, os.path.join(MVD, 'hub_fetch.py'), '--mode', mode, '--since', since, '--out', out], check=True)
        games += json.load(open(out))
    con = sqlite3.connect(db)
    seen = {r[0] for r in con.execute('SELECT id FROM games')} | {r[0] for r in con.execute('SELECT game_id FROM errors')}
    con.close()
    new = [g for g in games if g['id'] not in seen]
    print(f'nightly: {len(games)} hub games since {since}, {len(new)} new', flush=True)
    if not new:
        return
    json.dump(new, open(os.path.join(WORK, 'manifest_all.json'), 'w'))
    run_passes(os.environ.get('PASSES', ','.join(passes.NIGHTLY)), db, os.environ.get('SOURCE', 'na'), os.environ.get('MODES', '4on4,1on1'))
    blob.upload_from_filename(db, if_generation_match=gen)
    print(f'nightly: canonical DB updated ({len(new)} games)', flush=True)


if __name__ == '__main__':
    os.makedirs(WORK, exist_ok=True)
    nightly() if sys.argv[1:] == ['nightly'] else shard()
