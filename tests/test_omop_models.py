"""D1-D3 / decisions 0004-0011: handmade sources through actual OMOP SQL, without expected/.

The shared build covers normal inputs; the legacy M1 fixture owns the deliberate late-record failure.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from fhir_line import omop
from fhir_line.runtime import ROOT, connect, environment
from fhir_line.store import append_rows, initialize
from mimic_fixture import HEADERS, write_sources
from test_m1_models import Fixture, coding, identifier, timestamp
from wp5_expected import cases as wp5_cases, person_values


def fhir_rows(resources):
    rows = []
    for resource in resources:
        payload = json.dumps(resource,ensure_ascii=False,separators=(',',':'))
        rows.append((1,resource['resourceType'],resource['id'],'urn:uuid:'+resource['id'],payload,
                     hashlib.sha256(payload.encode()).hexdigest(),'handmade-omop.json',
                     dt.datetime(2026,1,1,tzinfo=dt.timezone.utc)))
    return rows


def sources():
    f = Fixture()
    f.patient('omop-a')
    f.patient('omop-unmapped',code='unmapped',onset='1900-01-01',recorded='1900-01-01')
    # An earlier unmapped diagnosis must not extend the carried observation period.
    f.add('Condition','omop-unknown',subject=f.subject('omop-a'),code=coding('unmapped'),
          onsetDateTime=timestamp('1900-01-01'),recordedDate=timestamp('1900-01-01'))
    f.encounter('omop-a','omop-hh','HH','2025-05-01','2026-02-03')
    f.encounter('omop-a','omop-open','EMER','2025-02-01')
    f.bp('omop-a','omop-pair','2025-09-13',145,75)
    f.bp('omop-a','omop-unit','2025-10-01',120,80,systolic_unit='kPa',diastolic_unit='kPa')
    for resource in f.resources:
        if resource['resourceType']=='Patient' and resource['id']==identifier('Patient','omop-a'):
            resource['gender']='female'

    b = {name:[] for name in HEADERS}
    b['hosp/patients'] = [dict(subject_id='omop-b',gender='M',anchor_year=2111,anchor_age=78)]
    b['hosp/admissions'] = [
        dict(subject_id='omop-b',hadm_id='b-first',admittime='2110-01-01 12:00:00',dischtime='2110-01-03 12:00:00'),
        dict(subject_id='omop-b',hadm_id='b-next',admittime='2111-05-02 12:00:00',
             edregtime='2111-05-01 12:00:00',dischtime='2112-02-03 12:00:00')]
    b['hosp/diagnoses_icd'] = [
        dict(subject_id='omop-b',hadm_id=hadm,seq_num=1,icd_version='10',icd_code='I10')
        for hadm in ['b-first','b-next']]
    b['hosp/diagnoses_icd'] += [
        dict(subject_id='omop-b',hadm_id='b-first',seq_num=2,icd_version='10',icd_code='unmapped'),
        dict(subject_id='omop-b',hadm_id='b-first',seq_num=3,icd_version='9',icd_code='I10')]
    b['hosp/omr'] = [dict(subject_id='omop-b',chartdate='2111-11-23',seq_num=1,
                          result_name='Blood Pressure',result_value='140/60')]
    b['icu/chartevents'] = [dict(subject_id='omop-b',hadm_id='b-next',stay_id='stay',
        charttime='2111-06-10 12:00:00',storetime='2112-01-01 12:00:00',
        itemid='220179',value='142.00',valuenum='142',valueuom='mmHg')]
    return f.resources,b


class OmopModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache = ROOT/'.cache/FHIR-LINE-06'
        cache.mkdir(parents=True,exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(prefix='models-omop-',dir=cache)
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.folder = Path(cls.scratch.name)
        cls.database = cls.folder/'fixture.duckdb'
        resources,b = sources()
        with connect(cls.database) as con:
            initialize(con)
            append_rows(con,fhir_rows(resources))
        env = environment()
        for label in ['tmp','logs','target','duckdb','extensions','xdg']:
            (cls.folder/label).mkdir()
        env.update(FHIR_DB_PATH=str(cls.database),FHIR_DUCKDB_TEMP=str(cls.folder/'duckdb'),
                   FHIR_DUCKDB_EXTENSIONS=str(cls.folder/'extensions'),DBT_LOG_PATH=str(cls.folder/'logs'),
                   DBT_TARGET_PATH=str(cls.folder/'target'),TMPDIR=str(cls.folder/'tmp'),
                   XDG_CACHE_HOME=str(cls.folder/'xdg'),MIMIC_SOURCE_DIR=str(write_sources(cls.folder/'mimic',b)))
        cls.fixture_environment = env
        cls.build('fixture-omop-build.log')

    @classmethod
    def build(cls, name, command=None):
        log = ROOT/'.local/FHIR-LINE-06/logs'/name
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w') as output:
            # D3/ADR0009: this fixture deliberately retains unknown kPa as concept 0.
            # The quality mutation suite and the real-data build still run this gate.
            result = subprocess.run([str(ROOT/'.venv/bin/dbt'),'--no-use-colors',
                *(command or ['build','--no-partial-parse','--exclude','t_0008_D3_dqd_unit_completeness'])],cwd=ROOT,env=cls.fixture_environment,
                stdout=output,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode:
            raise RuntimeError('OMOP fixture dbt command failed; see '+str(log))

    def query(self, sql, parameters=()):
        with connect(self.database,read_only=True) as con:
            return con.execute(sql,parameters).fetchall()

    def test_0015_D3_D6_reviewed_omop_case(self):
        cases=wp5_cases('OMOP_fixture');self.assertEqual(len(cases),1)
        for case in cases:
            actual=self.query('''SELECT cast(last_bp_date as varchar),systolic,diastolic,controlled,reason
                FROM fct_bp_person WHERE hospital=? AND person_id=? AND as_of_label=?''',
                [case['hospital'],identifier('Patient',case['person']),case['as_of_label']])
            self.assertEqual(actual,[person_values(case)])

    def test_0004_D1_official_shape_and_required_values(self):
        with connect(self.database,read_only=True) as con:
            result = omop.check_shape(con)
        self.assertEqual(result['status'],'통과',result['detail'])

    def test_0005_D2_demographics_unknown_gender_and_measurement_year(self):
        self.assertEqual(self.query("""SELECT p.gender_concept_id,p.year_of_birth,e.measurement_year
            FROM person p JOIN person_ext e USING (person_id) WHERE e.hospital='B'"""),[(8507,2033,2111)])
        self.assertEqual(self.query('SELECT gender_concept_id,gender_source_value FROM person WHERE person_source_value=?',
            [identifier('Patient','omop-unmapped')]),[(0,None)])

    def test_0007_D2_person_ids_survive_rebuild_and_an_added_person(self):
        before = self.query('SELECT person_source_value,person_id FROM person ORDER BY person_source_value')
        addition = Fixture()
        addition.patient('omop-new-person')
        with connect(self.database) as con:
            append_rows(con,fhir_rows(addition.resources))
        # Rebuild the real demographics models after the input grows; do not restate the hash in Python.
        self.build('fixture-omop-person-rebuild.log',
                   ['run','--no-partial-parse','--select','omop_people','person','person_ext'])
        after = dict(self.query('SELECT person_source_value,person_id FROM person'))
        self.assertEqual(len(after),len(before)+1)
        for original,stable_id in before:
            self.assertEqual(after[original],stable_id)

    def test_0008_D3_panel_is_two_rows_with_each_original_component(self):
        prefix = identifier('Observation','omop-pair')
        rows = self.query("""SELECT m.measurement_source_value,m.measurement_concept_id,
            m.value_as_number,m.unit_concept_id,l.source_row_key FROM measurement m
            JOIN omop_source_link l ON l.omop_table='measurement' AND l.omop_id=m.measurement_id
            WHERE l.hospital='A' AND l.source_row_key IN (?,?) ORDER BY m.measurement_source_value""",
            [prefix+':8462-4',prefix+':8480-6'])
        self.assertEqual(rows,[('8462-4',3012888,75,8876,prefix+':8462-4'),
                               ('8480-6',3004249,145,8876,prefix+':8480-6')])

    def test_0008_D3_omr_pair_and_icu_preserve_original_value_text(self):
        rows = self.query("""SELECT measurement_source_value,value_as_number,unit_source_value,
            value_source_value,unit_concept_id FROM measurement m JOIN person_ext e USING (person_id)
            WHERE e.hospital='B' ORDER BY measurement_source_value""")
        self.assertEqual(rows,[('220179',142,'mmHg','142.00',8876),
                               ('omr_diastolic',60,None,'140/60',8876),
                               ('omr_systolic',140,None,'140/60',8876)])

    def test_0009_D2_unmapped_diagnoses_are_counted_and_admissions_are_not_collapsed(self):
        self.assertEqual(self.query("""SELECT hospital,carried,not_carried FROM omop_load_counts
            WHERE omop_table='condition_occurrence' ORDER BY hospital"""),[('A',1,2),('B',2,2)])
        self.assertEqual(self.query("""SELECT cast(condition_start_date as varchar),condition_source_value
            FROM condition_occurrence JOIN person_ext USING(person_id)
            WHERE hospital='B' ORDER BY condition_start_date"""),[('2110-01-01','I10'),('2111-05-02','I10')])

    def test_0009_D3_unknown_units_and_HH_visits_remain_with_zero_concepts(self):
        self.assertEqual(self.query("""SELECT count(*),min(unit_concept_id),max(unit_concept_id)
            FROM measurement WHERE unit_source_value='kPa'"""),[(2,0,0)])
        self.assertEqual(self.query("""SELECT visit_concept_id FROM visit_occurrence
            WHERE visit_source_value='HH'"""),[(0,)])
        self.assertEqual(self.query("""SELECT visit_concept_id FROM visit_occurrence
            WHERE visit_source_value='ed_admission'"""),[(262,)])

    def test_0011_D1_observation_period_uses_carried_dates_and_event_ends(self):
        rows = self.query("""SELECT cast(observation_period_start_date as varchar),
            cast(observation_period_end_date as varchar),observation_period_id=person_id
            FROM observation_period JOIN person p USING(person_id) WHERE p.person_source_value=?""",
            [identifier('Patient','omop-a')])
        self.assertEqual(rows,[('2020-01-01','2026-02-03',True)])
        self.assertEqual(self.query("""SELECT cast(visit_start_date as varchar),cast(visit_end_date as varchar)
            FROM visit_occurrence WHERE visit_source_value='EMER'"""),[('2025-02-01','2025-02-01')])
        self.assertEqual(self.query("""SELECT end_day FROM stg_a_visit WHERE source_code='EMER'"""),[(None,)])

    def test_0011_D1_every_event_has_one_original_source_key(self):
        with connect(self.database,read_only=True) as con:
            result = omop.check_links(con)
        self.assertEqual(result['status'],'통과',result['detail'])
        self.assertEqual(self.query("""SELECT source_row_key FROM omop_source_link
            WHERE omop_table='condition_occurrence' AND hospital='B' ORDER BY source_row_key"""),
            [('omop-b:b-first:1:10:I10',),('omop-b:b-next:1:10:I10',)])


if __name__=='__main__':
    unittest.main()
