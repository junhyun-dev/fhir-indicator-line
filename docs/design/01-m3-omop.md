# 설계 01 · M3 — 두 병원을 OMOP 표로 옮겨도 같은 숫자

- 2026-10-21 · 쓰는 쪽: 짝 Claude 세션 · 상태: **관문 통과**(10/21 사용자 · 셋 다 추천안 → 결정 0004 ~ 0006 · 나머지 0007 ~ 0010은 Claude) · 마일스톤 설계 글(표준 v2.2) · Codex는 이 글을 입력으로 읽어요.
- 지금 코드: `ccfb361` · 표준 과정 v2 4절 ③(Personal `builds/standard-process.md`).

## 1. 목표 · 하지 않는 것

이 반복이 끝나면 사실이어야 하는 것(완료 조건):

1. 두 병원 기록이 **OMOP CDM 5.4 표 다섯**(`person` · `observation_period` · `visit_occurrence` · `condition_occurrence` · `measurement`)과 `cdm_source`에 들어가고, 열 이름 · 형식이 공식 DuckDB DDL(OHDSI CommonDataModel `f6d2738` · `inst/ddl/5.4/duckdb/OMOPCDM_duckdb_5.4_ddl.sql`)과 같다.
2. 계산 층(L4 ~ L6)은 OMOP 표 · 확장 표 하나(`person_ext`) · 개념 목록만 읽고, **두 병원 숫자가 그대로**다 — A 3/5 → 4/6 · B 4/9 → 3/9(`expected/` 그대로 · 결정 0001 · 0003).
3. **원천 행이 조용히 사라지지 않는다** — 원천에서 직접 센 건수(Codex 밖 · `expected/omop_counts.csv`)와 OMOP 행 수가 병원 × 표마다 같고, 옮기지 않은 원천 행은 이유별 수로 남는다.
4. 원래 코드 · 값 글자는 `*_source_value`에, 사람의 원래 id는 `person_source_value`에, 방문 · 진단 · 혈압 행의 원래 행 키는 옆 표 `omop_source_link`에 남는다(사건 행 하나 = 한 줄 · 결정 0011 · 요청 06 사전 검토 R3에서 고침).

하지 않는 것: 지표에 안 쓰는 진단 · 검사 · 약 행 옮기기 · OHDSI 도구(Achilles · DQD) 돌리기 · 두 병원의 같은 사람 잇기 · Athena 전체 용어 묶음 · `condition_era` 같은 파생 표 · 심평원 지표 10.

## 2. 설계

```
병원 staging(병원마다 · 원래 코드 그대로)  →  omop 층(새 · 표 다섯 + person_ext + cdm_source)  →  계산 층 L4 ~ L6(OMOP 이름으로)  →  reports
                  └ seeds: concept(쓰는 표준 번호만) · source_to_concept_map(병원 로컬 코드 → 표준 번호)
```

| OMOP 표 | 한 행 | 어디서 | 원래 값이 남는 칸 |
|---|---|---|---|
| `person` | 사람 한 명 | 병원 staging의 환자 | `person_source_value`(A UUID · B `subject_id`) · `gender_source_value` |
| `person_ext`(확장 · 0005) | 사람 한 명 | 〃 | `hospital` · `measurement_year`(A 2025 · B `anchor_year`) |
| `observation_period` | 사람 한 명 | 옮긴 기록의 가장 이른 날 ~ 가장 늦은 날(CDM 관례) | — |
| `visit_occurrence` | 방문 한 번 | A Encounter · B 입원 · `omr` 외래 날 | `visit_source_value`(A `class.code` · B `admission` · `ed_admission` · `omr_day`) |
| `condition_occurrence` | 진단 하나 | A Condition · B 고혈압 코드가 붙은 입원마다 한 행(「가장 이른 진단」은 계산 층의 D2가 고름 — 지금은 B staging이 먼저 줄임) | `condition_source_value`(`59621000` · `4019` · `I10`) |
| `measurement` | 혈압 값 하나(수축기 · 이완기는 두 행) | A 성분 · B `omr` 「sys/dia」 · ICU | `measurement_source_value` · `unit_source_value` · `value_source_value`(B `omr` 원래 글자) |
| `omop_source_link`(옆 표 · 0011) | 사건 행 하나 | 방문 · 진단 · 혈압 행마다 | `source_row_key`(A 자원 id · B 원천 복합 키) |

- **번호 붙이기:** OMOP id는 정수예요. `person_id`는 `병원 + 원래 id`의 md5에서 만들어 사람이 늘어도 기존 번호가 바뀌지 않게 하고(136명 겹침 0 · 10/21), 사건 표 id는 정해진 순서의 `row_number()`예요(0007). MIMIC 공식 OMOP 0.9도 해시 id(64비트)를 써요 ●.
- **표준 번호:** 표준 코드(LOINC · SNOMED · ICD)는 `seeds/concept.csv`(쓰는 것만 · 공개 변환 둘에서 확인)로, 병원 로컬 코드(B `omr` · ICU itemid · 방문 종류)는 `seeds/source_to_concept_map.csv`(OMOP 표준 표 모양)로 찾아요. `code_map.csv`는 갈아타기(요청 07)에서 지워요.
- **정의가 계산 층으로:** 1/1 ~ 12/31 · 6/30 · 18 ~ 85세 · mm[Hg] · 외래 · 입원 · 응급 개념 묶음은 계산 층 한 곳(개념 목록 seed)에 둬요. 지금은 6/30이 두 병원 staging에 두 번 있어요.
- **요청 둘:** 06 「더하기」 — omop 층을 공통 테이블 옆에 만들고 건수 · DDL · 원래 값을 검사(계산 층 0줄 · `FROZEN_BASE` 그대로). 07 「갈아타기」(구조만) — 계산 층이 omop을 읽게 하고 `common` · `code_map`을 지움 · 숫자 그대로 · 끝나면 `FROZEN_BASE`를 07 커밋으로.

## 3. 대안과 고른 이유

| 결정 | 고른 것 | 견준 것 | 까닭 |
|---|---|---|---|
| 0004 OMOP의 자리 | OMOP이 공통 테이블을 **대신** | OMOP은 내보내기만 · 계산은 공통 테이블 그대로(계산 층 0줄) | 같은 뜻이 두 벌이면 어느 쪽이 맞는지 다시 물어야 해요. dbt-synthea도 OMOP이 마지막 층이고 분석은 그 위에서 해요 |
| 0005 두 병원을 어떻게 | OMOP 하나 + **확장 표**(`person_ext`)에 병원 · 측정 연도 | 병원마다 OMOP 하나(OHDSI 네트워크 방식) · `care_site`에 병원 | 공식 표는 그대로 두고 우리 것은 옆 표에(All of Us의 `src_id` 확장 표 · OHDSI 포럼 「확장은 1:1 옆 표로」). 병원마다 OMOP은 빌드 · 검사를 병원 수만큼 — M4 후보 |
| 0006 기록이 들어온 날 | **옮기지 않음** · 늦게 온 행이 생기면 검사가 실패 | 기준일마다 OMOP을 따로 만듦(OHDSI가 판을 새로 내는 방식 · `cdm_source` 날짜) | 지금 두 병원 모두 기록일 = 일이 일어난 날(늦게 온 행 0 · 10/21 DB) → 날짜로 자르면 숫자가 같아요 |
| 0007 OMOP id | `병원 + 원래 id` 해시 → 정수 | dbt-synthea의 `row_number()` | `row_number()`는 사람이 하나 늘면 뒤 번호가 다 밀려요(조용히 틀림) |
| 0008 혈압 한 번 | measurement **두 행**(수축기 · 이완기) | HL7 FHIR-to-OMOP IG 예시 맵의 세 행(묶음 행 + 두 성분) | dbt-synthea · OHDSI 포럼이 두 행. IG 맵은 「experimental」이고 성분 행에 날짜가 없어요 |
| 용어 | 쓰는 번호만 작은 목록(계정 없음) | Athena 전체 묶음(계정 · 수 GB) | 지표에 쓰는 번호는 열 개 남짓이고, 공개 변환 둘로 확인돼요 |

## 4. 참고한 것

- 카드: **FC-03**(변환할 때 유지할 정보와 바뀔 정보를 먼저 정한다 — 원본 필드 · 앱 필드 · 생략 조건을 표로, 생략은 알림) → 위 2절 표의 「원래 값이 남는 칸」과 완료 조건 3. **TR-01**(시험한 단위와 산출물의 범위를 함께) → 끝 보고에 「OHDSI 도구는 안 돌림」. FC-02 · SC-01 · SC-02는 이번에 안 닿음.
- 바깥: OHDSI CommonDataModel 5.4 필드 정의(`inst/csv/OMOP_CDMv5.4_Field_Level.csv` — `person_id`는 정수가 아니면 새 번호 · `*_source_value`는 「강력히 권장」 · 단위가 매핑 안 되면 0) · dbt-synthea `33fdbfa`(staging → intermediate → omop · 용어 seed · `source_to_concept_map` seed) · HL7 FHIR to OMOP IG 1.0.0(BloodPressureCodes: 8480-6 → 3004249 · 8462-4 → 3012888 · 「도메인은 표준 개념의 domain_id가 정한다」) · All of Us EHR 확장 표의 `src_id` · MIMIC-IV demo OMOP 0.9(병원 B 코드의 표준 번호 대조).
- 지난 결정: 0001 · 0002 · 0003.

## 5. 위험 · 모르는 것

- **조용히 빠지는 행**(유형 가이드 1장 3절): 표준 번호를 붙이는 join이 짝 없는 행을 버려요 → 원천 건수와 OMOP 건수 · 「안 옮긴 이유별 수」를 함께 비교.
- **id가 밀림** — 위 0007 · 해시 겹침은 테스트로.
- **단위 · 개념 0:** 단위가 매핑 안 되면 `unit_concept_id = 0`(CDM 관례). 계산 층이 8876(mm[Hg])만 쓰니 값이 빠지는 건 의도된 것 — 그 수를 따로 셈.
- **B의 나이:** `year_of_birth = anchor_year − anchor_age`로 두면 측정 연도 말 나이가 `anchor_age`와 같아요 — MIMIC 공식 OMOP 0.9도 같은 식이에요(10004422: 2111 − 78 = 2033 ● · 10/21 대조).
- **확인한 것(10/21):** ICD-9 `4019` · ICD-10 `I10` → 320128(MIMIC 공식 OMOP 0.9 · 원래 코드 번호 44821949 · 35207668 ●) · 같은 100명 ● · 응급실을 거친 입원 262 ●. A의 방문 종류 `HH`(34) · `VR`(5)은 dbt-synthea도 매핑하지 않아 0(원래 글자는 `visit_source_value`).
