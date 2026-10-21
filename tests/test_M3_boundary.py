"""D1-D6 / decisions 0004,0010: calculations know OMOP concepts and one indicator calendar."""
import csv
import re
import unittest

from fhir_line.runtime import ROOT


def sql_without_comments(text):
    return re.sub(r'/\*.*?\*/|--[^\n]*|\{#.*?#\}', ' ', text, flags=re.S)


class OmopBoundary(unittest.TestCase):
    def models(self):
        return sorted(path for layer in ('intermediate','marts','reports')
                      for path in (ROOT/'models'/layer).glob('*.sql'))

    def test_0010_D1_D2_D3_calculations_contain_no_hospital_or_source_codes(self):
        with (ROOT/'seeds/source_to_concept_map.csv').open(newline='') as stream:
            source_codes = {row['source_code'] for row in csv.DictReader(stream)}
        forbidden = ('AMB','IMP','EMER','8480-6','8462-4','59621000','I10','4010','4011','4019',
                     '220179','220180','onsetDateTime','effectiveDateTime','birthDate','component',
                     'anchor_year','anchor_age','chartevents','diagnoses_icd','Blood Pressure',
                     'icd_code','omr','record_day','hospital_a','hospital_b','code_map')
        files = self.models()
        self.assertTrue(files)
        for path in files:
            sql = sql_without_comments(path.read_text())
            for word in forbidden:
                with self.subTest(model=path.name, token=word):
                    self.assertIsNone(re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',sql,re.I))
            for code in source_codes:
                with self.subTest(model=path.name,source_code=code):
                    # Literal codes include HH/VR, units, genders and OMR halves, without banning aliases.
                    self.assertIsNone(re.search(r"(['\"])\s*"+re.escape(code)+r"\s*\1",sql,re.I))
            self.assertIsNone(re.search(r"(['\"])[AB]\1",sql))
            self.assertNotRegex(sql,r"(?i)\bsource\s*\(")
            self.assertNotRegex(sql,r"(?i)\bref\s*\(\s*['\"]stg_")

    def test_0010_D2_D3_standard_concept_numbers_only_come_from_seed(self):
        with (ROOT/'seeds/concept.csv').open(newline='') as stream:
            concepts = [row['concept_id'] for row in csv.DictReader(stream)]
        for path in self.models():
            sql = sql_without_comments(path.read_text())
            for concept in concepts:
                with self.subTest(model=path.name,concept=concept):
                    self.assertNotRegex(sql,r'(?<!\d)'+re.escape(concept)+r'(?!\d)')

    def test_0010_D1_D2_calendar_and_age_have_one_owner(self):
        owner = ROOT/'models/intermediate/int_person_period.sql'
        self.assertTrue(owner.exists())
        forbidden = (r'\bmake_date\s*\(',r'\bdate_trunc\s*\(',r'\byear_of_birth\b',
                     r'\bmeasurement_year\b',r'\b6\s*,\s*30\b',r'\b12\s*,\s*31\b',
                     r'\b1\s*,\s*1\b',r"\bdate\s*'\d{4}-(?:01-01|06-30|12-31)'")
        for path in self.models():
            if path==owner:
                continue
            sql = sql_without_comments(path.read_text())
            for pattern in forbidden:
                with self.subTest(model=path.name,pattern=pattern):
                    self.assertNotRegex(sql,'(?i)'+pattern)
        for path in (ROOT/'models/staging').rglob('*.sql'):
            sql = sql_without_comments(path.read_text())
            self.assertNotRegex(sql,r'(?i)\bmake_date\s*\(')
            self.assertNotIn('as_of_labels',sql)
            self.assertNotIn('hypertension_cutoff_day',sql)
            self.assertNotIn('age_at_year_end',sql)


if __name__=='__main__':
    unittest.main()
