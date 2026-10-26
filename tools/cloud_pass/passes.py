"""The demo passes the cloud runner knows, in the order they must run, and how each is invoked.

Every pass reads `manifest_all.json` (or the manifest named on its command line) from the
working directory and writes into $MVD_FEATURES_DB. `extract` fills `games`, which the others
select their games from, so it always runs first when it is asked for.
"""
import os

ORDER = ['extract', 'items', 'player_state', 'quad_exact', 'quad_approach', 'quad_track']
NIGHTLY = ORDER


def argv(name, workers, source='na', modes='4on4,1on1'):
    w = str(workers)
    return {
        'extract': ['extract.py', 'manifest_all.json', modes, w],
        'items': ['items_pass.py', '4on4'],
        'player_state': ['player_state_pass.py'],
        'quad_exact': ['quad_exact_pass.py', w],
        'quad_approach': ['quad_approach_pass.py', w],
        'quad_track': ['quad_track_pass.py', 'manifest_all.json', source, '--workers', w],
    }[name]


def ordered(names):
    names = [n.strip() for n in names.split(',') if n.strip()] if isinstance(names, str) else list(names)
    unknown = [n for n in names if n not in ORDER]
    if unknown:
        raise SystemExit(f'unknown pass(es): {unknown}; known: {ORDER}')
    return [n for n in ORDER if n in names]


def workers():
    return max(1, os.cpu_count() or 1)
