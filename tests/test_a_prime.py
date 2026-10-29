"""D1-D7 / ADR0013: real formatter, CSV parser, SQL and extraction with handmade inputs."""
import copy
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fhir_line import a_prime, a_prime_checks
from fhir_line.runtime import ROOT, connect, environment, writable_path
from fhir_line.store import initialize
from mimic_fixture import HEADERS, write_sources
from wp5_expected import cases as wp5_cases, person_values


def handmade():
    rows=[]
    for person,code,system in [('good','59621000',a_prime.SNOMED),('wrong','59621000','urn:example:unrelated'),('candidate','',''),('wrong-visit','59621000',a_prime.SNOMED)]:
        rows.extend([
            {'resourceType':'Patient','id':person,'birthDate':'1960-12-31','gender':'female'},
            {'resourceType':'Condition','id':'dx-'+person,'subject':{'reference':'Patient/'+person},
             'code':{'coding':[{'code':code,'system':system}]},'onsetDateTime':'2020-01-01','recordedDate':'2020-01-01'},
            {'resourceType':'Encounter','id':'op-'+person,'subject':{'reference':'Patient/'+person},
             'class':{'code':'AMB','system':a_prime.ACT if person!='wrong-visit' else 'urn:example:unrelated'},'period':{'start':'2025-02-01'}}])
    def pressure(key,when,sys,dia,unit='mm[Hg]',panel=a_prime.LOINC,component=a_prime.LOINC):
        rows.append({'resourceType':'Observation','id':key,'subject':{'reference':'Patient/good'},'status':'final',
            'code':{'coding':[{'code':'85354-9','system':panel}]},'effectiveDateTime':when,
            'component':[{'code':{'coding':[{'code':code,'system':component}]},'valueQuantity':{
                'value':Decimal(value),'code':unit,'system':a_prime.UCUM,'unit':'mmHg'}}
                for code,value in [('8480-6',sys),('8462-4',dia)]]})
    pressure('fraction','2025-09-30T23:00:00-02:00','109.51','76.761')
    rows[-1]['code']['coding'].insert(0,{'code':'85354-9','system':'urn:example:unrelated'})
    pressure('same-day','2025-09-30T09:00:00Z','115','80')
    pressure('last','2025-12-01','124','92')
    pressure('other-panel','2025-12-15','110','70',panel='urn:example:unrelated')
    pressure('other-unit','2025-12-20','110','70',unit='kPa')
    pressure('other-component','2025-12-21','110','70',component='urn:example:unrelated')
    pressure('ip-end','2025-12-30','110','70')
    pressure('partial','2025-08-20','121','0')
    rows[-1]['component'].pop()
    rows.append({'resourceType':'Encounter','id':'ip-good','subject':{'reference':'Patient/good'},
        'class':{'code':'IMP','system':a_prime.ACT},'period':{'start':'2025-12-29','end':'2025-12-30'}})
    rows.append({'resourceType':'Encounter','id':'not-ip-good','subject':{'reference':'Patient/good'},
        'class':{'code':'IMP','system':'urn:example:unrelated'},'period':{'start':'2025-12-01','end':'2026-01-01'}})
    return rows


class InputContract(unittest.TestCase):
    def setUp(self):
        cache=ROOT/'.cache/a-prime-tests';cache.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=cache);self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'input'

    def test_0013_D1_export_replay_preserves_bytes_and_refuses_changed_source(self):
        resources=handmade()
        first=a_prime.export_resources(resources,self.directory)
        before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.directory.iterdir()}
        second=a_prime.export_resources(resources,self.directory)
        self.assertFalse(first['reused']);self.assertTrue(second['reused'])
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.directory.iterdir()})
        resources[0]['gender']='male'
        with self.assertRaisesRegex(ValueError,'refusing overwrite'):
            a_prime.export_resources(resources,self.directory)
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.directory.iterdir()})

    def test_0013_D3_parser_preserves_fractional_scale_and_rejects_bad_pairs(self):
        self.assertEqual(a_prime.parse_bp('109.510/76.761'),('109.510','76.761'))
        self.assertEqual(a_prime.parse_bp('/75'),('','75'))
        for text in ('120/80/1','120','NaN/80','120/Infinity','120 /80','1e2/80'):
            with self.subTest(text=text),self.assertRaises(ValueError):a_prime.parse_bp(text)

    def test_0013_D1_input_hash_and_component_disagreement_fail_before_sql(self):
        a_prime.export_resources(handmade(),self.directory)
        file=self.directory/'bp_details.csv';file.write_bytes(file.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):a_prime.read_input(self.directory)
        tables=a_prime.transform(handmade())
        for replacement in ('76.761/109.51','110/77','109.51/76.761/0'):
            changed=copy.deepcopy(tables);changed['bp_details'][0]['bp_text']=replacement
            with self.subTest(replacement=replacement),self.assertRaises(ValueError):a_prime.validate_tables(changed)

    def test_0013_D1_duplicate_and_late_day_rejected_without_partial_publish(self):
        resources=handmade()
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            a_prime.export_resources(resources+[resources[0]],self.directory)
        self.assertFalse(self.directory.exists())
        resources[1]['recordedDate']='2020-01-02'
        with self.assertRaisesRegex(ValueError,'ADR0006'):
            a_prime.export_resources(resources,self.directory)
        self.assertFalse(self.directory.exists())

    def test_0013_D2_original_namespace_and_candidate_are_separate(self):
        tables=a_prime.transform(handmade())
        diagnoses={r['condition_id']:r for r in tables['diagnoses']}
        self.assertEqual(diagnoses['dx-good']['kcd_candidate_status'],'unverified')
        self.assertEqual(diagnoses['dx-wrong']['original_system'],'urn:example:unrelated')
        self.assertEqual(diagnoses['dx-wrong']['kcd_candidate_status'],'not_assigned')
        diagnoses['dx-wrong']['kcd_candidate_code']='I109'
        self.assertEqual(diagnoses['dx-wrong']['original_code'],'59621000')

    def test_0013_L2_new_locked_output_paths_and_symlink_alias_are_rejected(self):
        for target in ('expected_a_prime','answer_key_a_prime'):
            with self.subTest(target=target),self.assertRaises(ValueError):writable_path(ROOT/target/'attempt')
        link=Path(self.temp.name)/'reference';link.symlink_to(ROOT/'expected_a_prime',target_is_directory=True)
        with self.assertRaises(ValueError):writable_path(link/'attempt')
        leaf=Path(self.temp.name)/'projection.jsonl';leaf.symlink_to(ROOT/'answer_key_a_prime/README.md')
        with self.assertRaises(ValueError):a_prime_checks.write_projection(leaf,[])
        self.assertEqual(a_prime_checks.frozen_checker().verify_lock(ROOT/'expected_a_prime')['files'],8)

    def test_0013_D1_failed_input_check_cannot_leave_a_previous_success_report(self):
        a_prime.export_resources(handmade(),self.directory)
        output=Path(self.temp.name)/'actual';output.mkdir()
        (output/'result.json').write_text('{"ok":true,"status":"통과"}')
        with self.assertRaisesRegex(ValueError,'provenance'):
            a_prime_checks.check(self.directory,Path(self.temp.name)/'unused.duckdb',output)
        self.assertFalse(json.loads((output/'result.json').read_text())['ok'])

    def test_0013_L2_initial_lock_failure_invalidates_previous_success(self):
        output=Path(self.temp.name)/'actual';output.mkdir()
        (output/'result.json').write_text('{"ok":true,"status":"통과"}')
        with patch.object(a_prime_checks,'frozen_checker',side_effect=ValueError('injected lock failure')) as checker:
            with self.assertRaisesRegex(ValueError,'injected lock failure'):
                a_prime_checks.check(output=output)
        checker.assert_called_once_with()
        self.assertFalse(json.loads((output/'result.json').read_text())['ok'])

    def test_0013_L2_initial_lock_failure_does_not_truncate_a_hardlink_target(self):
        original=Path(self.temp.name)/'previous.json';original.write_text('{"ok":true}')
        output=Path(self.temp.name)/'actual';output.mkdir()
        (output/'result.json').hardlink_to(original)
        with patch.object(a_prime_checks,'frozen_checker',side_effect=ValueError('injected lock failure')):
            with self.assertRaisesRegex(ValueError,'injected lock failure'):
                a_prime_checks.check(output=output)
        self.assertEqual(json.loads(original.read_text()),{'ok':True})
        self.assertFalse(json.loads((output/'result.json').read_text())['ok'])

    def test_0013_L2_unsafe_initial_failure_paths_do_not_write_before_lock_check(self):
        protected=ROOT/'answer_key_a_prime/README.md';before=protected.read_bytes()
        link=Path(self.temp.name)/'protected';link.symlink_to(protected.parent,target_is_directory=True)
        leaf=Path(self.temp.name)/'leaf';leaf.mkdir()
        (leaf/'result.json').symlink_to(protected)
        outside=ROOT.parent/(Path(self.temp.name).name+'-forbidden-output')
        self.assertFalse(outside.exists())
        for output in (ROOT/'expected_a_prime',link,leaf,outside):
            with self.subTest(output=output),patch.object(a_prime_checks,'frozen_checker') as checker:
                with self.assertRaises(ValueError):a_prime_checks.check(output=output)
                checker.assert_not_called()
        self.assertEqual(protected.read_bytes(),before)
        self.assertTrue((leaf/'result.json').is_symlink())
        self.assertFalse(outside.exists())

    def test_0013_L2_projection_output_replaces_a_hardlink_without_changing_original(self):
        source=Path(self.temp.name)/'shared.txt';source.write_text('original')
        alias=Path(self.temp.name)/'output.jsonl';alias.hardlink_to(source)
        a_prime_checks.write_projection(alias,[])
        self.assertEqual(source.read_text(),'original')
        self.assertEqual(alias.read_text(),'')


class CloneReferenceContract(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.cache/a-prime-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.addCleanup(self.cleanup)
        (self.root/'expected').mkdir()
        (self.root/'expected/sample.csv').write_text('value\n1\n')
        sha=hashlib.sha256((self.root/'expected/sample.csv').read_bytes()).hexdigest()
        (self.root/'expected/SHA256SUMS').write_text(sha+'  sample.csv\n')
        for folder in ('expected_a_prime','answer_key_a_prime'):(self.root/folder).mkdir()
        for relative in a_prime_checks.frozen_checker().LOCK_FILES:
            (self.root/relative).write_bytes((ROOT/relative).read_bytes())
        (self.root/'expected_a_prime/SHA256SUMS').write_bytes((ROOT/'expected_a_prime/SHA256SUMS').read_bytes())
        spec=importlib.util.spec_from_file_location('clone_source_setup',ROOT/'scripts/source_data.py')
        self.helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.helper)

    def cleanup(self):
        for path in [self.root,*self.root.rglob('*')]:
            if path.is_dir():path.chmod(stat.S_IMODE(path.stat().st_mode)|0o700)
        self.temp.cleanup()

    def test_0013_L2_clone_checks_all_frozen_bytes_before_removing_write_bits(self):
        self.helper.prepare_expected(self.root)
        checker=a_prime_checks.frozen_checker()
        self.assertTrue(checker.verify_lock(self.root/'expected_a_prime')['ok'])

    def test_0013_L2_changed_clone_reference_is_rejected_before_new_chmod(self):
        file=self.root/'answer_key_a_prime/README.md';file.write_bytes(b'changed copy')
        mode=file.stat().st_mode
        with self.assertRaisesRegex(ValueError,'SHA256'):
            self.helper.prepare_expected(self.root)
        self.assertEqual(file.stat().st_mode,mode)


class ActualSqlContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache=ROOT/'.cache/a-prime-tests';cache.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=cache);cls.addClassCleanup(cls.temp.cleanup)
        cls.directory=Path(cls.temp.name);cls.database=cls.directory/'fixture.duckdb'
        cls.input=cls.directory/'input'
        a_prime.export_resources(handmade(),cls.input)
        # A candidate-only and unrelated-namespace row must not acquire SNOMED meaning.
        import csv
        file=cls.input/'diagnoses.csv'
        with file.open(newline='') as f:rows=list(csv.DictReader(f))
        for r in rows:
            if r['condition_id'] in ('dx-wrong','dx-candidate'):
                r.update(kcd_candidate_code='I109',kcd_candidate_status='unverified')
        with file.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=a_prime.FIELDS['diagnoses']);writer.writeheader();writer.writerows(rows)
        manifest=json.loads((cls.input/'manifest.json').read_text());body=file.read_bytes()
        manifest['files'][file.name]={'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
        (cls.input/'manifest.json').write_text(json.dumps(manifest))
        a_prime.read_input(cls.input)
        with connect(cls.database) as con:initialize(con)
        env=environment()
        for name in ('tmp','logs','target','duckdb','extensions','xdg'):(cls.directory/name).mkdir()
        env.update(FHIR_DB_PATH=str(cls.database),FHIR_DUCKDB_TEMP=str(cls.directory/'duckdb'),
            FHIR_DUCKDB_EXTENSIONS=str(cls.directory/'extensions'),DBT_LOG_PATH=str(cls.directory/'logs'),
            DBT_TARGET_PATH=str(cls.directory/'target'),TMPDIR=str(cls.directory/'tmp'),XDG_CACHE_HOME=str(cls.directory/'xdg'),
            MIMIC_SOURCE_DIR=str(write_sources(cls.directory/'mimic',{name:[] for name in HEADERS})),
            A_PRIME_SOURCE_DIR=str(cls.input))
        log=ROOT/'.local/FHIR-LINE-A-PRIME/fixture-build.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w') as output:
            # D3/ADR0013: unknown source units deliberately remain concept 0 in this fixture.
            result=subprocess.run([str(ROOT/'.venv/bin/dbt'),'--no-use-colors','build','--no-partial-parse',
                '--exclude','t_0008_D3_dqd_unit_completeness'],
                cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode:raise RuntimeError('A-prime fixture build failed; see local fixture-build.log')

    def query(self,sql):
        with connect(self.database,read_only=True) as con:return con.execute(sql).fetchall()

    def test_0015_D3_D6_two_reviewed_aprime_cases(self):
        cases=wp5_cases('A_PRIME_fixture');self.assertEqual(len(cases),2)
        for case in cases:
            with self.subTest(case=case['id']),connect(self.database,read_only=True) as con:
                row=con.execute('''SELECT cast(last_bp_date as varchar),systolic,diastolic,controlled,reason
                    FROM fct_bp_person WHERE hospital=? AND person_id=? AND as_of_label=?''',
                    [case['hospital'],case['person'],case['as_of_label']]).fetchall()
                self.assertEqual(row,[person_values(case)])

    def test_0013_D2_candidate_only_and_wrong_system_never_map_to_hypertension(self):
        self.assertEqual(self.query('SELECT source_person_id,concept_id FROM omop_diagnoses ORDER BY 1'),
                         [('candidate',0),('good',320128),('wrong',0),('wrong-visit',320128)])
        self.assertEqual(self.query('SELECT condition_source_value FROM condition_occurrence'),[('59621000',),('59621000',)])

    def test_0013_D1_D3_actual_input_and_staging_projection_agree(self):
        want={r['kind']+':'+r['source_row_key']:r['facts'] for r in a_prime.projection(a_prime.read_input(self.input))}
        with connect(self.database,read_only=True) as con:
            actual={r['kind']+':'+r['source_row_key']:r['facts'] for r in a_prime_checks.staging_projection(con)}
        self.assertEqual(actual,want)
        self.assertEqual(actual['bp_component:fraction:8480-6']['value'],'109.51')
        self.assertEqual(actual['bp_component:fraction:8462-4']['value'],'76.761')

    def test_0013_D3_unmapped_panel_component_units_remain_with_zero_meaning(self):
        self.assertEqual(self.query("""SELECT source_row_key,concept_id,unit_concept_id FROM omop_event_rows
             WHERE source_row_key IN ('other-panel:8480-6','other-component:8480-6','other-unit:8480-6') ORDER BY 1"""),
            [('other-component:8480-6',0,8876),('other-panel:8480-6',0,8876),('other-unit:8480-6',3004249,0)])

    def test_0013_D1_D4_D5_D6_original_days_minima_and_last_measurement(self):
        self.assertEqual(self.query("""SELECT as_of_label,person_id,cast(last_bp_date as varchar),systolic,diastolic,controlled
             FROM fct_bp_person ORDER BY as_of_label DESC"""),
             [('sep30','good','2025-09-30',109.51,76.761,1),('dec31','good','2025-12-01',124.0,92.0,0)])
        self.assertEqual(self.query("SELECT count(*) FROM int_bp_daily WHERE bp_date='2025-12-30'"),[(0,)])
        self.assertEqual(self.query("SELECT distinct systolic_min,diastolic_min FROM int_bp_daily WHERE bp_date='2025-08-20'"),[(121.0,None)])
        self.assertEqual(self.query('SELECT as_of_label,numerator,denominator FROM bp_summary ORDER BY 1 DESC'),
                         [('sep30',1,1),('dec31',0,1)])

    def test_0013_D3_staging_value_mutation_is_rejected_by_actual_extractor(self):
        with connect(self.database) as con:
            con.execute('BEGIN')
            try:
                con.execute("UPDATE stg_aprime_bp_value SET parsed_value_text='110' WHERE source_row_key='fraction:8480-6'")
                with self.assertRaisesRegex(ValueError,'lost original'):
                    list(a_prime_checks.staging_projection(con))
            finally:con.execute('ROLLBACK')

    def test_0013_D1_actual_fact_extraction_reads_sql_and_original_namespace(self):
        fields=a_prime_checks.frozen_checker().CONTRACTS['omop_facts.csv']['fields']
        with connect(self.database,read_only=True) as con:rows=a_prime_checks.actual_facts(con,fields)
        keyed={(r['omop_table'],r['source_row_key']):r for r in rows}
        self.assertEqual(keyed['measurement','fraction:8480-6']['value_as_number'],'109.510')
        self.assertEqual(keyed['condition_occurrence','dx-good']['reference_system'],a_prime.SNOMED)
        self.assertNotIn(('condition_occurrence','dx-wrong'),keyed)


if __name__=='__main__':unittest.main()
