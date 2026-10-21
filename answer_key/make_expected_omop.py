"""기대 결과 쪽 계산 · M3 · 원천에서 직접 센 OMOP 행 수(병원 × 표)와 끝까지 따라갈 행.

원천(병원 A 원본 FHIR 묶음 · 병원 B MIMIC-IV 데모 2.2 CSV)을 읽기만 하고, 파이프라인과 따로 센다. 쓰는 쪽: Claude 세션(Codex 밖).
어떤 원천 행이 어느 OMOP 표의 한 행이 되나는 코드 저장소 docs/design/01-m3-omop.md 2절 · 결정 0004 ~ 0010:
  person               A Patient 하나 · B patients 한 줄
  visit_occurrence     A Encounter 하나(모든 class) · B admissions 한 줄 + omr에 기록이 있는 날 가운데 입원 · 응급실 구간 밖의 날
  condition_occurrence 표준 번호 목록에 있는 진단만 옮김(A Condition 하나 · B diagnoses_icd 한 줄) — 나머지는 「안 옮김」으로 셈
  measurement          A 혈압 묶음(85354-9)의 성분 8480-6 · 8462-4 하나마다 · B omr 「Blood Pressure」 한 줄마다 두 행 + chartevents 220179 · 220180 한 줄
  observation_period   옮긴 기록이 하나라도 있는 사람 하나(가장 이른 날 ~ 가장 늦은 날)
  person_ext           person과 같음 · cdm_source 1행(두 병원 합쳐서)
파이썬 표준 라이브러리만 쓴다. 돌리는 법: python3 -I make_expected_omop.py <A 원본 fhir 폴더> <B MIMIC 데모 폴더> <내놓을 폴더>
"""
import collections, csv, glob, gzip, json, os, sys

A_CONDITION = {"59621000"}                                   # 결정 0009 · SNOMED Essential hypertension
B_CONDITION = {("10", "I10"), ("9", "4010"), ("9", "4011"), ("9", "4019")}
A_BP = {"8480-6", "8462-4"}
B_BP_ITEMS = {"220179", "220180"}
FOLLOW = [("A", "8e2eb664"), ("B", "10004422")]             # 끝까지 따라갈 사람(앞 글자) · 그 사람의 마지막 혈압 날 행
CONCEPT = {"8480-6": 3004249, "omr_systolic": 3004249, "220179": 3004249,  # 결정 0008 · 0009: 수축기 · 이완기(LOINC 표준 번호)
           "8462-4": 3012888, "omr_diastolic": 3012888, "220180": 3012888}
MM_HG = 8876                                                  # UCUM mm[Hg] · B omr은 단위 글자가 없고 결정 0003에서 mm[Hg]로 정함


def day(ts):
    return ts[:10] if ts else None


def subject(r):
    return r.get("subject", {}).get("reference", "").split(":")[-1]


def codes(concept):
    return [c.get("code") for c in concept.get("coding", [])]


def hospital_a(src):
    res = {}
    for f in sorted(glob.glob(os.path.join(src, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            for e in json.load(fh)["entry"]:
                r = e["resource"]
                res[(r["resourceType"], r["id"])] = r              # 같은 자원이 두 번 오면 하나로
    by = collections.defaultdict(list)
    for (t, _), r in res.items():
        by[t].append(r)
    days = collections.defaultdict(list)
    out = collections.Counter()
    skipped = collections.Counter()
    rows = []
    out["person"] = len(by["Patient"])
    for e in by["Encounter"]:
        out["visit_occurrence"] += 1
        days[subject(e)] += [day(e["period"]["start"]), day(e["period"].get("end")) or day(e["period"]["start"])]
    for c in by["Condition"]:
        if set(codes(c["code"])) & A_CONDITION:
            out["condition_occurrence"] += 1
            days[subject(c)].append(day(c.get("onsetDateTime")))
        else:
            skipped["condition_occurrence"] += 1
    for o in by["Observation"]:
        if "85354-9" not in codes(o["code"]):
            continue
        for comp in o.get("component", []):
            for code in codes(comp["code"]):
                if code in A_BP:
                    out["measurement"] += 1
                    d = day(o.get("effectiveDateTime"))
                    days[subject(o)].append(d)
                    q = comp.get("valueQuantity", {})
                    rows.append(("A", subject(o), code, d, CONCEPT[code], q.get("value"), MM_HG if q.get("code") == "mm[Hg]" else 0, ""))
    out["observation_period"] = sum(1 for p in by["Patient"] if days.get(p["id"]))
    out["person_ext"] = out["person"]
    return out, skipped, rows


def gz(folder, name):
    with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def hospital_b(src):
    out = collections.Counter()
    skipped = collections.Counter()
    rows = []
    days = collections.defaultdict(list)
    patients = list(gz(src, "hosp/patients.csv.gz"))
    out["person"] = len(patients)
    stays = collections.defaultdict(list)
    admit = {}
    for a in gz(src, "hosp/admissions.csv.gz"):
        start, end = day(a["edregtime"] or a["admittime"]), day(a["dischtime"])
        stays[a["subject_id"]].append((start, end))
        admit[a["hadm_id"]] = day(a["admittime"])
        out["visit_occurrence"] += 1
        days[a["subject_id"]] += [start, end]
    omr_days = set()
    for r in gz(src, "hosp/omr.csv.gz"):
        omr_days.add((r["subject_id"], r["chartdate"]))
        if r["result_name"] == "Blood Pressure":
            out["measurement"] += 2
            days[r["subject_id"]].append(r["chartdate"])
            sys_, dia = r["result_value"].split("/")
            rows += [("B", r["subject_id"], "omr_systolic", r["chartdate"], CONCEPT["omr_systolic"], sys_, MM_HG, r["result_value"]),
                     ("B", r["subject_id"], "omr_diastolic", r["chartdate"], CONCEPT["omr_diastolic"], dia, MM_HG, r["result_value"])]
    for p, d in omr_days:
        if not any(s <= d <= e for s, e in stays.get(p, [])):
            out["visit_occurrence"] += 1
            days[p].append(d)
    for r in gz(src, "hosp/diagnoses_icd.csv.gz"):
        if (r["icd_version"], r["icd_code"]) in B_CONDITION:
            out["condition_occurrence"] += 1
            days[r["subject_id"]].append(admit[r["hadm_id"]])
        else:
            skipped["condition_occurrence"] += 1
    for r in gz(src, "icu/chartevents.csv.gz"):
        if r["itemid"] in B_BP_ITEMS:
            out["measurement"] += 1
            days[r["subject_id"]].append(day(r["charttime"]))
    out["observation_period"] = sum(1 for p in patients if days.get(p["subject_id"]))
    out["person_ext"] = out["person"]
    return out, skipped, rows


TABLES = ["person", "person_ext", "observation_period", "visit_occurrence", "condition_occurrence", "measurement"]


def main(a_src, b_src, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    counts = [["hospital", "omop_table", "carried", "not_carried"]]
    follow = [["hospital", "person_source_value", "measurement_source_value", "measurement_date", "measurement_concept_id",
               "value_as_number", "unit_concept_id", "value_source_value"]]
    for h, (out, skipped, rows) in (("A", hospital_a(a_src)), ("B", hospital_b(b_src))):
        counts += [[h, t, out[t], skipped[t]] for t in TABLES]
        for fh, prefix in FOLLOW:
            if fh != h:
                continue
            mine = [r for r in rows if r[1].startswith(prefix)]
            last = max(r[3] for r in mine)
            follow += sorted([list(r) for r in mine if r[3] == last], key=lambda r: r[2])
    counts.append(["AB", "cdm_source", 1, 0])
    for name, table in (("omop_counts.csv", counts), ("omop_follow.csv", follow)):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(table)
    for r in counts[1:]:
        print(*r)
    for r in follow[1:]:
        print(*r)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
