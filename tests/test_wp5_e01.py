"""D1-D7 / ADR0015: reviewed E01 cases through both candidates and the product SQL."""
import re
import unittest

from experiments.sql_modeling_04 import run as e01
from fhir_line.runtime import ROOT
from wp5_expected import cases, person_values


class Wp5E01(unittest.TestCase):
    def test_0015_D1_D7_twelve_E01_cases_in_product_and_both_candidates(self):
        bundle=e01.reviewed_bundle()
        con=e01.memory_connection();self.addCleanup(con.close)
        e01.load_inputs(con,e01.fixture_rows(bundle))
        e01.execute_candidates(con,bundle)
        con.execute('''CREATE VIEW int_bp_daily AS SELECT d.*,p.as_of_label
            FROM q1_reference d JOIN periods p USING(hospital,person_id,as_of)''')
        sql=(ROOT/'models/marts/fct_bp_person.sql').read_text()
        sql=re.sub(r"\{\{\s*ref\('([^']+)'\)\s*\}\}",
            lambda m:'periods' if m[1]=='int_person_period' else m[1],sql)
        con.execute('CREATE TABLE product_person AS '+sql)
        selected=cases('E01');self.assertEqual(len(selected),12)
        for case in selected:
            for table in ('product_person','q2_reference','q2_alternative'):
                with self.subTest(case=case['id'],table=table):
                    row=con.execute(f'''SELECT cast(last_bp_date as varchar),systolic,diastolic,controlled,reason
                        FROM {table} WHERE hospital=? AND person_id=? AND as_of_label=?''',
                        [case['hospital'],case['person'],case['as_of_label']]).fetchall()
                    self.assertEqual(row,[person_values(case)])
