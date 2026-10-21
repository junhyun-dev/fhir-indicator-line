# 0009 · 표준 번호는 쓰는 것만 작은 목록으로(계정 없음)

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: Claude(Athena 계정이 필요한 길은 안 감)

## 결정

- `seeds/concept.csv` — 쓰는 표준 번호만(OMOP `concept` 표의 열 그대로). 줄은 dbt-synthea 용어 seed(`33fdbfa`)에서 그대로 옮겨요: 3004249 · 3012888 · 8876 · 320128 · 9201 · 9202 · 9203 · 8507 · 8532 · 32817 · 798878, 그리고 262(응급실과 입원 · dbt-synthea 코드가 쓰는 번호).
- `seeds/source_to_concept_map.csv` — 원래 코드 → 표준 번호(OMOP `source_to_concept_map` 열 그대로 · `source_vocabulary_id`에 병원과 원천을 적음): A `8480-6` · `8462-4` · `59621000` · `AMB` · `IMP` · `EMER`(`HH` · `VR`은 0) · B `I10` · `4010` · `4011` · `4019` · `omr_systolic` · `omr_diastolic` · `220179` · `220180` · 방문 종류 · 단위 `mm[Hg]` · `mmHg`.
- 계산 층이 쓰는 묶음(혈압 두 번호 · 고혈압 · 외래 · 입원 · 응급 · mm[Hg])은 `seeds/indicator_concepts.csv` 한 곳(결정 0010).

## 이유와 대안

- 대안: Athena 전체 용어 묶음(계정 · 수 GB).
- 병원 B의 ICD 코드 → 320128은 MIMIC-IV demo OMOP 0.9(공식 변환본)의 `condition_occurrence`로 대조해요(결과 칸에).

## 참고한 것

dbt-synthea `seeds/vocabulary/concept_seed.csv` · `seeds/stcm/` · HL7 FHIR to OMOP IG(「도메인은 표준 개념의 domain_id가 정한다」) · CDM 5.4 관례(매핑 안 되는 단위는 0).

## 결과

◆ `concept` 12행(11행은 로컬 dbt-synthea seed와 같음 · 262는 MIMIC 공식 OMOP 0.9가 응급실 거친 입원에 씀 ● 38행) · `source_to_concept_map` 28행 · `indicator_concepts` 8행 · 단위 0인 혈압 0 · 번호 없는 방문 39(A HH 34 · VR 5 · 원래 글자는 남음) · 병원 B `4019` · `I10` → 320128은 MIMIC 공식 OMOP 0.9와 같음(100행) ●(`c8ea151`).

카드로 되돌림: MP-02(사후 확인).
