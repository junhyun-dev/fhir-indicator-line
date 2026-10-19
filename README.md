# fhir-indicator-line

합성 FHIR Bundle을 두 배치로 나누고, 받은 본문을 보존하며, 같은 자원의 최신 내용을 하나로 고르는 학습 프로젝트다. 요청 02는 L0~L2와 dbt 틀까지다. D1~D7 임상 규칙을 적용하는 L3~L6 SQL 모델은 요청 03에서 Codex가 쓰고, `expected/` 기대 결과(읽기 전용)와 그 비교 검사는 짝 Claude 세션이 쓴다(10/19). 검사 명령은 `sh scripts/check.sh` 하나이고, 지킬 것은 `AGENTS.md`에 있다.

```bash
mkdir -p .cache/FHIR-LINE-02/tmp .cache/FHIR-LINE-02/pip models/{staging,intermediate,marts}
TMPDIR="$PWD/.cache/FHIR-LINE-02/tmp" python3 -m venv .venv
PIP_CONFIG_FILE=/dev/null PIP_CACHE_DIR="$PWD/.cache/FHIR-LINE-02/pip" TMPDIR="$PWD/.cache/FHIR-LINE-02/tmp" \
  .venv/bin/python -m pip install --require-hashes -r requirements.lock
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line split
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line load data/batches/batch_1
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line load data/batches/batch_2
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line check
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

L3~L6은 `source('fhir', 'latest_resources')`에서 다음 순서로 읽는다. 두 기준일은 `seeds/as_of_dates.csv`, 고혈압 코드 목록은 `seeds/hypertension_codes.csv`에 있다. FHIR의 코드·값 연결과 날짜 변환은 staging에서 한 번 처리한다.

| 층 | 모델 | 한 행 |
|---|---|---|
| L3 staging | stg_patient, stg_encounter, stg_condition, stg_bp_component | 환자 / 방문 / 진단×코드 / 관찰×성분 코드 |
| L3 staging | stg_as_of_dates | 기준일과 2025년 측정 기간 |
| L4 intermediate | int_bp_daily | 기준일×사람×사용할 혈압 날짜 |
| L5 marts | fct_bp_person | 기준일×평가 대상 한 사람 |
| L5 marts | dim_as_of_dates | 대상이 없는 경우에도 요약에 전할 기준일 |
| L6 reports | bp_summary | 기준일별 분모·분자·비율 |

D1은 날짜 문자열의 앞 10자를 쓰고 기준일 뒤 기록을 보지 않는다. D2 대상 판정은 fct_bp_person의 eligibility CTE 한 곳에 있다: 연말 나이 18~85세, 상반기까지 시작해 측정 연도와 겹친 고혈압, 기간 내 AMB 방문이다. 고혈압·혈압 코드는 system 없이 code만 비교한다.

D3·D4는 입원/응급실 기간(양 끝 포함)을 제외하고 `valueQuantity.code=mm[Hg]`인 숫자를 성분별로 그 날의 최솟값으로 묶는다. 성분 위치는 쓰지 않는다. 쓸 성분이 없는 날은 없애고, 하나만 있는 날은 남긴다. D5·D6은 마지막 유효일을 골라 `혈압 없음` → `마지막 날에 한쪽 값만` → 140/90 임계값 순서로 분류한다. 혈압 없는 대상도 분모에 남는다. 대상 0명인 기준일은 분모·분자 0, rate NULL이다. **D7 제외 대상은 빼지 않는 학습용 계산**이며 CMS 지표 전체 구현은 아니다.

모델은 view라서 현재 latest_resources를 읽는다. as_of는 기록 날짜의 가시성을 뜻하며, 과거 배치 버전으로 되돌린 데이터베이스 snapshot을 뜻하지 않는다. 서로 다른 시각인 원본 갱신시각·임상 시각·수신시각을 합치지 않는다.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/dbt.py debug
sh scripts/check.sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line layers
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m fhir_line check --strict
```

wrapper가 프로필·DB·임시파일·로그 경로와 telemetry 설정을 전달하므로 전역 dbt 설정은 필요 없다. 확인 사다리 전에 dbt parse로 실제 의존 관계를 읽는다. staging은 source/seed, intermediate는 staging, marts는 intermediate/staging, reports는 marts에만 의존한다. marts끼리 읽지 않는다. 선언하지 않은 직접 테이블 읽기도 거부한다. 동적 relation macro와 복잡한 직접 SQL 접근은 이 작은 검사기의 지원 범위가 아니므로 명시적 source/ref와 CTE로 표현한다.

확인 사다리는 원본/배치/raw/latest 행 수, 자원 종류·혈압 수, 같은 자원 본문을 비교한다. ④는 `person_<YYYY-MM-DD>.csv`의 7열·모든 행을 fct_bp_person과 비교하고, summary CSV의 날짜·분모·분자·비율 4열을 bp_summary와 비교한다. 두 결과 모델의 자료형 계약도 검사한다. 행 순서는 무시하고 중복 행 수는 보존하며 숫자의 표현 차이는 해당 DB 자료형으로 정규화한다. ⑤는 지정 환자의 12/01 혈압 원문·해시를 세 층에서 비교한다. expected를 쓰거나 수정하지 않는다.

`sh scripts/check.sh`는 기대 CSV의 해시·읽기 전용 상태, 기존 검사기 시험, 작은 별도 DuckDB의 테스트 01~15와 Q3, 실제 dbt build, 층 방향, 사다리의 순서로 실행한다. 가짜 FHIR를 쓰는 시험은 실제 기대 파일과 원본을 사용하지 않고 dbt를 한 번만 실행한다. 기본 check는 기대 폴더/모델 부재를 기다림으로 표시할 수 있지만, 종료 명령의 `check --strict`는 기다림도 실패로 센다.

①은 `raw=배치1+배치2`, `latest=배치1+배치2−공통 (resource_type,id) 수=원본 자원 수`를 검사한다. 날짜 없는 자원을 두 번 받으면 raw에 배치마다 한 행씩 남고 latest에는 하나가 남는다. 공통 자원 수는 따로 보고한다. strict에서 모든 칸을 통과하면 exit 0, 실패나 기다림이 있으면 exit 1이다. 결과는 `.local/FHIR-LINE-02/summaries/verification-ladder.json`과 `.md`에 남는다.

L0~L2·설치 근거는 `.local/FHIR-LINE-02/summaries/FHIR-LINE-02.reply.md`, L3~L6·테스트·결과는 `.local/FHIR-LINE-03/summaries/FHIR-LINE-03.reply.md`에서 확인한다.
