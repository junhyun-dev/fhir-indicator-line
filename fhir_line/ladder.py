"""L2/D1-D3 verification only; no D1-D7 clinical transformation or answer generation."""
import collections
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

from .bundles import entries
from .layers import check as check_layers
from . import omop
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


ROW_KEYS = {'fct_bp_person':('hospital','as_of_label','person_id'),
            'bp_summary':('hospital','as_of_label')}
DIFFERENCE_KINDS = ('cell_diffs','missing_rows','unexpected_rows')
INDEX_FIELDS = ('run_at','product_commit','status',*DIFFERENCE_KINDS)


def table_differences(table, headers, wanted, actual):
    """D1,D5-D7 / ADR0010, REQ-cell-diff: pair unique keys; compare duplicate keys as multisets."""
    keys = ROW_KEYS[table]
    if any(key not in headers for key in keys):
        raise ValueError('행 키 열 계약이 맞지 않음')
    key_indexes = [headers.index(key) for key in keys]
    groups = []
    for rows in (wanted,actual):
        grouped = collections.defaultdict(collections.Counter)
        for row, count in rows.items():
            grouped[tuple(row[i] for i in key_indexes)][row] += count
        groups.append(grouped)
    differences = {kind:[] for kind in DIFFERENCE_KINDS}
    for key in sorted(set(groups[0]) | set(groups[1])):
        expected_rows, actual_rows = (group.get(key,collections.Counter()) for group in groups)
        row_key = dict(zip(keys,key))
        if sum(expected_rows.values())==sum(actual_rows.values())==1:
            expected_row,actual_row = next(iter(expected_rows)),next(iter(actual_rows))
            for column,expected_value,actual_value in zip(headers,expected_row,actual_row):
                if expected_value!=actual_value:
                    differences['cell_diffs'].append({'table':table,'row':row_key.copy(),'column':column,
                                                       'expected':expected_value,'actual':actual_value})
        else:
            for kind,remaining in (('missing_rows',expected_rows-actual_rows),
                                   ('unexpected_rows',actual_rows-expected_rows)):
                for row in sorted(remaining):
                    differences[kind].extend({'table':table,'row':row_key.copy()}
                                              for _ in range(remaining[row]))
    return differences


def compare_table(connection, folder, kind, table, columns=None):
    """④ D1,D5-D7 / ADR0010: compare expected cells and row multiplicity by hospital."""
    files = sorted(f for f in folder.glob(kind+'_*.csv') if re.fullmatch(kind+r'_[A-Z]+\.csv',f.name))
    relation = connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name=?",[table]).fetchone()[0]
    if not files or not relation:
        return {'status':'기다림','detail':f'expected/{kind}_<병원>.csv 또는 {table} 없음'}
    have = {r[1]:r[2] for r in connection.execute(f"PRAGMA table_info('{table}')").fetchall()}
    comparisons = []
    differences = {name:[] for name in DIFFERENCE_KINDS}
    for file in files:
        hospital = file.stem.split('_',1)[1]
        with file.open(newline='') as f:
            reader = csv.DictReader(f)
            csv_headers = list(reader.fieldnames or [])
            headers = list(columns or csv_headers)
            expected = list(reader)
        missing_csv = [key for key in ROW_KEYS[table] if key not in csv_headers or key not in headers]
        missing_db = [key for key in ROW_KEYS[table] if key not in have]
        if missing_csv or missing_db:
            return {'status':'실패','detail':f'{table} 열 계약이 맞지 않음 (기대 CSV/비교열: {", ".join(missing_csv) or "없음"}; DB: {", ".join(missing_db) or "없음"})',
                    'missing_csv_columns':missing_csv,'missing_db_columns':missing_db}
        if any(None in row or any(v is None for v in row.values()) for row in expected):
            return {'status':'실패','detail':'expected CSV 행의 열 개수가 헤더와 다름; 기준을 고치지 않음'}
        if not headers or len(csv_headers)!=len(set(csv_headers)) or len(headers)!=len(set(headers)) or any(h not in have or h not in csv_headers for h in headers):
            return {'status':'실패','detail':f'expected와 {table}의 열 계약이 맞지 않음; 기준을 고치지 않음'}
        if any(row['hospital']!=hospital for row in expected):
            return {'status':'실패','detail':f'{file.name}의 hospital 열이 파일 이름과 다름; 기준을 고치지 않음'}
        projection = ','.join('"'+h.replace('"','""')+'"' for h in headers)
        actual_rows = connection.execute('SELECT '+projection+f' FROM {table} WHERE hospital=?',[hospital]).fetchall()
        actual = collections.Counter(tuple(normalized_cell(v,have[h]) for h,v in zip(headers,row)) for row in actual_rows)
        wanted = collections.Counter(tuple(normalized_cell(row[h],have[h]) for h in headers) for row in expected)
        changed = table_differences(table,headers,wanted,actual)
        for name in DIFFERENCE_KINDS:
            differences[name].extend(changed[name])
        comparisons.append({'hospital':hospital,'expected_rows':len(expected),'actual_rows':len(actual_rows),
                            'cells_per_row':len(headers),
                            **{name:len(changed[name]) for name in DIFFERENCE_KINDS},
                            'all_cells_equal':actual==wanted})
    passed = all(c['all_cells_equal'] for c in comparisons)
    return {'status':'통과' if passed else '실패','detail':'병원마다 기대 CSV 열 전체를 행 순서와 무관하게 비교; 중복 행도 셈',
            'comparisons':comparisons,**differences,
            'on_mismatch':'기준이 틀린 것 같다/구현 불일치 가능성을 반환; expected는 읽기만 함'}


def compare_expected(connection, folder):
    """④ 사람별: expected/person_<병원>.csv와 fct_bp_person(D2 · D5 · D6)."""
    return compare_table(connection, folder, 'person', 'fct_bp_person')


SUMMARY_COLUMNS = ('hospital','as_of_label','denominator','numerator','rate')  # 설명 열(note)은 비교하지 않음


def compare_summary(connection, folder):
    """④ 요약: expected/summary_<병원>.csv와 bp_summary(D6 · D7 · rate는 넷째 자리 반올림)."""
    return compare_table(connection, folder, 'summary', 'bp_summary', SUMMARY_COLUMNS)


INTEGERS = ('TINYINT','SMALLINT','INTEGER','BIGINT','HUGEINT')
NUMBERS = INTEGERS+('FLOAT','DOUBLE','DECIMAL')
TYPE_CONTRACT = {  # 열 계약(요청 03 4절 · M2 요청 04에서 병원 · 기준일 이름 더함): 값이 같아도 자료형이 다르면 실패
    'fct_bp_person':{'hospital':('VARCHAR',),'as_of_label':('VARCHAR',),'person_id':('VARCHAR',),'as_of':('DATE',),
                     'last_bp_date':('DATE',),'systolic':NUMBERS,'diastolic':NUMBERS,'controlled':INTEGERS,'reason':('VARCHAR',)},
    'bp_summary':{'hospital':('VARCHAR',),'as_of_label':('VARCHAR',),'denominator':INTEGERS,'numerator':INTEGERS,'rate':NUMBERS}}


def check_types(connection):
    """④ 자료형: 두 결과 표의 열이 계약한 자료형인지."""
    problems = []
    for table, contract in TYPE_CONTRACT.items():
        columns = {r[1]:r[2] for r in connection.execute(f"PRAGMA table_info('{table}')").fetchall()} if connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name=?",[table]).fetchone()[0] else None
        if columns is None:
            return {'status':'기다림','detail':table+' 없음'}
        for column, allowed in contract.items():
            if not columns.get(column,'').startswith(allowed):
                problems.append(f'{table}.{column}: {columns.get(column,"없음")}')
    return {'status':'통과' if not problems else '실패','detail':'자료형 계약 '+('맞음' if not problems else ', '.join(problems))}


def combine(**parts):
    """④ = 사람별 + 요약 + 자료형. 하나라도 실패면 실패, 하나라도 기다림이면 기다림."""
    states = [p['status'] for p in parts.values()]
    status = '실패' if '실패' in states else '기다림' if '기다림' in states else '통과'
    return {'status':status,'detail':' · '.join(f'{k} {v["status"]}' for k,v in parts.items()),**parts}


def overall(ladder_rows, strict=False):
    """전체 판정. strict(요청 03부터 check.sh)는 기다림도 실패로 센다(검토 R3)."""
    states = [r['status'] for r in ladder_rows]
    return '실패' if '실패' in states or (strict and '기다림' in states) else '통과'


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


def check(expected, strict=False):
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
                fourth = combine(사람별=compare_expected(connection,folder),요약=compare_summary(connection,folder),자료형=check_types(connection))
            except (ValueError,InvalidOperation,csv.Error,OSError) as error:
                fourth = {'status':'실패','detail':'expected 읽기/셀 자료형 오류: '+type(error).__name__+'; 기준을 고치지 않음'}
            fifth = source_anchor(connection)
            sixth = omop.check(connection,folder)  # M3 · 결정 0004 ~ 0010
        else:
            fourth = {'status':'기다림','detail':'expected/ 없음; 사용자 모델/정답 대기'}
            fifth = {'status':'기다림','detail':'요청대로 expected/가 있을 때만 원천 기준 검사 실행'}
            sixth = {'status':'기다림','detail':'expected/ 없음'}
    ladder = [dict(step=str(i),**item) for i,item in enumerate((first,second,third,fourth,fifth,sixth),1)]
    # ADR0013: the new frozen reference is a required comparison, not another hospital's old expected.
    from .a_prime_checks import check as check_aprime
    try:
        aprime = check_aprime()
    except (ValueError,OSError,KeyError,TypeError,omop.duckdb.Error) as error:
        aprime = {'ok':False,'status':'실패','detail':'A-prime actual input/extraction failed: '+type(error).__name__}
    ladder.append({'step':'7','status':aprime['status'],'detail':'A′ 원래 임상 경로: 입력·staging 원천4745/CSV·OMOP 비교; KCD 미연동'})
    status = overall(ladder,strict)
    report = {'status':status,'strict':strict,'layers':layer_result,'ladder':ladder,
              'expected_read_only':True,'a_prime':aprime,'D1_D7_models_implemented':fourth.get('자료형',{}).get('status') in ('통과','실패')}
    write_report(report)
    return report


class IndexContractError(ValueError):
    """L2 / ADR0010 R4: retain the rejected index and the newly archived CSV."""


def archive_differences(report):
    """D1,D5-D7 / ADR0010, REQ-cell-diff: retain each check and append one index record."""
    runs = ARTIFACTS/'runs'
    runs.mkdir(parents=True,exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc)
    while True:
        run_folder = runs/timestamp.strftime('%Y%m%dT%H%M%S.%fZ')
        try:
            run_folder.mkdir()
            break
        except FileExistsError:
            timestamp += dt.timedelta(microseconds=1)
    run_at = timestamp.isoformat(timespec='microseconds').replace('+00:00','Z')
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty = bool(subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT,text=True))
    counts = {name:len(report[name]) for name in DIFFERENCE_KINDS}
    fields = ('run_at','table','hospital','as_of_label','row_key','column','expected','actual','kind')
    with (run_folder/'cell-diff.csv').open('x',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for name,label in zip(DIFFERENCE_KINDS,('다른 칸','빠진 행','남는 행')):
            for item in report[name]:
                writer.writerow({'run_at':run_at,'table':item['table'],
                                 'hospital':item['row'].get('hospital',''),
                                 'as_of_label':item['row'].get('as_of_label',''),
                                 'row_key':json.dumps(item['row'],ensure_ascii=False,sort_keys=True),
                                 'column':item.get('column',''),'expected':item.get('expected',''),
                                 'actual':item.get('actual',''),'kind':label})
    with (runs/'index.csv').open('a+',newline='') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        stream.seek(0)
        previous = stream.read()
        if previous:
            try:
                reader = csv.reader(io.StringIO(previous,newline=''),strict=True)
                valid = next(reader,None)==list(INDEX_FIELDS) and all(len(row)==len(INDEX_FIELDS) for row in reader)
            except csv.Error:
                valid = False
            if not valid or not previous.endswith(('\n','\r')):
                raise IndexContractError('index.csv의 열 계약이 맞지 않아요. 기존 파일과 이번 실행 CSV를 보존했어요.')
        stream.seek(0,2)
        writer = csv.DictWriter(stream,fieldnames=INDEX_FIELDS)
        if stream.tell()==0:
            writer.writeheader()
        writer.writerow({'run_at':run_at,'product_commit':commit,'status':report['status'],**counts})
        stream.flush()
    return {'run_at':run_at,'product_commit':commit,'product_dirty':dirty,
            'cell_diff_csv':str(run_folder/'cell-diff.csv'),'index_csv':str(runs/'index.csv')}


PUBLIC_PARTS = ('layers','a_prime','사람별','요약','자료형','모양','건수','따라가기','원래 행')
PUBLIC_COUNTS = ('source_resources','shared_resource_keys','raw_rows','latest_rows',
                 'expected_raw_rows','expected_latest_rows','blood_pressure_panels',
                 'blood_pressure_panels_in_2025','duplicated_resources','different_payload_resources',
                 'expected_rows','actual_rows','cells_per_row',*DIFFERENCE_KINDS)
PUBLIC_REASONS = ('혈압 없음','마지막 날에 한쪽 값만','수축기 140 이상','이완기 90 이상','조절됨')


def public_cell(column, value):
    """D1,D5-D7 / ADR0010 R1: validate public cell meanings; never copy arbitrary text."""
    text = '' if value is None else str(value)
    if column=='hospital' and re.fullmatch(r'[A-Z][A-Z_]{0,31}',text):
        return text
    if column=='as_of_label' and re.fullmatch(r'[a-z][a-z_]*\d{0,2}',text):
        return text
    if column in ('as_of','last_bp_date'):
        if not text:
            return text
        try:
            return dt.date.fromisoformat(text).isoformat()
        except ValueError:
            pass
    if column in ('systolic','diastolic','controlled','denominator','numerator','rate'):
        if not text or re.fullmatch(r'[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?',text):
            return text
    if column=='reason' and text in PUBLIC_REASONS:
        return text
    return '[비공개]'


def public_report(value):
    """D1,D5-D7 / ADR0010 R1: construct an allowlisted view for stdout and Markdown."""
    if not isinstance(value,dict):
        return {}
    result = {}
    if 'status' in value:
        result['status'] = value['status'] if value['status'] in ('통과','실패','기다림') else '실패'
    for key in ('strict','expected_read_only','D1_D7_models_implemented','ok','all_cells_equal','product_dirty','archive_failed'):
        if isinstance(value.get(key),bool):
            result[key] = value[key]
    for key in PUBLIC_COUNTS:
        if type(value.get(key)) is int and value[key]>=0:
            result[key] = value[key]
    for key in ('missing_csv_columns','missing_db_columns'):
        if isinstance(value.get(key),list):
            result[key] = [column for column in value[key] if isinstance(column,str)
                           and any(column in keys for keys in ROW_KEYS.values())]
    for key in ('hospital','as_of_label','as_of'):
        if key in value:
            result[key] = public_cell(key,value[key])
    if value.get('step') in tuple(str(i) for i in range(1,8)):
        result['step'] = value['step']
    for key in (*PUBLIC_PARTS,'row','run'):
        if isinstance(value.get(key),dict):
            result[key] = public_report(value[key])
    for key,keys in (('batch_resources',('1','2')),('difference_counts',DIFFERENCE_KINDS)):
        if isinstance(value.get(key),dict):
            result[key] = {k:v for k,v in value[key].items() if k in keys and type(v) is int and v>=0}
    for key in ('ladder','comparisons',*DIFFERENCE_KINDS):
        if isinstance(value.get(key),list):
            result[key] = [public_report(item) for item in value[key] if isinstance(item,dict)]
    if 'table' in value:
        table = value['table']
        result['table'] = table if isinstance(table,str) and table in TYPE_CONTRACT else '[비공개]'
    if 'column' in value:
        column = value['column'] if isinstance(value['column'],str) else ''
        result['column'] = column if any(column in columns for columns in TYPE_CONTRACT.values()) else '[비공개]'
        for key in ('expected','actual'):
            if key in value:
                result[key] = public_cell(column,value[key])
    if re.fullmatch(r'[0-9a-f]{40}',str(value.get('product_commit',''))):
        result['product_commit'] = value['product_commit']
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z',str(value.get('run_at',''))):
        result['run_at'] = value['run_at']
    if 'detail' in value:
        # Free text may contain identifiers, even without an identifying key.
        # Build explanations only from already projected states and counts.
        state = result.get('status','확인 필요')
        if result.get('archive_failed'):
            result['detail'] = '실행 이력 저장 실패: index.csv의 열 계약을 확인하세요. 이번 실행 CSV는 보존했어요.'
        elif result.get('missing_csv_columns') or result.get('missing_db_columns'):
            result['detail'] = ('열 계약이 맞지 않음 (기대 CSV/비교열: '+', '.join(result.get('missing_csv_columns',[]))+
                                '; DB: '+', '.join(result.get('missing_db_columns',[]))+')')
        elif all(key in result for key in ('source_resources','raw_rows','latest_rows')):
            result['detail'] = f'원본 {result["source_resources"]:,}개 · raw {result["raw_rows"]:,}행 · latest {result["latest_rows"]:,}행'
        elif all(key in result for key in ('blood_pressure_panels','blood_pressure_panels_in_2025')):
            result['detail'] = f'혈압 {result["blood_pressure_panels"]}개 · 2025년 {result["blood_pressure_panels_in_2025"]}개'
        elif all(key in result for key in ('duplicated_resources','different_payload_resources')):
            result['detail'] = f'공통 자원 {result["duplicated_resources"]}개 · 다른 본문 {result["different_payload_resources"]}개'
        else:
            parts = [f'{key} {result[key]["status"]}' for key in PUBLIC_PARTS
                     if key in result and 'status' in result[key]]
            result['detail'] = ' · '.join(parts) if parts else f'검사 {state} · 상세는 로컬 JSON에 보존해요.'
    return result


def write_report(report):
    # D1,D5-D7 / ADR0010, REQ-cell-diff: preserve the existing latest JSON/Markdown locations.
    for name in DIFFERENCE_KINDS:
        report[name] = [item for step in report['ladder'] for part in ('사람별','요약')
                        for item in step.get(part,{}).get(name,[])]
    report['difference_counts'] = {name:len(report[name]) for name in DIFFERENCE_KINDS}
    archive_error = None
    try:
        report['run'] = archive_differences(report)
    except IndexContractError as error:
        archive_error = error
        report.pop('run',None)
        report.update(status='실패',archive_failed=True,detail='index.csv 열 계약 오류; 이번 실행 CSV 보존')
    (ARTIFACTS/'summaries').mkdir(parents=True,exist_ok=True)
    (ARTIFACTS/'summaries/verification-ladder.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    visible = public_report(report)
    rows = ['| 칸 | 상태 | 실제 결과 |','|---|---|---|']
    if archive_error is not None:
        rows = ['실패: '+visible['detail'],'',*rows]
    if not report['ladder']:
        rows.append('| — | 실패 | 층 방향 검사 실패로 사다리 실행 안 함 |')
    for row in visible['ladder']:
        rows.append('| '+row['step']+' | '+row['status']+' | '+row['detail']+' |')
    shared = next((row['shared_resource_keys'] for row in visible['ladder'] if 'shared_resource_keys' in row),None)
    if shared is not None:
        rows.extend(['',f'두 배치에 공통인 (resource_type, id): {shared:,}개.'])
    counts = visible['difference_counts']
    rows.extend(['',f'셀 차이 {counts["cell_diffs"]}개 · 빠진 행 {counts["missing_rows"]}개 · 남는 행 {counts["unexpected_rows"]}개.',
                 '실행별 상세는 .local/FHIR-LINE-02/runs/의 CSV와 로컬 JSON에 보존해요.'])
    if visible['cell_diffs']:
        rows.extend(['','| 표 | 병원 | 기준 시점 | 열 | 기대 | 실제 |','|---|---|---|---|---|---|'])
        for item in visible['cell_diffs']:
            cells = [item['table'],item['row'].get('hospital',''),item['row'].get('as_of_label',''),
                     item['column'],item['expected'],item['actual']]
            rows.append('| '+' | '.join(str(cell).replace('|','\\|').replace('\n','<br>').replace('\r','') for cell in cells)+' |')
    (ARTIFACTS/'summaries/verification-ladder.md').write_text('\n'.join(rows)+'\n')
    if archive_error is not None:
        raise archive_error
