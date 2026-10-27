"""D1-D3 / ADR0004,0008,0009,0011: mutate in-memory rows, using the actual dbt test SQL.

The fixtures are synthetic contracts, not new clinical expected files.
"""
import re
import unittest

import duckdb
import jinja2
import yaml

from fhir_line.runtime import ROOT


class DbtQualityMutation(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(':memory:', config={'memory_limit': '2GB', 'threads': 2})
        self.addCleanup(self.con.close)
        self.con.execute("""
            CREATE TABLE person (person_id INTEGER, year_of_birth INTEGER);
            INSERT INTO person VALUES (1,1990);
            CREATE TABLE observation_period (observation_period_start_date DATE, observation_period_end_date DATE);
            INSERT INTO observation_period VALUES ('2025-01-01','2025-12-31');
            CREATE TABLE visit_occurrence (visit_start_date DATE, visit_end_date DATE);
            INSERT INTO visit_occurrence VALUES ('2025-05-01','2025-05-02');
            CREATE TABLE concept (concept_id INTEGER, domain_id VARCHAR, standard_concept VARCHAR, invalid_reason VARCHAR);
            INSERT INTO concept VALUES (8876,'Unit','S',NULL),(320128,'Condition','S',NULL),(999,'Unit','S',NULL);
            CREATE TABLE measurement (measurement_concept_id INTEGER, unit_concept_id INTEGER, unit_source_value VARCHAR);
            INSERT INTO measurement VALUES (3004249,8876,'mm[Hg]');
            CREATE TABLE condition_occurrence (condition_concept_id INTEGER);
            INSERT INTO condition_occurrence VALUES (320128);
            CREATE TABLE source_to_concept_map (target_concept_id INTEGER);
            INSERT INTO source_to_concept_map VALUES (320128);
            CREATE TABLE cdm_source (cdm_source_name VARCHAR);
            INSERT INTO cdm_source VALUES ('learning fixture');
            CREATE TABLE omop_load_counts (hospital VARCHAR, omop_table VARCHAR, not_carried INTEGER);
            INSERT INTO omop_load_counts VALUES ('A','condition_occurrence',0);
        """)
        schema = yaml.safe_load((ROOT / 'models/omop/schema.yml').read_text())
        self.checks = {}
        for section in ('models', 'seeds'):
            for model in schema.get(section, []):
                for item in model.get('data_tests', []):
                    if isinstance(item, dict):
                        for generic, spec in item.items():
                            if generic.startswith('dqd_'):
                                self.checks[spec['name']] = (model['name'], generic, spec)

    def result(self, name, **overrides):
        self.assertIn(name, self.checks, 'The quality check must be installed in the real YAML')
        model, generic, spec = self.checks[name]
        # Only dbt's test-block syntax changes to a standard Jinja macro; SQL stays intact.
        text = (ROOT / 'macros/test_dqd.sql').read_text()
        text = re.sub(r'{%\s*test\s+(\w+)\s*\(', r'{% macro test_\1(', text)
        text = re.sub(r'{%\s*endtest\s*%}', '{% endmacro %}', text)
        module = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(text).module
        arguments = dict(spec.get('arguments', {}))
        for key, value in arguments.items():
            if isinstance(value, str) and (match := re.fullmatch(r"ref\('([^']+)'\)", value)):
                arguments[key] = match[1]
        arguments.update(overrides)
        sql = str(getattr(module, 'test_' + generic)(model=model, **arguments))
        return self.con.execute(sql).fetchall()

    def mutation(self, name, update):
        self.assertEqual(self.result(name), [], 'The untouched fixture must pass')
        self.con.execute(update)
        self.assertEqual(len(self.result(name)), 1, 'One deliberately bad row must fail')

    def test_0008_D3_unit_completeness_mutation(self):
        self.mutation('t_0008_D3_dqd_unit_completeness', 'UPDATE measurement SET unit_concept_id=NULL')

    def test_0009_D3_unit_domain_mutation(self):
        self.mutation('t_0009_D3_dqd_unit_domain', "UPDATE concept SET domain_id='Measurement' WHERE concept_id=8876")

    def test_0009_D2_mapping_standard_valid_mutation(self):
        self.mutation('t_0009_D2_dqd_mapping_standard_valid', "UPDATE concept SET standard_concept=NULL WHERE concept_id=320128")

    def test_0004_D1_cdm_name_completeness_mutation(self):
        self.mutation('t_0004_D1_dqd_cdm_name_complete', 'UPDATE cdm_source SET cdm_source_name=NULL')

    def test_0004_D2_birth_year_low_mutation(self):
        self.mutation('t_0004_D2_dqd_birth_year_low', 'UPDATE person SET year_of_birth=1849')

    def test_0011_D1_period_date_order_mutation(self):
        self.mutation('t_0011_D1_dqd_period_date_order', "UPDATE observation_period SET observation_period_start_date='2026-01-01'")

    def test_0011_D1_visit_date_order_mutation(self):
        self.mutation('t_0011_D1_dqd_visit_date_order', "UPDATE visit_occurrence SET visit_start_date='2025-05-03'")

    def test_0009_D2_condition_completeness_mutation(self):
        self.mutation('t_0009_D2_dqd_condition_completeness', 'UPDATE condition_occurrence SET condition_concept_id=0')

    def test_0008_D3_unit_plausibility_mutation(self):
        self.mutation('t_0008_D3_dqd_bp_unit_plausibility', 'UPDATE measurement SET unit_concept_id=999')

    def test_0009_D1_not_carried_warns_instead_of_errors(self):
        name = 't_0009_D1_dqd_unmapped_diagnoses_warning'
        self.mutation(name, 'UPDATE omop_load_counts SET not_carried=1')
        config = self.checks[name][2]['config']
        self.assertEqual(config['severity'], 'warn')
        self.assertEqual(config['warn_if'], '> 0')
        self.assertEqual(self.result(name, threshold=1), [])

    def test_0004_D2_percentage_threshold_is_strict_and_not_rounded(self):
        name = 't_0004_D2_dqd_birth_year_low'
        self.con.execute('DELETE FROM person')
        self.con.execute('INSERT INTO person SELECT i,CASE WHEN i=1 THEN 1849 ELSE 1850 END FROM range(1,101) r(i)')
        self.assertEqual(self.result(name), [], 'Exactly 1% must pass a 1% threshold')
        self.con.execute('UPDATE person SET year_of_birth=1849 WHERE person_id=2')
        self.assertEqual(len(self.result(name)), 1)
        self.assertEqual(self.result(name, threshold=2), [])
        self.assertEqual(len(self.result(name, threshold=1.999)), 1)

    def test_0008_D3_source_presence_and_unknown_unit_are_separate(self):
        complete = 't_0008_D3_dqd_unit_completeness'
        plausible = 't_0008_D3_dqd_bp_unit_plausibility'
        self.con.execute('UPDATE measurement SET unit_concept_id=0')
        self.assertEqual(len(self.result(complete)), 1)
        self.assertEqual(self.result(plausible), [], 'DQD leaves concept 0 to completeness')
        self.con.execute('UPDATE measurement SET unit_concept_id=NULL,unit_source_value=NULL')
        self.assertEqual(self.result(complete), [], 'No source and no concept is outside this completeness denominator')

    def test_0009_D1_empty_denominator_does_not_manufacture_a_violation(self):
        self.con.execute('DELETE FROM measurement')
        self.assertEqual(self.result('t_0008_D3_dqd_unit_completeness'), [])
        self.assertEqual(self.result('t_0008_D3_dqd_bp_unit_plausibility'), [])

    def test_0009_D3_orphan_unit_and_invalid_mapping_are_detected(self):
        self.con.execute('UPDATE measurement SET unit_concept_id=123456')
        self.assertEqual(len(self.result('t_0009_D3_dqd_unit_domain')), 1)
        self.con.execute("UPDATE concept SET invalid_reason='D' WHERE concept_id=320128")
        self.assertEqual(len(self.result('t_0009_D2_dqd_mapping_standard_valid')), 1)

    def test_0008_D3_each_measurement_concept_keeps_its_own_denominator(self):
        self.con.execute('DELETE FROM measurement')
        self.con.execute("INSERT INTO measurement SELECT 3004249,CASE WHEN i<=6 THEN 999 ELSE 8876 END,'mm[Hg]' FROM range(1,101) r(i)")
        self.con.execute("INSERT INTO measurement SELECT 3012888,8876,'mm[Hg]' FROM range(1000)")
        failed = self.result('t_0008_D3_dqd_bp_unit_plausibility')
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][:3], (3004249, 6, 100))


if __name__ == '__main__':
    unittest.main()
