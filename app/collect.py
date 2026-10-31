"""Fetch official source snapshots; never store keys or request URLs in data files."""
import json
import math
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from config import DATA_DIR

KEY = urllib.parse.unquote(os.getenv('DATA_GO_KR_KEY', ''))

def fetch(url, params, xml=False):
    query = urllib.parse.urlencode({**params, 'serviceKey': KEY})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url + '?' + query, timeout=45) as r:
                raw = r.read().decode('utf-8-sig')
            if xml:
                root = ET.fromstring(raw)
                if root.findtext('resultCode') != '0':
                    raise ValueError('API result: ' + str(root.findtext('resultCode')))
                return root
            obj = json.loads(raw)
            if 'data' not in obj:
                raise ValueError('API returned no data')
            return obj
        except Exception:
            if attempt == 2:
                raise RuntimeError('공공 API 요청 실패: ' + url.split('/')[-1]) from None
            time.sleep(1 + attempt)

def xml_dict(element):
    result = {}
    for child in element:
        value = xml_dict(child) if len(child) else (child.text or '')
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    return result

def gov(endpoint):
    url = 'https://api.odcloud.kr/api/gov24/v3/' + endpoint
    first = fetch(url, {'page': 1, 'perPage': 1000})
    rows = first['data']
    size = first.get('perPage', 1000)
    for page in range(2, math.ceil(first['totalCount'] / size) + 1):
        rows.extend(fetch(url, {'page': page, 'perPage': size})['data'])
    print(endpoint, len(rows), flush=True)
    return rows

def welfare(local=False):
    if local:
        base = 'https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/'
        endpoint = 'LcgvWelfarelist'
        extra = {'ctpvNm': '충청남도'}
    else:
        base = 'https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/'
        endpoint = 'NationalWelfarelistV001'
        extra = {}
    rows = []
    page = 1
    while True:
        root = fetch(base + endpoint, {'callTp': 'L', 'pageNo': page,
                     'numOfRows': 500, 'srchKeyCode': '003', **extra}, True)
        rows.extend(xml_dict(e) for e in root.findall('servList'))
        if page * 500 >= int(root.findtext('totalCount', '0')):
            break
        page += 1
    print(endpoint, len(rows), flush=True)
    return rows

def detail(source, sid):
    local = source == 'local'
    base = ('https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/' if local
            else 'https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/')
    ep = 'LcgvWelfaredetailed' if local else 'NationalWelfaredetailedV001'
    return xml_dict(fetch(base + ep, {'callTp': 'D', 'servId': sid}, True))

def _main():
    if not KEY:
        raise SystemExit('DATA_GO_KR_KEY를 설정하세요.')
    output = {'collected_at': datetime.now(timezone.utc).isoformat(), 'sources': {}, 'errors': [],'source_status':{}}
    old = DATA_DIR / 'snapshot.json'
    if old.exists():
        previous=json.loads(old.read_text(encoding='utf-8'))
        output['sources'] = previous['sources']
        output['source_status']=previous.get('source_status',{})
    tasks = [('gov_list', lambda: gov('serviceList')),
             ('gov_conditions', lambda: gov('supportConditions')),
             ('national', lambda: welfare()), ('local', lambda: welfare(True))]
    for name, task in tasks:
        try:
            output['sources'][name] = task()
            output['source_status'][name]={'fetched_at':datetime.now(timezone.utc).isoformat(),'state':'ok'}
        except Exception as exc:
            output['errors'].append({'source': name, 'error': str(exc)})
            output['source_status'].setdefault(name,{})['state']='stale'
            print(name, 'failed (previous data retained)', flush=True)
    temp = DATA_DIR / 'snapshot.tmp'
    temp.write_text(json.dumps(output, ensure_ascii=False), encoding='utf-8')
    temp.replace(old)
    from engine import build_catalog
    catalog = build_catalog(output)
    catalog.sort(key=lambda p:(not p['senior'],p['scope']!='청양군',p['title']))
    # Cache actual source detail for senior-facing national/local candidates.
    cache_path = DATA_DIR / 'details.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    used = {'national': 0, 'local': 0}
    ledger_path=DATA_DIR/'traffic.json'
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {}
    if ledger.get('date')!=today:ledger={'date':today,'national':0,'local':0}
    # Conservative allowance during development; reserve three attempts per detail request.
    limits={'national':int(os.getenv('NATIONAL_DETAIL_DAILY_BUDGET','20')),
            'local':int(os.getenv('LOCAL_DETAIL_DAILY_BUDGET','90'))}
    for p in catalog:
        for ref in p['sources']:
            source, sid = ref['source'], ref['id']
            key = source + ':' + sid
            source_updated=next((v['updated'] for v in p.get('versions',[p])
                                 if any(r['source']==source and r['id']==sid for r in v['sources'])),p['updated'])
            old_detail=cache.get(key,{})
            current='data' in old_detail and old_detail.get('list_updated')==source_updated
            if source in used and not current and ledger[source]+3 <= limits[source]:
                try:
                    ledger[source]+=3
                    ledger_path.write_text(json.dumps(ledger),encoding='utf-8')
                    cache[key] = {'data':detail(source, sid),'fetched_at':datetime.now(timezone.utc).isoformat(),
                                  'list_updated':source_updated}
                    used[source] += 1
                except Exception:
                    break
    detail_temp=DATA_DIR/'details.tmp'
    detail_temp.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    detail_temp.replace(cache_path)
    print('catalog candidates:', len(catalog), 'detail requests:', used, flush=True)

def main():
    lock=DATA_DIR/'.refresh.lock'
    if lock.exists() and time.time()-lock.stat().st_mtime>3600:lock.unlink()
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        print('refresh already in progress',flush=True)
        return
    try:
        os.close(fd)
        _main()
    finally:
        lock.unlink(missing_ok=True)

if __name__ == '__main__':
    main()
