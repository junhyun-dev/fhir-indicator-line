"""D1-D7 / ADR0001,0003,0005,0010,0013: S01-S12, approved tiny variants only.

Wrong queries are deliberately executed in memory; frozen inputs/expected files never change.
"""
import copy
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run as e01


class SqlMeaning(unittest.TestCase):
    def setUp(self):
        self.bundle = e01.reviewed_bundle()
        self.rows = e01.fixture_rows(self.bundle)
        self.con = e01.memory_connection()
        self.addCleanup(self.con.close)
        e01.load_inputs(self.con, self.rows)
        e01.create_expected(self.con, self.bundle)

    def good(self):
        result = e01.execute_candidates(self.con, self.bundle)
        self.assertEqual(result['q1_reference']['rows'], 19)
        self.assertEqual(result['q2_reference']['rows'], 12)
        self.assertEqual(result['summary_by_date']['rows'], 8)
        self.assertEqual(result['summary_by_label']['rows'], 6)
        self.assertEqual(result['dimensions'], {'dim_source':3,'dim_person':8,'dim_date':6,'periods':16,
            'source_as_of_scope':8,'source_label_scope':6,'fct_bp_person_as_of':12})
        return result

    def test_L2_missing_external_expected_invalidates_previous_success_without_opening_DB(self):
        with tempfile.TemporaryDirectory(dir=e01.BASE/'tmp') as folder:
            base = Path(folder)
            latest = base/'latest.json'
            latest.write_text('{"status":"통과"}\n')
            with patch.object(e01, 'BASE', base), patch.object(e01, 'DATABASE', base/'experiment.duckdb'), \
                 patch.object(e01, 'check_space', return_value={}), \
                 patch.object(e01, 'reviewed_bundle', side_effect=e01.ExperimentError('LEAD_REVIEW_REQUIRED')), \
                 patch.object(e01.duckdb, 'connect') as connect, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(e01.main([]), 1)
            connect.assert_not_called()
            self.assertEqual(json.loads(latest.read_text())['status'], '실패')
            reports = list((base/'runs').glob('*/result.json'))
            self.assertEqual(len(reports), 1)
            self.assertEqual(json.loads(reports[0].read_text())['error'], 'LEAD_REVIEW_REQUIRED')

    def reject(self, sql, kind, expected=None):
        self.con.execute('CREATE OR REPLACE TABLE broken_output AS '+sql)
        with self.assertRaises(e01.ExperimentError) as caught:
            e01.compare(self.con, 'broken_output', expected or 'expected_'+kind, kind)
        self.assertIn(caught.exception.code, ('EXPECTED_MISMATCH','KEY_CONTRACT','TYPE_CONTRACT'))
        return caught.exception

    def replace_one(self, name, old, new):
        text = e01.query_text(self.con, name)
        self.assertEqual(text.count(old), 1)
        return text.replace(old, new)

    def test_S01_D4_independent_component_minima(self):
        self.good()
        for field, bad in [('systolic_min',145),('diastolic_min',95)]:
            with self.subTest(field=field):
                self.reject(f"SELECT * REPLACE (CASE WHEN person_id='p1' AND hospital IN ('A','A_PRIME') AND bp_date='2025-09-30' THEN {bad} ELSE {field} END AS {field}) FROM q1_reference", 'daily')

    def test_S02_D5_D7_last_complete_pair_or_mixed_components_is_wrong(self):
        self.good()
        bad = self.replace_one('q2_last_reference','from daily_with_label\n','from daily_with_label where systolic_min is not null and diastolic_min is not null\n')
        self.reject(bad, 'person')
        self.reject("SELECT * REPLACE (CASE WHEN hospital='A' AND person_id='p1' AND as_of_label='dec31' THEN 92 ELSE diastolic END AS diastolic) FROM q2_reference", 'person')

    def test_S03_D3_D5_null_only_day_rejects_Q1_before_Q2(self):
        bad = self.replace_one('q1_daily_reference','and bp.value_as_number is not null','')
        with self.assertRaises(e01.ExperimentError) as caught:
            e01.execute_candidates(self.con, self.bundle, {'q1_daily_reference':bad})
        self.assertEqual(caught.exception.code, 'EXPECTED_MISMATCH')
        self.assertEqual(self.con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('q2_reference','q2_alternative')").fetchone()[0],0)
        e01.load_inputs(self.con, self.rows)
        self.good()

    def test_S04_D3_admission_end_and_any_nonmatching_admission(self):
        self.good()
        old='and bp.measurement_date between visits.visit_start_date and visits.visit_end_date'
        bad=self.replace_one('q1_daily_reference',old,'and bp.measurement_date >= visits.visit_start_date and bp.measurement_date < visits.visit_end_date')
        self.reject(bad,'daily')
        text=e01.query_text(self.con,'q1_daily_reference')
        bad=text.replace('and not exists (','and exists (').replace(old,old.replace(' between ',' not between '))
        self.reject(bad,'daily')

    def test_S05_D2_diagnosis_times_visit_join_must_not_multiply_people(self):
        self.good()
        error=self.reject('''SELECT f.* FROM q2_reference f JOIN persons p USING(hospital,person_id)
            JOIN conditions d USING(hospital,omop_person_id)
            JOIN visits v USING(hospital,omop_person_id) WHERE v.visit_concept_id=9202''','person')
        self.assertEqual(error.code,'KEY_CONTRACT')
        self.assertEqual(error.details['max_multiplicity'],4)

    def test_S06_D1_0005_source_is_part_of_every_join(self):
        self.good()
        bad=self.replace_one('q2_last_reference','d.hospital=e.hospital and d.as_of_label=e.as_of_label','d.as_of_label=e.as_of_label')
        self.reject(bad,'person')

    def test_S07_D1_0010_actual_date_and_label_are_not_interchangeable(self):
        self.good()
        bad=self.replace_one('q2_last_reference','partition by hospital, as_of_label, person_id','partition by hospital, person_id')
        self.reject(bad,'person')
        self.reject('''SELECT s.hospital,s.as_of,coalesce(sum(f.controlled),0)::integer numerator,
            count(f.person_id)::integer denominator,round(sum(f.controlled)::double/nullif(count(f.person_id),0),4)::double rate
            FROM source_as_of_scope s LEFT JOIN q2_reference f USING(hospital,as_of_label) GROUP BY s.hospital,s.as_of''','summary_by_date')

    def test_S08_L2_0010_duplicate_concept_input_is_rejected(self):
        rows=copy.deepcopy(self.rows);rows['indicator_concepts'].append(rows['indicator_concepts'][0])
        with self.assertRaises(e01.ExperimentError) as caught:e01.load_inputs(self.con,rows)
        self.assertEqual(caught.exception.code,'KEY_CONTRACT')
        self.assertEqual((caught.exception.details['duplicate_groups'],caught.exception.details['max_multiplicity']),(1,2))
        e01.load_inputs(self.con,self.rows);self.good()

    def test_S09_0005_0007_person_duplicate_and_one_orphan_are_rejected(self):
        duplicate=copy.deepcopy(self.rows);duplicate['persons'].append(duplicate['persons'][0])
        with self.assertRaises(e01.ExperimentError) as caught:e01.load_inputs(self.con,duplicate)
        self.assertEqual(caught.exception.code,'PERSON_DUPLICATES')
        self.assertEqual(caught.exception.details,{'natural':{'groups':1,'max_multiplicity':2},'omop':{'groups':1,'max_multiplicity':2}})
        orphan=copy.deepcopy(self.rows);row=list(orphan['measurements'][0]);row[1]='A|orphan|m14|3004249';row[2]=999;orphan['measurements'].append(tuple(row))
        with self.assertRaises(e01.ExperimentError) as caught:e01.load_inputs(self.con,orphan)
        self.assertEqual(caught.exception.code,'ORPHAN_ROWS');self.assertEqual(caught.exception.details['rows'],1)
        e01.load_inputs(self.con,self.rows);self.good()

    def test_S10_D2_D6_zero_people_keep_both_summary_scopes(self):
        rows=copy.deepcopy(self.rows);rows['conditions']=[r for r in rows['conditions'] if r[0]!='B']
        self.assertEqual(len(self.rows['conditions'])-len(rows['conditions']),1)
        e01.load_inputs(self.con,rows);e01.create_expected(self.con,self.bundle)
        # This is the approved fourth input variant, not a rewrite of the base oracle.
        for phase, names in [('q1',('daily_reference','daily_alternative')),('q2',('last_reference','last_alternative'))]:
            for suffix in names:
                table=phase+'_'+suffix.rsplit('_',1)[1]
                self.con.execute(f'CREATE TABLE {table} AS '+e01.query_text(self.con,phase+'_'+suffix))
                if phase=='q1':e01.compare(self.con,table,'expected_daily','daily')
        e01.compare(self.con,'q2_alternative','q2_reference','person')
        e01.summarize(self.con)
        self.assertEqual(self.con.execute("SELECT count(*) FROM q2_reference WHERE hospital='B'").fetchone()[0],0)
        self.assertEqual(self.con.execute("SELECT numerator,denominator,rate FROM summary_by_date WHERE hospital='B'").fetchall(),[(0,0,None)]*4)
        self.assertEqual(self.con.execute("SELECT numerator,denominator,rate FROM summary_by_label WHERE hospital='B'").fetchall(),[(0,0,None)]*2)
        self.reject('''SELECT hospital,as_of,sum(controlled)::integer numerator,count(*)::integer denominator,
            round(sum(controlled)::double/count(*),4)::double rate FROM q2_reference GROUP BY hospital,as_of''','summary_by_date','summary_by_date')

    def test_S11_0013_derived_and_parent_are_never_combined(self):
        self.good()
        with self.assertRaises(e01.ExperimentError) as caught:e01.select_scope(self.con,['A','A_PRIME'],dt.date(2025,9,30))
        self.assertEqual(caught.exception.code,'DERIVED_SOURCE_OVERLAP')
        self.assertEqual(e01.select_scope(self.con,['A'],dt.date(2025,9,30))[0][2:4],(1,2))

    def test_S12_D1_D6_counts_and_rates_are_not_additive_over_time(self):
        self.good()
        total=self.con.execute("SELECT sum(denominator) FROM summary_by_date WHERE hospital='A'").fetchone()[0]
        unique=self.con.execute("SELECT count(DISTINCT person_id) FROM q2_reference WHERE hospital='A'").fetchone()[0]
        self.assertEqual((total,unique),(5,3))
        with self.assertRaises(e01.ExperimentError) as caught:e01.select_scope(self.con,['A'],[dt.date(2025,9,30),dt.date(2025,12,31)])
        self.assertEqual(caught.exception.code,'NON_ADDITIVE_SCOPE')
        with self.assertRaises(e01.ExperimentError) as caught:e01.select_scope(self.con,['B'],dt.date(2025,12,31))
        self.assertEqual(caught.exception.code,'SCOPE_NOT_FOUND')
        self.reject("SELECT * REPLACE (CASE WHEN hospital='B' THEN make_date(2025,month(as_of)::integer,day(as_of)::integer) ELSE as_of END AS as_of) FROM summary_by_date",'summary_by_date')

    def test_D1_D6_types_null_precision_and_resource_settings(self):
        self.good()
        self.assertEqual(self.con.execute('SELECT current_setting(\'threads\')').fetchone()[0],1)
        self.assertEqual(self.con.execute("SELECT systolic_min,diastolic_min FROM q1_reference WHERE hospital='A' AND person_id='p3' AND as_of='2025-09-30'").fetchone(),(109.51,76.761))
        self.reject('SELECT * REPLACE (controlled::double AS controlled) FROM q2_reference','person')

    def test_L2_guarded_paths_hash_failures_and_select_only(self):
        with self.assertRaises(e01.ExperimentError):e01.checked_output(e01.ROOT/'data/fhir.duckdb')
        with self.assertRaises(e01.ExperimentError):e01.query_text(self.con,'q1_daily_reference',{'q1_daily_reference':"ATTACH 'not-allowed.duckdb' AS x"})
        with patch.object(e01,'EXPERIMENT_LIMIT',0):
            with self.assertRaises(e01.ExperimentError) as caught:e01.check_space()
            self.assertEqual(caught.exception.code,'STORAGE_LIMIT')
        with tempfile.TemporaryDirectory(dir=e01.BASE/'tmp') as folder:
            base=Path(folder);original=base/'original';original.write_bytes(b'private')
            alias=base/'hard';alias.hardlink_to(original)
            with self.assertRaises(e01.ExperimentError):e01.checked_output(alias)
            symbolic=base/'link';symbolic.symlink_to(e01.ROOT/'expected',target_is_directory=True)
            with self.assertRaises(e01.ExperimentError):e01.checked_output(symbolic/'output.json')
            self.assertEqual(original.read_bytes(),b'private')
        manifest=(e01.DEFAULT_EXPECTED/'SHA256SUMS').read_bytes()
        with patch.object(Path,'read_bytes',autospec=True,side_effect=lambda p: b'changed' if p.name=='daily.csv' else manifest if p.name=='SHA256SUMS' else b''):
            with self.assertRaises(e01.ExperimentError) as caught:e01.reviewed_bundle()
            self.assertEqual(caught.exception.code,'EXTERNAL_HASH_MISMATCH')


if __name__ == '__main__':
    unittest.main(verbosity=2)
