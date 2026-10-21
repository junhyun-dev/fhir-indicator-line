"""⑥ OMOP 확인(M3 · 결정 0004 ~ 0010): 공식 DDL 모양 · 필수 칸 · 원천에서 센 건수 · 끝까지 따라갈 행.

기대 결과(expected/omop_counts.csv · omop_follow.csv)는 Codex 밖에서 원천을 직접 세어 만든 것이고 읽기만 한다.
쓰는 쪽: 짝 Claude 세션(검사기는 Codex 밖 · 10/19).
"""
import collections
import csv
import re

import duckdb

from .runtime import ROOT

DDL = ROOT/'vendor/omop/OMOPCDM_duckdb_5.4_ddl.sql'
CDM_TABLES = ('person','observation_period','visit_occurrence','condition_occurrence','measurement','cdm_source')
EVENT_TABLES = ('observation_period','visit_occurrence','condition_occurrence','measurement')
EXT_CONTRACT = {'person_id':'INTEGER','hospital':'VARCHAR','measurement_year':'INTEGER'}  # 결정 0005 · 공식 표가 아님
LOAD_COUNTS = 'omop_load_counts'  # 병원 × 표마다 옮긴 행 · 안 옮긴 행(FC-03 · 생략은 알림)
LINK = 'omop_source_link'          # 결정 0011: 사건 행 하나 = 원래 행 키 한 줄(공식 표가 아님)
LINK_CONTRACT = {'omop_table':'VARCHAR','omop_id':'INTEGER','hospital':'VARCHAR','source_row_key':'VARCHAR'}
LINKED = {'visit_occurrence':'visit_occurrence_id','condition_occurrence':'condition_occurrence_id','measurement':'measurement_id'}
FOLLOW_COLUMNS = ('measurement_source_value','measurement_date','measurement_concept_id','value_as_number','unit_concept_id','value_source_value')


def official_columns():
    """공식 DDL을 빈 메모리 DB에 그대로 만들고 표마다 (열, 형식, 필수)를 읽는다."""
    con = duckdb.connect()
    con.execute(DDL.read_text().replace('@cdmDatabaseSchema.',''))
    return {t:[(r[1],r[2],bool(r[3])) for r in con.execute(f"PRAGMA table_info('{t}')").fetchall()] for t in CDM_TABLES}


def exists(connection, table):
    return connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name=?",[table]).fetchone()[0]>0


def check_shape(connection):
    """공식 표 다섯 + cdm_source: 열 이름 · 순서 · 형식이 DDL과 같고, 필수 칸에 빈 값이 없나. person_ext는 계약한 세 열."""
    missing = [t for t in CDM_TABLES+('person_ext',) if not exists(connection,t)]
    if missing:
        return {'status':'기다림','detail':'OMOP 표 없음: '+', '.join(missing)}
    problems = []
    for table, columns in official_columns().items():
        actual = [(r[1],r[2]) for r in connection.execute(f"PRAGMA table_info('{table}')").fetchall()]
        if actual!=[(c,t) for c,t,_ in columns]:
            want = dict((c,t) for c,t,_ in columns)
            have = dict(actual)
            diff = [f'{c}: {have.get(c,"없음")}≠{want.get(c,"없음")}' for c in list(want)+[c for c in have if c not in want] if have.get(c)!=want.get(c)]
            problems.append(f'{table} 모양 다름({"; ".join(diff[:4]) or "열 순서"})')
            continue
        for column,_,required in columns:
            if required:
                nulls = connection.execute(f'SELECT count(*) FROM {table} WHERE "{column}" IS NULL').fetchone()[0]
                if nulls:
                    problems.append(f'{table}.{column} 필수 칸 빈 값 {nulls}')
    ext = dict((r[1],r[2]) for r in connection.execute("PRAGMA table_info('person_ext')").fetchall())
    if ext!=EXT_CONTRACT:
        problems.append(f'person_ext 모양 {ext}')
    keys = connection.execute('SELECT count(*), count(DISTINCT person_id) FROM person').fetchone()
    if keys[0]!=keys[1]:
        problems.append(f'person_id 겹침 {keys[0]-keys[1]}')
    orphans = connection.execute('SELECT count(*) FROM person p WHERE NOT EXISTS (SELECT 1 FROM person_ext e WHERE e.person_id=p.person_id)').fetchone()[0]
    if orphans:
        problems.append(f'person_ext에 없는 사람 {orphans}')
    return {'status':'통과' if not problems else '실패',
            'detail':'공식 DDL과 열 · 형식 · 필수 칸 '+('같음' if not problems else '다름: '+' / '.join(problems))}


def actual_counts(connection):
    counts = collections.Counter()
    for h,n in connection.execute('SELECT e.hospital, count(*) FROM person p JOIN person_ext e USING (person_id) GROUP BY 1').fetchall():
        counts[(h,'person')] = n
    for h,n in connection.execute('SELECT hospital, count(*) FROM person_ext GROUP BY 1').fetchall():
        counts[(h,'person_ext')] = n
    for table in EVENT_TABLES:
        for h,n in connection.execute(f'SELECT e.hospital, count(*) FROM {table} x JOIN person_ext e USING (person_id) GROUP BY 1').fetchall():
            counts[(h,table)] = n
        unowned = connection.execute(f'SELECT count(*) FROM {table} x WHERE NOT EXISTS (SELECT 1 FROM person_ext e WHERE e.person_id=x.person_id)').fetchone()[0]
        if unowned:
            counts[('?',table)] = unowned
    counts[('AB','cdm_source')] = connection.execute('SELECT count(*) FROM cdm_source').fetchone()[0]
    return counts


def compare_counts(connection, folder):
    """원천에서 직접 센 건수(병원 × 표)와 실제 OMOP 행 수 · 안 옮긴 행 수(omop_load_counts)."""
    path = folder/'omop_counts.csv'
    if not path.exists():
        return {'status':'기다림','detail':'expected/omop_counts.csv 없음'}
    if not (all(exists(connection,t) for t in CDM_TABLES+('person_ext',)) and exists(connection,LOAD_COUNTS)):
        return {'status':'기다림','detail':'OMOP 표 또는 '+LOAD_COUNTS+' 없음'}
    with path.open(newline='') as f:
        expected = list(csv.DictReader(f))
    actual = actual_counts(connection)
    # ADR0013: explicitly register only the frozen derived source, never ignore extras.
    if any(h == 'A_PRIME' for h,_ in actual):
        from .a_prime_checks import frozen_checker
        checker = frozen_checker()
        manifest = checker.read_manifest(ROOT/'expected_a_prime/manifest.json')
        for table,count in manifest['omop_counts'].items():
            expected.append({'hospital':'A_PRIME','omop_table':table,'carried':str(count),
                             'not_carried':str(manifest['counts']['unmapped_diagnosis_codings'] if table=='condition_occurrence' else 0)})
    skipped = {(h,t):n for h,t,n in connection.execute(f'SELECT hospital, omop_table, not_carried FROM {LOAD_COUNTS}').fetchall()}
    rows, bad = [], []
    for r in expected:
        key = (r['hospital'],r['omop_table'])
        got, got_skipped = actual.get(key,0), skipped.get(key,0)
        rows.append({'hospital':key[0],'table':key[1],'expected':int(r['carried']),'actual':got,
                     'expected_not_carried':int(r['not_carried']),'actual_not_carried':got_skipped})
        if got!=int(r['carried']) or got_skipped!=int(r['not_carried']):
            bad.append(f'{key[0]} {key[1]} {got}/{r["carried"]}'+(f' 안 옮김 {got_skipped}/{r["not_carried"]}' if got_skipped!=int(r['not_carried']) else ''))
    extra = [f'{h} {t} {n}' for (h,t),n in actual.items() if (h,t) not in {(r['hospital'],r['omop_table']) for r in expected} and n]
    bad += ['기대에 없는 행 '+x for x in extra]
    return {'status':'통과' if not bad else '실패','detail':'병원 × 표 건수 '+('원천과 같음' if not bad else '다름: '+', '.join(bad)),'counts':rows}


def compare_follow(connection, folder):
    """끝까지 따라갈 행: 그 사람 · 그 날의 measurement 행이 기대 결과와 셀마다 같나(개수 포함)."""
    path = folder/'omop_follow.csv'
    if not path.exists():
        return {'status':'기다림','detail':'expected/omop_follow.csv 없음'}
    if not all(exists(connection,t) for t in ('person','person_ext','measurement')):
        return {'status':'기다림','detail':'OMOP 표 없음'}
    with path.open(newline='') as f:
        expected = list(csv.DictReader(f))
    norm = lambda v: '' if v is None else (str(float(v)) if re.fullmatch(r'-?\d+(\.\d+)?',str(v)) else str(v))  # noqa: E731
    bad = []
    for key in sorted({(r['hospital'],r['person_source_value'],r['measurement_date']) for r in expected}):
        want = collections.Counter(tuple(norm(r[c]) for c in FOLLOW_COLUMNS) for r in expected
                                   if (r['hospital'],r['person_source_value'],r['measurement_date'])==key)
        got_rows = connection.execute('SELECT '+', '.join('m.'+c for c in FOLLOW_COLUMNS)+''' FROM measurement m
            JOIN person p USING (person_id) JOIN person_ext e USING (person_id)
            WHERE e.hospital=? AND p.person_source_value=? AND m.measurement_date=CAST(? AS DATE)''',list(key)).fetchall()
        got = collections.Counter(tuple(norm(v.isoformat() if hasattr(v,'isoformat') else v) for v in row) for row in got_rows)
        if got!=want:
            bad.append(f'{key[0]} {key[1][:8]} {key[2]}: 기대 {sum(want.values())}행 · 실제 {sum(got.values())}행 · 다른 행 {sum((want-got).values())}')
    return {'status':'통과' if not bad else '실패','detail':'따라갈 행 '+('셀마다 같음' if not bad else '다름: '+'; '.join(bad))}


def check_links(connection):
    """결정 0011: 사건 표의 행마다 원래 행 키가 꼭 한 줄 · 키는 병원 × 표 안에서 겹치지 않음 · 병원이 person_ext와 같음."""
    if not all(exists(connection,t) for t in (LINK,'person_ext',*LINKED)):
        return {'status':'기다림','detail':LINK+' 또는 사건 표 없음'}
    have = dict((r[1],r[2]) for r in connection.execute(f"PRAGMA table_info('{LINK}')").fetchall())
    if have!=LINK_CONTRACT:
        return {'status':'실패','detail':f'{LINK} 모양 {have}'}
    bad = []
    for table, key in LINKED.items():
        n, linked_once, wrong_hospital = connection.execute(f"""SELECT count(*),
              count(*) FILTER (WHERE (SELECT count(*) FROM {LINK} l WHERE l.omop_table='{table}' AND l.omop_id=x.{key})=1),
              count(*) FILTER (WHERE EXISTS (SELECT 1 FROM {LINK} l JOIN person_ext e ON e.person_id=x.person_id
                                             WHERE l.omop_table='{table}' AND l.omop_id=x.{key} AND l.hospital<>e.hospital))
            FROM {table} x""").fetchone()
        links, keys, dangling = connection.execute(f"""SELECT count(*), count(DISTINCT hospital||'|'||source_row_key),
              count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM {table} x WHERE x.{key}=l.omop_id))
            FROM {LINK} l WHERE omop_table='{table}'""").fetchone()
        if not (n==linked_once==links==keys) or wrong_hospital or dangling or connection.execute(
                f"SELECT count(*) FROM {LINK} WHERE omop_table='{table}' AND (source_row_key IS NULL OR source_row_key='')").fetchone()[0]:
            bad.append(f'{table}: 행 {n} · 한 줄씩 이어진 행 {linked_once} · 이음 {links} · 다른 키 {keys} · 병원 다름 {wrong_hospital} · 짝 없는 이음 {dangling}')
    others = connection.execute(f"SELECT count(*) FROM {LINK} WHERE omop_table NOT IN ({','.join(repr(t) for t in LINKED)})").fetchone()[0]
    if others:
        bad.append(f'다른 표 이름 {others}')
    return {'status':'통과' if not bad else '실패','detail':'원래 행 키 '+('사건 행마다 한 줄' if not bad else '다름: '+'; '.join(bad))}


def check(connection, folder):
    """⑥ = 모양 + 건수 + 따라갈 행 + 원래 행 키. 하나라도 실패면 실패, 하나라도 기다림이면 기다림."""
    parts = {'모양':check_shape(connection),'건수':compare_counts(connection,folder),'따라가기':compare_follow(connection,folder),
             '원래 행':check_links(connection)}
    states = [p['status'] for p in parts.values()]
    status = '실패' if '실패' in states else '기다림' if '기다림' in states else '통과'
    return {'status':status,'detail':' · '.join(f'{k} {v["status"]}' for k,v in parts.items()),**parts}
