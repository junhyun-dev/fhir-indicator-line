"""D1,D5-D7 / ADR0010: independent review R1-R4 regression inputs.

글: 만들기 · 의료 · Codex · 2026-10-27
"""
import contextlib
import csv
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fhir_line import ladder, omop
from fhir_line.__main__ import main
from fhir_line.runtime import CACHE, connect


class PublicOutputContract(unittest.TestCase):
    private_id = '87654321'

    def report(self):
        return {'status':'실패','layers':{'status':'통과'},'ladder':[
            {'step':'1','status':'통과','detail':'private '+self.private_id,
             'shared_resource_keys':0},
            {'step':'6','status':'실패','detail':'private '+self.private_id,
             '따라가기':{'status':'실패','detail':'B '+self.private_id+' expected one row'}}]}

    def test_R1_D1_0010_free_text_and_unknown_fields_never_reach_stdout(self):
        report=self.report()
        report['diagnostic_note']=self.private_id
        report['layers']['issues']=['private '+self.private_id]
        output=io.StringIO()
        with patch.object(sys,'argv',['fhir_line','check']),patch.dict(os.environ), \
             patch.object(ladder,'check',return_value=report),contextlib.redirect_stdout(output):
            self.assertEqual(main(),1)
        self.assertNotIn(self.private_id,output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'],'실패')

    def test_R1_D1_0010_omop_detail_stays_in_local_json_not_markdown(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,connect(':memory:') as con:
            con.execute("SET memory_limit='2GB'")
            folder=Path(folder)
            with (folder/'omop_follow.csv').open('w',newline='') as stream:
                writer=csv.writer(stream)
                writer.writerow(('hospital','person_source_value',*omop.FOLLOW_COLUMNS))
                writer.writerow(('B',self.private_id,'8480-6','2025-09-01','3004249','128','8876','128'))
            con.execute('CREATE TABLE person(person_id INTEGER,person_source_value VARCHAR)')
            con.execute('CREATE TABLE person_ext(person_id INTEGER,hospital VARCHAR)')
            con.execute('CREATE TABLE measurement(person_id INTEGER,measurement_source_value VARCHAR,measurement_date DATE,measurement_concept_id INTEGER,value_as_number DOUBLE,unit_concept_id INTEGER,value_source_value VARCHAR)')
            con.execute('INSERT INTO person VALUES (1,?)',[self.private_id])
            con.execute("INSERT INTO person_ext VALUES (1,'B')")
            report=self.report()
            follow=omop.compare_follow(con,folder)
            self.assertIn(self.private_id,follow['detail'])
            report['ladder'][1].update(detail=follow['detail'],따라가기=follow)
            with patch.object(ladder,'ARTIFACTS',folder):
                ladder.write_report(report)
            self.assertIn(self.private_id,(folder/'summaries/verification-ladder.json').read_text())
            self.assertNotIn(self.private_id,(folder/'summaries/verification-ladder.md').read_text())

    def test_R1_D5_0010_only_public_cells_are_projected(self):
        report=self.report()
        report['cell_diffs']=[
            {'table':'fct_bp_person','row':{'hospital':'A','as_of_label':'dec31','person_id':self.private_id},
             'column':'systolic','expected':'128','actual':'129'},
            {'table':'fct_bp_person','row':{'hospital':'A','as_of_label':'dec31'},
             'column':'person_id','expected':self.private_id,'actual':'12345678'},
            {'table':'fct_bp_person','row':{'hospital':'A','as_of_label':'dec31'},
             'column':'reason','expected':'note '+self.private_id,'actual':'조절됨'}]
        visible=ladder.public_report(report)
        self.assertNotIn(self.private_id,json.dumps(visible))
        self.assertNotIn('12345678',json.dumps(visible))
        self.assertEqual(visible['cell_diffs'][0]['row'],{'hospital':'A','as_of_label':'dec31'})
        self.assertEqual((visible['cell_diffs'][0]['expected'],visible['cell_diffs'][0]['actual']),('128','129'))


class RequiredRowKeysContract(unittest.TestCase):
    def check_missing(self,table,kind,missing,side):
        keys=('hospital','as_of_label','person_id') if table=='fct_bp_person' else ('hospital','as_of_label')
        columns=(*keys,'systolic') if kind=='person' else (*keys,'denominator','numerator','rate')
        sample={'hospital':'A','as_of_label':'dec31','person_id':'synthetic-person',
                'systolic':'128','denominator':'6','numerator':'4','rate':'0.6667'}
        db_columns=[key for key in columns if side!='DB' or key!=missing]
        csv_columns=[key for key in columns if side!='CSV' or key!=missing]
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,connect(':memory:') as con:
            con.execute("SET memory_limit='2GB'")
            with (Path(folder)/(kind+'_A.csv')).open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(csv_columns)
                writer.writerow([sample[key] for key in csv_columns])
            con.execute('CREATE TABLE '+table+' ('+', '.join(key+' VARCHAR' for key in db_columns)+')')
            con.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in db_columns)+')',
                        [sample[key] for key in db_columns])
            result=ladder.compare_table(con,Path(folder),kind,table)
            self.assertEqual(result['status'],'실패')
            self.assertIn('열 계약',result['detail'])
            self.assertIn(missing,result['detail'])
            self.assertIn(missing,ladder.public_report(result)['detail'])

    def test_R2_D2_0010_required_keys_in_both_csv_and_db(self):
        for table,kind,keys in [('fct_bp_person','person',('hospital','as_of_label','person_id')),
                                ('bp_summary','summary',('hospital','as_of_label'))]:
            for missing in keys:
                for side in ('CSV','DB'):
                    with self.subTest(table=table,missing=missing,side=side):
                        self.check_missing(table,kind,missing,side)

    def test_R2_D2_0010_summary_projection_does_not_hide_missing_csv_label(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,connect(':memory:') as con:
            con.execute("SET memory_limit='2GB'")
            with (Path(folder)/'summary_A.csv').open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['hospital','denominator','numerator','rate'])
                writer.writerow(['A','6','4','0.6667'])
            con.execute('CREATE TABLE bp_summary(hospital VARCHAR,as_of_label VARCHAR,denominator INTEGER,numerator INTEGER,rate DOUBLE)')
            con.execute("INSERT INTO bp_summary VALUES ('A','dec31',6,4,0.6667)")
            result=ladder.compare_summary(con,Path(folder))
            self.assertEqual(result['status'],'실패')
            self.assertIn('as_of_label',result['detail'])


class MandatoryExternalCasesContract(unittest.TestCase):
    def run_missing_cases(self,skip=False):
        module=importlib.import_module('test_cell_diff')
        environment=dict(os.environ)
        environment.pop('FHIR_CELL_DIFF_CASES',None)
        environment.pop('FHIR_SKIP_EXTERNAL_CELL_CASES',None)
        if skip:
            environment['FHIR_SKIP_EXTERNAL_CELL_CASES']='1'
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder, \
             patch.dict(os.environ,environment,clear=True), \
             patch.object(module,'EXTERNAL_CASES',Path(folder)/'absent-cases.json'):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                result=unittest.TextTestRunner(stream=output).run(
                    unittest.defaultTestLoader.loadTestsFromTestCase(module.LeadFrozenCellCases))
        return result,output.getvalue()

    def test_R3_D5_0010_missing_default_cases_fails_instead_of_skipping(self):
        result,output=self.run_missing_cases()
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.skipped,[])
        self.assertIn('FHIR_CELL_DIFF_CASES',output)

    def test_R3_D5_0010_explicit_skip_labels_incomplete_verification(self):
        result,output=self.run_missing_cases(skip=True)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(len(result.skipped),1)
        self.assertIn('건너뜀 · 완료 검증 아님',output)


class IndexContract(unittest.TestCase):
    header='run_at,product_commit,status,cell_diffs,missing_rows,unexpected_rows\n'

    def test_R4_L2_0010_bad_index_keeps_original_bytes_and_run_csv(self):
        invalid=[
            'run_at,status,product_commit,cell_diffs,missing_rows,unexpected_rows\n',
            self.header+'old,commit,통과,0,0,0,extra\n',
            self.header+'"unfinished\n',
            self.header.rstrip('\n'),
        ]
        CACHE.mkdir(parents=True,exist_ok=True)
        for content in invalid:
            with self.subTest(content=content),tempfile.TemporaryDirectory(dir=CACHE) as folder:
                root=Path(folder);(root/'runs').mkdir()
                index=root/'runs/index.csv';index.write_text(content)
                original=index.read_bytes()
                report={'status':'통과',**{kind:[] for kind in ladder.DIFFERENCE_KINDS}}
                with patch.object(ladder,'ARTIFACTS',root),self.assertRaisesRegex(ValueError,'index.csv.*열 계약'):
                    ladder.archive_differences(report)
                self.assertEqual(index.read_bytes(),original)
                files=list((root/'runs').glob('*/cell-diff.csv'))
                self.assertEqual(len(files),1)
                with files[0].open(newline='') as stream:
                    self.assertEqual(len(next(csv.reader(stream))),9)

    def test_R4_R1_L2_0010_index_failure_invalidates_latest_success_without_public_ids(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,patch.object(ladder,'ARTIFACTS',Path(folder)):
            root=Path(folder)
            initial={'status':'통과','ladder':[{'step':'1','status':'통과','detail':'counts','shared_resource_keys':0}]}
            ladder.write_report(initial)
            index=root/'runs/index.csv';index.write_text('wrong header\n');original=index.read_bytes()
            with self.assertRaises(ValueError):
                ladder.write_report(PublicOutputContract().report())
            latest=json.loads((root/'summaries/verification-ladder.json').read_text())
            self.assertEqual(latest['status'],'실패')
            markdown=(root/'summaries/verification-ladder.md').read_text()
            self.assertNotIn(PublicOutputContract.private_id,markdown)
            self.assertIn('실행 이력',markdown)
            self.assertEqual(index.read_bytes(),original)
            self.assertEqual(len(list((root/'runs').glob('*/cell-diff.csv'))),2)


if __name__=='__main__':
    unittest.main()
