"""Optional GPU candidate retrieval. No ML dependencies, user query storage, or eligibility changes."""
import array
import hashlib
import json
import math
import os
import sqlite3
import threading
import urllib.request
from contextlib import contextmanager

from config import DATA_DIR

DIMENSIONS = 1024
_index_lock = threading.Lock()


def settings():
    return tuple(os.getenv(k, '') for k in ('EMBEDDING_URL', 'EMBEDDING_API_KEY', 'EMBEDDING_MODEL'))


def configured():
    return all(settings())


def policy_text(policy):
    return '\n'.join(str(policy.get(k) or '')[:limit] for k, limit in
                     (('title', 200), ('summary', 650), ('target', 650), ('benefit', 1500)))


def fingerprint(policy):
    return hashlib.sha256(policy_text(policy).encode()).hexdigest()


@contextmanager
def connection():
    conn = sqlite3.connect(DATA_DIR / 'policy-vectors.sqlite3', timeout=5)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS vectors(model TEXT, fingerprint TEXT, '
                     'vector BLOB, PRIMARY KEY(model, fingerprint))')
        with conn:
            yield conn
    finally:
        conn.close()


def valid_vector(values):
    if not isinstance(values, list) or len(values) != DIMENSIONS:
        raise ValueError('Invalid embedding dimensions')
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
        raise ValueError('Non-finite embedding')
    norm = math.sqrt(sum(v * v for v in values))
    if not 0.9 <= norm <= 1.1:
        raise ValueError('Embedding must be normalized')
    return array.array('f', (v / norm for v in values))


def encode(texts, timeout):
    url, key, model = settings()
    request = urllib.request.Request(url.rstrip('/') + '/v1/embeddings',
        data=json.dumps({'model': model, 'input': texts}, ensure_ascii=False).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Embedding response too large')
    payload = json.loads(raw)
    data = payload.get('data', [])
    if payload.get('model') != model or len(data) != len(texts):
        raise ValueError('Embedding response model/count mismatch')
    if any(type(item.get('index')) is not int for item in data) or sorted(item['index'] for item in data) != list(range(len(texts))):
        raise ValueError('Embedding response index mismatch')
    return [valid_vector(item['embedding']) for item in sorted(data, key=lambda item: item['index'])]


def index_catalog(catalog):
    """Background only: embed changed public policy text, commit in small resumable batches."""
    if not configured() or not _index_lock.acquire(blocking=False):
        return 0
    try:
        model = settings()[2]
        with connection() as conn:
            known = {r[0] for r in conn.execute('SELECT fingerprint FROM vectors WHERE model=?', (model,))}
        pending = {fingerprint(p): policy_text(p) for p in catalog if fingerprint(p) not in known}
        rows = list(pending.items())
        for start in range(0, len(rows), 8):
            batch = rows[start:start + 8]
            vectors = encode([text for _, text in batch], timeout=60)
            with connection() as conn:
                conn.executemany('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',
                    [(model, key, vec.tobytes()) for (key, _), vec in zip(batch, vectors)])
        return len(rows)
    finally:
        _index_lock.release()


def index_current():
    from engine import load_catalog
    return index_catalog(load_catalog()[0])


def rerank(catalog, profile, lexical):
    """RRF blends top-60 candidate lists; final eligibility/ranking remains in engine.finalize."""
    if not configured() or not catalog:
        return lexical
    query = ' '.join([*(profile.get('focus_summary') or profile.get('story_summary') or []),
                      *profile.get('search_terms', [])]).strip()[:1500]
    if not query:
        return lexical
    try:
        model = settings()[2]
        with connection() as conn:
            stored = dict(conn.execute('SELECT fingerprint, vector FROM vectors WHERE model=?', (model,)))
        # A new publication or partial rebuild must never hide new/unindexed policies.
        keys = [fingerprint(p) for p in catalog]
        if any(key not in stored for key in keys):
            return lexical
        query_vector = encode([query], timeout=2)[0]
        scores = []
        for policy, key in zip(catalog, keys):
            vector = array.array('f')
            vector.frombytes(stored[key])
            if len(vector) != DIMENSIONS or any(not math.isfinite(v) for v in vector):
                return lexical
            scores.append((sum(a * b for a, b in zip(query_vector, vector)), policy))
        semantic = [p for _, p in sorted(scores, key=lambda item: (-item[0], item[1]['id']))[:60]]
        fused = {}
        for ranked in (lexical[:60], semantic):
            for rank, policy in enumerate(ranked, 1):
                fused[policy['id']] = fused.get(policy['id'], 0) + 1 / (60 + rank)
        order = {p['id']: i for i, p in enumerate(lexical)}
        return sorted(lexical, key=lambda p: (-fused.get(p['id'], 0), order[p['id']]))
    except Exception:
        # Timeout, busy GPU, bad response or index damage preserves the working lexical path.
        return lexical


if __name__ == '__main__':
    print('New public-policy embeddings:', index_current())
