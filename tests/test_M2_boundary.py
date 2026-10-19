"""D1/D2/D3/M2/M2B: hospital syntax must stop before the shared L4-L6 SQL."""
import unittest

from fhir_line.runtime import ROOT


class CommonBoundary(unittest.TestCase):
    def test_M2_D1_D2_D3_hospital_syntax_stays_below_L4(self):
        forbidden = ('AMB', 'IMP', 'EMER', '8480-6', '8462-4', '59621000',
                     'onsetDateTime', 'effectiveDateTime', 'birthDate', 'component',
                     'omr', 'anchor_year', 'anchor_age', 'chartevents', 'diagnoses_icd',
                     '220179', '220180', 'Blood Pressure', 'icd_code')
        files = sorted(path for layer in ('intermediate', 'marts', 'reports')
                       for path in (ROOT/'models'/layer).rglob('*.sql'))
        self.assertTrue(files, 'L4-L6 models must exist')
        for path in files:
            sql = path.read_text().casefold()
            for token in forbidden:
                with self.subTest(model=str(path.relative_to(ROOT)), token=token):
                    self.assertNotIn(token.casefold(), sql)


if __name__ == '__main__':
    unittest.main()
