"""⑥ OMOP 확인이 약속마다 실제로 보는지 재는 시험(뮤테이션 테스트 · 표준 과정 v1.7 · M3 결정 0004 ~ 0010).

공식 DDL로 작은 가짜 OMOP을 만들고, 약속 하나만 깨뜨렸을 때 검사가 실패하는지 본다. 쓰는 쪽: 짝 Claude 세션.
"""
import csv
import tempfile
import unittest
from pathlib import Path

import duckdb

from fhir_line import omop

COUNTS = [('A','person',1,0),('A','person_ext',1,0),('A','observation_period',1,0),('A','visit_occurrence',1,0),
          ('A','condition_occurrence',1,2),('A','measurement',2,0),('AB','cdm_source',1,0)]
FOLLOW = [('A','p-1','8480-6','2025-09-13',3004249,145,8876,''),('A','p-1','8462-4','2025-09-13',3012888,75,8876,'')]


def build(con):
    con.execute(omop.DDL.read_text().replace('@cdmDatabaseSchema.',''))
    con.execute('CREATE TABLE person_ext (person_id INTEGER, hospital VARCHAR, measurement_year INTEGER)')
    con.execute('CREATE TABLE omop_load_counts (hospital VARCHAR, omop_table VARCHAR, carried INTEGER, not_carried INTEGER)')
    con.execute("INSERT INTO person (person_id, gender_concept_id, year_of_birth, race_concept_id, ethnicity_concept_id, person_source_value) VALUES (11, 8532, 1960, 0, 0, 'p-1')")
    con.execute("INSERT INTO person_ext VALUES (11, 'A', 2025)")
    con.execute("INSERT INTO observation_period VALUES (11, 11, DATE '2025-01-02', DATE '2025-09-13', 32817)")
    con.execute("INSERT INTO visit_occurrence (visit_occurrence_id, person_id, visit_concept_id, visit_start_date, visit_end_date, visit_type_concept_id) VALUES (1, 11, 9202, DATE '2025-09-13', DATE '2025-09-13', 32817)")
    con.execute("INSERT INTO condition_occurrence (condition_occurrence_id, person_id, condition_concept_id, condition_start_date, condition_type_concept_id, condition_source_value) VALUES (1, 11, 320128, DATE '2025-01-02', 32817, '59621000')")
    for i, (_, _, code, day, concept, value, unit, text) in enumerate(FOLLOW, 1):
        con.execute('''INSERT INTO measurement (measurement_id, person_id, measurement_concept_id, measurement_date, measurement_type_concept_id,
                       value_as_number, unit_concept_id, measurement_source_value, value_source_value) VALUES (?, 11, ?, ?, 32817, ?, ?, ?, ?)''',
                    [i, concept, day, value, unit, code, text or None])
    con.execute("INSERT INTO cdm_source VALUES ('learning', 'L', 'me', NULL, NULL, NULL, DATE '2025-12-31', DATE '2026-10-21', '5.4', 798878, 'subset')")
    con.execute("INSERT INTO omop_load_counts VALUES ('A','condition_occurrence',1,2)")
    return con


class OmopChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        with (self.folder/'omop_counts.csv').open('w', newline='') as f:
            csv.writer(f).writerows([('hospital','omop_table','carried','not_carried'), *COUNTS])
        with (self.folder/'omop_follow.csv').open('w', newline='') as f:
            csv.writer(f).writerows([('hospital','person_source_value','measurement_source_value','measurement_date','measurement_concept_id',
                                      'value_as_number','unit_concept_id','value_source_value'), *FOLLOW])
        self.con = build(duckdb.connect())

    def tearDown(self):
        self.tmp.cleanup()

    def status(self):
        return omop.check(self.con, self.folder)

    def test_baseline_passes(self):
        result = self.status()
        self.assertEqual(result['status'], '통과', result['detail'])

    def test_missing_tables_wait(self):
        self.assertEqual(omop.check(duckdb.connect(), self.folder)['status'], '기다림')

    def test_shape_breaks_fail(self):
        cases = {
            'value_as_number double': 'ALTER TABLE measurement ALTER value_as_number TYPE DOUBLE',
            'extra column': 'ALTER TABLE person ADD COLUMN hospital VARCHAR',
            'dropped column': 'ALTER TABLE visit_occurrence DROP COLUMN visit_source_value',
            'required null': '''CREATE TABLE m AS SELECT * FROM measurement; DROP TABLE measurement; ALTER TABLE m RENAME TO measurement;
                                UPDATE measurement SET measurement_type_concept_id = NULL WHERE measurement_id = 1''',  # dbt 표에는 NOT NULL이 없음
            'person_ext shape': 'ALTER TABLE person_ext DROP COLUMN measurement_year',
            'duplicate person': "INSERT INTO person (person_id, gender_concept_id, year_of_birth, race_concept_id, ethnicity_concept_id) VALUES (11, 8507, 1970, 0, 0)",
        }
        for name, sql in cases.items():
            with self.subTest(case=name):
                self.con = build(duckdb.connect())
                self.con.execute(sql)
                self.assertEqual(omop.check_shape(self.con)['status'], '실패', name)

    def test_count_breaks_fail(self):
        cases = {
            'row dropped': 'DELETE FROM measurement WHERE measurement_id = 2',
            'row without hospital': "INSERT INTO visit_occurrence (visit_occurrence_id, person_id, visit_concept_id, visit_start_date, visit_end_date, visit_type_concept_id) VALUES (2, 99, 9202, DATE '2025-01-01', DATE '2025-01-01', 32817)",
            'not carried differs': "UPDATE omop_load_counts SET not_carried = 1",
            'cdm_source twice': "INSERT INTO cdm_source SELECT * FROM cdm_source",
        }
        for name, sql in cases.items():
            with self.subTest(case=name):
                self.con = build(duckdb.connect())
                self.con.execute(sql)
                self.assertEqual(omop.compare_counts(self.con, self.folder)['status'], '실패', name)

    def test_follow_breaks_fail(self):
        cases = {
            'value': 'UPDATE measurement SET value_as_number = 146 WHERE measurement_id = 1',
            'concept': 'UPDATE measurement SET measurement_concept_id = 0 WHERE measurement_id = 2',
            'unit': 'UPDATE measurement SET unit_concept_id = 0 WHERE measurement_id = 1',
            'source text': "UPDATE measurement SET value_source_value = '145' WHERE measurement_id = 1",
            'source code': "UPDATE measurement SET measurement_source_value = 'systolic' WHERE measurement_id = 1",
            'same day twice': 'INSERT INTO measurement SELECT * REPLACE (9 AS measurement_id) FROM measurement WHERE measurement_id = 1',
        }
        for name, sql in cases.items():
            with self.subTest(case=name):
                self.con = build(duckdb.connect())
                self.con.execute(sql)
                self.assertEqual(omop.compare_follow(self.con, self.folder)['status'], '실패', name)


if __name__ == '__main__':
    unittest.main()
