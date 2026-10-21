#!/usr/bin/env python3
"""D1-D7 / ADR0011,0013: read-only comparison; never rewrite expected files.

CSV numeric/date syntax is validated here. Database-native types remain the
responsibility of the existing ladder and the future actual-output extractor.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

CONTRACTS = {
    "person.csv": {
        "fields": ("hospital", "as_of_label", "person_id", "as_of", "last_bp_date", "systolic", "diastolic", "controlled", "reason"),
        "key": ("hospital", "as_of_label", "person_id"),
        "integers": {"controlled"}, "numbers": {"systolic", "diastolic"},
        "dates": {"as_of", "last_bp_date"},
        "nullable": {"last_bp_date", "systolic", "diastolic"},
    },
    "summary.csv": {
        "fields": ("hospital", "as_of_label", "denominator", "numerator", "rate"),
        "key": ("hospital", "as_of_label"), "integers": {"denominator", "numerator"},
        "numbers": {"rate"}, "dates": set(), "nullable": {"rate"},
    },
    "omop_facts.csv": {
        "fields": ("hospital", "omop_table", "source_person_id", "source_row_key", "start_date", "end_date", "concept_id", "value_as_number", "unit_concept_id", "reference_code", "reference_system", "reference_unit", "year_of_birth", "gender_source_value", "measurement_year"),
        "key": ("hospital", "omop_table", "source_row_key"),
        "integers": {"concept_id", "unit_concept_id", "year_of_birth", "measurement_year"},
        "numbers": {"value_as_number"}, "dates": {"start_date", "end_date"},
        "nullable": {"start_date", "end_date", "concept_id", "unit_concept_id", "value_as_number", "reference_code", "reference_system", "reference_unit", "year_of_birth", "gender_source_value", "measurement_year"},
    },
}

LOCK_FILES = {
    "expected_a_prime/person.csv", "expected_a_prime/summary.csv", "expected_a_prime/omop_facts.csv",
    "expected_a_prime/manifest.json", "answer_key_a_prime/calculate.py", "answer_key_a_prime/check.py",
    "answer_key_a_prime/test_contract.py", "answer_key_a_prime/README.md",
}
CLINICAL_ROUTE = "preserved_source_clinical"
KCD_ROUTE = "kcd_to_omop"


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def read_manifest(path):
    result = json.loads(Path(path).read_text(), object_pairs_hook=strict_object)
    if not isinstance(result, dict):
        raise ValueError("manifest must be an object")
    return result


def mapping_readiness(manifest, route):
    """D2 / ADR0009,0013: scope success to preserved original meaning, never KCD."""
    if route not in (CLINICAL_ROUTE, KCD_ROUTE):
        raise ValueError("unknown comparison route")
    content = read_manifest(manifest)
    mapping = content.get("mapping", {})
    if not isinstance(mapping, dict):
        raise ValueError("invalid mapping metadata")
    basis, candidate = mapping.get("clinical_basis", {}), mapping.get("kcd_candidate", {})
    if not isinstance(basis, dict) or not isinstance(candidate, dict):
        raise ValueError("invalid route metadata")
    clinical_ok = (
        basis.get("status") == "accepted_existing_source_mapping"
        and basis.get("system") == "http://snomed.info/sct"
        and basis.get("code") == "59621000"
        and type(basis.get("target_concept_id")) is int
        and basis["target_concept_id"] == 320128
        and basis.get("decision") == "0009"
        and basis.get("uses_kcd_candidate") is False
    )
    # This contract has no accepted KCD mapping. A fabricated verified flag cannot add one.
    candidate_consistent = all(candidate.get(key) == value for key, value in {
        "usage": "annotation_only", "kcd_dot_normalization": "unverified",
        "kcd_to_omop": "unverified", "product_mapping_gate": "blocked",
        "mt056_decimal_supplement": "unverified", "vocabulary_release": "",
        "mapping_relationship": "",
    }.items()) and "target_concept_id" in candidate and candidate["target_concept_id"] is None
    declared = mapping.get("comparison_route")
    contract_ok = content.get("contract") == "a-prime-preserve-all-3" and declared == CLINICAL_ROUTE
    return {
        "ok": route == CLINICAL_ROUTE and contract_ok and clinical_ok and candidate_consistent,
        "route": route, "manifest_route": declared, "manifest_contract_ok": contract_ok,
        "clinical_basis_ok": clinical_ok, "kcd_metadata_consistent": candidate_consistent,
        "kcd_route_ok": False, "kcd_to_omop": candidate.get("kcd_to_omop", "missing"),
        "kcd_product_mapping_gate": candidate.get("product_mapping_gate", "missing"),
        "scope": "preserved source clinical comparison only; no KCD linkage or implementation acceptance",
    }


def verify_lock(expected):
    """ADR0013: both hash content and all write bits must be protected."""
    expected = Path(expected).absolute()
    if expected.is_symlink() or expected.resolve() != expected:
        raise ValueError("symlink in expected directory")
    if expected.name != "expected_a_prime":
        raise ValueError("invalid expected directory name")
    root = expected.parent
    listing = expected / "SHA256SUMS"
    if listing.is_symlink() or (root / "answer_key_a_prime").is_symlink():
        raise ValueError("symlink in locked directories or manifest")
    paths = {}
    for line in listing.read_text().splitlines():
        checksum, name = line.split(maxsplit=1)
        if not re.fullmatch(r"[0-9a-f]{64}", checksum) or name not in LOCK_FILES or name in paths:
            raise ValueError("invalid lock entry")
        path = root / name
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("symlink in locked paths")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("locked file hash mismatch")
        paths[name] = path
    if set(paths) != LOCK_FILES:
        raise ValueError("incomplete lock manifest")
    for path in [*paths.values(), listing, expected, root / "answer_key_a_prime"]:
        if path.stat().st_mode & 0o222:
            raise ValueError("write permission in locked reference")
    return {"ok": True, "files": len(paths), "manifest_and_directories_read_only": True}


def parse_cell(value, field, contract):
    if value is None:
        raise ValueError("missing CSV cell")
    if value == "":
        if field not in contract["nullable"]:
            raise ValueError("required cell is empty: " + field)
        return None
    if field in contract["integers"]:
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
            raise ValueError("invalid integer: " + field)
        return int(value)
    if field in contract["numbers"]:
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value):
            raise ValueError("invalid numeric syntax: " + field)
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError("invalid number: " + field) from None
        if not number.is_finite() or value != value.strip():
            raise ValueError("invalid finite number: " + field)
        return number
    if field in contract["dates"]:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("invalid date: " + field)
        return date.fromisoformat(value)
    return value


def load_csv(path, contract):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(contract["fields"]):
            raise ValueError("CSV columns/order mismatch")
        rows = list(reader)
    index = {}
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("CSV width mismatch")
        parsed = {field: parse_cell(row[field], field, contract) for field in contract["fields"]}
        key = tuple(parsed[field] for field in contract["key"])
        if key in index:
            raise ValueError("duplicate comparison key")
        index[key] = parsed
    return index


def compare_csv(expected, actual, name):
    if Path(expected).samefile(actual):
        raise ValueError("actual output aliases expected file")
    contract = CONTRACTS[name]
    expected_rows, actual_rows = load_csv(expected, contract), load_csv(actual, contract)
    missing = expected_rows.keys() - actual_rows.keys()
    extra = actual_rows.keys() - expected_rows.keys()
    mismatches = {}
    for key in expected_rows.keys() & actual_rows.keys():
        for field in contract["fields"]:
            if expected_rows[key][field] != actual_rows[key][field]:
                mismatches[field] = mismatches.get(field, 0) + 1
    # Never print complete patient/source keys or payloads in reports.
    return {"ok": not (missing or extra or mismatches), "expected_rows": len(expected_rows),
        "actual_rows": len(actual_rows), "missing": len(missing), "extra": len(extra),
        "mismatches_by_column": mismatches}


def compare_source_facts(manifest, actual):
    expected = read_manifest(manifest)["source_fact_hashes"]
    actual_hashes = {}
    with Path(actual).open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line, object_pairs_hook=strict_object)
            if not isinstance(row, dict) or set(row) != {"kind", "source_row_key", "facts"}:
                raise ValueError("source projection columns mismatch")
            if not isinstance(row["kind"], str) or not isinstance(row["source_row_key"], str):
                raise ValueError("invalid source projection key")
            facts = row["facts"]
            if not isinstance(facts, dict) or any(not isinstance(v, str) for v in facts.values()):
                raise ValueError("source projection fields must be strings")
            key = row["kind"] + ":" + row["source_row_key"]
            if key in actual_hashes:
                raise ValueError("duplicate source projection key")
            body = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            actual_hashes[key] = hashlib.sha256(body.encode()).hexdigest()
    missing, extra = expected.keys() - actual_hashes.keys(), actual_hashes.keys() - expected.keys()
    changed = sum(expected[k] != actual_hashes[k] for k in expected.keys() & actual_hashes.keys())
    return {"ok": not (missing or extra or changed), "expected_rows": len(expected),
        "actual_rows": len(actual_hashes), "missing": len(missing), "extra": len(extra), "changed": changed}


def compare_all(expected, actual, source_facts, *, route):
    result = {name: compare_csv(Path(expected) / name, Path(actual) / name, name) for name in CONTRACTS}
    result["source_facts"] = compare_source_facts(Path(expected) / "manifest.json", source_facts)
    data_equal = all(r["ok"] for r in result.values())
    readiness = mapping_readiness(Path(expected) / "manifest.json", route)
    return {"route": route, "ok": data_equal and readiness["ok"], "data_equal": data_equal,
            "route_readiness": readiness, "comparisons": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--source-facts", type=Path, required=True)
    parser.add_argument("--route", choices=(CLINICAL_ROUTE, KCD_ROUTE), required=True,
                        help="explicit scope; kcd_to_omop remains unsupported and fails this contract")
    args = parser.parse_args()
    try:
        verify_lock(args.expected)
        result = compare_all(args.expected, args.actual, args.source_facts, route=args.route)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"comparison failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    parser.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
