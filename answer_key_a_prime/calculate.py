#!/usr/bin/env python3
"""D1-D7 / ADR 0004-0011,0013: independent source-only A-prime reference.

No product imports, database reads, exporter parsing, or existing expected inputs.
The KCD mapping gate remains unverified; condition concepts refer to original A.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

HOSPITAL = "A_PRIME"
YEAR = 2025
AS_OFS = (("sep30", "09-30"), ("dec31", "12-31"))
SNOMED_SYSTEM = "http://snomed.info/sct"
LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"
VISIT_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
BP_CODES = {"8480-6": 3004249, "8462-4": 3012888}
VISIT_CODES = {"AMB": 9202, "IMP": 9201, "EMER": 9203, "HH": 0, "VR": 0}
UNIT_CODES = {"mm[Hg]": 8876}
PERSON_FIELDS = ("hospital", "as_of_label", "person_id", "as_of", "last_bp_date",
                 "systolic", "diastolic", "controlled", "reason")
SUMMARY_FIELDS = ("hospital", "as_of_label", "denominator", "numerator", "rate")
FACT_FIELDS = ("hospital", "omop_table", "source_person_id", "source_row_key",
               "start_date", "end_date", "concept_id", "value_as_number",
               "unit_concept_id", "reference_code", "reference_system",
               "reference_unit", "year_of_birth", "gender_source_value", "measurement_year")


def day(value):
    """D1: written calendar day, without timezone conversion."""
    if not value:
        return ""
    result = str(value)[:10]
    date.fromisoformat(result)
    return result


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean blood pressure")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non-finite blood pressure")
    return result


def numeric_text(value):
    return "" if value is None else format(number(value), "f")


def canonical_hash(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def reference(resource):
    return resource["subject"]["reference"].rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def codes(resource):
    return resource.get("code", {}).get("coding", [])


def is_hypertension(row):
    """R01 / D2: source code plus namespace, never code text alone."""
    return row["code"] == "59621000" and row["system"] == SNOMED_SYSTEM


def visit_concept(row):
    return VISIT_CODES.get(row["code"], 0) if row["system"] == VISIT_SYSTEM else 0


def bp_concept(row):
    return BP_CODES.get(row["code"], 0) if row["panel_accepted"] and row["system"] == LOINC_SYSTEM else 0


def unit_concept(row):
    return UNIT_CODES.get(row["unit"], 0) if row["unit_system"] == UCUM_SYSTEM else 0


def collect(resources):
    """Preserve selected source facts before deriving indicator/OMOP references."""
    people, visits, diagnoses, pressures, fingerprints = {}, [], [], [], {}
    resource_counts = Counter()
    panel_count = fractional_panels = unapproved_panels = 0
    statuses = Counter()

    def source_fact(kind, key, facts):
        identity = kind + ":" + key
        if identity in fingerprints:
            raise ValueError("duplicate source fact key")
        if any(not isinstance(v, str) for v in facts.values()):
            raise ValueError("source projection fields must be strings")
        fingerprints[identity] = canonical_hash(facts)

    for r in resources:
        kind = r.get("resourceType", "")
        resource_counts[kind] += 1
        if kind not in ("Patient", "Encounter", "Condition", "Observation"):
            continue
        rid = r["id"]
        if kind == "Patient":
            if rid in people:
                raise ValueError("duplicate patient")
            birth = r["birthDate"]
            people[rid] = {"birth_year": int(birth[:4]), "gender": r.get("gender", "")}
            source_fact("person", rid, {
                "person_id": rid, "birth_date": birth, "gender": r.get("gender", ""),
                "deceased_datetime": r.get("deceasedDateTime", ""),
                "deceased_boolean": str(r.get("deceasedBoolean", "")).lower(),
                "measurement_year": str(YEAR),
            })
        elif kind == "Encounter":
            pid = reference(r)
            period = r.get("period", {})
            start, end = period.get("start", ""), period.get("end", "")
            class_code = r.get("class", {}).get("code", "")
            system = r.get("class", {}).get("system", "")
            if not day(start):
                raise ValueError("visit without start day")
            visits.append({"pid": pid, "key": rid, "code": class_code, "system": system,
                           "start": day(start), "end": day(end) or day(start)})
            source_fact("visit", rid, {"person_id": pid, "class_code": class_code,
                "class_system": system, "start": start, "end": end, "recorded": start})
        elif kind == "Condition":
            pid = reference(r)
            start, end = r.get("onsetDateTime", ""), r.get("abatementDateTime", "")
            recorded = r.get("recordedDate") or start
            if day(recorded) != day(start):
                raise ValueError("ADR0006 late diagnosis record")
            for index, coding in enumerate(codes(r)):
                code, system = coding.get("code", ""), coding.get("system", "")
                diagnoses.append({"pid": pid, "key": rid, "code": code, "system": system,
                                  "start": day(start), "end": day(end)})
                source_fact("diagnosis", rid + ":" + str(index), {
                    "person_id": pid, "condition_id": rid, "coding_index": str(index),
                    "code": code, "system": system, "start": start, "end": end,
                    "recorded": recorded,
                    "clinical_status": json.dumps(r.get("clinicalStatus", {}), sort_keys=True,
                                                   ensure_ascii=False, separators=(",", ":")),
                })
        # Retain same-code candidates; clinical meaning requires the namespaces below.
        elif any(c.get("code") == "85354-9" for c in codes(r)):
            pid, effective = reference(r), r.get("effectiveDateTime", "")
            if not day(effective):
                raise ValueError("blood pressure without effective day")
            panel_count += 1
            statuses[r.get("status", "")] += 1
            panel_codings = [{"code": c.get("code", ""), "system": c.get("system", "")} for c in codes(r)]
            panel = next(c for c in panel_codings if c["code"] == "85354-9")
            panel_accepted = any(c["code"] == "85354-9" and c["system"] == LOINC_SYSTEM for c in panel_codings)
            unapproved_panels += not panel_accepted
            panel_text = json.dumps(panel_codings, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fractional = False
            for component in r.get("component", []):
                quantity = component.get("valueQuantity", {})
                value = number(quantity.get("value"))
                for coding in codes(component):
                    code = coding.get("code", "")
                    if code not in BP_CODES:
                        continue
                    key = rid + ":" + code
                    unit = quantity.get("code", "")
                    pressures.append({"pid": pid, "key": key, "code": code,
                        "system": coding.get("system", ""), "day": day(effective),
                        "value": value, "unit": unit, "unit_system": quantity.get("system", ""),
                        "panel_code": panel["code"], "panel_system": panel["system"],
                        "panel_codings": panel_text, "panel_accepted": panel_accepted})
                    fractional |= value is not None and value != value.to_integral_value()
                    source_fact("bp_component", key, {"person_id": pid,
                        "observation_id": rid, "effective": effective,
                        "status": r.get("status", ""), "panel_code": panel["code"],
                        "panel_system": panel["system"], "panel_codings": panel_text,
                        "code": code, "system": coding.get("system", ""),
                        "value": numeric_text(value), "unit_code": unit,
                        "unit_system": quantity.get("system", ""),
                        "unit_display": quantity.get("unit", "")})
            fractional_panels += fractional
    for row in visits + diagnoses + pressures:
        if row["pid"] not in people:
            raise ValueError("unresolved source person")
    for rows in (visits, pressures):
        if len({r["key"] for r in rows}) != len(rows):
            raise ValueError("duplicate event key")
    return {"people": people, "visits": visits, "diagnoses": diagnoses, "pressures": pressures,
        "source_fact_hashes": fingerprints, "resource_counts": dict(sorted(resource_counts.items())),
        "panels": panel_count, "fractional_panels": fractional_panels,
        "unapproved_panels": unapproved_panels, "statuses": dict(statuses)}


def indicator(source, year=YEAR):
    """D1-D7 / ADR0010: direct Decimal reference, independent of product SQL."""
    person_rows, summary_rows = [], []
    visits, diagnoses, pressures = (defaultdict(list) for _ in range(3))
    for name, index in (("visits", visits), ("diagnoses", diagnoses), ("pressures", pressures)):
        for row in source[name]:
            index[row["pid"]].append(row)
    for label, suffix in AS_OFS:
        as_of, first, cutoff = f"{year}-{suffix}", f"{year}-01-01", f"{year}-06-30"
        current = []
        for pid, person in sorted(source["people"].items()):
            if not 18 <= year - person["birth_year"] <= 85:
                continue
            if not any(is_hypertension(d) and d["start"] and d["start"] <= min(cutoff, as_of)
                       and (not d["end"] or d["end"] >= first) for d in diagnoses[pid]):
                continue
            if not any(visit_concept(v) == 9202 and first <= v["start"] <= as_of for v in visits[pid]):
                continue
            daily = defaultdict(dict)
            for bp in pressures[pid]:
                if not first <= bp["day"] <= as_of or not bp_concept(bp) or unit_concept(bp) != 8876 or bp["value"] is None:
                    continue
                if any(visit_concept(v) in (9201, 9203) and v["start"] <= as_of
                       and v["start"] <= bp["day"] <= v["end"] for v in visits[pid]):
                    continue
                bucket, code = daily[bp["day"]], bp["code"]
                bucket[code] = min(bucket.get(code, bp["value"]), bp["value"])
            last = max(daily, default="")
            systolic = daily[last].get("8480-6") if last else None
            diastolic = daily[last].get("8462-4") if last else None
            controlled = 0
            if not last:
                reason = "혈압 없음"
            elif systolic is None or diastolic is None:
                reason = "마지막 날에 한쪽 값만"
            elif systolic < 140 and diastolic < 90:
                controlled, reason = 1, "조절됨"
            else:
                reason = "수축기 140 이상" if systolic >= 140 else "이완기 90 이상"
            current.append(dict(zip(PERSON_FIELDS, (HOSPITAL, label, pid, as_of, last,
                numeric_text(systolic), numeric_text(diastolic), str(controlled), reason))))
        person_rows.extend(current)
        denominator, numerator = len(current), sum(int(r["controlled"]) for r in current)
        rate = (Decimal(numerator) / denominator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if denominator else None
        if source["people"]:
            summary_rows.append(dict(zip(SUMMARY_FIELDS, (HOSPITAL, label, str(denominator),
                                                        str(numerator), numeric_text(rate)))))
    return person_rows, summary_rows


def omop_reference(source):
    """ADR0008/0011/0013: original-A clinical facts, not a KCD mapping assertion."""
    rows, event_dates = [], defaultdict(list)

    def add(table, pid, key, **fields):
        row = {field: "" for field in FACT_FIELDS}
        row.update(hospital=HOSPITAL, omop_table=table, source_person_id=pid, source_row_key=key)
        row.update({k: str(v) for k, v in fields.items()})
        if table in ("visit_occurrence", "condition_occurrence", "measurement"):
            if row["start_date"]:
                event_dates[pid].append((row["start_date"], row["end_date"] or row["start_date"]))
        rows.append(row)

    for pid, person in sorted(source["people"].items()):
        add("person", pid, pid, year_of_birth=person["birth_year"], gender_source_value=person["gender"],
            concept_id={"male": 8507, "female": 8532}.get(person["gender"], 0))
        add("person_ext", pid, pid, measurement_year=YEAR)
    for v in source["visits"]:
        add("visit_occurrence", v["pid"], v["key"], start_date=v["start"], end_date=v["end"],
            concept_id=visit_concept(v), reference_code=v["code"], reference_system=v["system"])
    for d in source["diagnoses"]:
        if is_hypertension(d):
            add("condition_occurrence", d["pid"], d["key"], start_date=d["start"], end_date=d["end"],
                concept_id=320128, reference_code=d["code"], reference_system=d["system"])
    for bp in source["pressures"]:
        add("measurement", bp["pid"], bp["key"], start_date=bp["day"], end_date=bp["day"],
            concept_id=bp_concept(bp), value_as_number=numeric_text(bp["value"]),
            unit_concept_id=unit_concept(bp), reference_code=bp["code"],
            reference_system=bp["system"], reference_unit=bp["unit"])
    for pid, intervals in sorted(event_dates.items()):
        add("observation_period", pid, pid, start_date=min(s for s, _ in intervals),
            end_date=max(e for _, e in intervals), concept_id=32817)
    keys = [(r["omop_table"], r["source_row_key"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate reference OMOP key")
    return sorted(rows, key=lambda r: (r["omop_table"], r["source_row_key"]))


def read_source(directory):
    resources, files = [], []
    paths = sorted(Path(directory).glob("*.json"))
    if not paths:
        raise ValueError("no source FHIR files")
    for path in paths:
        body = path.read_bytes()
        bundle = json.loads(body, parse_float=Decimal)
        resources.extend(entry["resource"] for entry in bundle.get("entry", []))
        files.append({"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
    return resources, sorted(files, key=lambda r: (r["sha256"], r["bytes"]))


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def mapping_contract():
    """D2 / ADR0009,0013: accepted original meaning, separate unverified annotation."""
    return {
        "comparison_route": "preserved_source_clinical",
        "clinical_basis": {
            "status": "accepted_existing_source_mapping", "system": SNOMED_SYSTEM,
            "code": "59621000", "target_concept_id": 320128, "decision": "0009",
            "uses_kcd_candidate": False,
        },
        "kcd_candidate": {
            "candidate_claim_code": "I109", "kcd_edition_for_2025": "KCD-8",
            "edition_context": "measurement year; not original claim edition",
            "kcd_dot_normalization": "unverified", "kcd_to_omop": "unverified",
            "mt056_decimal_supplement": "unverified", "product_mapping_gate": "blocked",
            "vocabulary_release": "", "mapping_relationship": "", "target_concept_id": None,
            "usage": "annotation_only",
        },
    }


def generate(directory, output):
    output = Path(output)
    repo = Path(__file__).resolve().parents[1]
    resolved = output.resolve()
    if resolved != repo / "expected_a_prime" and not resolved.is_relative_to(repo / ".local/FHIR-LINE-A-PRIME"):
        raise ValueError("output must be expected_a_prime or its local review evidence directory")
    if output.exists() and any(output.iterdir()):
        raise ValueError("refusing to overwrite existing expected output")
    resources, source_files = read_source(directory)
    source = collect(resources)
    if not source["people"]:
        raise ValueError("reference source has no patients")
    person, summary = indicator(source)
    facts = omop_reference(source)
    output.mkdir(parents=True, exist_ok=True)
    for name, fields, rows in (("person", PERSON_FIELDS, person), ("summary", SUMMARY_FIELDS, summary),
                               ("omop_facts", FACT_FIELDS, facts)):
        write_csv(output / (name + ".csv"), fields, rows)
    manifest = {
        "contract": "a-prime-preserve-all-3", "phase": "pre-review-unlocked", "hospital": HOSPITAL,
        "derived_from": "A", "independent_population": False, "measurement_year": YEAR,
        "definitions": "D1-D7; ADR0004-0011,0013", "source_files": source_files,
        "source_resource_counts": source["resource_counts"],
        "counts": {"people": len(source["people"]), "visits": len(source["visits"]),
            "diagnosis_codings": len(source["diagnoses"]), "mapped_reference_diagnoses": sum(is_hypertension(d) for d in source["diagnoses"]),
            "unmapped_diagnosis_codings": sum(not is_hypertension(d) for d in source["diagnoses"]),
            "bp_panels": source["panels"], "bp_components": len(source["pressures"]),
            "fractional_panels": source["fractional_panels"],
            "fractional_components": sum(b["value"] is not None and b["value"] != b["value"].to_integral_value() for b in source["pressures"]),
            "source_facts": len(source["source_fact_hashes"])},
        "bp_statuses": source["statuses"], "omop_counts": dict(Counter(r["omop_table"] for r in facts)),
        "namespace_contract": {
            "diagnosis": {"system": SNOMED_SYSTEM, "code": "59621000", "target_concept_id": 320128},
            "panel": {"system": LOINC_SYSTEM, "code": "85354-9"},
            "component": {"system": LOINC_SYSTEM, "codes": BP_CODES},
            "unit": {"system": UCUM_SYSTEM, "codes": UNIT_CODES, "display_is_not_a_code": True},
            "visit": {"system": VISIT_SYSTEM, "codes": VISIT_CODES},
            "unmatched": "preserve original source facts; no namespace normalization or new mapping",
        },
        "namespace_issues": {
            "same_diagnosis_code_other_system": sum(d["code"] == "59621000" and not is_hypertension(d) for d in source["diagnoses"]),
            "panel_candidates_without_approved_system": source["unapproved_panels"],
            "component_other_system": sum(b["system"] != LOINC_SYSTEM for b in source["pressures"]),
            "unit_not_approved_pair": sum(unit_concept(b) == 0 for b in source["pressures"]),
            "visit_other_system": sum(v["system"] != VISIT_SYSTEM for v in source["visits"]),
        },
        "mapping": mapping_contract(),
        "source_fact_hashes": dict(sorted(source["source_fact_hashes"].items())),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {"phase": manifest["phase"], "counts": manifest["counts"], "omop_counts": manifest["omop_counts"],
            "summaries": summary, "comparison_route": manifest["mapping"]["comparison_route"],
            "kcd_mapping_gate": manifest["mapping"]["kcd_candidate"]["product_mapping_gate"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.source, args.output), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"reference calculation failed: {exc}\n")


if __name__ == "__main__":
    main()
