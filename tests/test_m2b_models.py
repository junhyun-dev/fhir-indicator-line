"""D1-D6/M2B: handmade B CSVs through unchanged L4-L6 in one isolated dbt build."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from fhir_line.runtime import ROOT, connect, environment
from fhir_line.store import initialize
from mimic_fixture import HEADERS, write_sources


def cases():
    rows = {name:[] for name in HEADERS}

    def admission(person, hadm, start, end, ed=''):
        rows['hosp/admissions'].append(dict(subject_id=person,hadm_id=hadm,
            admittime=start+' 12:00:00',dischtime=end+' 12:00:00',
            edregtime=ed+' 23:00:00' if ed else ''))

    def patient(person, year=2111, code='I10', version='10', onset=None):
        rows['hosp/patients'].append(dict(subject_id=person,anchor_year=year,anchor_age=50))
        start=onset or str(year-1)+'-01-01'
        hadm=person+'-diagnosis'
        admission(person,hadm,start,start)
        rows['hosp/diagnoses_icd'].append(dict(subject_id=person,hadm_id=hadm,
            seq_num=1,icd_code=code,icd_version=version))

    def omr(person, day, value='113/44', name='Blood Pressure', sequence=1):
        rows['hosp/omr'].append(dict(subject_id=person,chartdate=day,seq_num=sequence,
            result_name=name,result_value=value))

    patient('split')
    omr('split','2111-02-01')
    patient('overlap')
    admission('overlap','overlap-stay','2111-05-04','2111-05-06',ed='2111-05-03')
    for day in ('2111-05-03','2111-05-05','2111-05-06'):
        omr('overlap',day)
    patient('height_only')
    omr('height_only','2111-02-01','170','Height')
    omr('height_only','2111-03-01','120/80','Blood Pressure Sitting')
    patient('late',onset='2111-07-01')
    omr('late','2111-08-01')
    for code in ('4010','4011','4019'):
        person='code_'+code
        patient(person,code=code,version='9',onset='2111-06-30')
        omr(person,'2111-08-01')
    patient('wrong_version',code='I10',version='9')
    omr('wrong_version','2111-02-01')
    patient('other_year',year=2196)
    omr('other_year','2196-02-01')
    omr('other_year','2197-01-01','190/110')
    patient('icu',code='4019',version='9')
    omr('icu','2111-05-01')
    admission('icu','icu-stay','2111-08-10','2111-08-12',ed='2111-08-09')
    for item,value in (('220179',200),('220180',120)):
        rows['icu/chartevents'].append(dict(subject_id='icu',hadm_id='icu-stay',stay_id='stay',
            itemid=item,charttime='2111-08-11 12:00:00',storetime='2112-01-01 12:00:00',
            value=str(value),valuenum=value,valueuom='mmHg'))
    patient('boundary')
    omr('boundary','2111-06-06','139/60')
    omr('boundary','2111-11-23','140/60')
    return rows


class HospitalBModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache=ROOT/'.cache/FHIR-LINE-05'
        cache.mkdir(parents=True,exist_ok=True)
        cls.scratch=tempfile.TemporaryDirectory(prefix='models-b-',dir=cache)
        cls.addClassCleanup(cls.scratch.cleanup)
        folder=Path(cls.scratch.name)
        cls.database=folder/'fixture.duckdb'
        source=write_sources(folder/'mimic',cases())
        with connect(cls.database) as con:
            initialize(con)
        env=environment()
        for label in ('tmp','logs','target','duckdb','extensions','xdg'):
            (folder/label).mkdir()
        env.update(FHIR_DB_PATH=str(cls.database),FHIR_DUCKDB_TEMP=str(folder/'duckdb'),
            FHIR_DUCKDB_EXTENSIONS=str(folder/'extensions'),DBT_LOG_PATH=str(folder/'logs'),
            DBT_TARGET_PATH=str(folder/'target'),TMPDIR=str(folder/'tmp'),XDG_CACHE_HOME=str(folder/'xdg'),
            MIMIC_SOURCE_DIR=str(source))
        log=ROOT/'.local/FHIR-LINE-05/logs/fixture-b-dbt-build.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w') as output:
            result=subprocess.run([str(ROOT/'.venv/bin/dbt'),'--no-use-colors','build','--no-partial-parse'],
                cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=120)
        if result.returncode:
            raise RuntimeError('B fixture dbt build failed; see '+str(log))

    def query(self, sql, parameters=()):
        with connect(self.database,read_only=True) as con:
            return con.execute(sql,parameters).fetchall()

    def person(self, person, label='dec31'):
        rows=self.query("""SELECT cast(as_of as varchar),cast(last_bp_date as varchar),systolic,
            diastolic,controlled,reason FROM fct_bp_person
            WHERE hospital='B' AND person_id=? AND as_of_label=?""",[person,label])
        self.assertEqual(len(rows),1,person)
        return rows[0]

    def test_M2B_D3_D5_D6_split_pair_and_empty_unit_mapping(self):
        self.assertEqual(self.person('split'),('2111-12-31','2111-02-01',113,44,1,'조절됨'))
        self.assertEqual(self.query("""SELECT source_code,source_unit IS NOT NULL,length(source_unit)
            FROM code_map WHERE hospital='B' AND source_code LIKE 'omr_%' ORDER BY source_code"""),
            [('omr_diastolic',True,0),('omr_systolic',True,0)])
        self.assertEqual(self.query("""SELECT concept,value FROM bp_value
            WHERE hospital='B' AND person_id='split' ORDER BY concept"""),[('diastolic',44),('systolic',113)])

    def test_M2B_D2_D3_outpatient_days_exclude_admission_and_include_other_results(self):
        self.assertEqual(self.query("SELECT count(*) FROM fct_bp_person WHERE hospital='B' AND person_id='overlap'"),[(0,)])
        self.assertEqual(self.query("SELECT count(*) FROM visit WHERE hospital='B' AND person_id='overlap' AND visit_type='outpatient'"),[(0,)])
        self.assertEqual(self.person('height_only'),('2111-12-31',None,None,None,0,'혈압 없음'))

    def test_M2B_D2_onset_cutoff_and_versioned_diagnosis_codes(self):
        for person in ('late','wrong_version'):
            with self.subTest(person=person):
                self.assertEqual(self.query("SELECT count(*) FROM fct_bp_person WHERE hospital='B' AND person_id=?",[person]),[(0,)])
        for code in ('4010','4011','4019'):
            with self.subTest(code=code):
                self.assertEqual(self.person('code_'+code)[4],1)

    def test_M2B_D1_D2_person_calendars_keep_different_years(self):
        self.assertEqual(self.person('split','sep30')[0],'2111-09-30')
        self.assertEqual(self.person('other_year','sep30')[0],'2196-09-30')
        self.assertEqual(self.person('other_year')[:5],('2196-12-31','2196-02-01',113,44,1))
        self.assertEqual(self.query("SELECT DISTINCT hospital FROM fct_bp_person"),[('B',)])

    def test_M2B_D1_D3_D5_icu_values_are_inpatient_and_chart_day_is_visible(self):
        self.assertEqual(self.query("""SELECT count(*),min(cast(record_day as varchar)),min(std_unit)
            FROM bp_value WHERE hospital='B' AND person_id='icu' AND source_code IN ('220179','220180')"""),
            [(2,'2111-08-11','mm[Hg]')])
        self.assertEqual(self.query("""SELECT cast(bp_date as varchar) FROM int_bp_daily
            WHERE hospital='B' AND person_id='icu' AND as_of_label='dec31'"""),[('2111-05-01',)])
        self.assertEqual(self.person('icu')[1:5],('2111-05-01',113,44,1))

    def test_M2B_D6_exact_140_60_changes_control_at_last_day(self):
        self.assertEqual(self.person('boundary','sep30')[4],1)
        self.assertEqual(self.person('boundary')[1:],('2111-11-23',140,60,0,'수축기 140 이상'))


if __name__=='__main__':
    unittest.main()
