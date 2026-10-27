"""D1,D5-D7 / ADR0010, REQ-medical-cell-diff-1027: lead-owned cases and history.

Read the external frozen cases; never copy their person IDs into this repository.
글: 만들기 · 의료 · Codex · 2026-10-27
"""
import collections
import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fhir_line import ladder
from fhir_line.__main__ import main
from fhir_line.runtime import CACHE, ROOT, connect
from test_expected_mutation import PERSON_TYPES, SUMMARY_TYPES, rows_of


EXTERNAL_CASES = Path(os.environ.get('FHIR_CELL_DIFF_CASES',
    str(Path.home()/'personal/builds/medical-data-hands-on/answer-key/cell_diff/cases.json')))


class LeadFrozenCellCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('FHIR_SKIP_EXTERNAL_CELL_CASES')=='1':
            message='건너뜀 · 완료 검증 아님: 외부 고정 사례 다섯 개를 실행하지 않아요.'
            print(message)
            raise unittest.SkipTest(message)
        if not EXTERNAL_CASES.is_file():
            raise FileNotFoundError('필수 외부 기대 입력 cases.json이 없어요. FHIR_CELL_DIFF_CASES로 고정 파일을 지정하세요.')
        digest = hashlib.sha256(EXTERNAL_CASES.read_bytes()).hexdigest()
        locks = dict((name.removeprefix('*'),sha) for sha,name in
                     (line.split(maxsplit=1) for line in EXTERNAL_CASES.with_name('SHA256SUMS').read_text().splitlines() if line.strip()))
        if locks.get(EXTERNAL_CASES.name)!=digest:
            raise ValueError('Lead-owned case hash mismatch; do not edit expected values')
        cls.cases = {case['case']:case for case in json.loads(EXTERNAL_CASES.read_text())['cases']}

    def run_case(self, number):
        case = self.cases[number]
        with connect(':memory:') as con:
            con.execute("SET memory_limit='2GB'")
            for table,types,pattern in [('fct_bp_person',PERSON_TYPES,'person_[A-Z].csv'),
                                        ('bp_summary',SUMMARY_TYPES,'summary_[A-Z].csv')]:
                con.execute('CREATE TABLE '+table+' ('+', '.join(f'"{c}" {t}' for c,t in types.items())+')')
                con.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in types)+')',rows_of(pattern,types))
            change = case['change']
            if isinstance(change,dict):
                key = change.get('row',change.get('delete_row',change.get('duplicate_row')))
                where = ' AND '.join(f'"{column}"=?' for column in key)
                parameters = list(key.values())
                if 'column' in change:
                    con.execute(f'UPDATE {change["table"]} SET "{change["column"]}"=? WHERE '+where,
                                [change['to'],*parameters])
                elif 'delete_row' in change:
                    con.execute('DELETE FROM '+change['table']+' WHERE '+where,parameters)
                else:
                    con.execute('INSERT INTO '+change['table']+' SELECT * FROM '+change['table']+' WHERE '+where,parameters)
            parts = (ladder.compare_expected(con,ROOT/'expected'),ladder.compare_summary(con,ROOT/'expected'))
            actual = {'status':'통과' if all(part['status']=='통과' for part in parts) else '실패',
                      **{kind:[item for part in parts for item in part[kind]] for kind in ladder.DIFFERENCE_KINDS}}
        expected = {key:case[key] for key in ('status',*ladder.DIFFERENCE_KINDS)}
        # unittest's default dict diff would print real IDs on failure.
        self.assertTrue(actual==expected,f'Lead case {number} differs; inspect local comparison details, keep IDs off stdout')

    def test_D5_D7_case_0_no_change(self):
        self.run_case(0)

    def test_D5_case_1_person_systolic(self):
        self.run_case(1)

    def test_D6_case_2_summary_numerator(self):
        self.run_case(2)

    def test_D2_case_3_missing_person(self):
        self.run_case(3)

    def test_D2_case_4_extra_duplicate(self):
        self.run_case(4)


class DuplicateKeyContract(unittest.TestCase):
    columns = ('hospital','as_of_label','person_id','systolic')

    def differences(self,expected,actual):
        return ladder.table_differences('fct_bp_person',self.columns,
                                       collections.Counter(expected),collections.Counter(actual))

    def test_D5_duplicate_key_cancels_equal_rows_without_pairing_changed_rows(self):
        old = ('A','dec31','synthetic-person','128')
        other = (*old[:3],'130')
        changed = (*old[:3],'129')
        result = self.differences([old,other],[old,changed])
        self.assertEqual(result['cell_diffs'],[])
        self.assertEqual(len(result['missing_rows']),1)
        self.assertEqual(len(result['unexpected_rows']),1)

    def test_D5_duplicate_actual_key_does_not_turn_one_change_into_a_cell_pair(self):
        old = ('A','dec31','synthetic-person','128')
        changed = (*old[:3],'129')
        result = self.differences([old],[changed,changed])
        self.assertEqual([len(result[k]) for k in ladder.DIFFERENCE_KINDS],[0,1,2])

    def test_D5_duplicate_expected_key_and_row_order_keep_multiplicity(self):
        one = ('A','dec31','synthetic-person','128')
        two = (*one[:3],'129')
        self.assertEqual([len(v) for v in self.differences([one,one,two],[two,one,one]).values()],[0,0,0])
        self.assertEqual([len(v) for v in self.differences([one,one],[one]).values()],[0,1,0])

    def test_D7_numeric_four_and_four_point_zero_match_in_compare_summary(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,connect(':memory:') as con:
            with (Path(folder)/'summary_A.csv').open('w',newline='') as stream:
                writer=csv.writer(stream)
                writer.writerow(ladder.SUMMARY_COLUMNS)
                writer.writerow(['A','dec31','6','4','0.6667'])
            con.execute('CREATE TABLE bp_summary(hospital VARCHAR,as_of_label VARCHAR,denominator DOUBLE,numerator DOUBLE,rate DOUBLE)')
            con.execute("INSERT INTO bp_summary VALUES ('A','dec31',6.0,4.0,0.6667)")
            result=ladder.compare_summary(con,Path(folder))
            self.assertEqual(result['status'],'통과')
            self.assertEqual([len(result[k]) for k in ladder.DIFFERENCE_KINDS],[0,0,0])


class RunHistoryContract(unittest.TestCase):
    def report(self,fail=True):
        part={kind:[] for kind in ladder.DIFFERENCE_KINDS}
        if fail:
            part['cell_diffs']=[{'table':'fct_bp_person','row':{'hospital':'A','as_of_label':'sep30','person_id':'synthetic-private-id'},
                                 'column':'systolic','expected':'128','actual':'129'}]
            part['missing_rows']=[{'table':'fct_bp_person','row':{'hospital':'B','as_of_label':'dec31','person_id':'synthetic-missing-id'}}]
            part['unexpected_rows']=[{'table':'bp_summary','row':{'hospital':'A','as_of_label':'dec31'}}]
        return {'status':'실패' if fail else '통과','layers':{'status':'통과'},
                'ladder':[{'step':'1','status':'통과','detail':'synthetic counts','shared_resource_keys':0},
                          {'step':'4','status':'실패' if fail else '통과','detail':'synthetic comparison','사람별':part}]}

    def test_D5_D7_csv_counts_keys_values_and_two_same_clock_runs_are_preserved(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        fixed=dt.datetime(2026,10,27,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,patch.object(ladder,'ARTIFACTS',Path(folder)):
            with patch.object(ladder.dt,'datetime') as clock:
                clock.now.return_value=fixed
                first=self.report()
                ladder.write_report(first)
                csv_path=Path(first['run']['cell_diff_csv'])
                original=csv_path.read_bytes()
                first_markdown=(Path(folder)/'summaries/verification-ladder.md').read_text()
                self.assertNotIn('synthetic-private-id',first_markdown)
                self.assertNotIn('synthetic-missing-id',first_markdown)
                self.assertIn('| fct_bp_person | A | sep30 | systolic | 128 | 129 |',first_markdown)
                second=self.report(False)
                ladder.write_report(second)
            with csv_path.open(newline='') as stream: rows=list(csv.DictReader(stream))
            self.assertEqual([r['kind'] for r in rows],['다른 칸','빠진 행','남는 행'])
            self.assertEqual((rows[0]['expected'],rows[0]['actual']),('128','129'))
            self.assertEqual(json.loads(rows[0]['row_key'])['person_id'],'synthetic-private-id')
            self.assertEqual(csv_path.read_bytes(),original)
            self.assertNotEqual(first['run']['run_at'],second['run']['run_at'])
            self.assertEqual(len([p for p in (Path(folder)/'runs').iterdir() if p.is_dir()]),2)
            with (Path(folder)/'runs/index.csv').open(newline='') as stream: index=list(csv.DictReader(stream))
            self.assertEqual([r['status'] for r in index],['실패','통과'])
            self.assertEqual([[r[k] for k in ladder.DIFFERENCE_KINDS] for r in index],[['1','1','1'],['0','0','0']])
            with Path(second['run']['cell_diff_csv']).open(newline='') as stream:
                self.assertEqual(list(csv.DictReader(stream)),[])
            latest=json.loads((Path(folder)/'summaries/verification-ladder.json').read_text())
            self.assertEqual(latest['status'],'통과')
            self.assertEqual(latest['run'],second['run'])
            markdown=(Path(folder)/'summaries/verification-ladder.md').read_text()
            self.assertNotIn('synthetic-private-id',markdown)
            self.assertNotIn('synthetic-missing-id',markdown)

    def test_D1_early_layer_failure_is_archived_and_invalidates_latest_success(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder,patch.object(ladder,'ARTIFACTS',Path(folder)):
            ladder.write_report(self.report(False))
            with patch.object(ladder,'check_layers',return_value={'status':'실패'}):
                result=ladder.check(Path(folder)/'unused')
            self.assertEqual(result['status'],'실패')
            with (Path(folder)/'runs/index.csv').open(newline='') as stream: index=list(csv.DictReader(stream))
            self.assertEqual([r['status'] for r in index],['통과','실패'])
            latest=json.loads((Path(folder)/'summaries/verification-ladder.json').read_text())
            self.assertEqual(latest['status'],'실패')

    def test_D5_check_cli_hides_person_keys_while_retaining_hospital_column_and_values(self):
        report=self.report()
        output=io.StringIO()
        with patch.object(sys,'argv',['fhir_line','check']),patch.dict(os.environ), \
             patch.object(ladder,'check',return_value=report),contextlib.redirect_stdout(output):
            self.assertEqual(main(),1)
        text=output.getvalue()
        self.assertNotIn('synthetic-private-id',text)
        self.assertNotIn('synthetic-missing-id',text)
        visible=json.loads(text)['ladder'][1]['사람별']['cell_diffs'][0]
        self.assertEqual((visible['row']['hospital'],visible['column'],visible['expected'],visible['actual']),
                         ('A','systolic','128','129'))


if __name__=='__main__':
    unittest.main()
