"""Fours re-pass (v3): item take events + power-up intervals, for run cards, RA timing and item-control stats."""
import json, sqlite3, subprocess, os, time, urllib.request, gzip, shutil, tempfile
from multiprocessing import Pool
ANALYZER=os.path.abspath('../qw-analyze'); DB='/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
def process(g):
    gid=g['id']; sha=g['demo_sha256']; tmp=tempfile.mkdtemp(prefix='mvd_')
    try:
        url=f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz"; gz=os.path.join(tmp,'d.mvd.gz'); mvd=os.path.join(tmp,'d.mvd')
        with urllib.request.urlopen(url,timeout=60) as r, open(gz,'wb') as f: shutil.copyfileobj(r,f)
        with gzip.open(gz,'rb') as fi, open(mvd,'wb') as fo: shutil.copyfileobj(fi,fo)
        out=subprocess.run([ANALYZER,'-view','full',mvd],capture_output=True,timeout=120)
        d=json.loads(out.stdout); END=d['streams']['global']['matchEnd']
        team={p['name']:p['team'] for p in d['match']['players']}
        for sp_ in d['streams']['players']:
            if sp_['name'] not in team and sp_.get('team'): team[sp_['name']]=sp_['team']
        takes=[]; pws=[]
        for it in (d.get('items') or {}).get('items') or []:
            for ph in it.get('phases') or []:
                if ph.get('takenAt') is None or not ph.get('takenBy') or ph['takenBy'] not in team: continue
                takes.append((gid,ph['takenAt'],ph['takenBy'],team[ph['takenBy']],it['kind'],it['name'],it.get('loc',''),ph.get('availableFrom'),int(ph['takenAt']-(ph.get('availableFrom') or ph['takenAt']))))
        for p in d['streams']['players']:
            if p['name'] not in team: continue
            for k,lab in (('q','quad'),('pe','pent'),('r','ring')):
                for iv in p.get(k,[]) or []: pws.append((gid,p['name'],team[p['name']],lab,iv['s'],iv['e']))
        return {'id':gid,'takes':takes,'pws':pws}
    except Exception as e:
        return {'id':gid,'error':f'{type(e).__name__}: {str(e)[:120]}'}
    finally: shutil.rmtree(tmp,ignore_errors=True)
def main():
    con=sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS item_takes(game_id INT, t INT, name TEXT, team TEXT, kind TEXT, item TEXT, loc TEXT, available_from INT, wait_ms INT)")
    con.execute("CREATE INDEX IF NOT EXISTS it_g ON item_takes(game_id)")
    con.execute("CREATE TABLE IF NOT EXISTS powerups(game_id INT, name TEXT, team TEXT, kind TEXT, s INT, e INT)")
    con.execute("CREATE INDEX IF NOT EXISTS pw_g ON powerups(game_id)"); con.commit()
    done={r[0] for r in con.execute("SELECT DISTINCT game_id FROM item_takes")}
    ids={r[0] for r in con.execute("SELECT id FROM games WHERE mode='4on4'")}
    games=[g for g in json.load(open('manifest_all.json')) if g['id'] in ids and g['id'] not in done]
    print(f'todo {len(games)} fours', flush=True); t0=time.time(); n=0; errs=0
    with Pool(6) as pool:
        for res in pool.imap_unordered(process, games, chunksize=2):
            n+=1
            if 'error' in res: errs+=1; print('ERR',res['id'],res['error'],flush=True)
            else:
                con.executemany("INSERT INTO item_takes VALUES (?,?,?,?,?,?,?,?,?)",res['takes'])
                con.executemany("INSERT INTO powerups VALUES (?,?,?,?,?,?)",res['pws'])
            if n%50==0: con.commit(); print(f'{n}/{len(games)} {errs} errors {time.time()-t0:.0f}s', flush=True)
    con.commit(); print(f'FINISHED {n} {errs} errors {time.time()-t0:.0f}s', flush=True)
if __name__=='__main__': main()
