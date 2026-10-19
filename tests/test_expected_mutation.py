"""④ 기대 결과 비교가 열마다 실제로 보는지 재는 시험(뮤테이션 테스트 · 표준 과정 v1.7).

기대 결과 파일(expected/)로 가짜 fct_bp_person · bp_summary를 만들고, 열 하나만 망가뜨렸을 때
비교가 실패하는지 본다. 쓰는 쪽: 짝 Claude 세션(기대 결과와 검사기는 Codex 밖 · 10/19).
"""
import csv
import datetime as dt
import unittest

import duckdb

from fhir_line.ladder import SUMMARY_COLUMNS, compare_expected, compare_summary
from fhir_line.runtime import ROOT

EXPECTED = ROOT / 'expected'
PERSON_TYPES = {'person_id':'VARCHAR','as_of':'DATE','last_bp_date':'DATE','systolic':'DOUBLE',
                'diastolic':'DOUBLE','controlled':'INTEGER','reason':'VARCHAR'}
SUMMARY_TYPES = {'as_of':'DATE','denominator':'INTEGER','numerator':'INTEGER','rate':'DOUBLE'}


def rows_of(pattern, columns):
    rows = []
    for path in sorted(EXPECTED.glob(pattern)):
        with path.open(newline='') as f:
            rows += [[r[c] or None for c in columns] for r in csv.DictReader(f)]
    return rows


def table(name, types, rows):
    con = duckdb.connect()
    con.execute('CREATE TABLE '+name+' ('+', '.join(f'"{c}" {t}' for c,t in types.items())+')')
    con.executemany('INSERT INTO '+name+' VALUES ('+', '.join('?'*len(types))+')', rows)
    return con


def changed(value, sql_type):
    """그 열의 값 하나를 다른 값으로(자료형에 맞게)."""
    if sql_type=='DATE':
        return (dt.date.fromisoformat(value)+dt.timedelta(days=1)).isoformat()
    if sql_type=='INTEGER' and value in ('0','1'):
        return '1' if value=='0' else '0'
    if sql_type in ('INTEGER','DOUBLE'):
        return str(float(value)+1)
    return value+'x'


class PersonCheckSeesEveryColumn(unittest.TestCase):
    columns = list(PERSON_TYPES)

    def setUp(self):
        self.rows = rows_of('person_*.csv', self.columns)

    def test_baseline_passes(self):
        self.assertEqual(compare_expected(table('fct_bp_person',PERSON_TYPES,self.rows),EXPECTED)['status'],'통과')

    def test_each_column_mutation_fails(self):
        for i,column in enumerate(self.columns):
            with self.subTest(column=column):
                rows = [list(r) for r in self.rows]
                rows[0][i] = changed(rows[0][i],PERSON_TYPES[column])
                result = compare_expected(table('fct_bp_person',PERSON_TYPES,rows),EXPECTED)
                self.assertEqual(result['status'],'실패',column+' 열을 망가뜨려도 통과함')

    def test_missing_duplicate_and_extra_rows_fail(self):
        cases = {'missing':self.rows[1:], 'duplicate':self.rows+[self.rows[0]],
                 'extra':self.rows+[['00000000-0000-0000-0000-000000000000']+self.rows[0][1:]]}
        for name,rows in cases.items():
            with self.subTest(case=name):
                self.assertEqual(compare_expected(table('fct_bp_person',PERSON_TYPES,rows),EXPECTED)['status'],'실패')


class SummaryCheckSeesEveryColumn(unittest.TestCase):
    columns = list(SUMMARY_COLUMNS)

    def setUp(self):
        self.rows = rows_of('summary_*.csv', self.columns)

    def test_baseline_passes(self):
        self.assertEqual(compare_summary(table('bp_summary',SUMMARY_TYPES,self.rows),EXPECTED)['status'],'통과')

    def test_each_column_mutation_fails(self):
        for i,column in enumerate(self.columns):
            with self.subTest(column=column):
                rows = [list(r) for r in self.rows]
                rows[-1][i] = changed(rows[-1][i],SUMMARY_TYPES[column])
                result = compare_summary(table('bp_summary',SUMMARY_TYPES,rows),EXPECTED)
                self.assertEqual(result['status'],'실패',column+' 열을 망가뜨려도 통과함')

    def test_rate_must_be_rounded_to_four_places(self):
        rows = [list(r) for r in self.rows]
        rows[-1][3] = str(4/6)
        self.assertEqual(compare_summary(table('bp_summary',SUMMARY_TYPES,rows),EXPECTED)['status'],'실패')


if __name__=='__main__':
    unittest.main()
