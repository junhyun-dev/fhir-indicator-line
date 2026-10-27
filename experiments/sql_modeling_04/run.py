#!/usr/bin/env python3
"""D1-D7 / ADR0001,0003,0005,0010,0013: isolated E01, no product DB access.

python3 experiments/sql_modeling_04/run.py --expected-root <reviewed external e01 folder>
Uses only the existing DuckDB package and Python standard library.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import duckdb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / '.local/FHIR-LINE-SQL-04'
DATABASE = BASE / 'experiment.duckdb'
DEFAULT_EXPECTED = Path(os.environ.get('FHIR_E01_EXPECTED_ROOT', str(ROOT / 'answer_key_lead/e01')))
EXPERIMENT_LIMIT = 512 * 1024 * 1024
PROJECT_LIMIT = 5_000_000_000
FIXTURES = {
    'sources': [('hospital','VARCHAR'),('derived_from','VARCHAR')],
    'persons': [('hospital','VARCHAR'),('person_id','VARCHAR'),('omop_person_id','INTEGER'),('measurement_year','INTEGER'),('year_of_birth','INTEGER')],
    'conditions': [('hospital','VARCHAR'),('source_row_key','VARCHAR'),('omop_person_id','INTEGER'),('condition_concept_id','INTEGER'),('condition_start_date','DATE'),('condition_end_date','DATE')],
    'visits': [('hospital','VARCHAR'),('source_row_key','VARCHAR'),('omop_person_id','INTEGER'),('visit_concept_id','INTEGER'),('visit_start_date','DATE'),('visit_end_date','DATE')],
    'measurements': [('hospital','VARCHAR'),('source_row_key','VARCHAR'),('omop_person_id','INTEGER'),('measurement_concept_id','INTEGER'),('measurement_date','DATE'),('value_as_number','DOUBLE'),('unit_concept_id','INTEGER')],
    'indicator_concepts': [('concept_set','VARCHAR'),('concept_id','INTEGER')],
    'as_of_labels': [('as_of_label','VARCHAR'),('month','INTEGER'),('day','INTEGER')],
}
EXPECTED = {
    'daily': [('hospital','VARCHAR'),('person_id','VARCHAR'),('as_of','DATE'),('bp_date','DATE'),('systolic_min','DOUBLE'),('diastolic_min','DOUBLE')],
    'person': [('hospital','VARCHAR'),('person_id','VARCHAR'),('as_of_label','VARCHAR'),('as_of','DATE'),('last_bp_date','DATE'),('systolic','DOUBLE'),('diastolic','DOUBLE'),('controlled','INTEGER'),('reason','VARCHAR')],
    'summary_by_date': [('hospital','VARCHAR'),('as_of','DATE'),('numerator','INTEGER'),('denominator','INTEGER'),('rate','DOUBLE')],
    'summary_by_label': [('hospital','VARCHAR'),('as_of_label','VARCHAR'),('numerator','INTEGER'),('denominator','INTEGER'),('rate','DOUBLE')],
}
KEYS = {'daily': ('hospital','person_id','as_of','bp_date'), 'person': ('hospital','person_id','as_of'),
        'summary_by_date': ('hospital','as_of'), 'summary_by_label': ('hospital','as_of_label')}
NULLABLE = {'sources': {'derived_from'}, 'conditions': {'condition_end_date'}, 'measurements': {'value_as_number'}}
CSV_FILES = {f'fixtures/{name}.csv' for name in list(FIXTURES)[:5]} | {f'expected_manual/{name}.csv' for name in EXPECTED}


class ExperimentError(ValueError):
    def __init__(self, code, **details):
        self.code, self.details = code, details
        super().__init__(code)


def require(condition, code, **details):
    if not condition:
        raise ExperimentError(code, **details)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def reviewed_bundle(folder=DEFAULT_EXPECTED):
    folder = Path(folder)
    text = (folder / 'README.md').read_text()
    approval = re.search(r'^## 리드 검수[^\n]*\n(?P<body>.*?)(?=^## |\Z)', text, re.M | re.S)
    require(approval and re.search(r'^검수:.*Claude 리드.*\*\*받아들임\.\*\*', approval['body'], re.M), 'LEAD_REVIEW_REQUIRED')
    manifest = (folder / 'SHA256SUMS').read_bytes()
    hashes = {}
    for line in manifest.decode().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        require(match and match[2] in CSV_FILES and match[2] not in hashes, 'HASH_MANIFEST_INVALID')
        hashes[match[2]] = match[1]
    require(set(hashes) == CSV_FILES, 'HASH_MANIFEST_INVALID')
    contents = {}
    for name, expected_hash in hashes.items():
        body = (folder / name).read_bytes()
        require(digest(body) == expected_hash, 'EXTERNAL_HASH_MISMATCH', file=name)
        contents[name] = body
    return {'contents': contents, 'hashes': hashes, 'manifest_sha256': digest(manifest),
            'approval_readme_sha256': digest(text.encode())}


def parse_csv(body, columns):
    reader = csv.reader(io.StringIO(body.decode('utf-8'), newline=''))
    require(next(reader, None) == [c for c, _ in columns], 'CSV_HEADER')
    result = []
    for row in reader:
        require(len(row) == len(columns), 'CSV_WIDTH')
        typed = []
        for value, (_, kind) in zip(row, columns):
            if value == '':
                typed.append(None)
            elif kind == 'INTEGER':
                require(bool(re.fullmatch(r'[+-]?\d+', value)), 'INTEGER_FORMAT')
                typed.append(int(value))
            elif kind == 'DOUBLE':
                number = float(value)
                require(math.isfinite(number), 'NONFINITE_NUMBER')
                typed.append(number)
            elif kind == 'DATE':
                date = dt.date.fromisoformat(value)
                require(date.isoformat() == value, 'DATE_FORMAT')
                typed.append(date)
            else:
                typed.append(value)
        result.append(tuple(typed))
    return result


def fixture_rows(bundle):
    result = {}
    for name, columns in FIXTURES.items():
        if name in ('indicator_concepts','as_of_labels'):
            body = (ROOT / 'seeds' / f'{name}.csv').read_bytes()
        else:
            body = bundle['contents'][f'fixtures/{name}.csv']
            require((HERE / 'fixtures' / f'{name}.csv').read_bytes() == body, 'FIXTURE_COPY_MISMATCH', file=name)
        result[name] = parse_csv(body, columns)
    return result


def memory_connection():
    checked_output(BASE/'tmp').mkdir(parents=True, exist_ok=True)
    return duckdb.connect(':memory:', config={'memory_limit': '128MB', 'threads': 1,
        'temp_directory': str(BASE/'tmp'),
        'autoinstall_known_extensions': False, 'autoload_known_extensions': False})


def key_check(con, table, columns):
    names = ','.join(columns)
    nulls = con.execute(f'SELECT count(*) FROM {table} WHERE ' + ' OR '.join(f'{c} IS NULL' for c in columns)).fetchone()[0]
    groups = con.execute(f'SELECT count(*),coalesce(max(n),0) FROM (SELECT count(*) n FROM {table} GROUP BY {names} HAVING count(*)>1)').fetchone()
    require(not nulls and not groups[0], 'KEY_CONTRACT', table=table, key=list(columns), null_rows=nulls, duplicate_groups=groups[0], max_multiplicity=groups[1])


def orphan_check(con, child, parent, columns):
    condition = ' AND '.join(f'c.{c}=p.{p}' for c, p in columns)
    count = con.execute(f'SELECT count(*) FROM {child} c WHERE NOT EXISTS (SELECT 1 FROM {parent} p WHERE {condition})').fetchone()[0]
    require(count == 0, 'ORPHAN_ROWS', table=child, rows=count)


def validate_inputs(con):
    require(sum(con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in FIXTURES) <= 128, 'INPUT_LIMIT')
    # Report both person key groups before stopping; do not deduplicate a broken fixture.
    duplicates = {}
    for label, columns in [('natural', 'hospital,person_id'), ('omop', 'omop_person_id')]:
        count, maximum = con.execute(f'SELECT count(*),coalesce(max(n),0) FROM (SELECT count(*) n FROM persons GROUP BY {columns} HAVING count(*)>1)').fetchone()
        if count:
            duplicates[label] = {'groups': count, 'max_multiplicity': maximum}
    require(not duplicates, 'PERSON_DUPLICATES', **duplicates)
    for table, columns in FIXTURES.items():
        mandatory = [c for c, _ in columns if c not in NULLABLE.get(table, set())]
        if mandatory:
            n = con.execute(f'SELECT count(*) FROM {table} WHERE ' + ' OR '.join(f'{c} IS NULL' for c in mandatory)).fetchone()[0]
            require(n == 0, 'REQUIRED_NULL', table=table, rows=n)
    for table, key in [('sources',('hospital',)), ('persons',('hospital','person_id')), ('persons',('omop_person_id',)),
                       ('indicator_concepts',('concept_set','concept_id')), ('as_of_labels',('as_of_label',))]:
        key_check(con, table, key)
    orphan_check(con, 'persons', 'sources', [('hospital','hospital')])
    for name in ('conditions','visits','measurements'):
        key_check(con, name, ('hospital','source_row_key'))
        orphan_check(con, name, 'persons', [('hospital','hospital'),('omop_person_id','omop_person_id')])
    for table, field, group in [('conditions','condition_concept_id','essential_hypertension'),
                                ('visits','visit_concept_id',None), ('measurements','measurement_concept_id',None),
                                ('measurements','unit_concept_id','bp_unit')]:
        allowed = " and concept_set='" + group + "'" if group else ''
        count = con.execute(f'SELECT count(*) FROM {table} x WHERE NOT EXISTS (SELECT 1 FROM indicator_concepts c WHERE c.concept_id=x.{field}{allowed})').fetchone()[0]
        require(not count, 'CONCEPT_REFERENCE', table=table, rows=count)
    parents = dict(con.execute('SELECT hospital,derived_from FROM sources').fetchall())
    for source in parents:
        seen = set()
        current = source
        while current is not None:
            require(current in parents and current not in seen, 'SOURCE_GRAPH')
            seen.add(current)
            current = parents[current]
    for key in [('hospital','person_id','as_of'), ('hospital','person_id','as_of_label')]:
        key_check(con, 'periods', key)
    for table, key in [('dim_date',('as_of',)), ('source_as_of_scope',('hospital','as_of')),
                       ('source_label_scope',('hospital','as_of_label'))]:
        key_check(con, table, key)


def load_inputs(con, rows):
    for name in ('daily_adapter','fct_bp_person_as_of','summary_by_date','summary_by_label'):
        con.execute(f'DROP VIEW IF EXISTS {name}')
    for name in ('q1_reference','q1_alternative','q2_reference','q2_alternative'):
        con.execute(f'DROP TABLE IF EXISTS {name}')
    con.execute((HERE / 'schema.sql').read_text())
    for name, values in rows.items():
        if values:
            placeholders = ','.join('?' for _ in FIXTURES[name])
            con.executemany(f'INSERT INTO {name} VALUES ({placeholders})', values)
    validate_inputs(con)


def create_expected(con, bundle):
    for name, columns in EXPECTED.items():
        con.execute(f'CREATE OR REPLACE TABLE expected_{name} (' + ','.join(f'{c} {t}' for c,t in columns) + ')')
        values = parse_csv(bundle['contents'][f'expected_manual/{name}.csv'], columns)
        con.executemany(f'INSERT INTO expected_{name} VALUES (' + ','.join('?' for _ in columns) + ')', values)
        key_check(con, f'expected_{name}', KEYS[name])


def compare(con, actual, expected, kind):
    columns = [(c, str(t)) for c, t, *_ in con.execute(f'DESCRIBE SELECT * FROM {actual}').fetchall()]
    require(columns == EXPECTED[kind], 'TYPE_CONTRACT', table=actual, actual=columns)
    key_check(con, actual, KEYS[kind])
    left = con.execute(f'SELECT count(*) FROM (SELECT * FROM {expected} EXCEPT ALL SELECT * FROM {actual})').fetchone()[0]
    right = con.execute(f'SELECT count(*) FROM (SELECT * FROM {actual} EXCEPT ALL SELECT * FROM {expected})').fetchone()[0]
    require((left,right) == (0,0), 'EXPECTED_MISMATCH', table=actual, expected_minus_actual=left, actual_minus_expected=right)
    return {'rows': con.execute(f'SELECT count(*) FROM {actual}').fetchone()[0], 'left': left, 'right': right}


def adapter_check(con):
    con.execute('CREATE OR REPLACE VIEW daily_adapter AS SELECT d.*,p.as_of_label FROM q1_reference d JOIN periods p USING (hospital,person_id,as_of)')
    n = con.execute('SELECT count(*) FROM q1_reference').fetchone()[0]
    require(con.execute('SELECT count(*) FROM daily_adapter').fetchone()[0] == n, 'ADAPTER_MULTIPLICITY')
    key_check(con, 'daily_adapter', KEYS['daily'])
    orphan_check(con, 'q1_reference', 'periods', [('hospital','hospital'),('person_id','person_id'),('as_of','as_of')])
    # Date -> label -> date is a one-to-one roundtrip per hospital/person.
    wrong = con.execute('''SELECT count(*) FROM daily_adapter a JOIN periods p USING (hospital,person_id,as_of_label) WHERE a.as_of<>p.as_of''').fetchone()[0]
    require(not wrong, 'ADAPTER_ROUNDTRIP')
    for table in ('q1_reference','q1_alternative'):
        count = con.execute(f'SELECT count(*) FROM (SELECT * FROM {table} EXCEPT ALL SELECT hospital,person_id,as_of,bp_date,systolic_min,diastolic_min FROM daily_adapter)').fetchone()[0]
        require(not count, 'ADAPTER_PROJECTION')


def summarize(con):
    key_check(con, 'q2_reference', KEYS['person'])
    orphan_check(con, 'q2_reference', 'periods', [('hospital','hospital'),('person_id','person_id'),('as_of','as_of'),('as_of_label','as_of_label')])
    con.execute('''CREATE OR REPLACE VIEW fct_bp_person_as_of AS SELECT *,1::integer AS denominator_contribution,controlled::integer AS numerator_contribution FROM q2_reference''')
    con.execute('''CREATE OR REPLACE VIEW summary_by_date AS
        SELECT s.hospital,s.as_of,coalesce(sum(f.controlled),0)::integer numerator,
               count(f.person_id)::integer denominator,
               round(sum(f.controlled)::double/nullif(count(f.person_id),0),4)::double rate
        FROM source_as_of_scope s LEFT JOIN q2_reference f USING(hospital,as_of)
        GROUP BY s.hospital,s.as_of''')
    con.execute('''CREATE OR REPLACE VIEW summary_by_label AS
        SELECT s.hospital,s.as_of_label,coalesce(sum(f.controlled),0)::integer numerator,
               count(f.person_id)::integer denominator,
               round(sum(f.controlled)::double/nullif(count(f.person_id),0),4)::double rate
        FROM source_label_scope s LEFT JOIN q2_reference f USING(hospital,as_of_label)
        GROUP BY s.hospital,s.as_of_label''')


def query_text(con, name, overrides=None):
    text = (overrides or {}).get(name)
    if text is None:
        text = (HERE/'queries'/f'{name}.sql').read_text()
    statements = con.extract_statements(text)
    require(len(statements) == 1 and statements[0].type == duckdb.StatementType.SELECT, 'SELECT_ONLY')
    return text


def execute_candidates(con, bundle, overrides=None):
    create_expected(con, bundle)
    result = {}
    for phase, kind, names in [('Q1','daily',('q1_daily_reference','q1_daily_alternative')),
                               ('Q2','person',('q2_last_reference','q2_last_alternative'))]:
        tables = []
        for name in names:
            table = ('q1_' if phase=='Q1' else 'q2_') + name.rsplit('_',1)[1]
            con.execute(f'CREATE TABLE {table} AS ' + query_text(con, name, overrides))
            result[table] = compare(con, table, f'expected_{kind}', kind)
            tables.append(table)
        result[phase+'_two_way'] = compare(con, tables[1], tables[0], kind)
        if phase == 'Q1':
            adapter_check(con)
    summarize(con)
    for kind in ('summary_by_date','summary_by_label'):
        result[kind] = compare(con, kind, 'expected_'+kind, kind)
    result['dimensions'] = {name: con.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
                            for name in ('dim_source','dim_person','dim_date','periods','source_as_of_scope','source_label_scope','fct_bp_person_as_of')}
    return result


def select_scope(con, hospitals, as_of):
    parents = dict(con.execute('SELECT hospital,derived_from FROM sources').fetchall())
    chosen = set(hospitals)
    for hospital in chosen:
        current = parents.get(hospital)
        while current:
            require(current not in chosen, 'DERIVED_SOURCE_OVERLAP')
            current = parents.get(current)
    require(len(hospitals) == len(chosen) == 1, 'MULTI_SOURCE_SCOPE')
    require(isinstance(as_of, dt.date) and not isinstance(as_of, dt.datetime), 'NON_ADDITIVE_SCOPE')
    rows = con.execute('SELECT * FROM summary_by_date WHERE hospital=? AND as_of=?', [hospitals[0],as_of]).fetchall()
    require(len(rows)==1, 'SCOPE_NOT_FOUND')
    return rows


def checked_output(path):
    path = Path(path).absolute()
    require(path.is_relative_to(BASE) and path.resolve().is_relative_to(BASE), 'UNSAFE_OUTPUT')
    for current in (path, *path.parents):
        if current == ROOT.parent:
            break
        require(not current.is_symlink(), 'UNSAFE_OUTPUT')
        if current.is_file():
            require(current.stat().st_nlink == 1, 'UNSAFE_OUTPUT')
    return path


def disk_bytes(folder):
    return sum(p.lstat().st_blocks*512 for p in [folder,*folder.rglob('*')] if p.exists()) if folder.exists() else 0


def check_space():
    experiment, project = disk_bytes(BASE), disk_bytes(ROOT)
    require(experiment < EXPERIMENT_LIMIT and project < PROJECT_LIMIT, 'STORAGE_LIMIT', experiment_bytes=experiment, project_bytes=project)
    return {'experiment_bytes': experiment, 'project_bytes': project}


def write_json(path, value):
    path = checked_output(path)
    temporary = checked_output(path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp'))
    with temporary.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description='E01: reviewed manual inputs, two SQL pairs, one isolated DB')
    parser.add_argument('--expected-root', type=Path, default=DEFAULT_EXPECTED)
    args = parser.parse_args(argv)
    started = time.monotonic()
    report = {'status': '실패', 'phase': 'initial', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    run_folder = None
    try:
        for path in (BASE, BASE/'tmp', BASE/'runs', BASE/'run.lock', BASE/'latest.json'):
            checked_output(path)
        BASE.mkdir(parents=True, exist_ok=True)
        (BASE/'tmp').mkdir(exist_ok=True)
        (BASE/'runs').mkdir(exist_ok=True)
        with (BASE/'run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run_folder = checked_output(BASE/'runs'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+uuid.uuid4().hex[:8]))
            run_folder.mkdir()
            write_json(run_folder/'result.json', report)
            write_json(BASE/'latest.json', report)
            checked_output(DATABASE)
            checked_output(Path(str(DATABASE)+'.wal'))
            before_size = check_space()
            bundle = reviewed_bundle(args.expected_root)
            report.update(phase='inputs', expected_hashes=bundle['hashes'], manifest_sha256=bundle['manifest_sha256'], approval_readme_sha256=bundle['approval_readme_sha256'])
            rows = fixture_rows(bundle)
            report['input_rows'] = {name: len(values) for name, values in rows.items()}
            files = [HERE/'schema.sql',HERE/'run.py',*sorted((HERE/'queries').glob('*.sql')),
                     ROOT/'seeds/indicator_concepts.csv',ROOT/'seeds/as_of_labels.csv',
                     ROOT/'models/intermediate/int_bp_daily.sql',ROOT/'models/marts/fct_bp_person.sql']
            report['code_hashes'] = {str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in files}
            report['product_commit'] = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            report['product_dirty'] = bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True))
            with duckdb.connect(str(DATABASE), config={'memory_limit':'128MB','threads':1,
                    'temp_directory':str(BASE/'tmp'), 'autoinstall_known_extensions':False,
                    'extension_directory':str(BASE/'tmp/extensions'),
                    'autoload_known_extensions':False}) as con:
                load_inputs(con, rows)
                report['phase'] = 'Q1_then_Q2'
                report['comparisons'] = execute_candidates(con, bundle)
                report['duckdb'] = dict(con.execute("SELECT name,value FROM duckdb_settings() WHERE name IN ('memory_limit','threads')").fetchall())
                for name, kind in [('q1_reference','daily'),('q1_alternative','daily'),('q2_reference','person'),('q2_alternative','person'),('summary_by_date','summary_by_date'),('summary_by_label','summary_by_label')]:
                    output = checked_output(run_folder/(name+'.csv'))
                    with output.open('x', newline='') as stream:
                        writer = csv.writer(stream, lineterminator='\n')
                        writer.writerow([c for c,_ in EXPECTED[kind]])
                        writer.writerows(con.execute(f'SELECT * FROM {name} ORDER BY '+','.join(KEYS[kind])).fetchall())
                report['output_hashes'] = {p.name:digest(p.read_bytes()) for p in sorted(run_folder.glob('*.csv'))}
            verified_again = reviewed_bundle(args.expected_root)
            require(all(verified_again[key] == bundle[key] for key in ('hashes', 'manifest_sha256', 'approval_readme_sha256')), 'INPUT_CHANGED_DURING_RUN')
            report.update(status='통과',phase='complete',storage_before=before_size,storage_after=check_space())
            report.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic()-started,3))
            report['experiment_growth_bytes'] = report['storage_after']['experiment_bytes'] - before_size['experiment_bytes']
            report['run_folder'] = str(run_folder.relative_to(ROOT))
            write_json(run_folder/'result.json', report)
            write_json(BASE/'latest.json', report)
    except Exception as exc:
        report.update(status='실패',phase=report.get('phase'),error=exc.code if isinstance(exc,ExperimentError) else type(exc).__name__,details=exc.details if isinstance(exc,ExperimentError) else {})
        # No fallback writes if the output itself is unsafe or another writer owns the lock.
        if run_folder is not None:
            write_json(run_folder/'result.json', report)
            write_json(BASE/'latest.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report['status']=='통과' else 1


if __name__ == '__main__':
    raise SystemExit(main())
