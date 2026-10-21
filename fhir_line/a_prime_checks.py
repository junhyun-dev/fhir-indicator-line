"""D1-D7 / ADR0013: actual CSV/staging/OMOP outputs against the frozen v3 reference."""
import csv
from contextlib import contextmanager
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import tempfile

from . import a_prime
from .runtime import ROOT, DATABASE, connect, writable_path


def frozen_checker():
    spec=importlib.util.spec_from_file_location('locked_aprime_checker',ROOT/'answer_key_a_prime/check.py')
    checker=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checker.verify_lock(ROOT/'expected_a_prime')
    return checker


def text(value):
    if value is None:return ''
    if hasattr(value,'isoformat'):return value.isoformat()
    return str(value)


def records(connection, query):
    cursor=connection.execute(query)
    columns=[column[0] for column in cursor.description]
    return [dict(zip(columns,row)) for row in cursor.fetchall()]


@contextmanager
def output_stream(path, newline=None):
    """ADR0013: validate leaf symlinks; replace rather than truncate a shared inode."""
    path=writable_path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline=newline,
                dir=path.parent,prefix='.aprime-',delete=False) as stream:
            temporary=Path(stream.name)
            yield stream
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


def write_projection(path, rows):
    with output_stream(path) as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')


def staging_projection(connection):
    tables={name:[] for name in a_prime.FIELDS}
    for table,model in [('persons','person'),('diagnoses','diagnosis'),('visits','visit')]:
        projection=','.join('"'+field+'"' for field in a_prime.FIELDS[table])
        tables[table]=[{key:text(value) for key,value in row.items()}
                       for row in records(connection,f'SELECT {projection} FROM stg_aprime_{model}')]
    yield from a_prime.projection(tables)
    for row in records(connection,'SELECT * FROM stg_aprime_bp_value'):
        parsed=text(row['parsed_value_text'])
        if parsed!=row['original_value'] or (parsed and row['value']!=Decimal(parsed)):
            raise ValueError('Staging parsed BP lost original value/scale')
        facts={key:text(row[key]) for key in ('person_id','observation_id','effective','status','panel_code','panel_system','panel_codings')}
        facts.update(code=text(row['source_code']),system=text(row['source_system']),value=parsed,
                     unit_code=text(row['unit_mapping_code']),unit_system=text(row['unit_system']),unit_display=text(row['unit_display']))
        yield {'kind':'bp_component','source_row_key':row['source_row_key'],'facts':facts}


def actual_facts(connection, fields):
    result=[]
    def add(table, row, **values):
        item=dict.fromkeys(fields,'')
        item.update(hospital='A_PRIME',omop_table=table,source_person_id=row['source_person_id'],source_row_key=row['source_row_key'])
        item.update({key:text(value) for key,value in values.items()})
        result.append(item)
    for row in records(connection,"""SELECT p.*,e.measurement_year,p.person_source_value as source_person_id,
             p.person_source_value as source_row_key FROM person p JOIN person_ext e USING(person_id)
             WHERE e.hospital='A_PRIME'"""):
        add('person',row,year_of_birth=row['year_of_birth'],gender_source_value=row['gender_source_value'],concept_id=row['gender_concept_id'])
        add('person_ext',row,measurement_year=row['measurement_year'])
    for row in records(connection,"""SELECT o.*,p.person_source_value as source_person_id,p.person_source_value as source_row_key
            FROM observation_period o JOIN person p USING(person_id) JOIN person_ext e USING(person_id)
            WHERE e.hospital='A_PRIME'"""):
        add('observation_period',row,start_date=row['observation_period_start_date'],end_date=row['observation_period_end_date'],concept_id=row['period_type_concept_id'])
    definitions=[
        ('visit_occurrence','visit_occurrence_id','visit_start_date','visit_end_date','visit_concept_id','visit_source_value','stg_aprime_visit','class_system'),
        ('condition_occurrence','condition_occurrence_id','condition_start_date','condition_end_date','condition_concept_id','condition_source_value','stg_aprime_diagnosis','original_system'),
        ('measurement','measurement_id','measurement_date','measurement_date','measurement_concept_id','measurement_source_value','stg_aprime_bp_value','source_system')]
    for table,identifier,start,end,concept,code,stage,system in definitions:
        query=f"""SELECT o.*,l.source_row_key,p.person_source_value as source_person_id,s.{system} as reference_system
            FROM {table} o JOIN person p USING(person_id) JOIN person_ext e USING(person_id)
            JOIN omop_source_link l ON l.omop_table='{table}' AND l.omop_id=o.{identifier}
            LEFT JOIN {stage} s ON s.source_row_key=l.source_row_key
            WHERE e.hospital='A_PRIME' AND l.hospital='A_PRIME'"""
        for row in records(connection,query):
            values=dict(start_date=row[start],end_date=row[end],concept_id=row[concept],reference_code=row[code],reference_system=row['reference_system'])
            if table=='measurement':
                values.update(value_as_number=row['value_as_number'],unit_concept_id=row['unit_concept_id'],reference_unit=row['unit_source_value'])
            add(table,row,**values)
    return result


def write_csv(path, fields, rows):
    with output_stream(path,newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows({field:text(row[field]) for field in fields} for row in rows)


def check(source=a_prime.DEFAULT, database=DATABASE, output=ROOT/'.local/FHIR-LINE-A-PRIME/actual'):
    output=writable_path(output);output.mkdir(parents=True,exist_ok=True)
    with output_stream(output/'result.json') as stream:
        json.dump({'ok':False,'status':'실패','phase':'checking_actual_inputs'},stream)
    checker=frozen_checker()
    tables=a_prime.read_input(source)
    write_projection(output/'input_source_facts.jsonl',a_prime.projection(tables))
    manifest=ROOT/'expected_a_prime/manifest.json'
    source_manifest=json.loads((Path(source)/'manifest.json').read_text())
    if source_manifest['source_files']!=checker.read_manifest(manifest)['source_files']:
        raise ValueError('A-prime provenance differs from frozen original source files')
    input_result=checker.compare_source_facts(manifest,output/'input_source_facts.jsonl')
    with connect(database,read_only=True) as connection:
        if connection.execute("SELECT count(*) FROM person_ext WHERE hospital NOT IN ('A','B','A_PRIME') OR hospital IS NULL").fetchone()[0]:
            raise ValueError('Unregistered clinical source')
        write_projection(output/'staging_source_facts.jsonl',staging_projection(connection))
        for name,table in [('person.csv','fct_bp_person'),('summary.csv','bp_summary')]:
            fields=checker.CONTRACTS[name]['fields']
            rows=records(connection,'SELECT '+','.join(fields)+f" FROM {table} WHERE hospital='A_PRIME'")
            write_csv(output/name,fields,rows)
        fields=checker.CONTRACTS['omop_facts.csv']['fields']
        write_csv(output/'omop_facts.csv',fields,actual_facts(connection,fields))
        from .ladder import check_types
        from .omop import check_shape
        types=check_types(connection);shape=check_shape(connection)
    compared=checker.compare_all(ROOT/'expected_a_prime',output,output/'staging_source_facts.jsonl',route='preserved_source_clinical')
    ok=input_result['ok'] and compared['ok'] and types['status']=='통과' and shape['status']=='통과'
    result={'ok':ok,'status':'통과' if ok else '실패','scope':'derived A_PRIME; preserved original clinical meaning only',
            'input_projection':input_result,'staging_and_clinical':compared,'sql_types':types,'omop_shape':shape,
            'kcd_linkage_complete':False,'derived_from':'A','independent_population':False}
    with output_stream(output/'result.json') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
