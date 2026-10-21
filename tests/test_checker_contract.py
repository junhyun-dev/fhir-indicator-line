"""검사기 계약(요청 03 사전 검토 R1 · R3 · 자료형): 짝 Claude 세션이 쓴 시험.

R1 L6 요약(reports)은 marts만 읽는다 · R3 check.sh의 strict는 기다림도 실패 · 결과 표의 자료형 계약.
"""
import unittest

import duckdb

from fhir_line.ladder import check_types, overall
from fhir_line.layers import validate


def node(name, layer, deps):
    return {'name':name,'resource_type':'model','original_file_path':f'models/{layer}/{name}.sql',
            'depends_on':{'nodes':deps},'raw_code':"select * from {{ ref('x') }}"}


class ReportsLayer(unittest.TestCase):
    def graph(self, summary_layer, summary_deps):
        return {'sources':{'source.fhir.latest_resources':{'name':'latest_resources','resource_type':'source'}},
                'nodes':{'model.stg':node('stg','staging',['source.fhir.latest_resources']),
                         'model.com':node('com','common',['model.stg']),
                         'model.int':node('int','intermediate',['model.com']),
                         'model.fct':node('fct','marts',['model.int']),
                         'model.sum':node('sum',summary_layer,summary_deps)}}

    def test_R1_reports_may_read_marts(self):
        self.assertEqual(validate(self.graph('reports',['model.fct']))['issues'],[])

    def test_R1_marts_still_cannot_read_marts(self):
        self.assertEqual(validate(self.graph('marts',['model.fct']))['status'],'실패')

    def test_R1_reports_cannot_skip_to_staging(self):
        self.assertEqual(validate(self.graph('reports',['model.stg']))['status'],'실패')


class CommonLayer(unittest.TestCase):
    def test_M2_intermediate_reads_common_not_hospital_staging(self):
        ok = ReportsLayer().graph('reports',['model.fct'])
        self.assertEqual(validate(ok)['issues'],[])
        ok['nodes']['model.int']['depends_on']['nodes'] = ['model.stg']
        self.assertEqual(validate(ok)['status'],'실패')

    def test_M2_hospital_staging_in_subfolder_is_staging(self):
        g = ReportsLayer().graph('reports',['model.fct'])
        g['nodes']['model.stg']['original_file_path'] = 'models/staging/hospital_b/stg.sql'
        self.assertEqual(validate(g)['issues'],[])


class OmopLayer(unittest.TestCase):
    def graph(self, omop_deps, int_deps):
        g = ReportsLayer().graph('reports',['model.fct'])
        g['nodes']['model.omop'] = node('omop','omop',omop_deps)
        g['nodes']['model.int']['depends_on']['nodes'] = int_deps
        return g

    def test_M3_omop_reads_staging_and_intermediate_reads_omop(self):
        self.assertEqual(validate(self.graph(['model.stg'],['model.omop']))['issues'],[])

    def test_M3_omop_cannot_read_common_or_source(self):
        self.assertEqual(validate(self.graph(['model.com'],['model.omop']))['status'],'실패')
        self.assertEqual(validate(self.graph(['source.fhir.latest_resources'],['model.omop']))['status'],'실패')

    def test_M3_intermediate_still_cannot_read_staging(self):
        self.assertEqual(validate(self.graph(['model.stg'],['model.stg']))['status'],'실패')


class StrictOverall(unittest.TestCase):
    rows = [{'status':'통과'},{'status':'기다림'}]

    def test_R3_waiting_passes_only_without_strict(self):
        self.assertEqual(overall(self.rows),'통과')
        self.assertEqual(overall(self.rows,strict=True),'실패')

    def test_R3_failure_fails_either_way(self):
        self.assertEqual(overall([{'status':'실패'}]),'실패')


class TypeContract(unittest.TestCase):
    good = {'fct_bp_person':'hospital VARCHAR, as_of_label VARCHAR, person_id VARCHAR, as_of DATE, last_bp_date DATE, systolic DOUBLE, diastolic DOUBLE, controlled INTEGER, reason VARCHAR',
            'bp_summary':'hospital VARCHAR, as_of_label VARCHAR, denominator BIGINT, numerator HUGEINT, rate DOUBLE'}

    def connection(self, **override):
        con = duckdb.connect()
        for table, columns in {**self.good, **override}.items():
            con.execute(f'CREATE TABLE {table} ({columns})')
        return con

    def test_contract_types_pass(self):
        self.assertEqual(check_types(self.connection())['status'],'통과')

    def test_wrong_types_fail(self):
        cases = {'as_of text':{'fct_bp_person':self.good['fct_bp_person'].replace('as_of DATE','as_of VARCHAR')},
                 'controlled boolean':{'fct_bp_person':self.good['fct_bp_person'].replace('controlled INTEGER','controlled BOOLEAN')},
                 'rate text':{'bp_summary':self.good['bp_summary'].replace('rate DOUBLE','rate VARCHAR')},
                 'no hospital':{'bp_summary':self.good['bp_summary'].replace('hospital VARCHAR, ','')}}
        for name, override in cases.items():
            with self.subTest(case=name):
                self.assertEqual(check_types(self.connection(**override))['status'],'실패')

    def test_missing_table_waits(self):
        con = duckdb.connect()
        con.execute(f"CREATE TABLE fct_bp_person ({self.good['fct_bp_person']})")
        self.assertEqual(check_types(con)['status'],'기다림')


if __name__=='__main__':
    unittest.main()
