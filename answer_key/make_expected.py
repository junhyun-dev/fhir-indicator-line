"""정답 쪽 계산 · M1 · 고혈압 환자 가운데 혈압이 조절되는 사람(CMS165 셈법의 학습용 판).

원본 FHIR 묶음 파일을 읽기만 하고, 파이프라인과 따로 기준 시각마다 사람별 정답과 요약을 만든다.
정의 D1 ~ D7은 builds/medical-data-hands-on 그림 24 · 경계 표는 thinking/m1-change-log.md.
쓰는 쪽: Claude 세션(Codex 밖 · 사용자 10/19). 파이썬 표준 라이브러리만 쓴다.
돌리는 법: python3 make_expected.py <원본 fhir 폴더> <내놓을 폴더>
"""
import csv, datetime, glob, hashlib, json, os, sys

YEAR_START, YEAR_END, HALF_YEAR = "2025-01-01", "2025-12-31", "2025-06-30"  # D1 · D2
AS_OF = ["2025-09-30", "2025-12-31"]  # 배치 1만(10/1 앞) · 배치 2까지
HYPERTENSION = {"59621000"}           # D2 고혈압 코드 목록(seed 표와 같은 값)
BP_PANEL, SYSTOLIC, DIASTOLIC = "85354-9", "8480-6", "8462-4"  # D3


def day(ts):  # D1: 적힌 글자 그대로 앞 10자리를 「그 날」로(시간대를 바꾸지 않음)
    return ts[:10] if ts else None


def record_day(r):  # 배치를 가른 날짜(요청 02 1절과 같은 규칙) · 없으면 두 배치에 다
    t = r["resourceType"]
    if t == "Observation":
        return day(r.get("effectiveDateTime"))
    if t == "Encounter":
        return day(r.get("period", {}).get("start"))
    if t == "Condition":
        return day(r.get("recordedDate") or r.get("onsetDateTime"))
    return None


def person(r):
    return r.get("subject", {}).get("reference", "").split(":")[-1]


def codes(concept):
    return {c.get("code") for c in concept.get("coding", [])}


def days_between(a, b):  # a ~ b의 날(끝 포함)
    d, end = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b or a)
    while d <= end:
        yield d.isoformat()
        d += datetime.timedelta(days=1)


def answer(resources, as_of):
    seen = [r for r in resources if record_day(r) is None or record_day(r) <= as_of]
    last = min(YEAR_END, as_of)
    patients = {r["id"]: r for r in seen if r["resourceType"] == "Patient"}
    rows = []
    for pid, p in sorted(patients.items()):
        mine = [r for r in seen if person(r) == pid]
        born = datetime.date.fromisoformat(p["birthDate"])
        age = 2025 - born.year - ((12, 31) < (born.month, born.day))      # D2 그 해 끝의 나이
        htn = any(r["resourceType"] == "Condition" and codes(r["code"]) & HYPERTENSION
                  and day(r.get("onsetDateTime")) <= HALF_YEAR
                  and (day(r.get("abatementDateTime")) or "9999") >= YEAR_START for r in mine)
        encounters = [r for r in mine if r["resourceType"] == "Encounter"]
        visit = any(e["class"]["code"] == "AMB" and YEAR_START <= day(e["period"]["start"]) <= last
                    for e in encounters)
        if not (18 <= age <= 85 and htn and visit):                           # D2 평가 대상
            continue
        skip = {d for e in encounters if e["class"]["code"] in ("IMP", "EMER")  # D3 입원 · 응급실 날
                for d in days_between(day(e["period"]["start"]), day(e["period"].get("end")))}
        daily = {}                                                             # 날 → [수축기들, 이완기들]
        for o in mine:
            if o["resourceType"] != "Observation" or BP_PANEL not in codes(o["code"]):
                continue
            d = day(o.get("effectiveDateTime"))
            if not (YEAR_START <= d <= last) or d in skip:
                continue
            for c in o.get("component", []):                                  # D3 그 코드의 원소에서만
                q = c.get("valueQuantity", {})
                if q.get("code") != "mm[Hg]":                                  # D3 단위
                    continue
                if SYSTOLIC in codes(c["code"]):
                    daily.setdefault(d, [[], []])[0].append(q["value"])
                elif DIASTOLIC in codes(c["code"]):
                    daily.setdefault(d, [[], []])[1].append(q["value"])
        if not daily:
            rows.append([pid, as_of, "", "", "", 0, "혈압 없음"])                # D6 기록이 없으면 조절 안 됨
            continue
        d = max(daily)                                                         # D5 마지막 날
        s = min(daily[d][0]) if daily[d][0] else None                          # D4 따로 가장 낮은 값
        a = min(daily[d][1]) if daily[d][1] else None
        if s is None or a is None:
            ok, why = 0, "마지막 날에 한쪽 값만"
        else:
            ok = int(s < 140 and a < 90)                                       # D6
            why = "조절됨" if ok else ("수축기 140 이상" if s >= 140 else "이완기 90 이상")
        rows.append([pid, as_of, d, s if s is not None else "", a if a is not None else "", ok, why])
    return rows


def main(src, out):
    resources = []
    for f in sorted(glob.glob(os.path.join(src, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            resources += [e["resource"] for e in json.load(fh)["entry"]]
    os.makedirs(out, exist_ok=True)
    hashes = {}
    for as_of in AS_OF:                                                        # D7 제외 대상은 빼지 않음
        rows = answer(resources, as_of)
        files = {f"person_{as_of}.csv": [["person_id", "as_of", "last_bp_date", "systolic",
                                           "diastolic", "controlled", "reason"]] + rows,
                 f"summary_{as_of}.csv": [["as_of", "denominator", "numerator", "rate", "note"],
                                          [as_of, len(rows), sum(r[5] for r in rows),
                                           round(sum(r[5] for r in rows) / len(rows), 4) if rows else "",
                                           "학습용 계산(제외 대상 안 뺌 · D7)"]]}
        for name, table in files.items():
            with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows(table)
            with open(os.path.join(out, name), "rb") as fh:
                hashes[name] = hashlib.sha256(fh.read()).hexdigest()
    common(resources, out, hashes)  # M2: 두 병원이 같이 쓰는 모양(병원 · 기준일 이름 열 · 10/19)
    with open(os.path.join(out, "SHA256SUMS"), "w", encoding="utf-8") as fh:
        fh.writelines(f"{h}  {n}\n" for n, h in sorted(hashes.items()))


LABEL = {"2025-09-30": "sep30", "2025-12-31": "dec31"}


def common(resources, out, hashes):
    """person_A.csv · summary_A.csv — 값은 위와 같고, 열만 병원 B와 같은 모양(make_expected_b.py)."""
    person = [["hospital", "as_of_label", "person_id", "as_of", "last_bp_date", "systolic", "diastolic", "controlled", "reason"]]
    summary = [["hospital", "as_of_label", "denominator", "numerator", "rate"]]
    for as_of in AS_OF:
        rows = answer(resources, as_of)
        person += [["A", LABEL[as_of]] + r for r in rows]
        k = sum(r[5] for r in rows)
        summary.append(["A", LABEL[as_of], len(rows), k, round(k / len(rows), 4) if rows else ""])
    for name, table in (("person_A.csv", person), ("summary_A.csv", summary)):
        with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(table)
        with open(os.path.join(out, name), "rb") as fh:
            hashes[name] = hashlib.sha256(fh.read()).hexdigest()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
