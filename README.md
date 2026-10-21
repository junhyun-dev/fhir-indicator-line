# fhir-indicator-line

병원 A의 합성 FHIR와 병원 B의 MIMIC-IV 데모 CSV를 OMOP CDM 5.4로 연결해 혈압 지표를 계산하는 학습 프로젝트다. A의 Bundle은 두 배치로 나누고 본문을 보존하며 최신 자원을 고른다. 병원별 staging은 원천 사실을 해석하고 OMOP이 표준 코드를 붙인다. 계산 층은 OMOP과 지표 개념 seed만 읽는다. Codex가 구현하고, 읽기 전용 expected와 비교 검사·설계·결정 문서는 짝 Claude 세션이 관리한다. 검사 명령은 sh scripts/check.sh이며 작업 규칙은 AGENTS.md에 있다.

```bash
mkdir -p .cache/FHIR-LINE-02/tmp .cache/FHIR-LINE-02/pip
TMPDIR="$PWD/.cache/FHIR-LINE-02/tmp" python3 -m venv .venv
PIP_CONFIG_FILE=/dev/null PIP_CACHE_DIR="$PWD/.cache/FHIR-LINE-02/pip" TMPDIR="$PWD/.cache/FHIR-LINE-02/tmp" \
  .venv/bin/python -m pip install --require-hashes -r requirements.lock
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line split
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line load data/batches/batch_1
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line load data/batches/batch_2
sh scripts/check.sh
```

설치 전 캐시 디렉터리를 만들고 wheel 용량을 확인한다. 이 lock은 CPython 3.12/Linux x86_64용이다. 설치 버전은 dbt Core 1.11.11, dbt-duckdb 1.10.1, DuckDB 1.4.3이며 전이 의존성도 고정했다. 기존 FHIR는 `.local/FHIR-LINE-01/runs/original/fhir/`에서 읽기만 한다. 생성 자료·DB·캐시·받은 패키지는 Git에서 제외한다.

## L0: 날짜로 나누기

`config/resource_dates.json` 한 곳에 자원별 날짜 필드를 둔다. 날짜의 앞 10글자를 그대로 2025-10-01과 비교하며 시간대를 바꾸지 않는다. Condition은 recordedDate, 없으면 onsetDateTime이다. Patient의 생일, Device의 제조·만료일은 임상 기록 발생일로 쓰지 않는다. 명시한 날짜가 없는 자원은 두 배치에 모두 들어간다. 처음 보는 자원 종류는 매핑을 명시할 때까지 실패한다.

자원과 entry의 원본 JSON 문자열은 공백까지 보존한다. Bundle wrapper의 type 등은 그대로 두고 entry 배열만 나눈다. 이 파일은 적재 입력이며 FHIR 서버로 transaction을 보내는 기능은 없다. 배치별 manifest에는 원래 파일 위치, 출력 파일 SHA256, 자원 종류별 수가 있다. 같은 입력으로 다시 실행하면 기존 출력의 해시를 검사하고 재사용하며, 입력이 달라지면 덮어쓰기를 거부한다.

## L1/L2: 받은 것과 고른 것

`data/fhir.duckdb` 하나에 저장한다. Python DuckDB와 dbt는 threads=2, memory_limit=512MB, 프로젝트 안 임시 경로를 쓰며 extension 자동 다운로드는 끈다.

`raw_resources`는 `(batch_id, resource_type, id)`가 키다. 배치 번호는 양의 정수이며 열은 `batch_id`, `resource_type`, `id`, `full_url`, `payload_json`, `payload_hash`, `source_file`, `received_at`이다. payload는 원문 문자열이고 hash는 그 UTF-8 SHA256이다. 로더는 INSERT만 한다. 같은 배치 재시도는 기존 수신시각·본문을 유지하며, 같은 키의 다른 본문은 전체 배치 transaction을 실패시킨다. 파일이 바뀌면 manifest 검증 단계에서 실패한다.

배치·DB 출력은 프로젝트 밖, `expected/`, 기존 `.local/FHIR-LINE-01/` 아래를 거부한다. 해시는 원문 UTF-8 기준이므로 공백 변경도 다른 본문이다.

`latest_resources`는 `(resource_type, id)`마다 한 행인 view다. 이미 본 본문 hash의 최초 배치 번호를 `change_batch_id`로 삼고 그 번호가 가장 큰 본문을 고른다. 같은 본문의 재수신·역순 도착이 새 수정 차례를 만들지 않는다. 145/75(batch 1) → 135/75(batch 2) → 예전 본문 재수신 뒤에도 135/75를 남긴다. 실제로 과거 내용으로 되돌리는 업무 계약이나 삭제 전파는 이번 범위에 없다.

`meta.lastUpdated`는 원본 자원 갱신시각, `Encounter.period`/`Observation.effectiveDateTime`은 임상 시각, `received_at`은 이 로더의 배치 수신시각이다. 서로 대신하지 않는다. 다른 도구로 DB를 직접 UPDATE하는 것을 막는 권한 시스템은 만들지 않았다.

## OMOP과 지표 계산

| 층 | 모델 | 한 행 |
|---|---|---|
| staging/hospital_a | stg_a_person, stg_a_condition, stg_a_visit, stg_a_bp_value | 사람 / 원래 진단 코드 / 방문 / 혈압 성분 |
| staging/hospital_b | stg_b_person, stg_b_diagnosis, stg_b_visit, stg_b_bp_value | 사람 / 입원별 원래 진단 / 방문 / OMR·ICU 혈압 성분 |
| omop | person, person_ext | 사람 / 병원·측정 연도 |
| omop | observation_period, visit_occurrence, condition_occurrence, measurement | 관찰 기간 / 방문 / 매핑된 진단 / 혈압 값 하나 |
| omop | cdm_source, omop_source_link, omop_load_counts | 출처 / 사건별 원천 키 / 병원·테이블별 적재·누락 집계 |
| intermediate | int_person_period | 병원×기준 시점×사람의 기간·나이 |
| intermediate | int_bp_daily | 병원×기준 시점×사람×유효 혈압 날짜 |
| marts | fct_bp_person, dim_as_of | 대상 한 사람 / 요약에 남길 병원×기준 시점 |
| reports | bp_summary | 병원×기준 시점별 분모·분자·비율 |

공식 CDM 테이블 여섯의 열 순서·자료형은 vendor/omop의 공식 DuckDB DDL과 같다. person_ext는 person_id·hospital·measurement_year만 가진 1:1 확장 테이블이다. 사람 ID는 병원과 원래 ID의 MD5에서 INTEGER로 만들어 입력 환자가 늘어도 유지하며, 충돌·0은 검사가 실패한다. 사건은 omop_event_rows에서 테이블별 정렬 후 번호를 한 번 부여하고 공식 테이블과 원천 연결이 공유한다. 사건 ID는 같은 입력에서 같으며, 입력이 늘 때의 기존 번호 유지는 보장하지 않는다.

omop_people와 omop_diagnoses는 사람 사실·매핑과 미매핑 진단 집계에 쓰는 내부 모델이다. 원래 코드·단위·값 글자는 공식 source_value 열에, 사건의 원래 행 키는 omop_source_link에 보존한다. A는 자원 ID와 성분 코드, B는 입원 ID 또는 진단·OMR·ICU의 복합 키를 쓴다. 공식 테이블에 임의 열을 추가하지 않는다. B 진단은 원본 입원별 행을 유지하고 D2에서 EXISTS로 판단한다.

int_person_period가 person/person_ext와 as_of_labels를 읽어 1/1~12/31, 6/30, 실제 기준일, 기간 끝과 연말 나이를 한 곳에서 만든다(결정 0010). 내부 조인에는 omop_person_id INTEGER를 사용하고 fct와 daily의 person_id는 기존 원래 ID 글자다. 병원 staging에는 기준 시점 cross join이나 지표 날짜·나이 계산을 두지 않는다. observation_period는 옮긴 기록의 관찰 범위이며 지표 측정 기간으로 대체하지 않는다.

seeds/indicator_concepts.csv의 여섯 개념 묶음이 수축기·이완기·단위·고혈압·외래·입원/응급을 정한다. 계산 SQL에는 병원 분기, 원래 코드, 표준 번호 숫자가 없다. 병원별 코드 매핑은 source_to_concept_map, 날짜·원천 종류 해석은 그 병원의 staging에서 맡는다. concept/source_to_concept_map의 승인된 용어 부분집합은 유지하며 추가 패키지나 전체 용어 다운로드가 필요하지 않다. 참조 구현이 필요하면 이 PC의 ~/dev/projects/upstream/dbt-synthea(33fdbfa) 사본을 먼저 읽는다.

D1은 원문 날짜의 앞 10자를 사용하고 시간대를 바꾸지 않는다. 기준일 뒤 임상 기록은 보지 않는다. record_day는 사건 staging에 남기고 임상 날짜와 같은지 dbt 테스트가 확인한다. 다른 행이 들어오면 빌드가 멈춘다(0006). OMOP과 계산에는 수신 날짜를 대신 만들어 넣지 않는다.

D2는 fct_bp_person의 eligible CTE 한 곳에서 판단한다. 연말 나이 18~85, 6월 말까지 시작해 측정 연도와 겹치는 고혈압, 측정 기간 안 외래 방문이 필요하다. 진단의 임상 시작일도 기준일 이하여야 한다. D3·D4는 혈압 단위 묶음과 값이 있는 성분을 사용하고 입원·응급 기간 양 끝을 포함해 제외한 뒤 같은 날 성분별 최솟값을 구한다. D5·D6은 마지막 유효일을 골라 혈압 없음 → 마지막 날에 한쪽 값만 → 140/90 순서로 판정한다. 혈압 값은 기존 출력 계약에 맞게 DOUBLE이다.

혈압 없는 대상도 분모에 남는다. dim_as_of는 필터 전 사람·기준 시점에서 가져와 분모 0·분자 0·rate NULL을 유지한다. 원천에 사람이 없는 병원의 요약까지 보장하지는 않는다. D7 제외 대상은 빼지 않는 학습용 계산이며 CMS 전체 구현은 아니다.

## 병원 B와 원본 보존

staging/hospital_b/sources.yml은 기존 다섯 gzip CSV(patients/admissions/diagnoses_icd/omr/chartevents)를 native read_csv, all_varchar로 읽는다. 기본 경로는 .local/public-data/mimic-iv-demo-2.2/extracted/mimic-iv-clinical-database-demo-2.2이며 MIMIC_SOURCE_DIR로 시험 입력만 바꿀 수 있다. 기존 원본은 읽기 전용이고 별도 로더나 원본 사본을 만들지 않는다.

B의 measurement_year는 anchor_year, year_of_birth는 anchor_year-anchor_age다. ICD 코드는 버전별로 매핑한다. 외래는 입원·응급 기간 밖의 OMR 기록 날짜이며 결과 이름으로 한정하지 않는다. 응급실 등록일(없으면 입원일)~퇴원일 구간을 유지하고, 응급실을 거친 입원의 표준 개념은 입원/응급 묶음에 포함한다.

정확한 Blood Pressure OMR 한 행은 혈압 성분 두 행이다. 140/60 같은 원문은 두 행에 남고 unit_source_value는 NULL이다. 매핑에서만 OMR_BP_NO_UNIT 표시로 승인된 단위를 붙인다. ICU는 charttime을 임상 날짜로, storetime은 원래 행 키에만 사용한다. 알 수 없는 단위·방문 개념 0도 OMOP 행은 유지하고 계산이 지표 개념 묶음으로 선택한다.

B staging 네 모델과 OMOP은 table로 저장해 gzip 스캔이 여러 view에 중첩되지 않게 한다. 계산 모델은 view여서 기준 시점 seed 변경을 반영한다. 같은 DuckDB 파일을 사용하고 memory_limit=512MB·threads=2·dbt concurrency=1을 유지한다. extension 자동 다운로드와 telemetry는 끄고 임시파일·캐시·로그는 이 저장소 안 경로를 사용한다.

## 검사와 근거

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/dbt.py debug
sh scripts/check.sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line layers
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line check --strict
```

의존 방향은 staging→omop→intermediate→marts→reports다. omop과 intermediate 내부 참조는 허용한다. 정확한 허용 범위는 AGENTS.md와 layers.py에 있고, 선언하지 않은 테이블 직접 읽기도 검사한다. 모델은 source/ref와 CTE로 표현한다. 공통 테이블 common과 code_map은 사용하지 않는다.

check.sh는 읽기 전용 기대 CSV 해시·권한, Python 고정 입력·경계 테스트, 실제 dbt build, 의존 방향과 단계별 검증을 실행한다. ① raw=배치 합, latest=합−공통 자원이고 ② 원천 집계 ③ 중복 본문 ④ 사람·요약의 셀과 자료형 ⑤ 원문 해시 ⑥ OMOP 모양·건수·추적용 혈압·원천 연결을 확인한다. strict는 기다림도 실패다. 결과는 .local/FHIR-LINE-02/summaries/verification-ladder.json과 .md에 남는다.

정상 M1/M2B/OMOP 시험은 실제 원본·expected와 격리한 작은 DB와 수제 입력을 사용하고 날짜 검사를 항상 적용한다. 늦게 기록된 원래 M1 사례는 별도 입력에서 0006 검사가 실패해야 통과하는 음성 테스트다. 정상 계산에서는 늦은 외래 방문 사례가 9월 말 제외·연말 포함을 확인하며 기존 임상 기대값을 유지한다.

L0~L2 근거는 .local/FHIR-LINE-02/summaries/FHIR-LINE-02.reply.md, M1은 FHIR-LINE-03, M2 공통화는 04, B 연결은 05, OMOP 추가는 06의 같은 summaries 답 파일에 있다. 현재 OMOP 계산 전환은 .local/FHIR-LINE-07/summaries/FHIR-LINE-07.reply.md에서 확인한다. 전환 전 daily·person 결과는 .local/FHIR-LINE-07/before/에 보존하고 기존 열로 두 방향 EXCEPT ALL을 비교한다.
