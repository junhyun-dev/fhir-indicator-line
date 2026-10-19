"""D1-D7/M2 / t01-t15: handmade FHIR through the actual SQL, in one isolated build.

No original/expected inputs are used here. Expected outcomes are specified per case.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from fhir_line.runtime import ROOT, connect, environment
from fhir_line.store import append_rows, initialize
from mimic_fixture import write_sources

SEPTEMBER = '2025-09-30'
DECEMBER = '2025-12-31'
PERIOD_LABELS = {SEPTEMBER:'sep30', DECEMBER:'dec31'}


def identifier(kind, label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'fhir-line-fixture:'+kind+':'+label))


def timestamp(day):
    return day+'T12:00:00+00:00' if len(day)==10 else day


def coding(code):
    # D2/D3 explicitly compare code only, including when system differs.
    return {'coding':[{'system':'urn:fixture-code-system','code':code}]}


class Fixture:
    def __init__(self):
        self.resources = []

    def add(self, kind, label, **fields):
        resource = {'resourceType':kind,'id':identifier(kind,label),**fields}
        self.resources.append(resource)

    def subject(self, person):
        return {'reference':'urn:uuid:'+identifier('Patient',person)}

    def patient(self, label, birth='1970-12-31', onset='2020-01-01',
                recorded='2020-01-01', abatement=None, visit='2025-01-15', code='59621000'):
        self.add('Patient',label,birthDate=birth)
        diagnosis = {'subject':self.subject(label),'code':coding(code),'onsetDateTime':timestamp(onset)}
        if recorded is not None:
            diagnosis['recordedDate'] = timestamp(recorded)
        if abatement is not None:
            diagnosis['abatementDateTime'] = timestamp(abatement)
        self.add('Condition',label,**diagnosis)
        if visit:
            self.encounter(label,label+'-amb','AMB',visit,visit)

    def encounter(self, person, label, class_code, start, end=None):
        period = {'start':timestamp(start)}
        if end is not None:
            period['end'] = timestamp(end)
        self.add('Encounter',label,subject=self.subject(person),**{'class':{'code':class_code}},period=period)

    def bp(self, person, label, day, systolic=104, diastolic=81,
           systolic_unit='mm[Hg]', diastolic_unit='mm[Hg]', unit_label='mm[Hg]', missing_numbers=False):
        components = []
        # D3/t13: diastolic deliberately appears first, as in the original shape.
        for code,value,unit in (('8462-4',diastolic,diastolic_unit),('8480-6',systolic,systolic_unit)):
            if value is None and not missing_numbers:
                continue
            quantity = {'system':'http://unitsofmeasure.org','code':unit,'unit':unit_label}
            if not missing_numbers:
                quantity['value'] = value
            components.append({'code':coding(code),'valueQuantity':quantity})
        self.add('Observation',label,subject=self.subject(person),code=coding('85354-9'),
                 effectiveDateTime=timestamp(day),component=components)


def cases():
    f = Fixture()
    for label in ('t01','t02','t03','t04','t04-dia','t05','t06','t07-imp','t07-emer',
                  't07-year','t08-unit','t08-both','t08-label','t08-missing','t09','t13','t14','t15'):
        f.patient(label)
    f.bp('t01','t01-bp','2025-02-01')
    f.bp('t02','t02-bp','2025-02-01',140,81)
    f.bp('t03','t03-bp','2025-02-01',104,90)
    f.bp('t04','t04-old','2025-02-01')
    f.bp('t04','t04-last','2025-08-01',150,None)
    f.bp('t04-dia','t04-dia-bp','2025-08-01',None,75)
    f.bp('t05','t05-first','2025-02-01',160,100)
    f.bp('t05','t05-second','2025-02-01',150,70)
    f.bp('t06','t06-before','2024-12-31')
    f.bp('t06','t06-after','2026-01-01')
    f.encounter('t07-imp','t07-admission','IMP','2025-01-10','2025-01-12')
    for day in ('2025-01-10','2025-01-11','2025-01-12'):
        f.bp('t07-imp','imp-'+day,day,180,110)
    f.bp('t07-imp','imp-before','2025-01-09')
    f.bp('t07-imp','imp-after','2025-01-13',130,81)
    f.encounter('t07-emer','t07-emergency','EMER','2025-01-20')
    f.bp('t07-emer','emer-before','2025-01-19')
    f.bp('t07-emer','emer-at','2025-01-20',180,110)
    f.bp('t07-emer','emer-after','2025-01-21',120,80)
    # Same day as t01: another person's emergency must not exclude t01's BP.
    f.encounter('t07-emer','t07-other-person','EMER','2025-02-01')
    f.encounter('t07-year','t07-year-admission','IMP','2024-12-31','2025-01-02')
    f.bp('t07-year','year-at-start','2025-01-01',180,110)
    f.bp('t07-year','year-at-end','2025-01-02',180,110)
    f.bp('t07-year','year-after','2025-01-03',118,78)
    f.bp('t08-unit','unit-wrong-code','2025-08-01',104,81,systolic_unit='kPa')
    for label in ('t08-both','t08-missing'):
        f.bp(label,label+'-old','2025-02-01')
    f.bp('t08-both','unit-both-bad','2025-08-01',systolic_unit='kPa',diastolic_unit='kPa')
    f.bp('t08-missing','unit-missing-values','2025-08-02',missing_numbers=True)
    f.bp('t08-label','unit-display-only','2025-08-01',unit_label='display is not the code')
    f.bp('t09','t09-bp','2025-02-01')
    f.encounter('t09','t09-second-amb','AMB','2025-03-15','2025-03-15')
    for label,options in (
        ('t10-july',{'onset':'2025-07-01','recorded':'2025-07-01'}),
        ('t10-cutoff',{'onset':'2025-06-30','recorded':'2025-06-30'}),
        ('t10-recorded',{'recorded':'2025-10-01'}),
        ('t10-code',{'code':'not-hypertension'}),
        ('t10-abated',{'abatement':'2024-12-31'}),
        ('t10-boundary',{'abatement':'2025-01-01'}),
        ('t10-fallback',{'recorded':None}),
        ('t11-17',{'birth':'2008-01-01'}),
        ('t11-86',{'birth':'1939-01-01'}),
        ('t11-18',{'birth':'2007-12-31'}),
        ('t11-85',{'birth':'1940-12-31'}),
        ('t12-none',{'visit':None}),
        ('t12-future',{'visit':'2025-10-31'}),
    ):
        f.patient(label,**options)
        f.bp(label,label+'-bp','2025-02-01')
    f.encounter('t12-none','t12-last-year','AMB','2024-12-31','2024-12-31')
    f.encounter('t12-none','t12-next-year','AMB','2026-01-01','2026-01-01')
    f.bp('t13','t13-reversed','2025-09-13',145,75)
    f.bp('t14','t14-september','2025-09-30T23:59:00-09:00')
    f.bp('t14','t14-december','2025-12-31T22:34:00+00:00',128,82)
    f.bp('t15','t15-first','2025-02-01',160,80)
    f.bp('t15','t15-second','2025-02-01',120,90)
    return f.resources


class IndicatorModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache = ROOT/'.cache/FHIR-LINE-05'
        cache.mkdir(parents=True,exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(prefix='models-',dir=cache)
        cls.addClassCleanup(cls.scratch.cleanup)
        folder = Path(cls.scratch.name)
        cls.database = folder/'fixture.duckdb'
        resources = cases()
        received = dt.datetime(2026,1,1,tzinfo=dt.timezone.utc)
        rows = []
        for r in resources:
            payload = json.dumps(r,ensure_ascii=False,separators=(',',':'))
            rows.append((1,r['resourceType'],r['id'],'urn:uuid:'+r['id'],payload,
                         hashlib.sha256(payload.encode()).hexdigest(),'handmade-fixture.json',received))
        with connect(cls.database) as con:
            initialize(con)
            append_rows(con,rows)
        env = environment()
        for label in ('tmp','logs','target','duckdb','extensions','xdg'):
            (folder/label).mkdir()
        env.update(FHIR_DB_PATH=str(cls.database),FHIR_DUCKDB_TEMP=str(folder/'duckdb'),
                   FHIR_DUCKDB_EXTENSIONS=str(folder/'extensions'),DBT_LOG_PATH=str(folder/'logs'),
                   DBT_TARGET_PATH=str(folder/'target'),TMPDIR=str(folder/'tmp'),XDG_CACHE_HOME=str(folder/'xdg'),
                   MIMIC_SOURCE_DIR=str(write_sources(folder/'empty-mimic')))
        log = ROOT/'.local/FHIR-LINE-05/logs/fixture-a-dbt-build.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w') as out:
            result = subprocess.run([str(ROOT/'.venv/bin/dbt'),'--no-use-colors','build','--no-partial-parse'],
                                    cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=90)
        if result.returncode:
            raise RuntimeError('Fixture dbt build failed; see '+str(log))

    def query(self, sql, parameters=()):
        with connect(self.database,read_only=True) as con:
            return con.execute(sql,parameters).fetchall()

    def person(self, label, as_of=DECEMBER):
        rows = self.query('''SELECT last_bp_date,systolic,diastolic,controlled,reason
            FROM fct_bp_person WHERE hospital='A' AND person_id=? AND as_of_label=?''',
            [identifier('Patient',label),PERIOD_LABELS[as_of]])
        self.assertEqual(len(rows),1,label)
        day,*values = rows[0]
        return (day.isoformat() if day else None,*values)

    def assert_absent(self, label, as_of=DECEMBER):
        self.assertEqual(self.query("SELECT count(*) FROM fct_bp_person WHERE hospital='A' AND person_id=? AND as_of_label=?",
                                   [identifier('Patient',label),PERIOD_LABELS[as_of]])[0][0],0,label)

    def daily(self, label):
        return [(day.isoformat(),s,d) for day,s,d in self.query('''SELECT bp_date,systolic_min,diastolic_min
            FROM int_bp_daily WHERE hospital='A' AND person_id=? AND as_of_label=? ORDER BY bp_date''',
            [identifier('Patient',label),'dec31'])]

    def test_t01_D2_D5_D6_normal_connection(self):
        self.assertEqual(self.person('t01'),('2025-02-01',104,81,1,'조절됨'))
        self.assertEqual(self.query("SELECT count(*),sum(controlled) FROM fct_bp_person WHERE hospital='A' AND person_id=? AND as_of_label=?",
                                   [identifier('Patient','t01'),'dec31']),[(1,1)])
        summaries = {label:(d,n,r) for label,d,n,r in self.query(
            "SELECT as_of_label,denominator,numerator,rate FROM bp_summary WHERE hospital='A'")}
        self.assertEqual(summaries,{'sep30':(23,15,0.6522),'dec31':(25,17,0.68)})

    def test_t02_D6_systolic_140_not_controlled(self):
        self.assertEqual(self.person('t02'),('2025-02-01',140,81,0,'수축기 140 이상'))

    def test_t03_D6_diastolic_90_not_controlled(self):
        self.assertEqual(self.person('t03'),('2025-02-01',104,90,0,'이완기 90 이상'))

    def test_t04_D5_D6_last_partial_overrides_older_pair_and_threshold(self):
        self.assertEqual(self.person('t04'),('2025-08-01',150,None,0,'마지막 날에 한쪽 값만'))
        self.assertEqual(self.person('t04-dia'),('2025-08-01',None,75,0,'마지막 날에 한쪽 값만'))

    def test_t05_D4_daily_minima_are_independent(self):
        self.assertEqual(self.daily('t05'),[('2025-02-01',150,70)])

    def test_t06_D1_D6_no_in_period_bp_stays_in_denominator(self):
        self.assertEqual(self.daily('t06'),[])
        self.assertEqual(self.person('t06'),(None,None,None,0,'혈압 없음'))

    def test_t07_D3_admission_emergency_boundaries_and_missing_end(self):
        self.assertEqual(self.daily('t07-imp'),[('2025-01-09',104,81),('2025-01-13',130,81)])
        self.assertEqual(self.daily('t07-emer'),[('2025-01-19',104,81),('2025-01-21',120,80)])
        self.assertEqual(self.daily('t07-year'),[('2025-01-03',118,78)])

    def test_t08_D3_unit_code_and_no_usable_component_day(self):
        self.assertEqual(self.person('t08-unit'),('2025-08-01',None,81,0,'마지막 날에 한쪽 값만'))
        for label in ('t08-both','t08-missing'):
            with self.subTest(label=label):
                self.assertEqual(self.daily(label),[('2025-02-01',104,81)])
                self.assertEqual(self.person(label),('2025-02-01',104,81,1,'조절됨'))
        self.assertEqual(self.person('t08-label'),('2025-08-01',104,81,1,'조절됨'))

    def test_t09_D2_multiple_ambulatory_visits_keep_one_person(self):
        self.assertEqual(self.person('t09'),('2025-02-01',104,81,1,'조절됨'))

    def test_t10_D1_D2_onset_abatement_code_and_record_visibility(self):
        for label in ('t10-july','t10-code','t10-abated'):
            with self.subTest(label=label):
                self.assert_absent(label)
        for label in ('t10-cutoff','t10-boundary','t10-fallback'):
            with self.subTest(label=label):
                self.assertEqual(self.person(label),('2025-02-01',104,81,1,'조절됨'))
        self.assert_absent('t10-recorded',SEPTEMBER)
        self.assertEqual(self.person('t10-recorded'),('2025-02-01',104,81,1,'조절됨'))

    def test_t11_D2_year_end_age_limits(self):
        for label in ('t11-17','t11-86'):
            with self.subTest(label=label):
                self.assert_absent(label)
        for label in ('t11-18','t11-85'):
            with self.subTest(label=label):
                self.assertEqual(self.person(label,SEPTEMBER)[3],1)

    def test_t12_D1_D2_no_ambulatory_visit_and_future_visit(self):
        self.assert_absent('t12-none')
        self.assert_absent('t12-future',SEPTEMBER)
        self.assertEqual(self.person('t12-future'),('2025-02-01',104,81,1,'조절됨'))

    def test_t13_D3_reversed_components_remain_paired_with_codes(self):
        rows = self.query("SELECT source_code,concept,value FROM bp_value WHERE hospital='A' AND observation_id=? ORDER BY source_code",
                          [identifier('Observation','t13-reversed')])
        self.assertEqual(rows,[('8462-4','diastolic',75),('8480-6','systolic',145)])
        self.assertEqual(self.person('t13'),('2025-09-13',145,75,0,'수축기 140 이상'))

    def test_t14_D1_written_day_without_timezone_shift(self):
        self.assertEqual(self.person('t14',SEPTEMBER),('2025-09-30',104,81,1,'조절됨'))
        self.assertEqual(self.person('t14'),('2025-12-31',128,82,1,'조절됨'))

    def test_t15_D4_minima_from_different_measurements_controlled(self):
        self.assertEqual(self.daily('t15'),[('2025-02-01',120,80)])
        self.assertEqual(self.person('t15')[3],1)

    def test_t12_D2_D6_empty_denominator_keeps_date_and_null_rate(self):
        # Only the isolated fixture seed is changed inside a rolled-back transaction.
        # Views then exercise the same SQL for an earlier cutoff with no eligible visit.
        with connect(self.database) as con:
            con.execute('BEGIN')
            try:
                con.execute("UPDATE as_of_labels SET month=1,day=1 WHERE as_of_label='sep30'")
                self.assertEqual(con.execute("SELECT denominator,numerator,rate FROM bp_summary WHERE hospital='A' AND as_of_label='sep30'").fetchall(),[(0,0,None)])
                self.assertEqual(con.execute("SELECT count(*) FROM fct_bp_person WHERE hospital='A' AND as_of_label='sep30'").fetchone()[0],0)
            finally:
                con.execute('ROLLBACK')


if __name__=='__main__':
    unittest.main()
