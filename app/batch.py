"""Daily batch: public APIs -> SQLite -> published catalog -> pre-analysis of public policy text.
The server only reads what this writes. No personal profile is sent or saved here.

  python app/batch.py                          # every stage
  python app/batch.py --stages collect,details,publish   # no LLM except cached decisions
  python app/batch.py --stages analyze --llm-limit 50
  python app/batch.py --dry-run                # counts only: no API, LLM or writes
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from config import DATA_DIR
import db

KST = ZoneInfo('Asia/Seoul')
STAGES = ('collect', 'details', 'publish', 'analyze')
# (stored source name, id field, fetcher). gov_detail carries 구비서류 for the preparation screen.
SOURCES = [('gov_list', '서비스ID', lambda c: c.gov('serviceList')),
           ('gov_conditions', '서비스ID', lambda c: c.gov('supportConditions')),
           ('gov_detail', '서비스ID', lambda c: c.gov('serviceDetail')),
           ('national', 'servId', lambda c: c.welfare()),
           ('local', 'servId', lambda c: c.welfare(True))]
SCOPE_ORDER = {'청양군': 0, '충청남도': 1, '전국': 2}
LOCK = DATA_DIR / '.refresh.lock'

def log(*args):
    print(*args, flush=True)

def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default

# --- stages --------------------------------------------------------------------------------------

def collect():
    """Fetch each source; a failed or empty source keeps its previous rows and is marked stale."""
    import collect as client
    for name, id_field, task in SOURCES:
        try:
            rows = task(client)
            if not rows:
                raise RuntimeError('공공 API가 빈 목록을 반환했어요.')
        except Exception as exc:
            with db.connect() as conn:
                db.set_source_status(conn, name, 'stale', error=str(exc)[:300])
            log(name, 'failed (previous data retained)')
            continue
        with db.connect() as conn:
            db.replace_source(conn, name, rows, id_field)
            db.set_source_status(conn, name, 'ok', rows=len(rows))

def details():
    """Fetch welfare details within the daily budget, senior and 청양군 programs first."""
    import collect as client
    from engine import build_catalog
    with db.connect() as conn:
        rows, cache = db.source_rows(conn), db.details(conn)
    catalog = build_catalog({'sources': rows}, cache)
    catalog.sort(key=lambda p: (not p['senior'], p['scope'] != '청양군', p['title']))
    today = datetime.now(KST).date().isoformat()
    # Reserve three attempts per detail request (fetch retries up to three times).
    limits = {'national': env_int('NATIONAL_DETAIL_DAILY_BUDGET', 20), 'local': env_int('LOCAL_DETAIL_DAILY_BUDGET', 90)}
    used = {'national': 0, 'local': 0}
    broken = set()
    for p in catalog:
        for ref in p['sources']:
            source, sid = ref['source'], ref['id']
            if source not in limits or source in broken:
                continue
            updated = next((v['updated'] for v in p.get('versions', [p])
                            if any(r['source'] == source and r['id'] == sid for r in v['sources'])), p['updated'])
            old = cache.get(f'{source}:{sid}', {})
            if 'data' in old and old.get('list_updated') == updated:
                continue
            with db.connect() as conn:
                if db.budget_used(conn, today, source) + 3 > limits[source]:
                    broken.add(source)
                    continue
                db.spend_budget(conn, today, source, 3)
            try:
                data = client.detail(source, sid)
            except Exception:
                broken.add(source)  # stop this source for today instead of burning the budget
                continue
            with db.connect() as conn:
                db.put_detail(conn, source, sid, updated, data)
            used[source] += 1
    log('detail requests:', used)
    return used

def attach_official_documents(catalog, gov_detail_rows):
    """구비서류 goes to a separate key: it is not analysis input, so fingerprints do not change."""
    docs = {str(r.get('서비스ID')): r.get('구비서류') for r in gov_detail_rows if r.get('구비서류')}
    for p in catalog:
        ref = next((r for r in p['sources'] if r['source'] == 'gov' and docs.get(r['id'])), None)
        if ref:
            p['official_documents'] = [{'text': str(docs[ref['id']]), 'source': [ref], 'field': '정부24 상세.구비서류'}]

def build(allow_llm, dedup_limit):
    from engine import build_catalog, semantic_merge
    from llm import configured
    with db.connect() as conn:
        rows, cache = db.source_rows(conn), db.details(conn)
    catalog = build_catalog({'sources': rows}, cache)
    catalog, relations = semantic_merge(catalog, allow_network=allow_llm and configured(),
                                        limit=None, llm_limit=dedup_limit)
    attach_official_documents(catalog, rows.get('gov_detail', []))
    return catalog, relations, {k: len(v) for k, v in rows.items()}

def stats_for(counts):
    with db.connect() as conn:
        status = db.source_status(conn)
        errors = [{'source': s, 'error': e} for s, st, e in
                  conn.execute('SELECT source, state, error FROM source_status') if st != 'ok']
    fetched = [v['fetched_at'] for v in status.values() if v.get('fetched_at')]
    return {'collected_at': max(fetched) if fetched else None, 'errors': errors, 'sources': status, 'counts': counts}

def analyze(limit, workers=4, catalog=None):
    """Analyze published policies with no cached analysis, most requested first. limit 0 means all."""
    from analysis import analyze as run_analysis, fingerprint
    from engine import load_catalog
    if catalog is None:
        catalog, _ = load_catalog()
    done_keys, wanted, failed = db.analyzed_keys(), db.demand(), db.failures()
    today = datetime.now(timezone.utc).date().isoformat()
    todo = []
    for p in catalog:
        key = fingerprint(p)
        attempts, last = failed.get(key, (0, ''))
        if key in done_keys or attempts >= 3 or (last or '').startswith(today):
            continue
        todo.append((key, p))
    def priority(item):
        p = item[1]
        # Demand is counted per policy ID; a merged policy inherits the demand of every source it absorbed.
        ids = {p['id']} | {r['source'] + '-' + r['id'] for r in p['sources']}
        merged = str(p.get('merge_reason', '')).startswith('AI')  # merging discards the parts' analyses
        return (-sum(wanted.get(i, 0) for i in ids), not merged, not p['senior'], SCOPE_ORDER.get(p['scope'], 3), p['title'])
    todo.sort(key=priority)
    chosen = todo[:limit] if limit > 0 else todo
    from llm import ModelRejected
    ok = bad = 0
    rejected = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_analysis, p): (key, p) for key, p in chosen}
        for future in as_completed(futures):
            key, p = futures[future]
            if future.cancelled():
                continue
            try:
                future.result()
                db.clear_demand([p['id']] + [r['source'] + '-' + r['id'] for r in p['sources']])
                ok += 1
            except ModelRejected as exc:
                # A refused key or quota is not the policy's fault: stop without counting it against the policy.
                rejected = exc
                for other in futures:
                    other.cancel()
                continue
            except Exception as exc:
                db.record_failure(key, p['id'], type(exc).__name__)
                bad += 1
            log(f'public analysis {ok + bad}/{len(chosen)}, verified={ok}, failed={bad}')
    if rejected:
        code = rejected.args[1] if len(rejected.args) > 1 else '?'
        log(f'LLM provider refused requests (HTTP {code}); analysis stopped. Check LLM_API_KEY/LLM_BASE_URL.')
    ready=db.analyzed_keys()
    remaining=sum(fingerprint(p) not in ready for p in catalog)
    log(f'analysis remaining after this run: {remaining}')
    return {'verified': ok, 'failed': bad, 'remaining': remaining, 'rejected': bool(rejected)}

# --- runner --------------------------------------------------------------------------------------

class Busy(RuntimeError):
    pass

def acquire_lock():
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime > 3 * 3600:
        LOCK.unlink(missing_ok=True)  # a crashed run must not block refreshes forever
    try:
        os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        raise Busy('refresh already in progress') from None

def run(stages=STAGES, llm_limit=100, dedup_limit=30, workers=4):
    acquire_lock()
    try:
        with db.connect() as conn:
            run_id = db.start_run(conn)
        published = False
        try:
            if 'collect' in stages:
                if not os.getenv('DATA_GO_KR_KEY'):
                    raise SystemExit('DATA_GO_KR_KEY를 설정하세요.')
                collect()
            if 'details' in stages:
                details()
            result=None
            if 'publish' in stages:
                catalog, relations, counts = build(allow_llm='analyze' in stages, dedup_limit=dedup_limit)
                if not catalog:
                    raise RuntimeError('게시할 정책이 없어요. 수집 결과를 확인해 주세요.')
                stats=stats_for(counts)
                if 'analyze' in stages:
                    result=analyze(llm_limit, workers, catalog=catalog)
                    stats['analysis_ready']=len(catalog)-result['remaining']
                    stats['analysis_total']=len(catalog)
                    # Keep serving the previous snapshot while a capped/rejected batch catches up.
                    if stats['analysis_ready']/len(catalog)<.95:
                        result['publication_deferred']=True
                        with db.connect() as conn:
                            db.end_run(conn,run_id,'failed',{'reason':'analysis_coverage_below_95_percent',**stats})
                        log('publication deferred: less than 95% analyzed; previous catalog retained')
                        return result
                with db.connect() as conn:
                    db.publish(conn, run_id, catalog, relations, stats)
                published = True
                log('published catalog:', len(catalog), 'relations:', len(relations))
            elif 'analyze' in stages:
                result=analyze(llm_limit, workers)
            if not published:
                with db.connect() as conn:
                    db.end_run(conn, run_id, 'done')
            return result
        except BaseException as exc:
            with db.connect() as conn:
                if published:
                    db.set_meta(conn,'last_analysis_error',json.dumps({'run_id':run_id,'error':type(exc).__name__}))
                else:
                    db.end_run(conn, run_id, 'failed', {'error': type(exc).__name__})
            raise
    finally:
        LOCK.unlink(missing_ok=True)

def due(now=None):
    """Daily schedule used by the server's maintenance loop (AUTO_REFRESH=1)."""
    if os.getenv('AUTO_REFRESH', '1') != '1' or not os.getenv('DATA_GO_KR_KEY'):
        return False
    now = now or datetime.now(KST)
    last = db.last_attempt()
    if not last:
        return True
    started = datetime.fromisoformat(last[0]).astimezone(KST)
    if last[1] == 'running' and now - started < timedelta(hours=3):
        return False
    if last[1]=='failed' or db.active_run() is None:
        return now - started >= timedelta(hours=1)  # nothing published yet: retry hourly
    return started.date() < now.date() and now.hour >= env_int('BATCH_HOUR', 4)

def scheduled_llm_limit():
    """BATCH_LLM_LIMIT for the scheduled run: 'all' analyzes every pending policy (returned as 0, the
    analyze() value for all), a positive number caps it, and 0 or a negative number turns LLM work off (None)."""
    raw = os.getenv('BATCH_LLM_LIMIT', '100').strip().lower()
    if raw == 'all':
        return 0
    try:
        limit = int(raw)
    except ValueError:
        return 100
    return limit if limit > 0 else None

def run_scheduled():
    # Two analysis workers leave LLM slots free for users.
    limit = scheduled_llm_limit()
    stages = STAGES if limit is not None else ('collect', 'details', 'publish')
    try:
        run(stages, llm_limit=limit or 0, dedup_limit=env_int('BATCH_DEDUP_LIMIT', 30), workers=2)
    except Busy:
        pass

def dry_run():
    from analysis import fingerprint
    catalog, relations, counts = build(allow_llm=False, dedup_limit=0)
    from engine import dedup_candidates
    keys = db.analyzed_keys()
    log('stored rows:', counts)
    log('catalog (cached merges applied):', len(catalog), 'relations:', len(relations))
    log('policies without analysis:', sum(fingerprint(p) not in keys for p in catalog),
        'senior:', sum(p['senior'] and fingerprint(p) not in keys for p in catalog))
    log('duplicate-title candidate pairs:', len(dedup_candidates(catalog, None)))

# --- one-time import of the former JSON/SQLite files ---------------------------------------------

_migrated = False
_migrate_lock = threading.Lock()

def migrate_legacy():
    """Import snapshot.json, details.json, traffic.json and analysis.sqlite3 once, then publish them.
    The old files are left untouched so a rollback to the previous image still works."""
    global _migrated
    if _migrated:
        return False
    with _migrate_lock:
        if _migrated:
            return False
        snapshot_path, details_path = DATA_DIR / 'snapshot.json', DATA_DIR / 'details.json'
        traffic_path, analysis_path = DATA_DIR / 'traffic.json', DATA_DIR / 'analysis.sqlite3'
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if db.get_meta(conn, 'legacy_import'):
                _migrated = True
                return False
            snapshot = None
            if snapshot_path.exists():
                snapshot = json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
                ids = {'gov_list': '서비스ID', 'gov_conditions': '서비스ID', 'national': 'servId', 'local': 'servId'}
                for name, rows in snapshot.get('sources', {}).items():
                    db.replace_source(conn, name, rows, ids.get(name, 'id'))
                    state = snapshot.get('source_status', {}).get(name, {})
                    error = next((e.get('error') for e in snapshot.get('errors', []) if e.get('source') == name), None)
                    conn.execute('INSERT OR REPLACE INTO source_status VALUES (?,?,?,?,?)',
                                 (name, state.get('state', 'ok'), state.get('fetched_at') or snapshot.get('collected_at'),
                                  len(rows), error))
            if details_path.exists():
                for key, value in json.loads(details_path.read_text(encoding='utf-8-sig')).items():
                    source, _, sid = key.partition(':')
                    if 'data' in value:
                        db.put_detail(conn, source, sid, value.get('list_updated'), value['data'], value.get('fetched_at'))
            if traffic_path.exists():
                ledger = json.loads(traffic_path.read_text(encoding='utf-8'))
                for source in ('national', 'local'):
                    if ledger.get('date') and ledger.get(source):
                        db.spend_budget(conn, ledger['date'], source, int(ledger[source]))
            if analysis_path.exists():
                import sqlite3
                old = sqlite3.connect(analysis_path)
                try:
                    conn.executemany('INSERT OR IGNORE INTO cache VALUES (?,?,?,?)',
                                     old.execute('SELECT key, kind, payload, created FROM cache').fetchall())
                finally:
                    old.close()
            db.set_meta(conn, 'legacy_import', db.now())
        published = False
        if snapshot is not None:
            catalog, relations, counts = build(allow_llm=False, dedup_limit=0)
            if catalog:
                with db.connect() as conn:
                    run_id = db.start_run(conn, snapshot.get('collected_at'))
                    db.publish(conn, run_id, catalog, relations, stats_for(counts))
                published = True
        _migrated = True
        return published

def main(argv=None):
    parser = argparse.ArgumentParser(description='이음온 공공 정책 일괄 수집·분석')
    parser.add_argument('--stages', default=','.join(STAGES), help='쉼표로 구분: ' + ','.join(STAGES))
    limit = scheduled_llm_limit()  # BATCH_LLM_LIMIT=0 (off) must not turn into 'all' here, so fall back to 100
    parser.add_argument('--llm-limit', type=int, default=100 if limit is None else limit, help='정책 분석 상한, 0은 전체')
    parser.add_argument('--dedup-limit', type=int, default=env_int('BATCH_DEDUP_LIMIT', 30), help='새 중복 판정 상한')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--analysis-status', action='store_true', help='게시 정책 분석 완료율·실패·토큰 사용량만 확인')
    parser.add_argument('--backfill', action='store_true', help='수집·중복 판정 없이 미분석 정책 전체 분석, 캐시로 재개')
    parser.add_argument('--retry-failed', action='store_true', help='현재 미분석 정책의 재시도 보류 해제')
    args = parser.parse_args(argv)
    migrate_legacy()
    if args.analysis_status:
        from analysis import fingerprint
        from engine import load_catalog
        catalog,_=load_catalog()
        keys=db.analyzed_keys(); failed=db.failures()
        pending=[fingerprint(p) for p in catalog if fingerprint(p) not in keys]
        print(json.dumps({'total':len(catalog),'ready':len(catalog)-len(pending),'pending':len(pending),
                          'failed':sum(k in failed for k in pending),
                          'retry_exhausted':sum(failed.get(k,(0,''))[0]>=3 for k in pending),
                          'usage':db.usage_summary()},ensure_ascii=False,indent=2))
        return 0
    if args.dry_run:
        return dry_run()
    if args.retry_failed:
        from engine import load_catalog
        from analysis import fingerprint
        ready=db.analyzed_keys()
        db.clear_failures([fingerprint(p) for p in load_catalog()[0] if fingerprint(p) not in ready])
    if args.backfill:
        args.stages='analyze';args.llm_limit=0
    stages = tuple(s.strip() for s in args.stages.split(',') if s.strip())
    unknown = set(stages) - set(STAGES)
    if unknown:
        parser.error('알 수 없는 단계: ' + ', '.join(sorted(unknown)))
    try:
        result=run(stages, args.llm_limit, args.dedup_limit, args.workers)
        if result and (result.get('publication_deferred') or (args.backfill and result['remaining'])):
            return 2  # An incomplete backfill must not be reported as fully successful.
    except Busy as exc:
        log(exc)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
