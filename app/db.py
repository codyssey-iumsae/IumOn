"""Public policy store (SQLite). Holds public source rows, the published catalog and analysis caches.
Personal answers are never written here; only public policy IDs are counted for analysis priority."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from config import DATA_DIR

PATH = DATA_DIR / 'iumon.sqlite3'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS collection_runs(
  run_id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT,
  state TEXT CHECK(state IN ('running','published','done','failed')), stats TEXT);
CREATE TABLE IF NOT EXISTS source_status(
  source TEXT PRIMARY KEY, state TEXT, fetched_at TEXT, row_count INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS source_rows(
  source TEXT, ord INTEGER, source_id TEXT, payload TEXT, fetched_at TEXT, PRIMARY KEY(source, ord));
CREATE TABLE IF NOT EXISTS welfare_details(
  source TEXT, source_id TEXT, list_updated TEXT, payload TEXT, fetched_at TEXT, PRIMARY KEY(source, source_id));
CREATE TABLE IF NOT EXISTS api_budget(day TEXT, source TEXT, used INTEGER, PRIMARY KEY(day, source));
CREATE TABLE IF NOT EXISTS policies(
  run_id INTEGER, ord INTEGER, policy_id TEXT, payload TEXT, PRIMARY KEY(run_id, ord));
CREATE TABLE IF NOT EXISTS policy_relations(
  run_id INTEGER, a TEXT, b TEXT, relation TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, kind TEXT, payload TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS analysis_failures(
  fingerprint TEXT PRIMARY KEY, policy_id TEXT, attempts INTEGER, last_error TEXT, last_attempt TEXT);
CREATE TABLE IF NOT EXISTS analysis_demand(policy_id TEXT PRIMARY KEY, hits INTEGER, last_seen TEXT);
'''
KEEP_RUNS = 3
_ready = set()
_ready_lock = threading.Lock()

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def connect():
    """One short-lived connection per use; commits on success, rolls back on error, always closes."""
    db = sqlite3.connect(PATH, timeout=30)
    try:
        if str(PATH) not in _ready:
            with _ready_lock:
                db.execute('PRAGMA journal_mode=WAL')
                db.executescript(SCHEMA)
                _ready.add(str(PATH))
        with db:
            yield db
    finally:
        db.close()

def get_meta(db, key):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else None

def set_meta(db, key, value):
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, value))

# --- public source rows -------------------------------------------------------------------------

def replace_source(db, source, rows, id_field):
    """A successful fetch replaces the whole source, so rows the API dropped disappear too."""
    db.execute('DELETE FROM source_rows WHERE source=?', (source,))
    stamp = now()
    db.executemany('INSERT INTO source_rows VALUES (?,?,?,?,?)',
                   [(source, i, str(r.get(id_field, '')), json.dumps(r, ensure_ascii=False), stamp)
                    for i, r in enumerate(rows)])

def source_rows(db):
    out = {}
    for source, payload in db.execute('SELECT source, payload FROM source_rows ORDER BY source, ord'):
        out.setdefault(source, []).append(json.loads(payload))
    return out

def set_source_status(db, source, state, rows=None, error=None):
    old = db.execute('SELECT fetched_at, row_count FROM source_status WHERE source=?', (source,)).fetchone()
    fetched, count = (now(), rows) if state == 'ok' else ((old or (None, None))[0], (old or (None, None))[1])
    db.execute('INSERT OR REPLACE INTO source_status VALUES (?,?,?,?,?)', (source, state, fetched, count, error))

def source_status(db):
    return {s: {'state': st, 'fetched_at': f} for s, st, f in
            db.execute('SELECT source, state, fetched_at FROM source_status')}

def details(db):
    """Same shape as the former details.json: {'source:id': {'data', 'fetched_at', 'list_updated'}}."""
    return {f'{s}:{i}': {'data': json.loads(p), 'fetched_at': f, 'list_updated': u}
            for s, i, u, p, f in db.execute('SELECT source, source_id, list_updated, payload, fetched_at FROM welfare_details')}

def put_detail(db, source, sid, list_updated, data, fetched_at=None):
    db.execute('INSERT OR REPLACE INTO welfare_details VALUES (?,?,?,?,?)',
               (source, sid, list_updated, json.dumps(data, ensure_ascii=False), fetched_at or now()))

def budget_used(db, day, source):
    row = db.execute('SELECT used FROM api_budget WHERE day=? AND source=?', (day, source)).fetchone()
    return row[0] if row else 0

def spend_budget(db, day, source, amount):
    db.execute('INSERT INTO api_budget VALUES (?,?,?) ON CONFLICT(day, source) DO UPDATE SET used=used+excluded.used',
               (day, source, amount))

# --- runs and the published catalog --------------------------------------------------------------

def start_run(db, started_at=None):
    return db.execute("INSERT INTO collection_runs(started_at, state) VALUES (?, 'running')",
                      (started_at or now(),)).lastrowid

def end_run(db, run_id, state, stats=None):
    """Close a run that did not publish: 'done' (no publish stage) or 'failed'."""
    db.execute('UPDATE collection_runs SET state=?, finished_at=?, stats=COALESCE(?, stats) WHERE run_id=?',
               (state, now(), json.dumps(stats, ensure_ascii=False) if stats is not None else None, run_id))

def publish(db, run_id, policies, relations, stats):
    """Write the new catalog and switch the active run in one transaction: readers see old or new, never half."""
    db.executemany('INSERT INTO policies VALUES (?,?,?,?)',
                   [(run_id, i, p['id'], json.dumps(p, ensure_ascii=False)) for i, p in enumerate(policies)])
    db.executemany('INSERT INTO policy_relations VALUES (?,?,?,?,?)',
                   [(run_id, r['a'], r['b'], r['relation'], r.get('reason', '')) for r in relations])
    db.execute("UPDATE collection_runs SET state='published', finished_at=?, stats=? WHERE run_id=?",
               (now(), json.dumps(stats, ensure_ascii=False), run_id))
    set_meta(db, 'active_run_id', str(run_id))
    old = [r for (r,) in db.execute("SELECT run_id FROM collection_runs WHERE state='published' ORDER BY run_id DESC")][KEEP_RUNS:]
    for table in ('policies', 'policy_relations'):
        db.executemany(f'DELETE FROM {table} WHERE run_id=?', [(r,) for r in old])

def active_run():
    """(run_id, stats) of the published catalog, or None before the first publish."""
    with connect() as db:
        value = get_meta(db, 'active_run_id')
        if not value:
            return None
        row = db.execute('SELECT stats FROM collection_runs WHERE run_id=?', (int(value),)).fetchone()
    return int(value), json.loads(row[0]) if row and row[0] else {}

def load_policies(run_id):
    with connect() as db:
        return [json.loads(p) for (p,) in db.execute('SELECT payload FROM policies WHERE run_id=? ORDER BY ord', (run_id,))]

def relations_for(run_id, ids):
    ids = set(ids)
    with connect() as db:
        rows = db.execute('SELECT a, b, relation, reason FROM policy_relations WHERE run_id=?', (run_id,)).fetchall()
    return [{'a': a, 'b': b, 'relation': r, 'reason': why} for a, b, r, why in rows if a in ids and b in ids]

def last_attempt():
    """(started_at, state) of the newest run, or None."""
    with connect() as db:
        return db.execute('SELECT started_at, state FROM collection_runs ORDER BY run_id DESC LIMIT 1').fetchone()

# --- analysis bookkeeping ------------------------------------------------------------------------

def record_demand(policy_ids):
    """A policy shown as '분석 대기' is analyzed first in the next batch. Only public IDs are stored."""
    if not policy_ids:
        return
    stamp = now()
    with connect() as db:
        db.executemany('INSERT INTO analysis_demand VALUES (?,1,?) ON CONFLICT(policy_id) '
                       'DO UPDATE SET hits=hits+1, last_seen=excluded.last_seen', [(i, stamp) for i in policy_ids])

def demand():
    with connect() as db:
        return dict(db.execute('SELECT policy_id, hits FROM analysis_demand'))

def record_failure(fingerprint, policy_id, error):
    with connect() as db:
        db.execute('INSERT INTO analysis_failures VALUES (?,?,1,?,?) ON CONFLICT(fingerprint) DO UPDATE SET '
                   'attempts=attempts+1, last_error=excluded.last_error, last_attempt=excluded.last_attempt',
                   (fingerprint, policy_id, str(error)[:300], now()))

def clear_demand(policy_ids):
    with connect() as db:
        db.executemany('DELETE FROM analysis_demand WHERE policy_id=?', [(i,) for i in policy_ids])

def analyzed_keys():
    with connect() as db:
        return {k for (k,) in db.execute("SELECT key FROM cache WHERE kind='policy'")}

def failures():
    with connect() as db:
        return {f: (n, t) for f, n, t in db.execute('SELECT fingerprint, attempts, last_attempt FROM analysis_failures')}
