"""Fetch a hub demo by sha256 into a temp dir and return the path of the unpacked .mvd.

With DEMO_BUCKET set (the Cloud Run demo passes), the gzipped demo is read from
gs://$DEMO_BUCKET/demos/<sha[:3]>/<sha>.mvd.gz first, and a demo fetched from the hub is
written back there, so a corpus is downloaded from d.quake.world once, not once per pass.
"""
import gzip
import os
import shutil
import time
import urllib.request

_bucket = None


def _cache():
    global _bucket
    name = os.environ.get('DEMO_BUCKET')
    if name and _bucket is None:
        from google.cloud import storage
        _bucket = storage.Client().bucket(name)
    return _bucket if name else None


def fetch_mvd(sha, tmp):
    gz = os.path.join(tmp, 'd.mvd.gz'); mvd = os.path.join(tmp, 'd.mvd')
    bucket = _cache(); blob = bucket.blob(f'demos/{sha[:3]}/{sha}.mvd.gz') if bucket else None
    if blob is not None and blob.exists():
        blob.download_to_filename(gz)
    else:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz", timeout=60) as r, open(gz, 'wb') as f:
                    shutil.copyfileobj(r, f)
                break
            except Exception:
                if attempt == 2: raise
                time.sleep(2)
        if blob is not None:
            try:
                blob.upload_from_filename(gz)
            except Exception:
                pass   # the cache is an optimisation; the demo is already here

    with gzip.open(gz, 'rb') as fi, open(mvd, 'wb') as fo:
        shutil.copyfileobj(fi, fo)
    return mvd
