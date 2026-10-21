"""기대 결과 쪽 계산 · M2 · 병원 B(MIMIC-IV 데모 2.2 CSV)에 M1 정의 D1 ~ D7을 옮긴 학습용 판.

원본 CSV를 읽기만 하고, 파이프라인과 따로 사람별 결과와 요약을 만든다. 쓰는 쪽: Claude 세션(Codex 밖).
병원 B로 옮긴 정의(사용자 10/19 · 변경 이력 thinking/m1-change-log.md · 근거 thinking/research/mimic-date-shift-1019.md):
  D1-B 그해 = 사람마다 기준 해(anchor_year)의 1/1 ~ 12/31 · 기준일 sep30 = 그 해 9/30, dec31 = 그 해 12/31
  D2-B 나이 = anchor_age(기준 해의 나이) · 고혈압 시작 = 본태성 고혈압 코드(ICD-10 I10 · ICD-9 401.x)가 처음 붙은 입원의 입원일
       외래 방문 = 외래 측정 표(omr)에 기록이 있는 날(입원 · 응급실 날은 빼고)
  D3-B 혈압 = omr 「Blood Pressure」의 「수축기/이완기」 글자 + 중환자실 chartevents 220179 · 220180(mmHg → mm[Hg]),
       입원 · 응급실 날(응급실 등록일 또는 입원일 ~ 퇴원일, 끝 포함)은 뺌
  D4 ~ D7은 병원 A와 같음.
파이썬 표준 라이브러리만 쓴다. 돌리는 법: python3 -I make_expected_b.py <MIMIC 데모 폴더> <내놓을 폴더>
"""
import collections, csv, datetime, gzip, hashlib, os, sys

LABELS = {"sep30": (9, 30), "dec31": (12, 31)}
SYSTOLIC_ITEM, DIASTOLIC_ITEM = "220179", "220180"


def rows(folder, name):
    with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def days_between(a, b):
    d, end = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)
    while d <= end:
        yield d.isoformat()
        d += datetime.timedelta(days=1)


def is_htn(r):  # D2-B 본태성 고혈압(병원 A의 SNOMED 59621000과 같은 뜻)
    return (r["icd_version"] == "10" and r["icd_code"] == "I10") or (r["icd_version"] == "9" and r["icd_code"].startswith("401"))


def answer(src):
    patients = {r["subject_id"]: r for r in rows(src, "hosp/patients.csv.gz")}
    admissions = collections.defaultdict(list)          # 사람 → [(입원일, 응급실 등록일 또는 입원일, 퇴원일)]
    admit_day = {}
    for a in rows(src, "hosp/admissions.csv.gz"):
        start = (a["edregtime"] or a["admittime"])[:10]
        admissions[a["subject_id"]].append((a["admittime"][:10], min(start, a["admittime"][:10]), a["dischtime"][:10]))
        admit_day[a["hadm_id"]] = a["admittime"][:10]
    onset = {}
    for r in rows(src, "hosp/diagnoses_icd.csv.gz"):
        if is_htn(r):
            d = admit_day[r["hadm_id"]]
            onset[r["subject_id"]] = min(onset.get(r["subject_id"], d), d)
    omr_days = collections.defaultdict(set)              # 외래 측정이 있는 날(이름 무관)
    bp = collections.defaultdict(list)                    # 사람 → [(날, 종류, 값)]
    for r in rows(src, "hosp/omr.csv.gz"):
        omr_days[r["subject_id"]].add(r["chartdate"])
        if r["result_name"] == "Blood Pressure":         # 자세가 붙은 이름은 이번엔 안 씀
            s, d = r["result_value"].split("/")
            bp[r["subject_id"]] += [(r["chartdate"], "s", float(s)), (r["chartdate"], "d", float(d))]
    for r in rows(src, "icu/chartevents.csv.gz"):
        if r["itemid"] in (SYSTOLIC_ITEM, DIASTOLIC_ITEM) and r["valuenum"] and r["valueuom"] == "mmHg":
            bp[r["subject_id"]].append((r["charttime"][:10], "s" if r["itemid"] == SYSTOLIC_ITEM else "d", float(r["valuenum"])))

    out = []
    for label, (m, dd) in LABELS.items():
        for pid, p in sorted(patients.items()):
            y = int(p["anchor_year"])
            start, as_of, half = f"{y}-01-01", f"{y}-{m:02d}-{dd:02d}", f"{y}-06-30"
            if not 18 <= int(p["anchor_age"]) <= 85:                                   # D2 나이
                continue
            if not (pid in onset and onset[pid] <= half):                              # D2 고혈압 시작
                continue
            skip = {d for _, s, e in admissions[pid] if s <= as_of for d in days_between(s, e)}   # D3 입원 · 응급실 날(병원 A처럼 시작일로 보임 여부)
            if not any(start <= d <= as_of and d not in skip for d in omr_days[pid]):  # D2 외래 방문
                continue
            daily = {}
            for d, kind, v in bp[pid]:
                if start <= d <= as_of and d not in skip:
                    daily.setdefault(d, {"s": [], "d": []})[kind].append(v)
            if not daily:
                out.append(["B", label, pid, as_of, "", "", "", 0, "혈압 없음"]); continue    # D6
            last = max(daily)                                                         # D5
            s = min(daily[last]["s"]) if daily[last]["s"] else None                   # D4
            a = min(daily[last]["d"]) if daily[last]["d"] else None
            if s is None or a is None:
                ok, why = 0, "마지막 날에 한쪽 값만"
            else:
                ok = int(s < 140 and a < 90)
                why = "조절됨" if ok else ("수축기 140 이상" if s >= 140 else "이완기 90 이상")
            fmt = lambda v: "" if v is None else (int(v) if v == int(v) else v)       # noqa: E731
            out.append(["B", label, pid, as_of, last, fmt(s), fmt(a), ok, why])
    return out


def main(src, dst):
    rows_ = answer(src)
    os.makedirs(dst, exist_ok=True)
    person = [["hospital", "as_of_label", "person_id", "as_of", "last_bp_date", "systolic", "diastolic", "controlled", "reason"]] + rows_
    summary = [["hospital", "as_of_label", "denominator", "numerator", "rate"]]
    for label in LABELS:
        mine = [r for r in rows_ if r[1] == label]
        n, k = len(mine), sum(r[7] for r in mine)
        summary.append(["B", label, n, k, round(k / n, 4) if n else ""])
    hashes = {}
    for name, table in (("person_B.csv", person), ("summary_B.csv", summary)):
        with open(os.path.join(dst, name), "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(table)
        with open(os.path.join(dst, name), "rb") as fh:
            hashes[name] = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(dst, "SHA256SUMS_B"), "w", encoding="utf-8") as fh:
        fh.writelines(f"{h}  {n}\n" for n, h in sorted(hashes.items()))
    for r in summary:
        print(*r, sep=",")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
