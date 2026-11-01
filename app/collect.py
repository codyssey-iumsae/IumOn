"""Public API client used by batch.py; never store keys or request URLs in data files."""
import json
import math
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import config  # noqa: F401  loads app/.env before the key is read

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
