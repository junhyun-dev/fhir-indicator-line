"""L2/D1-D3 verification only; no D1-D7 clinical transformation or answer generation."""
import collections
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path

from .bundles import entries
from .layers import check as check_layers
from .runtime import ARTIFACTS, DATABASE, ORIGINAL, ROOT, connect


def normalized_cell(value, sql_type=''):
    if value is None:
        return ''
    if isinstance(value,bool):
        return 'true' if value else 'false'
    if isinstance(value,(dt.date,dt.datetime)):
        return value.isoformat()
    value = str(value)
    if sql_type.startswith(('TINYINT','SMALLINT','INTEGER','BIGINT','HUGEINT','UTINYINT','USMALLINT','UINTEGER','UBIGINT','UHUGEINT','FLOAT','DOUBLE','DECIMAL')) and value:
        return str(Decimal(value).normalize())
    return value.lower() if sql_type=='BOOLEAN' and value.lower() in ('true','false') else value


def compare_expected(connection, folder):
    files = sorted(folder.glob('person_*.csv'))
    relation = connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name='fct_bp_person'").fetchone()[0]
    if not files or not relation:
        return {'status':'기다림','detail':'expected/person_<as_of>.csv 또는 사용자 fct_bp_person 없음'}
    columns = {r[1]:r[2] for r in connection.execute("PRAGMA table_info('fct_bp_person')").fetchall()}
    if 'as_of' not in columns:
        return {'status':'실패','detail':'fct_bp_person의 as_of 열 없음; 기준을 고치지 않음'}
    comparisons = []
    for file in files:
        match = re.fullmatch(r'person_(\d{4}-\d{2}-\d{2})\.csv',file.name)
        if match is None:
            return {'status':'실패','detail':'expected 파일의 기준일 형식을 확인해야 함; 기준을 고치지 않음'}
        date = match.group(1)
        with file.open(newline='') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            expected = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in expected):
            return {'status':'실패','detail':'expected CSV 행의 열 개수가 헤더와 다름; 기준을 고치지 않음'}
        if not headers or len(headers)!=len(set(headers)) or any(h not in columns for h in headers):
            return {'status':'실패','detail':'expected와 fct_bp_person의 열 계약이 맞지 않음; 기준을 고치지 않음'}
        projection = ','.join('"'+h.replace('"','""')+'"' for h in headers)
        actual_rows = connection.execute('SELECT '+projection+" FROM fct_bp_person WHERE left(cast(as_of AS VARCHAR),10)=?",[date]).fetchall()
        actual = collections.Counter(tuple(normalized_cell(v,columns[h]) for h,v in zip(headers,row)) for row in actual_rows)
        wanted = collections.Counter(tuple(normalized_cell(row[h],columns[h]) for h in headers) for row in expected)
        comparisons.append({'as_of':date,'expected_rows':len(expected),'actual_rows':len(actual_rows),
                            'cells_per_row':len(headers),'missing_rows':sum((wanted-actual).values()),
                            'unexpected_rows':sum((actual-wanted).values()),'all_cells_equal':actual==wanted})
    passed = all(c['all_cells_equal'] for c in comparisons)
    return {'status':'통과' if passed else '실패', 'detail':'기대 CSV 열 전체를 행 순서와 무관하게 비교; 중복 행도 셈',
            'comparisons':comparisons, 'on_mismatch':'기준이 틀린 것 같다/구현 불일치 가능성을 반환; expected는 읽기만 함'}


def source_anchor(connection):
    targets = []
    for path in sorted(ORIGINAL.glob('*.json')):
        text = path.read_bytes().decode('utf-8')
        bundle = json.loads(text)
        if not any(e.get('resource',{}).get('resourceType')=='Patient'
                   and e['resource']['id'].startswith('5393ea7f') for e in bundle.get('entry',[])):
            continue
        for entry, _, payload in entries(text):
            resource = entry['resource']
            if resource['resourceType']!='Observation' or not resource.get('effectiveDateTime','').startswith('2025-12-01'):
                continue
            if not any(c.get('code')=='85354-9' and c.get('system')=='http://loinc.org' for c in resource.get('code',{}).get('coding',[])):
                continue
            digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            raw = connection.execute('SELECT payload_hash,payload_json FROM raw_resources WHERE resource_type=? AND id=?',['Observation',resource['id']]).fetchall()
            latest = connection.execute('SELECT payload_hash,payload_json FROM latest_resources WHERE resource_type=? AND id=?',['Observation',resource['id']]).fetchall()
            passed = bool(raw) and len(latest)==1 and all(h==digest and p==payload for h,p in raw+latest)
            targets.append({'patient_id8':'5393ea7f','date':'2025-12-01','original_sha256':digest,'raw_rows':len(raw),'all_payloads_equal':passed})
    return {'status':'통과' if len(targets)==1 and targets[0]['all_payloads_equal'] else '실패',
            'detail':'원본 → raw → latest의 원문 및 SHA256 비교','targets':targets}


def assess_counts(source_count, batches, duplicate_count, raw_count, latest_count):
    sum_batches = sum(batches.values())
    data_ok = raw_count==sum_batches and latest_count==source_count==sum_batches-duplicate_count
    # L2: requester corrected step 1; every batch arrival remains in L1.
    return {'status':'통과' if data_ok else '실패',
            'detail':f'원본 {source_count:,}, batch1 {batches["1"]:,}, batch2 {batches["2"]:,}, raw {raw_count:,} = 배치 합 {sum_batches:,}, latest {latest_count:,} = 합−공통 {sum_batches-duplicate_count:,}',
            'source_resources':source_count,'batch_resources':batches,
            'shared_resource_keys':duplicate_count,'raw_rows':raw_count,'latest_rows':latest_count,
            'expected_raw_rows':sum_batches,'expected_latest_rows':sum_batches-duplicate_count,
            'L1_key_contract_satisfied':data_ok,
            'issue':None if data_ok else 'L1/L2 실제 행 수 불일치'}


def check(expected):
    layer_result = check_layers()
    if layer_result['status']!='통과':
        report = {'status':'실패','layers':layer_result,'ladder':[]}
        write_report(report)
        return report
    folder = Path(expected).resolve()
    batches = {}
    for n in (1,2):
        manifest = json.loads((ROOT/f'data/batches/batch_{n}/manifest.json').read_text())
        batches[str(n)] = manifest['resource_count']
    source_counts = collections.Counter()
    source_seen = set()
    for path in ORIGINAL.glob('*.json'):
        for entry in json.loads(path.read_bytes()).get('entry',[]):
            r = entry['resource']
            source_counts[r['resourceType']] += 1
            source_seen.add((r['resourceType'],r['id']))
    source_count = sum(source_counts.values())
    if source_count!=43643 or len(source_seen)!=source_count:
        raise ValueError('Read-only source no longer matches the request baseline')
    with connect(DATABASE,read_only=True) as connection:
        raw = connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0]
        latest = connection.execute('SELECT count(*) FROM latest_resources').fetchone()[0]
        duplicates, changed = connection.execute('''SELECT count(*),count(*) FILTER(WHERE variants>1 OR different_body) FROM (
            SELECT resource_type,id,count(*) AS arrivals,count(DISTINCT payload_hash) AS variants,
                   min(payload_json) IS DISTINCT FROM max(payload_json) AS different_body
            FROM raw_resources GROUP BY resource_type,id HAVING count(*)>1)''').fetchone()
        first = assess_counts(source_count,batches,duplicates,raw,latest)
        latest_counts = dict(connection.execute('SELECT resource_type,count(*) FROM latest_resources GROUP BY resource_type').fetchall())
        bp_where = '''resource_type='Observation' AND EXISTS (
            SELECT 1 FROM json_each(json_extract(r.payload_json,'$.code.coding')) c
            WHERE json_extract_string(c.value,'$.system')='http://loinc.org'
              AND json_extract_string(c.value,'$.code')='85354-9')'''
        bp, year_bp = connection.execute('''SELECT count(*), count(*) FILTER(WHERE
            left(json_extract_string(payload_json,'$.effectiveDateTime'),10)>='2025-01-01' AND
            left(json_extract_string(payload_json,'$.effectiveDateTime'),10)<'2026-01-01')
            FROM latest_resources r WHERE '''+bp_where).fetchone()
        second = {'status':'통과' if latest_counts==dict(source_counts) and bp==555 and year_bp==48 else '실패',
                  'detail':f'자원 종류별 수 원본과 비교, 혈압 {bp}, 2025년 혈압 {year_bp}',
                  'latest_resource_counts':latest_counts,'source_resource_counts':dict(source_counts),
                  'blood_pressure_panels':bp,'blood_pressure_panels_in_2025':year_bp}
        third = {'status':'통과' if changed==0 else '실패',
                 'detail':f'두 배치의 같은 자원 {duplicates}개, 다른 본문 {changed}개',
                 'duplicated_resources':duplicates,'different_payload_resources':changed}
        if folder.exists():
            try:
                fourth = compare_expected(connection,folder)
            except (ValueError,InvalidOperation,csv.Error,OSError) as error:
                fourth = {'status':'실패','detail':'expected 읽기/셀 자료형 오류: '+type(error).__name__+'; 기준을 고치지 않음'}
            fifth = source_anchor(connection)
        else:
            fourth = {'status':'기다림','detail':'expected/ 없음; 사용자 모델/정답 대기'}
            fifth = {'status':'기다림','detail':'요청대로 expected/가 있을 때만 원천 기준 검사 실행'}
    ladder = [dict(step=str(i),**item) for i,item in enumerate((first,second,third,fourth,fifth),1)]
    status = '실패' if any(r['status']=='실패' for r in ladder) else '통과'
    report = {'status':status,'layers':layer_result,'ladder':ladder,
              'expected_read_only':True,'D1_D7_models_implemented':False}
    write_report(report)
    return report


def write_report(report):
    (ARTIFACTS/'summaries').mkdir(parents=True,exist_ok=True)
    (ARTIFACTS/'summaries/verification-ladder.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    rows = ['| 칸 | 상태 | 실제 결과 |','|---|---|---|']
    if not report['ladder']:
        rows.append('| — | 실패 | 층 방향 검사 실패로 사다리 실행 안 함 |')
    for row in report['ladder']:
        rows.append('| '+row['step']+' | '+row['status']+' | '+row['detail']+' |')
    if report['ladder']:
        rows.extend(['',f'두 배치에 공통인 (resource_type, id): {report["ladder"][0]["shared_resource_keys"]:,}개.'])
    (ARTIFACTS/'summaries/verification-ladder.md').write_text('\n'.join(rows)+'\n')
