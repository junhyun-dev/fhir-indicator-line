[README](../README.md) · [파이프라인](pipeline.md) · [결정 기록](decisions/)

# 데이터 딕셔너리

원천의 필드가 어느 staging 열과 OMOP 열로 이어지는지 정리합니다. 아래 수치는 현재 적재 DB를 읽기 전용으로 조회한 스냅샷입니다. 범위는 이 프로젝트가 사용하는 열이며, 이름·주소·전화 값은 싣지 않습니다.

## 원천 → staging → OMOP

| 원천 필드 | staging 모델·열 | OMOP 표·열 | 매핑·변환 |
|---|---|---|---|
| A Patient.id / B hosp/patients.subject_id | stg_a_person / stg_b_person.person_id | person.person_id · person_source_value, person_ext.hospital | 병원+원래 ID를 MD5로 정수화; 원래 ID는 별도 보존 |
| A Patient.birthDate · gender | stg_a_person.year_of_birth · gender_source_value | person.year_of_birth · gender_concept_id | 생년월일의 연도; 성별은 코드 매핑 |
| B hosp/patients.anchor_year · anchor_age · gender | stg_b_person.measurement_year · year_of_birth · gender_source_value | person_ext.measurement_year · person.year_of_birth · gender_concept_id | 기준 연도−원천 나이; 기준 연도를 측정 연도로 사용 |
| A Encounter.class.code · period.start/end | stg_a_visit.source_code · start_day/end_day | visit_occurrence.visit_concept_id · visit_start_date · visit_end_date | class→방문 개념; 날짜 앞 10글자, 종료가 없으면 시작일 |
| A Condition.code.coding[].code · onsetDateTime · abatementDateTime | stg_a_condition.source_code · start_day/end_day | condition_occurrence.condition_concept_id · condition_start_date · condition_end_date | 고혈압 매핑만 옮김; 미매핑 진단은 내부 집계에 보존 |
| A Condition.recordedDate(없으면 onsetDateTime) | stg_a_condition.record_day | 옮기지 않음 | 임상 시작일과 같은 날짜인지 검사; 수신시각으로 대체하지 않음 |
| A Observation.code.coding[].code | stg_a_bp_value의 선택 조건 | measurement로 옮길 성분 선택 | 혈압 panel 85354-9만 선택; status는 현재 선택 조건이 아님 |
| A Observation.component[].code.coding[].code · valueQuantity.value | stg_a_bp_value.source_code · value | measurement.measurement_concept_id · value_as_number | 8480-6/8462-4→수축기/이완기; 성분마다 한 행 |
| A Observation.effectiveDateTime · component[].valueQuantity.code | stg_a_bp_value.bp_day · unit_source_value/unit_mapping_code | measurement.measurement_date · unit_source_value/unit_concept_id | 원문 날짜; 원래 단위를 보존하고 표준 단위를 매핑 |
| B hosp/admissions.admittime · edregtime · dischtime | stg_b_visit.source_code · start_day/end_day | visit_occurrence.visit_concept_id · visit_start_date · visit_end_date | 응급 등록이 있으면 그 날짜부터; ed_admission은 응급을 거친 입원 |
| B hosp/diagnoses_icd.icd_code · icd_version; admissions.admittime | stg_b_diagnosis.source_code/source_vocabulary_id · start_day | condition_occurrence.condition_source_value/condition_concept_id · condition_start_date | 입원별 원천 행 유지; 버전별 고혈압 코드 매핑; 진단 끝은 NULL |
| B hosp/omr.subject_id · chartdate | stg_b_visit의 omr_day · start_day/end_day | visit_occurrence.visit_concept_id · visit_start_date · visit_end_date | 입원/응급 기간 밖의 OMR 날짜를 외래 방문으로 해석 |
| B hosp/omr.result_value (실제 예: 100/58) | stg_b_bp_value.value · value_source_value | measurement.value_as_number · value_source_value | / 앞뒤 100 · 58로 두 행; 같은 원문을 두 행에 보존 |
| B hosp/omr.result_name · chartdate · 원문 단위 없음 | stg_b_bp_value.source_code · bp_day · unit_mapping_code/unit_source_value | measurement.measurement_concept_id · measurement_date · unit_concept_id/unit_source_value | Blood Pressure만 선택; OMR_BP_NO_UNIT→8876, 원문 단위는 NULL 유지 |
| B icu/chartevents.itemid · valuenum · value · valueuom · charttime | stg_b_bp_value.source_code · value · value_source_value · unit_source_value · bp_day | measurement의 성분·숫자·원문·단위·날짜 | 220179/220180만 선택; storetime은 행 키에만 사용 |
| A 자원 ID / B 원천 복합 키 | source_row_key → omop_event_rows | omop_source_link.omop_table/omop_id/hospital/source_row_key | 원래 사건 행과 OMOP 사건 번호를 함께 보존 |
| 옮긴 사건들의 start_day/end_day | omop_event_rows | observation_period 시작/종료일 | 최소 시작일~최대 종료일; 지표의 측정 기간과 구분 |

FHIR coding.system 자체로 분기하지 않고 병원별 source_vocabulary_id와 원래 코드로 매핑합니다. 혈압은 한 번의 관측에서 성분별 행으로 펼칩니다. 표준 번호와 이름은 맨 아래 코드 매핑 정의에서 찾을 수 있습니다.

## 읽는 법

- **한 행(grain)**과 키는 현재 적재 정의입니다. 키의 유일성은 아래 조회 시점의 중복 그룹 수로 표시하며 DB 제약 선언과 구분합니다.
- **행 수**는 병원별입니다. AB는 병원을 나눌 필요가 없는 공용 seed/출처 행입니다.
- **NULL / 빈문자 / 서로 다른 값(NDV)**을 구분합니다. NDV는 NULL을 제외하고 빈문자는 포함합니다. 빈문자는 정확한 빈 문자열이며 공백·빈 배열은 별도 값입니다.
- 날짜·숫자 열은 최소~최대를 표시합니다. 원천 CSV는 all_varchar로 읽은 타입이며, 날짜는 앞 10글자·숫자는 try_cast로 범위를 구했습니다. 식별자 값·범위는 생략하고 NULL/NDV만 표시합니다.
- raw/latest의 payload_json NDV는 저장 계약의 SHA256(payload_hash) 기준입니다. 원문 본문과 파일 경로는 예시로 출력하지 않습니다.
- CSV 프로파일은 dbt source와 같은 read_csv(header=true, all_varchar=true) 결과의 NULL 처리에 따릅니다.
- 아래 접힌 표에 사용하는 열의 뜻·타입·프로파일이 있습니다. 공식 OMOP에서 사용하지 않아 모두 NULL인 열은 한 묶음으로 따로 표시합니다.

## 원천 A

### FHIR Patient

**한 행:** 환자 자원 하나. **행 수:** A 36.
**키:** `id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 36 | — |  |
| `birthDate` | VARCHAR | 원문 생년월일; staging에서는 연도만 사용합니다 | 0 | 0 | 30 | 1945-10-14 ~ 2006-12-13 | 1954-03-22 |
| `gender` | VARCHAR | 원천 성별 코드 | 0 | 0 | 2 | — | female |

</details>

### FHIR Encounter

**한 행:** 방문 자원 하나. **행 수:** A 2,144.
**키:** `id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 2,144 | — |  |
| `subject.reference` | VARCHAR | FHIR 환자 자원 참조 | 0 | 0 | 36 | — |  |
| `class.code` | VARCHAR | FHIR 방문 class 원래 코드 | 0 | 0 | 5 | — | AMB |
| `period.start` | VARCHAR | 방문 시작 시각 | 0 | 0 | 2,117 | 1951-12-15 ~ 2025-12-30 | 1986-10-13T09:19:44+00:00 |
| `period.end` | VARCHAR | 방문 종료 시각 | 0 | 0 | 2,141 | 1951-12-17 ~ 2025-12-30 | 1986-10-13T09:34:44+00:00 |

</details>

### FHIR Condition

**한 행:** 진단 자원 하나. **행 수:** A 1,455.
**키:** `id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 1,455 | — |  |
| `subject.reference` | VARCHAR | FHIR 환자 자원 참조 | 0 | 0 | 36 | — |  |
| `code.coding[].code` | VARCHAR[] | 자원 코드 배열; staging에서 coding마다 펼칩니다 | 0 | 0 | 178 | — | 714628002 |
| `onsetDateTime` | VARCHAR | 진단 임상 시작 시각 | 0 | 0 | 1,180 | 1951-12-15 ~ 2025-12-22 | 1982-06-28T09:19:44+00:00 |
| `abatementDateTime` | VARCHAR | 진단 임상 종료 시각 | 398 | 0 | 812 | 1993-09-28 ~ 2025-12-22 | 2009-11-30T09:19:44+00:00 |
| `recordedDate` | VARCHAR | 진단 기록일; 없으면 onsetDateTime으로 record_day를 만듭니다 | 0 | 0 | 1,180 | 1951-12-15 ~ 2025-12-22 | 1982-06-28T09:19:44+00:00 |

</details>

### FHIR Observation BP panel

**한 행:** 혈압 panel 관측 자원 하나(85354-9). **행 수:** A 555.
**키:** `id`. 조회한 키 중복 그룹 0개.

Observation 전체 16,900개 중 혈압 panel만 집계했습니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 555 | — |  |
| `subject.reference` | VARCHAR | FHIR 환자 자원 참조 | 0 | 0 | 36 | — |  |
| `effectiveDateTime` | VARCHAR | 혈압 임상 측정 시각 | 0 | 0 | 554 | 1993-09-05 ~ 2025-12-16 | 2021-10-08T17:27:07+00:00 |
| `status` | VARCHAR | 원문 관측 상태; 현재 모델의 선별 조건에는 없습니다 | 0 | 0 | 1 | — | final |
| `code.coding[].code` | VARCHAR[] | 자원 코드 배열; staging에서 coding마다 펼칩니다 | 0 | 0 | 1 | — | 85354-9 |

</details>

### FHIR Observation BP component

**한 행:** 혈압 panel의 성분 코드 하나. **행 수:** A 1,110.
**키:** `id` + `component.code.coding[].code`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 555 | — |  |
| `component.code.coding[].code` | VARCHAR | 혈압 성분 코드 | 0 | 0 | 2 | — | 8480-6 |
| `component.valueQuantity.value` | DOUBLE | 성분 측정 숫자 | 0 | 0 | 111 | 48 ~ 164 | 108 |
| `component.valueQuantity.code` | VARCHAR | 원문 단위 코드 | 0 | 0 | 1 | — | mm[Hg] |

</details>

## 원천 B

### hosp/patients

**한 행:** 비식별 환자 하나. **행 수:** B 100.
**키:** `subject_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `subject_id` | VARCHAR | 비식별 원천 환자 ID | 0 | 0 | 100 | — |  |
| `gender` | VARCHAR | 원천 성별 코드 | 0 | 0 | 2 | — | F |
| `anchor_age` | VARCHAR | 기준 연도의 원천 나이 | 0 | 0 | 50 | 21 ~ 91 | 21 |
| `anchor_year` | VARCHAR | 환자별 기준 연도; B 측정 연도 | 0 | 0 | 62 | 2110 ~ 2201 | 2125 |

</details>

### hosp/admissions

**한 행:** 입원 하나. **행 수:** B 275.
**키:** `hadm_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `subject_id` | VARCHAR | 비식별 원천 환자 ID | 0 | 0 | 100 | — |  |
| `hadm_id` | VARCHAR | 원천 입원 ID | 0 | 0 | 275 | — |  |
| `admittime` | VARCHAR | 입원 시각 | 0 | 0 | 275 | 2110-04-11 ~ 2201-12-11 | 2196-02-24 14:38:00 |
| `dischtime` | VARCHAR | 퇴원 시각 | 0 | 0 | 275 | 2110-04-14 ~ 2201-12-17 | 2196-03-04 14:02:00 |
| `edregtime` | VARCHAR | 응급실 등록 시각; 있으면 방문 시작으로 사용합니다 | 93 | 0 | 181 | 2110-11-30 ~ 2201-10-30 | 2196-02-24 12:15:00 |

</details>

### hosp/diagnoses_icd

**한 행:** 입원의 순번별 진단 코드 하나. **행 수:** B 4,506.
**키:** `subject_id` + `hadm_id` + `seq_num` + `icd_version` + `icd_code`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `subject_id` | VARCHAR | 비식별 원천 환자 ID | 0 | 0 | 100 | — |  |
| `hadm_id` | VARCHAR | 원천 입원 ID | 0 | 0 | 275 | — |  |
| `seq_num` | VARCHAR | 원천에서 부여한 순번; 다른 열과 함께 행을 구분합니다 | 0 | 0 | 39 | 1 ~ 39 | 3 |
| `icd_code` | VARCHAR | 원천 ICD 코드 | 0 | 0 | 1,472 | — | 4139 |
| `icd_version` | VARCHAR | ICD 버전; 버전별 용어 체계로 매핑합니다 | 0 | 0 | 2 | 9 ~ 10 | 9 |

</details>

### hosp/omr

**한 행:** 환자·날짜·결과 종류·순번의 OMR 기록 하나. **행 수:** B 2,964.
**키:** `subject_id` + `chartdate` + `seq_num` + `result_name`. 조회한 키 중복 그룹 0개.

`subject_id + chartdate + seq_num`만 사용하면 중복 그룹이 818개입니다. 전체 원천 키에는 `result_name`도 포함합니다. 혈압 staging은 Blood Pressure로 먼저 제한하므로 해당 이름을 생략한 키를 사용합니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `subject_id` | VARCHAR | 비식별 원천 환자 ID | 0 | 0 | 79 | — |  |
| `chartdate` | VARCHAR | OMR 기록 날짜 | 0 | 0 | 945 | 2109-10-15 ~ 2202-12-17 | 2146-12-01 |
| `seq_num` | VARCHAR | 원천에서 부여한 순번; 다른 열과 함께 행을 구분합니다 | 0 | 0 | 27 | 1 ~ 27 | 1 |
| `result_name` | VARCHAR | OMR 측정 종류; 혈압 값은 Blood Pressure만 선택합니다 | 0 | 0 | 8 | — | Height (Inches) |
| `result_value` | VARCHAR | OMR 원문 결과; 혈압은 / 앞뒤 값을 성분으로 나눕니다 | 0 | 0 | 1,427 | — | 63 |

</details>

### icu/chartevents

**한 행:** 원천의 중환자실 관측 행 하나(아래 복합 키 중복 수 확인). **행 수:** B 668,862.
**키:** `subject_id` + `hadm_id` + `stay_id` + `itemid` + `charttime` + `storetime`. **후보 키 중복 그룹 21,896개**; 전체 원천의 유일키가 아닙니다.

전체 원천에 유일 행 ID가 제공되지는 않습니다. 위 6열은 **후보 키**입니다. 이 프로젝트가 선택한 혈압 부분집합은 16,696행·서로 다른 키 16,696개로 중복이 없습니다. 전체 ICU 자료에 이 키의 유일성을 일반화하지 않습니다. 아래 원천 값 범위는 혈압 이외의 ICU 항목도 포함합니다. 선택된 혈압 범위는 stg_b_bp_value와 measurement에서 따로 확인합니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `subject_id` | VARCHAR | 비식별 원천 환자 ID | 0 | 0 | 100 | — |  |
| `hadm_id` | VARCHAR | 원천 입원 ID | 0 | 0 | 128 | — |  |
| `stay_id` | VARCHAR | 원천 ICU stay ID | 0 | 0 | 140 | — |  |
| `itemid` | VARCHAR | 원천 ICU 항목 코드 | 0 | 0 | 1,318 | — | 225054 |
| `charttime` | VARCHAR | ICU 임상 측정 시각 | 0 | 0 | 36,303 | 2110-04-11 ~ 2201-12-13 | 2132-12-16 00:00:00 |
| `storetime` | VARCHAR | 원천 저장 시각; 행 키에만 사용하고 임상 날짜로 쓰지 않습니다 | 1,159 | 0 | 53,751 | 2110-04-11 ~ 2201-12-13 | 2132-12-15 23:45:00 |
| `value` | VARCHAR | ICU 원문 관측 문자열; 임의 텍스트 예시는 생략합니다 | 0 | 0 | 4,243 | — |  |
| `valuenum` | VARCHAR | ICU 숫자 결과; 숫자로 변환해 사용합니다 | 411,388 | 0 | 2,458 | -400 ~ 999999 | 100 |
| `valueuom` | VARCHAR | ICU 원문 단위 | 506,291 | 0 | 43 | — | % |

</details>

## 원문 적재

### raw_resources

**한 행:** 배치에 수신된 FHIR 자원 하나. **행 수:** A 44,655.
**키:** `batch_id` + `resource_type` + `id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `batch_id` | INTEGER | 수신 배치 번호 | 0 | 0 | 2 | 1 ~ 2 | 1 |
| `resource_type` | VARCHAR | FHIR 자원 종류 | 0 | 0 | 24 | — | Claim |
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 43,643 | — |  |
| `full_url` | VARCHAR | Bundle entry.fullUrl | 0 | 0 | 43,643 | — |  |
| `payload_json` | VARCHAR | 공백까지 보존한 자원 본문; NDV는 payload_hash 기준 | 0 | 0 | 43,643 | — |  |
| `payload_hash` | VARCHAR | 본문 UTF-8 SHA256 | 0 | 0 | 43,643 | — |  |
| `source_file` | VARCHAR | 배치가 읽은 원본 파일의 상대 경로 | 0 | 0 | 38 | — |  |
| `received_at` | TIMESTAMP WITH TIME ZONE | 로더가 기록한 배치 수신시각; 임상시각과 다릅니다 | 0 | 0 | 2 | 2026-10-19 11:20:22.814962+09:00 ~ 2026-10-19 11:21:16.225538+09:00 | 2026-10-19 11:20:22.814962+09:00 |

</details>

### latest_resources

**한 행:** 수정 차례로 선택한 최신 FHIR 자원 하나. **행 수:** A 43,643.
**키:** `resource_type` + `id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `batch_id` | INTEGER | 수신 배치 번호 | 0 | 0 | 2 | 1 ~ 2 | 1 |
| `resource_type` | VARCHAR | FHIR 자원 종류 | 0 | 0 | 24 | — | AllergyIntolerance |
| `id` | VARCHAR | 원래 FHIR resource.id | 0 | 0 | 43,643 | — |  |
| `full_url` | VARCHAR | Bundle entry.fullUrl | 0 | 0 | 43,643 | — |  |
| `payload_json` | VARCHAR | 공백까지 보존한 자원 본문; NDV는 payload_hash 기준 | 0 | 0 | 43,643 | — |  |
| `payload_hash` | VARCHAR | 본문 UTF-8 SHA256 | 0 | 0 | 43,643 | — |  |
| `source_file` | VARCHAR | 배치가 읽은 원본 파일의 상대 경로 | 0 | 0 | 38 | — |  |
| `received_at` | TIMESTAMP WITH TIME ZONE | 로더가 기록한 배치 수신시각; 임상시각과 다릅니다 | 0 | 0 | 2 | 2026-10-19 11:20:22.814962+09:00 ~ 2026-10-19 11:21:16.225538+09:00 | 2026-10-19 11:20:22.814962+09:00 |
| `change_batch_id` | INTEGER | 그 본문 해시가 처음 등장한 배치; 최신본 선택 기준 | 0 | 0 | 2 | 1 ~ 2 | 1 |

</details>

## 병원별 staging

### stg_a_person

**한 행:** 환자 원천 사실 하나. **행 수:** A 36.
**키:** `hospital` + `person_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | A |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 36 | — |  |
| `year_of_birth` | INTEGER | A는 birthDate의 연도, B는 anchor_year−anchor_age | 0 | 0 | 25 | 1945 ~ 2006 | 1954 |
| `gender_source_value` | VARCHAR | 원래 성별 코드 | 0 | 0 | 2 | — | female |
| `measurement_year` | INTEGER | A는 고정 측정 연도, B는 anchor_year | 0 | 0 | 1 | 2025 ~ 2025 | 2025 |
| `gender_vocabulary_id` | VARCHAR | 병원별 성별 용어 구분 | 0 | 0 | 1 | — | hospital_a_gender |

</details>

### stg_a_condition

**한 행:** 원천 코드 하나. **행 수:** A 1,455.
**키:** `hospital` + `source_row_key` + `source_code`. 조회한 키 중복 그룹 0개.

원천 사건 키는 FHIR 자원 ID이며 혈압은 성분 코드를 덧붙입니다. 진단은 coding별 행을 구분합니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | A |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | 0 | 0 | 1,455 | — |  |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 36 | — |  |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 178 | — | 444814009 |
| `start_day` | DATE | 사건 임상 시작 날짜 | 0 | 0 | 887 | 1951-12-15 ~ 2025-12-22 | 2019-06-03 |
| `end_day` | DATE | 사건 임상 종료 날짜 | 398 | 0 | 623 | 1993-09-28 ~ 2025-12-22 | 2019-06-26 |
| `record_day` | DATE | 원천 기록 날짜 검사에 사용; OMOP/계산에는 옮기지 않습니다 | 0 | 0 | 887 | 1951-12-15 ~ 2025-12-22 | 2019-06-03 |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 1 | — | hospital_a_dx |

</details>

### stg_a_visit

**한 행:** 원천 방문 하나. **행 수:** A 2,144.
**키:** `hospital` + `source_row_key`. 조회한 키 중복 그룹 0개.

원천 사건 키는 FHIR 자원 ID이며 혈압은 성분 코드를 덧붙입니다. 진단은 coding별 행을 구분합니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | A |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 36 | — |  |
| `start_day` | DATE | 사건 임상 시작 날짜 | 0 | 0 | 1,825 | 1951-12-15 ~ 2025-12-30 | 1986-10-13 |
| `end_day` | DATE | 사건 임상 종료 날짜 | 0 | 0 | 1,837 | 1951-12-17 ~ 2025-12-30 | 1986-10-13 |
| `record_day` | DATE | 원천 기록 날짜 검사에 사용; OMOP/계산에는 옮기지 않습니다 | 0 | 0 | 1,825 | 1951-12-15 ~ 2025-12-30 | 1986-10-13 |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 5 | — | AMB |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 1 | — | hospital_a_visit |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | 0 | 0 | 2,144 | — |  |

</details>

### stg_a_bp_value

**한 행:** 관측의 혈압 성분 하나. **행 수:** A 1,110.
**키:** `hospital` + `source_row_key`. 조회한 키 중복 그룹 0개.

원천 사건 키는 FHIR 자원 ID이며 혈압은 성분 코드를 덧붙입니다. 진단은 coding별 행을 구분합니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | A |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 36 | — |  |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 2 | — | 8480-6 |
| `value` | DOUBLE | 정규화한 혈압 성분 숫자 | 0 | 0 | 111 | 48 ~ 164 | 108 |
| `bp_day` | DATE | 원문 앞 10글자에서 읽은 혈압 날짜 | 0 | 0 | 548 | 1993-09-05 ~ 2025-12-16 | 1997-09-28 |
| `record_day` | DATE | 원천 기록 날짜 검사에 사용; OMOP/계산에는 옮기지 않습니다 | 0 | 0 | 548 | 1993-09-05 ~ 2025-12-16 | 1997-09-28 |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 1 | — | hospital_a_bp |
| `unit_vocabulary_id` | VARCHAR | 병원별 단위 용어 구분 | 0 | 0 | 1 | — | hospital_a_unit |
| `unit_mapping_code` | VARCHAR | 단위 매핑용 코드; OMR에는 승인된 대체 코드를 사용합니다 | 0 | 0 | 1 | — | mm[Hg] |
| `unit_source_value` | VARCHAR | 원문에 적힌 단위 코드; OMR은 NULL을 보존합니다 | 0 | 0 | 1 | — | mm[Hg] |
| `value_source_value` | VARCHAR | 관측 원문 문자열; OMR은 두 성분에 같은 원문을 보존합니다 | 1,110 | 0 | 0 | — |  |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | 0 | 0 | 1,110 | — |  |
| `is_omop_bp` | BOOLEAN | OMOP 혈압으로 옮길 성분인지 표시합니다 | 0 | 0 | 1 | — | True |

</details>

### stg_b_person

**한 행:** 환자 원천 사실 하나. **행 수:** B 100.
**키:** `hospital` + `person_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | B |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 100 | — |  |
| `year_of_birth` | INTEGER | A는 birthDate의 연도, B는 anchor_year−anchor_age | 0 | 0 | 65 | 2030 ~ 2149 | 2104 |
| `gender_source_value` | VARCHAR | 원래 성별 코드 | 0 | 0 | 2 | — | F |
| `measurement_year` | INTEGER | A는 고정 측정 연도, B는 anchor_year | 0 | 0 | 62 | 2110 ~ 2201 | 2125 |
| `gender_vocabulary_id` | VARCHAR | 병원별 성별 용어 구분 | 0 | 0 | 1 | — | hospital_b_gender |

</details>

### stg_b_diagnosis

**한 행:** 원천 코드 하나. **행 수:** B 4,506.
**키:** `hospital` + `source_row_key` + `source_code`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | B |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 100 | — |  |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | 0 | 0 | 4,506 | — |  |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 1,472 | — | 4139 |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 2 | — | hospital_b_icd9 |
| `start_day` | DATE | 사건 임상 시작 날짜 | 0 | 0 | 274 | 2110-04-11 ~ 2201-12-11 | 2120-05-12 |
| `end_day` | DATE | 사건 임상 종료 날짜 | 4,506 | 0 | 0 | — ~ — |  |
| `record_day` | DATE | 원천 기록 날짜 검사에 사용; OMOP/계산에는 옮기지 않습니다 | 0 | 0 | 274 | 2110-04-11 ~ 2201-12-11 | 2120-05-12 |

</details>

### stg_b_visit

**한 행:** 원천 방문 하나. **행 수:** B 1,109.
**키:** `hospital` + `source_row_key`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | B |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 100 | — |  |
| `start_day` | DATE | 사건 임상 시작 날짜 | 0 | 0 | 1,090 | 2109-10-15 ~ 2202-12-17 | 2196-02-24 |
| `end_day` | DATE | 사건 임상 종료 날짜 | 0 | 0 | 1,096 | 2109-10-15 ~ 2202-12-17 | 2196-03-04 |
| `record_day` | DATE | 원천 기록 날짜 검사에 사용; OMOP/계산에는 옮기지 않습니다 | 0 | 0 | 1,090 | 2109-10-15 ~ 2202-12-17 | 2196-02-24 |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 3 | — | ed_admission |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 1 | — | hospital_b_visit |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | 0 | 0 | 1,109 | — |  |

</details>

### stg_b_bp_value

**한 행:** 관측의 혈압 성분 하나. **행 수:** B 18,428.
**키:** `hospital` + `source_row_key`. 조회한 키 중복 그룹 0개.

OMR 키는 환자·날짜·순번·성분 코드이고, ICU 키는 환자·입원·stay·itemid·charttime·storetime에 itemid를 덧붙인 값입니다. 원천 문자열을 그대로 이어 붙이며 임상 날짜로 storetime을 사용하지 않습니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | 0 | 0 | 1 | — | B |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | 0 | 0 | 100 | — |  |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 4 | — | omr_systolic |
| `value` | DOUBLE | 정규화한 혈압 성분 숫자 | 0 | 0 | 181 | 18 ~ 215 | 110 |
| `bp_day` | DATE | 원문 앞 10글자에서 읽은 혈압 날짜 | 0 | 0 | 1,299 | 2109-10-15 ~ 2202-12-17 | 2146-12-01 |
| `record_day` | DATE | 원천 기록 날짜 검사에 사용; OMOP/계산에는 옮기지 않습니다 | 0 | 0 | 1,299 | 2109-10-15 ~ 2202-12-17 | 2146-12-01 |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 2 | — | hospital_b_omr |
| `unit_vocabulary_id` | VARCHAR | 병원별 단위 용어 구분 | 0 | 0 | 2 | — | hospital_b_omr_unit |
| `unit_mapping_code` | VARCHAR | 단위 매핑용 코드; OMR에는 승인된 대체 코드를 사용합니다 | 0 | 0 | 2 | — | OMR_BP_NO_UNIT |
| `unit_source_value` | VARCHAR | 원문에 적힌 단위 코드; OMR은 NULL을 보존합니다 | 1,732 | 0 | 1 | — | mmHg |
| `value_source_value` | VARCHAR | 관측 원문 문자열; OMR은 두 성분에 같은 원문을 보존합니다 | 0 | 0 | 856 | — | 110/70 |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | 0 | 0 | 18,428 | — |  |
| `is_omop_bp` | BOOLEAN | OMOP 혈압으로 옮길 성분인지 표시합니다 | 0 | 0 | 1 | — | True |

</details>

## OMOP CDM

### person

**한 행:** OMOP 환자 하나. **행 수:** A 36 · B 100.
**키:** `person_id`. 조회한 키 중복 그룹 0개.

**사용하지 않는 공식 열:** `month_of_birth`, `day_of_birth`, `birth_datetime`, `location_id`, `provider_id`, `care_site_id`, `gender_source_concept_id`, `race_source_value`, `race_source_concept_id`, `ethnicity_source_value`, `ethnicity_source_concept_id`. 각 열의 NULL 수는 병원별 전체 행 수와 같고, 빈문자 0·NDV 0입니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `gender_concept_id` | INTEGER | 매핑한 성별 표준 개념 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 8507 ~ 8532<br>B: 8507 ~ 8532 | 8507 / 8532 |
| `year_of_birth` | INTEGER | A는 birthDate의 연도, B는 anchor_year−anchor_age | A 0 · B 0 | A 0 · B 0 | A 25 · B 65 | A: 1945 ~ 2006<br>B: 2030 ~ 2149 | 1966 / 2104 |
| `race_concept_id` | INTEGER | 이번 적재에서는 0 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 0 ~ 0<br>B: 0 ~ 0 | 0 |
| `ethnicity_concept_id` | INTEGER | 이번 적재에서는 0 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 0 ~ 0<br>B: 0 ~ 0 | 0 |
| `person_source_value` | VARCHAR | OMOP에 보존한 원래 환자 ID | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `gender_source_value` | VARCHAR | 원래 성별 코드 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | male / F |

</details>

### observation_period

**한 행:** 환자의 옮긴 사건 관찰 범위 하나. **행 수:** A 36 · B 100.
**키:** `observation_period_id`. 조회한 키 중복 그룹 0개.

지표의 1/1~12/31 범위는 int_person_period가 별도로 만듭니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `observation_period_id` | INTEGER | person_id와 같은 관찰 기간 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `observation_period_start_date` | DATE | 옮긴 사건의 가장 이른 시작일 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | A: 1951-12-15 ~ 2015-07-16<br>B: 2109-10-15 ~ 2201-06-03 | 1984-07-15 / 2125-02-13 |
| `observation_period_end_date` | DATE | 옮긴 사건 종료일(없으면 시작일)의 최댓값 | A 0 · B 0 | A 0 · B 0 | A 34 · B 100 | A: 2002-11-17 ~ 2025-12-30<br>B: 2110-12-29 ~ 2202-12-17 | 2002-11-17 / 2126-01-24 |
| `period_type_concept_id` | INTEGER | 관찰 기간 출처 유형 개념 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 32817 ~ 32817<br>B: 32817 ~ 32817 | 32817 |

</details>

### visit_occurrence

**한 행:** 원천 방문 하나. **행 수:** A 2,144 · B 1,109.
**키:** `visit_occurrence_id`. 조회한 키 중복 그룹 0개.

**사용하지 않는 공식 열:** `visit_start_datetime`, `visit_end_datetime`, `provider_id`, `care_site_id`, `visit_source_concept_id`, `admitted_from_concept_id`, `admitted_from_source_value`, `discharged_to_concept_id`, `discharged_to_source_value`, `preceding_visit_occurrence_id`. 각 열의 NULL 수는 병원별 전체 행 수와 같고, 빈문자 0·NDV 0입니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `visit_occurrence_id` | INTEGER | 방문 사건의 OMOP 번호 | A 0 · B 0 | A 0 · B 0 | A 2,144 · B 1,109 | — |  |
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `visit_concept_id` | INTEGER | 매핑한 방문 종류 | A 0 · B 0 | A 0 · B 0 | A 4 · B 3 | A: 0 ~ 9203<br>B: 262 ~ 9202 | 9202 |
| `visit_start_date` | DATE | 방문 시작일 | A 0 · B 0 | A 0 · B 0 | A 1,825 · B 1,090 | A: 1951-12-15 ~ 2025-12-30<br>B: 2109-10-15 ~ 2202-12-17 | 1975-10-27 / 2180-04-27 |
| `visit_end_date` | DATE | 방문 종료일; 원천 종료가 없으면 시작일 | A 0 · B 0 | A 0 · B 0 | A 1,837 · B 1,096 | A: 1951-12-17 ~ 2025-12-30<br>B: 2109-10-15 ~ 2202-12-17 | 1975-10-27 / 2180-04-27 |
| `visit_type_concept_id` | INTEGER | 방문 기록 출처 유형 개념 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 32817 ~ 32817<br>B: 32817 ~ 32817 | 32817 |
| `visit_source_value` | VARCHAR | 원래 방문 코드 | A 0 · B 0 | A 0 · B 0 | A 5 · B 3 | — | AMB / omr_day |

</details>

### condition_occurrence

**한 행:** 매핑된 원천 진단 하나. **행 수:** A 10 · B 100.
**키:** `condition_occurrence_id`. 조회한 키 중복 그룹 0개.

**사용하지 않는 공식 열:** `condition_start_datetime`, `condition_end_datetime`, `condition_status_concept_id`, `stop_reason`, `provider_id`, `visit_occurrence_id`, `visit_detail_id`, `condition_source_concept_id`, `condition_status_source_value`. 각 열의 NULL 수는 병원별 전체 행 수와 같고, 빈문자 0·NDV 0입니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `condition_occurrence_id` | INTEGER | 진단 사건의 OMOP 번호 | A 0 · B 0 | A 0 · B 0 | A 10 · B 100 | — |  |
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 10 · B 53 | — |  |
| `condition_concept_id` | INTEGER | 매핑한 진단 표준 개념 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 320128 ~ 320128<br>B: 320128 ~ 320128 | 320128 |
| `condition_start_date` | DATE | 진단 임상 시작일 | A 0 · B 0 | A 0 · B 0 | A 10 · B 100 | A: 1986-07-21 ~ 2020-12-26<br>B: 2111-01-15 ~ 2201-12-11 | 1986-07-21 / 2157-11-18 |
| `condition_end_date` | DATE | 진단 임상 종료일; NULL은 종료 미제공 | A 10 · B 100 | A 0 · B 0 | A 0 · B 0 | A: — ~ —<br>B: — ~ — |  |
| `condition_type_concept_id` | INTEGER | 진단 기록 출처 유형 개념 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 32817 ~ 32817<br>B: 32817 ~ 32817 | 32817 |
| `condition_source_value` | VARCHAR | 원래 진단 코드 | A 0 · B 0 | A 0 · B 0 | A 1 · B 2 | — | 59621000 / 4019 |

</details>

### measurement

**한 행:** 관측의 혈압 성분 하나. **행 수:** A 1,110 · B 18,428.
**키:** `measurement_id`. 조회한 키 중복 그룹 0개.

**사용하지 않는 공식 열:** `measurement_datetime`, `measurement_time`, `operator_concept_id`, `value_as_concept_id`, `range_low`, `range_high`, `provider_id`, `visit_occurrence_id`, `visit_detail_id`, `measurement_source_concept_id`, `unit_source_concept_id`, `measurement_event_id`, `meas_event_field_concept_id`. 각 열의 NULL 수는 병원별 전체 행 수와 같고, 빈문자 0·NDV 0입니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `measurement_id` | INTEGER | 혈압 성분 사건의 OMOP 번호 | A 0 · B 0 | A 0 · B 0 | A 1,110 · B 18,428 | — |  |
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `measurement_concept_id` | INTEGER | 매핑한 혈압 성분 개념 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 3004249 ~ 3012888<br>B: 3004249 ~ 3012888 | 3012888 |
| `measurement_date` | DATE | 임상 측정 날짜 | A 0 · B 0 | A 0 · B 0 | A 548 · B 1,299 | A: 1993-09-05 ~ 2025-12-16<br>B: 2109-10-15 ~ 2202-12-17 | 2006-11-13 / 2180-04-27 |
| `measurement_type_concept_id` | INTEGER | 측정 기록 출처 유형 개념 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 32817 ~ 32817<br>B: 32817 ~ 32817 | 32817 |
| `value_as_number` | DECIMAL(18,3) | 혈압 성분 숫자; OMOP에서는 DECIMAL(18,3) | A 0 · B 0 | A 0 · B 0 | A 111 · B 181 | A: 48.000 ~ 164.000<br>B: 18.000 ~ 215.000 | 87.000 / 65.000 |
| `unit_concept_id` | INTEGER | 매핑한 단위 표준 개념 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | A: 8876 ~ 8876<br>B: 8876 ~ 8876 | 8876 |
| `measurement_source_value` | VARCHAR | 원래 혈압 성분 코드 | A 0 · B 0 | A 0 · B 0 | A 2 · B 4 | — | 8462-4 / omr_diastolic |
| `unit_source_value` | VARCHAR | 원문에 적힌 단위 코드; OMR은 NULL을 보존합니다 | A 0 · B 1,732 | A 0 · B 0 | A 1 · B 1 | — | mm[Hg] / mmHg |
| `value_source_value` | VARCHAR | 관측 원문 문자열; OMR은 두 성분에 같은 원문을 보존합니다 | A 1,110 · B 0 | A 0 · B 0 | A 0 · B 856 | — | 110/65 |

</details>

### cdm_source

**한 행:** 통합 CDM의 출처 설명 하나. **행 수:** AB 1.
**키:** `cdm_source_abbreviation`. 조회한 키 중복 그룹 0개.

**사용하지 않는 공식 열:** `source_description`, `source_documentation_reference`, `cdm_etl_reference`. 각 열의 NULL 수는 병원별 전체 행 수와 같고, 빈문자 0·NDV 0입니다.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `cdm_source_name` | VARCHAR | 이 통합 CDM의 출처 이름 | 0 | 0 | 1 | — | fhir-indicator-line learning CDM |
| `cdm_source_abbreviation` | VARCHAR | 출처 약어 | 0 | 0 | 1 | — | FIL |
| `cdm_holder` | VARCHAR | 학습 데이터 보유 주체 설명 | 0 | 0 | 1 | — | learning project |
| `source_release_date` | DATE | 프로젝트가 고정한 원천 기준 날짜 | 0 | 0 | 1 | 2026-10-21 ~ 2026-10-21 | 2026-10-21 |
| `cdm_release_date` | DATE | 프로젝트가 고정한 CDM 기준 날짜 | 0 | 0 | 1 | 2026-10-21 ~ 2026-10-21 | 2026-10-21 |
| `cdm_version` | VARCHAR | CDM 버전 문자열 | 0 | 0 | 1 | — | 5.4 |
| `cdm_version_concept_id` | INTEGER | CDM 버전 개념 | 0 | 0 | 1 | 798878 ~ 798878 | 798878 |
| `vocabulary_version` | VARCHAR | 사용한 용어 부분집합의 버전 설명 | 0 | 0 | 1 | — | subset 2026-10-21 (dbt-synthea 33fdbfa) |

</details>

## 확장·추적·내부 표

### person_ext

**한 행:** OMOP 환자의 병원·측정 연도 하나. **행 수:** A 36 · B 100.
**키:** `person_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `measurement_year` | INTEGER | A는 고정 측정 연도, B는 anchor_year | A 0 · B 0 | A 0 · B 0 | A 1 · B 62 | A: 2025 ~ 2025<br>B: 2110 ~ 2201 | 2025 / 2125 |

</details>

### omop_source_link

**한 행:** 옮긴 사건과 원천 행의 연결 하나. **행 수:** A 3,264 · B 19,637.
**키:** `omop_table` + `omop_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `omop_table` | VARCHAR | 대상 OMOP 표 이름 | A 0 · B 0 | A 0 · B 0 | A 3 · B 3 | — | measurement |
| `omop_id` | INTEGER | 해당 OMOP 표 안의 사건 번호 | A 0 · B 0 | A 0 · B 0 | A 2,144 · B 18,528 | — |  |
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | A 0 · B 0 | A 0 · B 0 | A 3,264 · B 19,637 | — |  |

</details>

### omop_load_counts

**한 행:** 병원·OMOP 표별 적재/미적재 건수 하나. **행 수:** A 6 · AB 1 · B 6.
**키:** `hospital` + `omop_table`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · AB 0 · B 0 | A 0 · AB 0 · B 0 | A 1 · AB 1 · B 1 | — | A / AB |
| `omop_table` | VARCHAR | 대상 OMOP 표 이름 | A 0 · AB 0 · B 0 | A 0 · AB 0 · B 0 | A 6 · AB 1 · B 6 | — | person / cdm_source |
| `carried` | INTEGER | 실제로 옮긴 행 수 | A 0 · AB 0 · B 0 | A 0 · AB 0 · B 0 | A 4 · AB 1 · B 3 | A: 10 ~ 2144<br>AB: 1 ~ 1<br>B: 100 ~ 18428 | 36 / 1 |
| `not_carried` | INTEGER | 미매핑으로 옮기지 않은 진단 행 수 | A 0 · AB 0 · B 0 | A 0 · AB 0 · B 0 | A 2 · AB 1 · B 2 | A: 0 ~ 1445<br>AB: 0 ~ 0<br>B: 0 ~ 4406 | 0 |

</details>

### omop_people

**한 행:** 매핑한 환자 원천 사실 하나. **행 수:** A 36 · B 100.
**키:** `person_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `source_person_id` | VARCHAR | 병원 안에서의 원래 환자 ID | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `year_of_birth` | INTEGER | A는 birthDate의 연도, B는 anchor_year−anchor_age | A 0 · B 0 | A 0 · B 0 | A 25 · B 65 | A: 1945 ~ 2006<br>B: 2030 ~ 2149 | 1966 / 2104 |
| `measurement_year` | INTEGER | A는 고정 측정 연도, B는 anchor_year | A 0 · B 0 | A 0 · B 0 | A 1 · B 62 | A: 2025 ~ 2025<br>B: 2110 ~ 2201 | 2025 / 2125 |
| `gender_source_value` | VARCHAR | 원래 성별 코드 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | male / F |
| `gender_concept_id` | INTEGER | 매핑한 성별 표준 개념 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 8507 ~ 8532<br>B: 8507 ~ 8532 | 8507 / 8532 |

</details>

### omop_diagnoses

**한 행:** 미매핑도 포함한 원천 진단 코드 하나. **행 수:** A 1,455 · B 4,506.
**키:** `hospital` + `source_row_key` + `source_code`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `source_person_id` | VARCHAR | 병원 안에서의 원래 환자 ID | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | A 0 · B 0 | A 0 · B 0 | A 1,455 · B 4,506 | — |  |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | A 0 · B 0 | A 0 · B 0 | A 178 · B 1,472 | — | 66383009 / 4139 |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 2 | — | hospital_a_dx / hospital_b_icd9 |
| `start_day` | DATE | 사건 임상 시작 날짜 | A 0 · B 0 | A 0 · B 0 | A 887 · B 274 | A: 1951-12-15 ~ 2025-12-22<br>B: 2110-04-11 ~ 2201-12-11 | 1980-06-16 / 2120-05-12 |
| `end_day` | DATE | 사건 임상 종료 날짜 | A 398 · B 4,506 | A 0 · B 0 | A 623 · B 0 | A: 1993-09-28 ~ 2025-12-22<br>B: — ~ — | 2012-12-31 |
| `concept_id` | INTEGER | 표준 개념 번호; 내부 진단의 0은 미매핑입니다 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 0 ~ 320128<br>B: 0 ~ 320128 | 0 |

</details>

### omop_event_rows

**한 행:** 옮길 사건 하나와 한 번 부여한 OMOP 번호. **행 수:** A 3,264 · B 19,637.
**키:** `omop_table` + `omop_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `omop_table` | VARCHAR | 대상 OMOP 표 이름 | A 0 · B 0 | A 0 · B 0 | A 3 · B 3 | — | measurement |
| `omop_id` | INTEGER | 해당 OMOP 표 안의 사건 번호 | A 0 · B 0 | A 0 · B 0 | A 2,144 · B 18,528 | — |  |
| `person_id` | INTEGER | 병원+원천 ID에서 만든 OMOP 환자 정수 키 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `source_row_key` | VARCHAR | 원천 사건의 행 키; 구성은 아래 키 설명을 참고합니다 | A 0 · B 0 | A 0 · B 0 | A 3,264 · B 19,637 | — |  |
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | A 0 · B 0 | A 0 · B 0 | A 8 · B 9 | — | 8462-4 / omr_diastolic |
| `start_day` | DATE | 사건 임상 시작 날짜 | A 0 · B 0 | A 0 · B 0 | A 1,833 · B 1,519 | A: 1951-12-15 ~ 2025-12-30<br>B: 2109-10-15 ~ 2202-12-17 | 2006-11-13 / 2180-04-27 |
| `end_day` | DATE | 사건 임상 종료 날짜 | A 10 · B 100 | A 0 · B 0 | A 1,845 · B 1,566 | A: 1951-12-17 ~ 2025-12-30<br>B: 2109-10-15 ~ 2202-12-17 | 2006-11-13 / 2180-04-27 |
| `concept_id` | INTEGER | 표준 개념 번호; 내부 진단의 0은 미매핑입니다 | A 0 · B 0 | A 0 · B 0 | A 7 · B 6 | A: 0 ~ 3012888<br>B: 262 ~ 3012888 | 3012888 |
| `value_as_number` | DECIMAL(18,3) | 혈압 성분 숫자; OMOP에서는 DECIMAL(18,3) | A 2,154 · B 1,209 | A 0 · B 0 | A 111 · B 181 | A: 48.000 ~ 164.000<br>B: 18.000 ~ 215.000 | 87.000 / 65.000 |
| `unit_concept_id` | INTEGER | 매핑한 단위 표준 개념 | A 2,154 · B 1,209 | A 0 · B 0 | A 1 · B 1 | A: 8876 ~ 8876<br>B: 8876 ~ 8876 | 8876 |
| `unit_source_value` | VARCHAR | 원문에 적힌 단위 코드; OMR은 NULL을 보존합니다 | A 2,154 · B 2,941 | A 0 · B 0 | A 1 · B 1 | — | mm[Hg] / mmHg |
| `value_source_value` | VARCHAR | 관측 원문 문자열; OMR은 두 성분에 같은 원문을 보존합니다 | A 3,264 · B 1,209 | A 0 · B 0 | A 0 · B 856 | — | 110/65 |

</details>

## 계산·요약

### int_person_period

**한 행:** 병원·기준 시점·환자 하나의 측정 기간과 나이. **행 수:** A 72 · B 200.
**키:** `hospital` + `as_of_label` + `person_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `as_of_label` | VARCHAR | 기준 시점 이름 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | sep30 |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |
| `as_of` | DATE | 환자 측정 연도의 실제 기준일 | A 0 · B 0 | A 0 · B 0 | A 2 · B 124 | A: 2025-09-30 ~ 2025-12-31<br>B: 2110-09-30 ~ 2201-12-31 | 2025-09-30 / 2125-09-30 |
| `measurement_start_day` | DATE | 측정 연도 시작일 | A 0 · B 0 | A 0 · B 0 | A 1 · B 62 | A: 2025-01-01 ~ 2025-01-01<br>B: 2110-01-01 ~ 2201-01-01 | 2025-01-01 / 2125-01-01 |
| `measurement_end_day` | DATE | 측정 연도 종료일 | A 0 · B 0 | A 0 · B 0 | A 1 · B 62 | A: 2025-12-31 ~ 2025-12-31<br>B: 2110-12-31 ~ 2201-12-31 | 2025-12-31 / 2125-12-31 |
| `period_end_day` | DATE | 측정 종료일과 기준일 중 이른 날짜 | A 0 · B 0 | A 0 · B 0 | A 2 · B 124 | A: 2025-09-30 ~ 2025-12-31<br>B: 2110-09-30 ~ 2201-12-31 | 2025-09-30 / 2125-09-30 |
| `hypertension_cutoff_day` | DATE | 진단 시작의 상한 날짜 | A 0 · B 0 | A 0 · B 0 | A 1 · B 62 | A: 2025-06-30 ~ 2025-06-30<br>B: 2110-06-30 ~ 2201-06-30 | 2025-06-30 / 2125-06-30 |
| `age_at_year_end` | INTEGER | 측정 연도−태어난 해 | A 0 · B 0 | A 0 · B 0 | A 25 · B 50 | A: 19 ~ 80<br>B: 21 ~ 91 | 59 / 21 |
| `omop_person_id` | INTEGER | OMOP 환자 정수 키; person_id와 조인합니다 | A 0 · B 0 | A 0 · B 0 | A 36 · B 100 | — |  |

</details>

### int_bp_daily

**한 행:** 병원·기준 시점·환자의 유효 혈압 날짜 하나. **행 수:** A 86 · B 327.
**키:** `hospital` + `as_of_label` + `person_id` + `bp_date`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `as_of_label` | VARCHAR | 기준 시점 이름 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | dec31 |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | A 0 · B 0 | A 0 · B 0 | A 27 · B 55 | — |  |
| `bp_date` | DATE | 남겨진 유효 혈압 날짜 | A 0 · B 0 | A 0 · B 0 | A 46 · B 193 | A: 2025-01-01 ~ 2025-12-16<br>B: 2110-01-04 ~ 2201-10-04 | 2025-04-01 / 2180-04-27 |
| `systolic_min` | DOUBLE | 같은 날 수축기 최솟값 | A 0 · B 0 | A 0 · B 0 | A 28 · B 61 | A: 82 ~ 145<br>B: 96 ~ 184 | 105 / 110 |
| `diastolic_min` | DOUBLE | 같은 날 이완기 최솟값 | A 0 · B 0 | A 0 · B 0 | A 28 · B 50 | A: 50 ~ 97<br>B: 44 ~ 109 | 83 / 65 |

</details>

### fct_bp_person

**한 행:** 병원·기준 시점의 대상 환자 하나. **행 수:** A 11 · B 18.
**키:** `hospital` + `as_of_label` + `person_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `as_of_label` | VARCHAR | 기준 시점 이름 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | sep30 / dec31 |
| `person_id` | VARCHAR | 원래 환자 ID; 병원과 함께 사용합니다 | A 0 · B 0 | A 0 · B 0 | A 6 · B 9 | — |  |
| `as_of` | DATE | 환자 측정 연도의 실제 기준일 | A 0 · B 0 | A 0 · B 0 | A 2 · B 18 | A: 2025-09-30 ~ 2025-12-31<br>B: 2111-09-30 ~ 2196-12-31 | 2025-09-30 / 2185-12-31 |
| `last_bp_date` | DATE | 기준 시점까지 마지막 유효 혈압 날짜 | A 0 · B 0 | A 0 · B 0 | A 7 · B 11 | A: 2025-04-21 ~ 2025-12-01<br>B: 2111-06-06 ~ 2196-08-03 | 2025-04-21 / 2185-07-08 |
| `systolic` | DOUBLE | 마지막 날 수축기 최솟값 | A 0 · B 0 | A 0 · B 0 | A 7 · B 10 | A: 94 ~ 145<br>B: 118 ~ 184 | 97 / 142 |
| `diastolic` | DOUBLE | 마지막 날 이완기 최솟값 | A 0 · B 0 | A 0 · B 0 | A 6 · B 9 | A: 50 ~ 97<br>B: 60 ~ 95 | 83 / 67 |
| `controlled` | INTEGER | 조절됨이면 1, 아니면 0 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 0 ~ 1<br>B: 0 ~ 1 | 1 / 0 |
| `reason` | VARCHAR | 혈압 없음/한쪽 값만/임계값/조절됨의 판정 사유 | A 0 · B 0 | A 0 · B 0 | A 3 · B 2 | — | 조절됨 / 수축기 140 이상 |

</details>

### dim_as_of

**한 행:** 환자가 존재하는 병원·기준 시점 하나. **행 수:** A 2 · B 2.
**키:** `hospital` + `as_of_label`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `as_of_label` | VARCHAR | 기준 시점 이름 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | sep30 |

</details>

### bp_summary

**한 행:** 병원·기준 시점의 조절률 요약 하나. **행 수:** A 2 · B 2.
**키:** `hospital` + `as_of_label`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `hospital` | VARCHAR | 원천 병원 구분; AB는 공용 정의/출처입니다 | A 0 · B 0 | A 0 · B 0 | A 1 · B 1 | — | A / B |
| `as_of_label` | VARCHAR | 기준 시점 이름 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | — | sep30 |
| `denominator` | INTEGER | 대상 환자 수 | A 0 · B 0 | A 0 · B 0 | A 2 · B 1 | A: 5 ~ 6<br>B: 9 ~ 9 | 5 / 9 |
| `numerator` | INTEGER | 조절된 대상 환자 수 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 3 ~ 4<br>B: 3 ~ 4 | 3 / 4 |
| `rate` | DOUBLE | 분자/분모, 소수 넷째 자리 반올림 | A 0 · B 0 | A 0 · B 0 | A 2 · B 2 | A: 0.6 ~ 0.6667<br>B: 0.3333 ~ 0.4444 | 0.6 / 0.4444 |

</details>

## 코드·기준 시점

### source_to_concept_map

**한 행:** 원천 용어 체계·코드의 매핑 하나. **행 수:** AB 28.
**키:** `source_vocabulary_id` + `source_code`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `source_code` | VARCHAR | 원래 진단·방문·혈압 성분 코드 | 0 | 0 | 26 | — | 8480-6 |
| `source_concept_id` | INTEGER | 원천 개념 번호; 이번 매핑에서는 0 | 0 | 0 | 1 | 0 ~ 0 | 0 |
| `source_vocabulary_id` | VARCHAR | 병원/종류별 원천 용어 구분; 코드와 함께 매핑 키입니다 | 0 | 0 | 13 | — | hospital_a_bp |
| `source_code_description` | VARCHAR | 원천 코드 설명 | 0 | 0 | 26 | — | 8480-6 |
| `target_concept_id` | INTEGER | 매핑 대상 표준 개념; 0이면 미매핑 | 0 | 0 | 11 | 0 ~ 3012888 | 3004249 |
| `target_vocabulary_id` | VARCHAR | 대상 표준 용어 체계 | 0 | 0 | 5 | — | LOINC |
| `valid_start_date` | DATE | 매핑/개념 유효 시작일 | 0 | 0 | 1 | 1970-01-01 ~ 1970-01-01 | 1970-01-01 |
| `valid_end_date` | DATE | 매핑/개념 유효 종료일 | 0 | 0 | 1 | 2099-12-31 ~ 2099-12-31 | 2099-12-31 |
| `invalid_reason` | VARCHAR | 무효 사유; 현재 빈 값 여부는 집계 참고 | 28 | 0 | 0 | — |  |

</details>

### indicator_concepts

**한 행:** 지표 개념 묶음의 표준 개념 하나. **행 수:** AB 8.
**키:** `concept_set` + `concept_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `concept_set` | VARCHAR | 지표 계산에 사용하는 표준 개념 묶음 | 0 | 0 | 6 | — | systolic |
| `concept_id` | INTEGER | 표준 개념 번호; 내부 진단의 0은 미매핑입니다 | 0 | 0 | 8 | 262 ~ 3012888 | 3004249 |

</details>

### concept

**한 행:** 허용한 용어 부분집합의 개념 하나. **행 수:** AB 12.
**키:** `concept_id`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `concept_id` | INTEGER | 표준 개념 번호; 내부 진단의 0은 미매핑입니다 | 0 | 0 | 12 | 262 ~ 3012888 | 320128 |
| `concept_name` | VARCHAR | 표준 개념 이름 | 0 | 0 | 12 | — | Essential hypertension |
| `domain_id` | VARCHAR | 개념의 데이터 도메인 | 0 | 0 | 7 | — | Condition |
| `vocabulary_id` | VARCHAR | 표준 용어 체계 | 0 | 0 | 7 | — | SNOMED |
| `concept_class_id` | VARCHAR | 개념 분류 | 0 | 0 | 7 | — | Disorder |
| `standard_concept` | VARCHAR | 표준 개념 표시 | 0 | 0 | 1 | — | S |
| `concept_code` | VARCHAR | 그 용어 체계의 코드 | 0 | 0 | 12 | — | 59621000 |
| `valid_start_date` | DATE | 매핑/개념 유효 시작일 | 0 | 0 | 5 | 1970-01-01 ~ 2023-02-08 | 2002-01-31 |
| `valid_end_date` | DATE | 매핑/개념 유효 종료일 | 0 | 0 | 1 | 2099-12-31 ~ 2099-12-31 | 2099-12-31 |
| `invalid_reason` | VARCHAR | 무효 사유; 현재 빈 값 여부는 집계 참고 | 12 | 0 | 0 | — |  |

</details>

### as_of_labels

**한 행:** 기준 시점 월·일 정의 하나. **행 수:** AB 2.
**키:** `as_of_label`. 조회한 키 중복 그룹 0개.

<details>
<summary>열 설명과 프로파일</summary>

| 열 | 타입 | 뜻 | NULL | 빈문자 | NDV | 최소 ~ 최대 | 예시 |
|---|---|---|---:|---:|---:|---|---|
| `as_of_label` | VARCHAR | 기준 시점 이름 | 0 | 0 | 2 | — | sep30 |
| `month` | INTEGER | 기준 시점의 월 | 0 | 0 | 2 | 9 ~ 12 | 9 |
| `day` | INTEGER | 기준 시점의 일 | 0 | 0 | 2 | 30 ~ 31 | 30 |

</details>

## 코드 매핑 정의

### source_to_concept_map · 28행

매핑 키는 `source_vocabulary_id + source_code`입니다. 표준 개념 이름은 적재된 concept과 조인한 값입니다. 0은 표준 개념을 붙이지 않은 상태입니다.

| 병원 | 원천 용어 구분 | 원래 코드 | 표준 번호 | 표준 개념 이름 | 대상 용어 |
|---|---|---|---:|---|---|
| A | hospital_a_bp | 8462-4 | 3012888 | Diastolic blood pressure | LOINC |
| A | hospital_a_bp | 8480-6 | 3004249 | Systolic blood pressure | LOINC |
| A | hospital_a_dx | 59621000 | 320128 | Essential hypertension | SNOMED |
| A | hospital_a_gender | female | 8532 | FEMALE | Gender |
| A | hospital_a_gender | male | 8507 | MALE | Gender |
| A | hospital_a_unit | mmHg | 8876 | millimeter mercury column | UCUM |
| A | hospital_a_unit | mm[Hg] | 8876 | millimeter mercury column | UCUM |
| A | hospital_a_visit | AMB | 9202 | Outpatient Visit | Visit |
| A | hospital_a_visit | EMER | 9203 | Emergency Room Visit | Visit |
| A | hospital_a_visit | HH | 0 | 미매핑 | Visit |
| A | hospital_a_visit | IMP | 9201 | Inpatient Visit | Visit |
| A | hospital_a_visit | VR | 0 | 미매핑 | Visit |
| B | hospital_b_gender | F | 8532 | FEMALE | Gender |
| B | hospital_b_gender | M | 8507 | MALE | Gender |
| B | hospital_b_icd10 | I10 | 320128 | Essential hypertension | SNOMED |
| B | hospital_b_icd9 | 4010 | 320128 | Essential hypertension | SNOMED |
| B | hospital_b_icd9 | 4011 | 320128 | Essential hypertension | SNOMED |
| B | hospital_b_icd9 | 4019 | 320128 | Essential hypertension | SNOMED |
| B | hospital_b_icu | 220179 | 3004249 | Systolic blood pressure | LOINC |
| B | hospital_b_icu | 220180 | 3012888 | Diastolic blood pressure | LOINC |
| B | hospital_b_icu_unit | mmHg | 8876 | millimeter mercury column | UCUM |
| B | hospital_b_icu_unit | mm[Hg] | 8876 | millimeter mercury column | UCUM |
| B | hospital_b_omr | omr_diastolic | 3012888 | Diastolic blood pressure | LOINC |
| B | hospital_b_omr | omr_systolic | 3004249 | Systolic blood pressure | LOINC |
| B | hospital_b_omr_unit | OMR_BP_NO_UNIT | 8876 | millimeter mercury column | UCUM |
| B | hospital_b_visit | admission | 9201 | Inpatient Visit | Visit |
| B | hospital_b_visit | ed_admission | 262 | Emergency Room and Inpatient Visit | Visit |
| B | hospital_b_visit | omr_day | 9202 | Outpatient Visit | Visit |

### indicator_concepts · 8행

| 개념 묶음 | 표준 번호 | 표준 개념 이름 |
|---|---:|---|
| bp_unit | 8876 | millimeter mercury column |
| diastolic | 3012888 | Diastolic blood pressure |
| essential_hypertension | 320128 | Essential hypertension |
| inpatient_or_ed_visit | 262 | Emergency Room and Inpatient Visit |
| inpatient_or_ed_visit | 9201 | Inpatient Visit |
| inpatient_or_ed_visit | 9203 | Emergency Room Visit |
| outpatient_visit | 9202 | Outpatient Visit |
| systolic | 3004249 | Systolic blood pressure |

## 날짜·누락·범위

- 임상 날짜는 원문 앞 10글자를 사용하며 시간대를 바꾸지 않습니다. record_day는 임상 날짜와 같은지 검사하는 열이고, received_at은 배치 수신시각입니다. meta.lastUpdated는 현재 latest_resources에서 제공된 행이 0개입니다.
- 미매핑 진단은 omop_diagnoses에 남고 condition_occurrence에는 옮기지 않습니다. 미매핑 방문과 단위는 개념 0을 보존하고 계산이 지표 개념 묶음으로 선택합니다.
- 계산은 입원·응급 기간을 제외하고 같은 날 성분별 최솟값에서 마지막 유효일을 고릅니다. 혈압이 없거나 한쪽 값만 있으면 조절됨으로 세지 않습니다.
- 이름·주소·전화에 해당하는 Patient.name/address/telecom은 이 변환에서 사용하지 않습니다. 학습용 정의이며 CMS165 전체 구현이 아닙니다.

조회 기준: 2026-10-21T09:14:46.419318+00:00. 값의 프로파일과 키 중복은 이 스냅샷의 관측 결과입니다.
