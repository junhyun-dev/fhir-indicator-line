"""D1-D7 / ADR0006,0008,0011,0013: hand-built inputs and checker mutations.

No product imports, source downloads, product database, or dbt invocation.
"""
import copy
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import calculate
import check


def patient(pid="p", birth="1960-12-31"):
    return {"resourceType": "Patient", "id": pid, "birthDate": birth, "gender": "female"}


def diagnosis(pid="p", rid="dx", start="2020-01-01", end="", recorded=None, code="59621000", system="http://snomed.info/sct"):
    return {"resourceType": "Condition", "id": rid, "subject": {"reference": "urn:uuid:" + pid},
        "onsetDateTime": start, "abatementDateTime": end, "recordedDate": recorded or start,
        "code": {"coding": [{"code": code, "system": system}]}}


def visit(pid="p", rid="op", start="2025-02-01", end="", code="AMB", system="http://terminology.hl7.org/CodeSystem/v3-ActCode"):
    return {"resourceType": "Encounter", "id": rid, "subject": {"reference": "urn:uuid:" + pid},
        "class": {"code": code, "system": system}, "period": {"start": start, "end": end}}


def bp(rid="bp", pid="p", when="2025-09-01", systolic="124", diastolic="92", unit="mm[Hg]",
       panel_system="http://loinc.org", component_system="http://loinc.org", unit_system="http://unitsofmeasure.org"):
    components = []
    # Deliberately diastolic first, opposite to MT056 string order.
    for code, value in (("8462-4", diastolic), ("8480-6", systolic)):
        if value is not None:
            components.append({"code": {"coding": [{"code": code, "system": component_system}]},
                "valueQuantity": {"value": Decimal(value), "code": unit, "system": unit_system, "unit": "mmHg"}})
    return {"resourceType": "Observation", "id": rid, "subject": {"reference": "urn:uuid:" + pid},
        "code": {"coding": [{"code": "85354-9", "system": panel_system}]}, "effectiveDateTime": when,
        "status": "final", "component": components}


class IndependentReference(unittest.TestCase):
    def result(self, *extra, base=None):
        resources = [patient(), diagnosis(), visit()] if base is None else base
        source = calculate.collect(resources + list(extra))
        rows, summary = calculate.indicator(source)
        return source, rows, summary

    def test_D4_components_have_independent_daily_minima(self):
        _, rows, _ = self.result(bp("first", systolic="160", diastolic="80"),
                                 bp("second", systolic="120", diastolic="90"))
        self.assertEqual((rows[0]["systolic"], rows[0]["diastolic"], rows[0]["controlled"]), ("120", "80", "1"))

    def test_D3_D5_inpatient_and_emergency_end_inclusive_then_last_day(self):
        for code in ("IMP", "EMER"):
            with self.subTest(code=code):
                _, rows, _ = self.result(bp("earlier", when="2025-09-01", systolic="145", diastolic="75"),
                    visit(rid="blocked", start="2025-09-02", end="2025-09-03", code=code),
                    bp("excluded", when="2025-09-03", systolic="90", diastolic="60"))
                self.assertEqual(rows[0]["last_bp_date"], "2025-09-01")
                self.assertEqual(rows[0]["reason"], "수축기 140 이상")

    def test_D3_inpatient_missing_end_means_start_day_only(self):
        _, rows, _ = self.result(visit(rid="ip", start="2025-09-01", code="IMP"),
            bp("earlier", when="2025-08-01", systolic="120", diastolic="70"),
            bp("excluded", when="2025-09-01", systolic="160", diastolic="95"))
        self.assertEqual(rows[0]["last_bp_date"], "2025-08-01")
        _, rows, _ = self.result(visit(rid="ip", start="2025-09-01", code="IMP"),
            bp("excluded", when="2025-09-01", systolic="160", diastolic="95"),
            bp("valid", when="2025-09-02", systolic="120", diastolic="70"))
        self.assertEqual(rows[0]["controlled"], "1")

    def test_D5_latest_day_overrides_earlier_better_values(self):
        _, rows, _ = self.result(bp("old", when="2025-08-01", systolic="120", diastolic="70"),
                                 bp("new", systolic="145", diastolic="75"))
        self.assertEqual((rows[0]["systolic"], rows[0]["reason"]), ("145", "수축기 140 이상"))

    def test_D6_exact_thresholds_are_not_controlled(self):
        for systolic, diastolic, reason in (("140", "80", "수축기 140 이상"), ("120", "90", "이완기 90 이상")):
            with self.subTest(systolic=systolic, diastolic=diastolic):
                _, rows, _ = self.result(bp(systolic=systolic, diastolic=diastolic))
                self.assertEqual((rows[0]["controlled"], rows[0]["reason"]), ("0", reason))

    def test_D6_fractional_values_are_not_rounded_before_threshold(self):
        _, rows, _ = self.result(bp(systolic="139.999", diastolic="89.999"))
        self.assertEqual((rows[0]["systolic"], rows[0]["diastolic"], rows[0]["controlled"]), ("139.999", "89.999", "1"))

    def test_D3_D6_missing_and_partial_priority_and_unusable_day(self):
        _, rows, _ = self.result()
        self.assertEqual(rows[0]["reason"], "혈압 없음")
        _, rows, _ = self.result(bp(systolic="150", diastolic=None))
        self.assertEqual(rows[0]["reason"], "마지막 날에 한쪽 값만")
        _, rows, _ = self.result(bp("valid", systolic="120", diastolic="70"),
            bp("bad", when="2025-09-02", systolic="150", diastolic="95", unit="kPa"))
        self.assertEqual(rows[0]["last_bp_date"], "2025-09-01")

    def test_D1_literal_day_is_not_utc_conversion(self):
        _, rows, _ = self.result(bp(when="2025-09-30T23:59:59-12:00", systolic="120", diastolic="70"))
        self.assertEqual(rows[0]["last_bp_date"], "2025-09-30")

    def test_D2_age_onset_abatement_and_outpatient_boundaries(self):
        cases = [([patient(birth="2008-01-01"), diagnosis(), visit()], 0, 0),
                 ([patient(birth="1940-12-31"), diagnosis(), visit()], 1, 1),
                 ([patient(birth="1939-12-31"), diagnosis(), visit()], 0, 0),
                 ([patient(), diagnosis(start="2025-06-30"), visit()], 1, 1),
                 ([patient(), diagnosis(start="2025-07-01"), visit()], 0, 0),
                 ([patient(), diagnosis(end="2024-12-31"), visit()], 0, 0),
                 ([patient(), diagnosis(end="2025-01-01"), visit()], 1, 1),
                 ([patient(), diagnosis(), visit(start="2025-10-01")], 0, 1)]
        for base, sep, dec in cases:
            with self.subTest(sep=sep, dec=dec, base=cases.index((base, sep, dec))):
                _, _, summaries = self.result(base=base)
                self.assertEqual([int(r["denominator"]) for r in summaries], [sep, dec])

    def test_D2_D7_multiple_visits_do_not_duplicate_and_death_not_excluded(self):
        deceased = patient(); deceased["deceasedDateTime"] = "2025-03-01"
        _, rows, _ = self.result(visit(rid="second"), bp(), base=[deceased, diagnosis(), visit()])
        self.assertEqual(len(rows), 2)

    def test_D7_zero_denominator_keeps_summary_and_null_rate(self):
        _, rows, summary = self.result(base=[patient(birth="2010-01-01")])
        self.assertFalse(rows)
        self.assertEqual([(r["denominator"], r["numerator"], r["rate"]) for r in summary], [("0", "0", ""), ("0", "0", "")])

    def test_ADR0006_late_record_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ADR0006"):
            self.result(base=[patient(), diagnosis(recorded="2025-10-01"), visit()])

    def test_ADR0013_fractional_components_and_non_target_diagnosis_preserved(self):
        source, _, _ = self.result(bp(systolic="109.51", diastolic="76.761"), diagnosis(rid="other", code="other"))
        self.assertEqual(source["fractional_panels"], 1)
        self.assertEqual(len(source["diagnoses"]), 2)
        facts = calculate.omop_reference(source)
        values = {r["reference_code"]: r["value_as_number"] for r in facts if r["omop_table"] == "measurement"}
        self.assertEqual(values, {"8480-6": "109.51", "8462-4": "76.761"})
        self.assertEqual(sum(r["omop_table"] == "condition_occurrence" for r in facts), 1)

    def test_ADR0008_0011_observation_period_uses_carried_ends_not_calendar(self):
        source, _, _ = self.result(visit(rid="ip", start="2025-10-01", end="2026-02-03", code="IMP"))
        periods = [r for r in calculate.omop_reference(source) if r["omop_table"] == "observation_period"]
        self.assertEqual((periods[0]["start_date"], periods[0]["end_date"]), ("2020-01-01", "2026-02-03"))

    def test_R01_D2_diagnosis_namespace_is_required_and_unmapped_source_retained(self):
        for system in ("urn:example:unrelated", ""):
            with self.subTest(system=system):
                source, rows, summaries = self.result(base=[patient(), diagnosis(system=system), visit()])
                facts = calculate.omop_reference(source)
                self.assertFalse(any(r["omop_table"] == "condition_occurrence" for r in facts))
                self.assertFalse(rows)
                self.assertEqual([r["denominator"] for r in summaries], ["0", "0"])
                self.assertEqual(len(source["diagnoses"]), 1)
                self.assertIn("diagnosis:dx:0", source["source_fact_hashes"])

    def test_R01_D3_panel_namespace_changes_projection_and_not_bp_meaning(self):
        original, _, _ = self.result(bp())
        for system in ("urn:example:unrelated", ""):
            with self.subTest(system=system):
                source, rows, _ = self.result(bp(panel_system=system))
                self.assertNotEqual(original["source_fact_hashes"], source["source_fact_hashes"])
                self.assertEqual(source["unapproved_panels"], 1)
                facts = [r for r in calculate.omop_reference(source) if r["omop_table"] == "measurement"]
                self.assertEqual(len(facts), 2)
                self.assertEqual({r["concept_id"] for r in facts}, {"0"})
                self.assertEqual(rows[0]["reason"], "혈압 없음")

    def test_R01_D3_component_and_unit_namespaces_do_not_infer_same_code_meaning(self):
        for changes in ({"component_system": "urn:example:unrelated"}, {"component_system": ""},
                        {"unit_system": "urn:example:unrelated"}, {"unit_system": ""}, {"unit": "mmHg"}):
            with self.subTest(changes=changes):
                source, rows, _ = self.result(bp(**changes))
                self.assertEqual(rows[0]["reason"], "혈압 없음")
                facts = [r for r in calculate.omop_reference(source) if r["omop_table"] == "measurement"]
                self.assertEqual(len(facts), 2)
                field = "concept_id" if "component_system" in changes else "unit_concept_id"
                self.assertEqual({r[field] for r in facts}, {"0"})

    def test_R01_D2_outpatient_namespace_is_required(self):
        source, rows, summary = self.result(base=[patient(), diagnosis(), visit(system="urn:example:unrelated")])
        self.assertFalse(rows)
        self.assertEqual([r["denominator"] for r in summary], ["0", "0"])
        facts = [r for r in calculate.omop_reference(source) if r["omop_table"] == "visit_occurrence"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["concept_id"], "0")

    def test_R01_D3_unrelated_IMP_namespace_does_not_create_inpatient_exclusion(self):
        _, rows, _ = self.result(bp(systolic="120", diastolic="70"),
            visit(rid="not-ip", start="2025-09-01", code="IMP", system="urn:example:unrelated"))
        self.assertEqual(rows[0]["controlled"], "1")

    def test_R01_D1_all_original_panel_coding_namespaces_are_fingerprinted(self):
        first = bp()
        first["code"]["coding"].append({"code": "unmapped-extra", "system": "urn:example:first"})
        second = copy.deepcopy(first); second["code"]["coding"][1]["system"] = "urn:example:second"
        a = calculate.collect([patient(), first]); b = calculate.collect([patient(), second])
        self.assertNotEqual(a["source_fact_hashes"], b["source_fact_hashes"])


    def test_ADR0013_D2_kcd_candidate_is_not_original_clinical_evidence(self):
        source = calculate.collect([patient(), diagnosis(), visit(), bp()])
        baseline = calculate.indicator(source)
        for candidate in ("I109", "I10", "", "urn:example:unrelated"):
            with self.subTest(candidate=candidate):
                source["diagnoses"][0]["kcd_candidate_code"] = candidate
                self.assertEqual(calculate.indicator(source), baseline)
        source["diagnoses"][0]["system"] = "urn:example:unrelated"
        source["diagnoses"][0]["kcd_candidate_code"] = "I109"
        self.assertFalse(calculate.indicator(source)[0])
        self.assertFalse([r for r in calculate.omop_reference(source)
                          if r["omop_table"] == "condition_occurrence"])


class CheckerMutations(unittest.TestCase):
    def setUp(self):
        local = Path(__file__).resolve().parents[1] / ".local/FHIR-LINE-A-PRIME"
        local.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="contract-", dir=local)
        self.root = Path(self.temp.name)
        self.expected, self.actual = self.root / "expected", self.root / "actual"
        self.expected.mkdir(); self.actual.mkdir()
        source = calculate.collect([patient(), diagnosis(), visit(), bp(systolic="109.51", diastolic="76.761")])
        person, summary = calculate.indicator(source)
        self.rows = {"person.csv": person, "summary.csv": summary, "omop_facts.csv": calculate.omop_reference(source)}
        for name, rows in self.rows.items():
            calculate.write_csv(self.expected / name, check.CONTRACTS[name]["fields"], rows)
            calculate.write_csv(self.actual / name, check.CONTRACTS[name]["fields"], rows)

    def tearDown(self):
        self.temp.cleanup()

    def compare(self, name, rows):
        calculate.write_csv(self.actual / name, check.CONTRACTS[name]["fields"], rows)
        return check.compare_csv(self.expected / name, self.actual / name, name)

    def test_ADR0013_positive_control_all_columns_equal(self):
        for name in self.rows:
            self.assertTrue(check.compare_csv(self.expected / name, self.actual / name, name)["ok"])

    def comparison_fixture(self):
        facts = {"value": "109.51"}
        source = self.root / "source_facts.jsonl"
        source.write_text(json.dumps({"kind": "bp_component", "source_row_key": "bp:8480-6", "facts": facts}) + "\n")
        # Handwritten route metadata, independent of the generator's metadata function.
        manifest = {"contract": "a-prime-preserve-all-3",
            "source_fact_hashes": {"bp_component:bp:8480-6": calculate.canonical_hash(facts)},
            "mapping": {"comparison_route": "preserved_source_clinical", "clinical_basis": {
                "status": "accepted_existing_source_mapping", "system": "http://snomed.info/sct",
                "code": "59621000", "target_concept_id": 320128, "decision": "0009",
                "uses_kcd_candidate": False},
                "kcd_candidate": {"candidate_claim_code": "I109", "kcd_edition_for_2025": "KCD-8",
                    "edition_context": "measurement year; not original claim edition",
                    "kcd_dot_normalization": "unverified", "kcd_to_omop": "unverified",
                    "mt056_decimal_supplement": "unverified", "product_mapping_gate": "blocked",
                    "vocabulary_release": "", "mapping_relationship": "", "target_concept_id": None,
                    "usage": "annotation_only"}}}
        self.save_manifest(manifest)
        return manifest, source

    def save_manifest(self, manifest):
        (self.expected / "manifest.json").write_text(json.dumps(manifest))

    def test_ADR0013_clinical_route_accepts_original_basis_with_kcd_unverified(self):
        manifest, source = self.comparison_fixture()
        result = check.compare_all(self.expected, self.actual, source, route="preserved_source_clinical")
        self.assertTrue(result["data_equal"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["route_readiness"]["clinical_basis_ok"])
        self.assertFalse(result["route_readiness"]["kcd_route_ok"])
        self.assertEqual(manifest["mapping"]["kcd_candidate"]["kcd_to_omop"], "unverified")

    def test_ADR0013_clinical_basis_must_be_exact_original_system_code_and_decision(self):
        manifest, source = self.comparison_fixture()
        for field, value in (("system", "urn:example:unrelated"), ("code", "I109"),
                             ("target_concept_id", 0), ("decision", ""),
                             ("status", "unverified"), ("uses_kcd_candidate", True),
                             ("uses_kcd_candidate", 0)):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(manifest)
                changed["mapping"]["clinical_basis"][field] = value
                self.save_manifest(changed)
                result = check.compare_all(self.expected, self.actual, source, route="preserved_source_clinical")
                self.assertTrue(result["data_equal"])
                self.assertFalse(result["ok"])

    def test_ADR0013_candidate_code_is_not_used_to_approve_clinical_route(self):
        manifest, source = self.comparison_fixture()
        for candidate in ("I109", "I10", "", "urn:example:unrelated"):
            with self.subTest(candidate=candidate):
                manifest["mapping"]["kcd_candidate"]["candidate_claim_code"] = candidate
                self.save_manifest(manifest)
                self.assertTrue(check.compare_all(self.expected, self.actual, source,
                                                 route="preserved_source_clinical")["ok"])

    def test_ADR0013_kcd_route_is_not_approved_by_candidate_or_fabricated_verified_status(self):
        manifest, source = self.comparison_fixture()
        for fabricated in (False, True):
            with self.subTest(fabricated=fabricated):
                if fabricated:
                    manifest["mapping"]["kcd_candidate"].update(kcd_to_omop="verified", product_mapping_gate="approved")
                self.save_manifest(manifest)
                result = check.compare_all(self.expected, self.actual, source, route="kcd_to_omop")
                self.assertTrue(result["data_equal"])
                self.assertFalse(result["ok"])
                self.assertFalse(result["route_readiness"]["kcd_route_ok"])
                if fabricated:
                    self.assertFalse(check.compare_all(self.expected, self.actual, source,
                                                      route="preserved_source_clinical")["ok"])

    def test_ADR0013_route_must_be_explicit_and_match_manifest(self):
        manifest, source = self.comparison_fixture()
        with self.assertRaises(TypeError):
            check.compare_all(self.expected, self.actual, source)
        with self.assertRaisesRegex(ValueError, "route"):
            check.compare_all(self.expected, self.actual, source, route="all")
        manifest["mapping"]["comparison_route"] = "kcd_to_omop"
        self.save_manifest(manifest)
        self.assertFalse(check.compare_all(self.expected, self.actual, source,
                                         route="preserved_source_clinical")["ok"])

    def test_ADR0013_approved_clinical_basis_does_not_hide_data_mismatch(self):
        _, source = self.comparison_fixture()
        rows = copy.deepcopy(self.rows["person.csv"])
        rows[0]["systolic"] = "110"
        self.compare("person.csv", rows)
        result = check.compare_all(self.expected, self.actual, source, route="preserved_source_clinical")
        self.assertTrue(result["route_readiness"]["clinical_basis_ok"])
        self.assertFalse(result["data_equal"])
        self.assertFalse(result["ok"])

    def test_ADR0013_actual_cannot_alias_expected_path_symlink_or_hardlink(self):
        original = self.expected / "person.csv"
        symbolic = self.root / "symbolic.csv"; symbolic.symlink_to(original)
        hard = self.root / "hard.csv"; hard.hardlink_to(original)
        for actual in (original, symbolic, hard):
            with self.subTest(alias=actual.name), self.assertRaisesRegex(ValueError, "aliases"):
                check.compare_csv(original, actual, "person.csv")

    def test_ADR0013_duplicate_json_field_is_rejected(self):
        manifest = self.root / "duplicate-manifest.json"
        actual = self.root / "duplicate-facts.jsonl"
        manifest.write_text(json.dumps({"source_fact_hashes": {"bp_component:bp:8480-6": calculate.canonical_hash({"value": "109.51"})}}))
        actual.write_text('{"kind":"bp_component","source_row_key":"bp:8480-6","facts":{"value":"200","value":"109.51"}}\n')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            check.compare_source_facts(manifest, actual)

    def test_ADR0013_generator_rejects_protected_and_existing_outputs(self):
        repo = Path(__file__).resolve().parents[1]
        for output in (repo / "expected", repo / "answer_key", repo / ".local/FHIR-LINE-01/new-output"):
            with self.subTest(output=output.name), self.assertRaisesRegex(ValueError, "output must"):
                calculate.generate(self.root, output)
        output = self.root / "existing"; output.mkdir(); (output / "marker").write_text("unchanged")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            calculate.generate(self.root, output)
        self.assertEqual((output / "marker").read_text(), "unchanged")

    def test_D1_D7_each_expected_column_mutation_is_rejected(self):
        for name, rows in self.rows.items():
            for field in check.CONTRACTS[name]["fields"]:
                with self.subTest(file=name, column=field):
                    altered = copy.deepcopy(rows)
                    value = altered[0][field]
                    contract = check.CONTRACTS[name]
                    if field in contract["numbers"] | contract["integers"]:
                        altered[0][field] = str(Decimal(value or "0") + 1)
                    elif field in contract["dates"]:
                        altered[0][field] = "2024-01-02"
                    else:
                        altered[0][field] = value + "_changed"
                    self.assertFalse(self.compare(name, altered)["ok"])

    def test_D3_component_swap_and_decimal_rounding_are_rejected(self):
        rows = copy.deepcopy(self.rows["person.csv"])
        rows[0]["systolic"], rows[0]["diastolic"] = rows[0]["diastolic"], rows[0]["systolic"]
        self.assertFalse(self.compare("person.csv", rows)["ok"])
        rows = copy.deepcopy(self.rows["omop_facts.csv"])
        next(r for r in rows if r["value_as_number"] == "109.51")["value_as_number"] = "110"
        self.assertFalse(self.compare("omop_facts.csv", rows)["ok"])

    def test_D3_D5_omitted_exclusion_or_wrong_last_day_is_rejected(self):
        for changes in ({"systolic": "180", "diastolic": "100", "controlled": "0", "reason": "수축기 140 이상"},
                        {"last_bp_date": "2025-08-01"}):
            rows = copy.deepcopy(self.rows["person.csv"]); rows[0].update(changes)
            self.assertFalse(self.compare("person.csv", rows)["ok"])

    def test_ADR0011_omitted_duplicate_and_empty_actual_are_rejected(self):
        for name, rows in self.rows.items():
            with self.subTest(file=name):
                self.assertFalse(self.compare(name, rows[1:])["ok"])
                self.assertFalse(self.compare(name, [])["ok"])
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    self.compare(name, rows + rows[:1])

    def test_ADR0013_derived_population_aggregation_is_rejected(self):
        rows = copy.deepcopy(self.rows["summary.csv"])
        for row in rows:
            row["hospital"] = "A+A_PRIME"
            row["denominator"] = str(int(row["denominator"]) * 2)
        self.assertFalse(self.compare("summary.csv", rows)["ok"])

    def test_D6_malformed_and_nonfinite_numeric_cells_are_rejected(self):
        for field, value in (("systolic", "NaN"), ("diastolic", "Infinity"), ("controlled", "1.0"), ("systolic", "not-a-number"), ("systolic", "1_20")):
            rows = copy.deepcopy(self.rows["person.csv"]); rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.compare("person.csv", rows)

    def test_ADR0013_source_hash_detects_every_field_missing_and_duplicate(self):
        facts = {"person_id": "p", "effective": "2025-09-01T23:00:00-02:00", "value": "109.51", "unit_code": "mm[Hg]", "code": "8480-6", "system": "http://loinc.org", "status": "final", "panel_code": "85354-9", "panel_system": "http://loinc.org", "panel_codings": '[{"code":"85354-9","system":"http://loinc.org"}]'}
        original = {"kind": "bp_component", "source_row_key": "b:8480-6", "facts": facts}
        manifest, actual = self.root / "manifest.json", self.root / "source_facts.jsonl"
        manifest.write_text(json.dumps({"source_fact_hashes": {"bp_component:b:8480-6": calculate.canonical_hash(facts)}}))

        def write(rows):
            actual.write_text("".join(json.dumps(row) + "\n" for row in rows))
        write([original])
        self.assertTrue(check.compare_source_facts(manifest, actual)["ok"])
        for field in facts:
            row = copy.deepcopy(original); row["facts"][field] += "_changed"; write([row])
            self.assertFalse(check.compare_source_facts(manifest, actual)["ok"])
        write([]); self.assertFalse(check.compare_source_facts(manifest, actual)["ok"])
        write([original, original])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check.compare_source_facts(manifest, actual)

    def test_R01_D1_handwritten_panel_projection_matches_source_and_detects_change(self):
        source = calculate.collect([patient(), bp(systolic="120", diastolic=None)])
        facts = {"person_id": "p", "observation_id": "bp", "effective": "2025-09-01", "status": "final",
            "panel_code": "85354-9", "panel_system": "http://loinc.org",
            "panel_codings": '[{"code":"85354-9","system":"http://loinc.org"}]',
            "code": "8480-6", "system": "http://loinc.org", "value": "120", "unit_code": "mm[Hg]",
            "unit_system": "http://unitsofmeasure.org", "unit_display": "mmHg"}
        manifest = self.root / "panel-manifest.json"; actual = self.root / "panel-facts.jsonl"
        manifest.write_text(json.dumps({"source_fact_hashes": {"bp_component:bp:8480-6": source["source_fact_hashes"]["bp_component:bp:8480-6"]}}))
        original = {"kind": "bp_component", "source_row_key": "bp:8480-6", "facts": facts}
        actual.write_text(json.dumps(original) + "\n")
        self.assertTrue(check.compare_source_facts(manifest, actual)["ok"])
        for field in ("panel_system", "panel_codings"):
            changed = copy.deepcopy(original); changed["facts"][field] = "urn:example:unrelated"
            actual.write_text(json.dumps(changed) + "\n")
            self.assertFalse(check.compare_source_facts(manifest, actual)["ok"])

    def test_ADR0013_lock_detects_hash_write_bits_and_missing_members(self):
        expected = self.root / "expected_a_prime"; expected.mkdir()
        code = self.root / "answer_key_a_prime"; code.mkdir()
        paths = [self.root / name for name in sorted(check.LOCK_FILES)]
        listing = expected / "SHA256SUMS"
        for path in paths:
            path.write_text("fixture\n")
        listing.write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + str(p.relative_to(self.root)) + "\n" for p in paths))
        try:
            for p in paths + [listing]: p.chmod(0o444)
            expected.chmod(0o555); code.chmod(0o555)
            self.assertTrue(check.verify_lock(expected)["ok"])
            paths[0].chmod(0o644)
            with self.assertRaisesRegex(ValueError, "permission"):
                check.verify_lock(expected)
            paths[0].write_text("mutated\n"); paths[0].chmod(0o444)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                check.verify_lock(expected)
            paths[0].chmod(0o644); paths[0].write_text("fixture\n"); paths[0].chmod(0o444)
            listing.chmod(0o644); listing.write_text(listing.read_text().splitlines()[0] + "\n"); listing.chmod(0o444)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                check.verify_lock(expected)
        finally:
            expected.chmod(0o755); code.chmod(0o755)
            for p in paths + [listing]: p.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
