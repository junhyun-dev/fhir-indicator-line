# fhir-indicator-line

병원 A의 합성 FHIR와 병원 B의 MIMIC-IV 데모 CSV를 공통 표로 연결해 혈압 지표를 계산하는 학습 프로젝트다. A의 Bundle은 두 배치로 나누고 본문을 보존하며 최신 자원 하나를 고른다. 병원별 staging이 자료의 모양·시계·방문 종류·나이를 해석하고, common 층이 코드 매핑 표로 공통 뜻을 붙인다. L4~L6은 이 공통 표만으로 같은 규칙을 적용한다. Codex가 구현하고 `expected/` 기대 결과(읽기 전용)와 그 비교 검사는 짝 Claude 세션이 쓴다. 검사 명령은 `sh scripts/check.sh` 하나이고, 지킬 것은 `AGENTS.md`에 있다.

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

배치·DB 출력은 프로젝트 밖, `expected/`, 기존 `.local/FHIR-LINE-01/` 아래를 거부한다. 지문은 원문 UTF-8 기준이므로 공백 변경도 다른 본문이다.

`latest_resources`는 `(resource_type, id)`마다 한 행인 view다. 이미 본 본문 hash의 최초 배치 번호를 `change_batch_id`로 삼고 그 번호가 가장 큰 본문을 고른다. 같은 본문의 재수신·역순 도착이 새 수정 차례를 만들지 않는다. 145/75(batch 1) → 135/75(batch 2) → 예전 본문 재수신 뒤에도 135/75를 남긴다. 실제로 과거 내용으로 되돌리는 업무 계약이나 삭제 전파는 이번 범위에 없다.

`meta.lastUpdated`는 원본 자원 갱신시각, `Encounter.period`/`Observation.effectiveDateTime`은 임상 시각, `received_at`은 이 로더의 배치 수신시각이다. 서로 대신하지 않는다. 다른 도구로 DB를 직접 UPDATE하는 것을 막는 권한 시스템은 만들지 않았다.

## dbt 계산 층과 확인 사다리

A staging은 `source('fhir', 'latest_resources')`, B staging은 선언된 mimic CSV source를 읽는다. 아래 공통 표부터 두 병원이 같은 계산을 따른다. `seeds/as_of_labels.csv`는 sep30/dec31의 월·일을 정하고, `seeds/code_map.csv`는 병원별 원래 코드·단위를 공통 concept/std_unit으로 매핑한다. A의 2025년·연말 나이·6/30 경계와 FHIR 날짜/원소 해석은 `models/staging/hospital_a/`에 있다.

| 층 | 모델 | 한 행 |
|---|---|---|
| L3 staging/hospital_a | stg_a_person_period | 병원×기준일 이름×사람; 실제 기준일·측정 기간·나이 |
| L3 staging/hospital_a | stg_a_condition, stg_a_visit, stg_a_bp_value | 진단×원래 코드 / 방문 / 관찰×원래 코드와 값 |
| L3 staging/hospital_b | stg_b_person_period | B의 사람×기준일 이름; anchor_year의 시계와 anchor_age |
| L3 staging/hospital_b | stg_b_condition, stg_b_visit, stg_b_bp_value | 버전별 진단 코드의 첫 입원 / 외래 날·입원 기간 / OMR·ICU 값 |
| common | person_period, condition, visit, bp_value | 병원별 줄을 같은 열로 연결; 진단·혈압에는 공통 뜻 부여 |
| L4 intermediate | int_bp_daily | 병원×기준일 이름×사람×사용할 혈압 날짜 |
| L5 marts | fct_bp_person | 병원×기준일 이름×평가 대상 한 사람 |
| L5 marts | dim_as_of | 대상이 없는 경우에도 요약에 전할 병원×기준일 이름 |
| L6 reports | bp_summary | 병원×기준일 이름별 분모·분자·비율 |

D1은 날짜 문자열의 앞 10자를 쓰고 해당 사람의 기준일 뒤 기록을 보지 않는다. 공통 person_period에는 hospital/as_of_label/person_id 키와 실제 as_of, 측정 시작/끝, period_end_day, hypertension_cutoff_day, age_at_year_end가 있다. D2 대상 판정은 fct_bp_person의 eligible CTE 한 곳에 있다: 연말 나이 18~85세, 상반기까지 시작해 측정 연도와 겹친 고혈압, 기간 내 outpatient 방문이다. A의 AMB/IMP/EMER 해석은 A staging만 안다.

code_map은 진단에서 `(hospital, source_code)`, 혈압에서 `(hospital, source_code, source_unit)`으로 연결한다. source_system은 출처 설명이며 필터가 아니다. common의 condition은 essential_hypertension, bp_value는 systolic/diastolic 뜻을 붙이고, 매핑되지 않은 코드는 제외한다. 혈압은 A staging에서 panel 85354-9의 원소별 code/value/quantity.code를 꺼내고, 단위가 매핑되지 않은 원소는 common에서 제외한다. 단위를 변환하거나 표시 문자열로 대체하지 않는다.

D3·D4는 같은 병원·사람의 inpatient_or_ed 기간(양 끝 포함)을 제외하고 매핑된 숫자를 성분별로 그 날의 최솟값으로 묶는다. 성분 위치는 쓰지 않는다. 쓸 성분이 없는 날은 없애고, 하나만 있는 날은 남긴다. D5·D6은 마지막 유효일을 골라 `혈압 없음` → `마지막 날에 한쪽 값만` → 140/90 임계값 순서로 분류한다. 혈압 없는 대상도 분모에 남는다. dim_as_of가 걸러내지 않은 person_period의 병원/label을 전달하므로 대상 0명인 기준일도 분모·분자 0, rate NULL이다. 원천에 사람이 0명인 병원의 요약 행까지 보장하지는 않는다. **D7 제외 대상은 빼지 않는 학습용 계산**이며 CMS 지표 전체 구현은 아니다.

A와 공통 계산 모델은 view라서 현재 latest_resources와 B staging 결과를 읽는다. B staging 네 개는 dbt build 때 테이블로 만든다. 실제 자료에서 외부 gzip 스캔을 여러 view에 중첩하면 512MB 한도를 넘기므로, B 전용 단계의 계산 결과를 한 번 저장하고 이후 층이 재사용한다. as_of는 기록 날짜의 가시성을 뜻하며, 과거 배치 버전으로 되돌린 데이터베이스 snapshot을 뜻하지 않는다. 서로 다른 시각인 원본 갱신시각·임상 시각·수신시각을 합치지 않는다.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/dbt.py debug
sh scripts/check.sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line layers
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line check --strict
```

wrapper가 프로필·DB·임시파일·로그 경로와 telemetry 설정을 전달하므로 전역 dbt 설정은 필요 없다. 확인 사다리 전에 dbt parse로 실제 의존 관계를 읽는다. staging은 source/seed, common은 staging/seed, intermediate는 common, marts는 intermediate/common, reports는 marts에만 의존한다. marts끼리 읽지 않는다. 선언하지 않은 직접 테이블 읽기도 거부한다. 동적 relation macro와 복잡한 직접 SQL 접근은 이 작은 검사기의 지원 범위가 아니므로 명시적 source/ref와 CTE로 표현한다.

확인 사다리는 원본/배치/raw/latest 행 수, 자원 종류·혈압 수, 같은 자원 본문을 비교한다. ④는 `person_<병원>.csv`의 9열·모든 행을 해당 병원의 fct_bp_person과 비교한다. summary CSV는 hospital/as_of_label/denominator/numerator/rate 5열을 bp_summary와 비교한다. 사람별 결과에는 실제 as_of 날짜가 있고, 요약은 병원/기준일 이름으로 묶는다. 두 결과 모델의 자료형 계약도 검사한다. 행 순서는 무시하고 중복 행 수는 보존하며 숫자의 표현 차이는 해당 DB 자료형으로 정규화한다. ⑤는 지정 환자의 12/01 혈압 원문·해시를 세 층에서 비교한다. expected를 쓰거나 수정하지 않는다.

`sh scripts/check.sh`는 기대 CSV의 해시·읽기 전용 상태, 기존 검사기 시험, 작은 별도 DuckDB의 테스트 01~15와 Q3 및 M2 경계 시험, 실제 dbt build, 층 방향, 사다리의 순서로 실행한다. M2 시험은 L4~L6 SQL에 A의 원본 코드/필드 이름이 새는지 확인한다. 가짜 FHIR를 쓰는 시험은 실제 기대 파일과 원본을 사용하지 않고 dbt를 한 번만 실행한다. 기본 check는 기대 폴더/모델 부재를 기다림으로 표시할 수 있지만, 종료 명령의 `check --strict`는 기다림도 실패로 센다.

①은 `raw=배치1+배치2`, `latest=배치1+배치2−공통 (resource_type,id) 수=원본 자원 수`를 검사한다. 날짜 없는 자원을 두 번 받으면 raw에 배치마다 한 행씩 남고 latest에는 하나가 남는다. 공통 자원 수는 따로 보고한다. strict에서 모든 칸을 통과하면 exit 0, 실패나 기다림이 있으면 exit 1이다. 결과는 `.local/FHIR-LINE-02/summaries/verification-ladder.json`과 `.md`에 남는다.

## 병원 B: 읽기 전용 MIMIC-IV 데모

`models/staging/hospital_b/sources.yml`은 patients/admissions/diagnoses_icd/omr/chartevents 다섯 source를 선언한다. DuckDB의 native read_csv로 gzip CSV를 문자열로 읽고 B staging에서 필요한 날짜/숫자를 해석한다. 같은 DuckDB 파일에 B staging 결과 네 개를 저장하며 원본 사본이나 별도 L1 로더는 만들지 않는다. 원본 변경을 반영하려면 dbt build를 다시 실행한다. 기본 위치는 `.local/public-data/mimic-iv-demo-2.2/extracted/mimic-iv-clinical-database-demo-2.2/`이며 프로세스 환경변수 `MIMIC_SOURCE_DIR`로 시험용 경로를 지정할 수 있다. 이미 받은 원본과 SHA256/ODbL 파일은 읽기만 한다.

B의 측정 연도/기준일/6월 말은 사람마다 anchor_year로 만들고 나이는 anchor_age를 쓴다. ICD-10 I10과 ICD-9 4010/4011/4019는 버전을 함께 확인하고, 그 사람의 해당 코드가 붙은 첫 입원일을 시작/record_day로 쓴다. 끝은 NULL이다. 외래는 결과 이름과 무관한 OMR 기록 날이며, 응급실 등록일(없으면 입원일)~퇴원일에 겹치는 날은 뺀다.

OMR의 정확한 Blood Pressure 줄을 omr_systolic/omr_diastolic 두 값으로 가른다. source_unit은 빈 문자열이며 code_map seed의 post_hook이 B의 NULL 단위만 빈 문자열로 맞춘다. A seed 행은 건드리지 않는다. ICU는 220179/220180의 valuenum과 valueuom=mmHg를 읽고 code_map에서 mm[Hg] 뜻을 붙인다. record_day와 BP 날짜는 charttime의 날짜이고 storetime은 안정된 원본 행 식별자에만 사용한다. 입원/응급실 날 제외는 기존 L4가 담당한다.

A 수제 시험은 헤더만 있는 B CSV.gz를 가리켜 실제 B 자료와 격리한다. B의 작은 시험은 수제 CSV.gz와 빈 A raw를 갖는 별도 DuckDB에 dbt를 한 번 실행한다. M2B 시험은 113/44, 외래/입원일 겹침, 6월 말 경계와 ICD 버전, 사람별 다른 연도, ICU 입원일 제외, 마지막 140/60을 확인한다. 실제 전체 검사는 기존 A 원본과 B 데모 100명을 함께 읽는다.

다음 병원을 연결할 자리는 `models/common/` 네 파일의 hospital_rows CTE다. 그 병원의 staging 네 모델을 만든 뒤 각 CTE에 같은 열의 SELECT를 UNION ALL로 더하고 code_map에 병원 매핑 행을 추가한다. 병원별 시계·나이·방문 해석은 새 staging에 두고 L4~L6의 계산은 유지한다. 요청 05에서는 다음 명령의 출력이 비어 있어야 한다.

```bash
git diff --stat e5b86a5 -- models/intermediate models/marts models/reports
```

L0~L2·설치 근거는 `.local/FHIR-LINE-02/summaries/FHIR-LINE-02.reply.md`, M1 계산·시험은 `.local/FHIR-LINE-03/summaries/FHIR-LINE-03.reply.md`, common 층으로 옮긴 근거는 `.local/FHIR-LINE-04/summaries/FHIR-LINE-04.reply.md`, B 연결 결과는 `.local/FHIR-LINE-05/summaries/FHIR-LINE-05.reply.md`에서 확인한다.
