# 설계 04 · SQL 의미 동등성과 출처·사람·실제 기준일의 차원 모델

- **무엇을:** Q1 같은 날 성분 최솟값/입원 제외, Q2 마지막 유효일을 기준/대안 두 질의로 비교할 작은 실험과 차원 모델을 설계한다.
- **왜:** D1~D7·결정0001·0003·0005·0007·0010·0011·0013을 유지하며 JOIN/시점/집계의 오류를 구별하기 위해서다.
- **파일/층:** 이 설계와 Personal 기존 기획5절/README의 글만. 제품 SQL·설정·기대값·원천·DB는 변경하지 않는다.
- **확인:** 기존 코드/ADR·M3 저장 근거를 읽고 수기 입력/예상 결과를 작성한 상태다. 새 SQL·DB·시험 실행이나 성능 측정은 없다.
- **남은 것:** 방법 감독의 별도 사전 검수와 이후 사용자 실험 결정. 2026-10-22 · 작성자 의료 Codex · 상태 **사전 검수 초안 / 미구현·미실험**.

## 1. 끝낼 질문과 기존 본보기

[기획5절](/home/junhyun/personal/builds/medical-data-hands-on/thinking/research/a-prime-and-sql-plan-1021.md#5-sql차원-모델링으로-보여-줄-결과물)이 작은 입력·수기 예상 행의 정본이다. 두 업무 질문(Q1/Q2) 각각 기준/대안 한 쌍, 합계 후보 SQL4개에서 끝낸다. fixture에 대한 동등성 검증이며 모든 미래 입력에 대한 증명이나 최적화 결과가 아니다.

M3 [설계01](01-m3-omop.md)은 공통 모델의 자리를 바꾸면서 A/B 숫자와 원천 행을 유지했다. 요청07의 [기존 반환](/home/junhyun/dev/projects/fhir-indicator-line/.local/FHIR-LINE-07/summaries/FHIR-LINE-07.reply.md)의 daily413행/person29행 양방향 EXCEPT ALL 0·0은 **10/21 당시 전환의 실행 근거**다. 이번 데이터의 행 수나 새 질의의 결과로 재사용하지 않는다. 가져오는 방법은 ‘행 단위/키를 먼저 정함→독립 근거와 비교→같은 열의 다중집합 비교’이며 새 공통 절차나 양식은 만들지 않는다. 당시처럼 계산 층을 갈아타는 작업은 이번에 없다.

## 2. 두 비교의 의미와 전제

### Q1 · 유효한 하루 값(D1·D3·D4 / 0004·0006·0008·0010)

- **기준:** 고정 `int_bp_daily.sql`의 개념/단위·기간 필터, 상관 NOT EXISTS 입원/응급 제외, 성분별 MIN을 별도 실험의 입력 관계 이름으로 연결한다. 기존 결과에는 라벨만 있으므로 비교용 바깥 SELECT에서 기간 키(hospital,as_of_label,person_id)로 1:1 연결해 as_of를 붙인다. 고정 파일은 수정하지 않으며 이 입력 이름/비교 열 투영 차이를 기록한다.
- **대안:** 사람·측정일별 제외 여부를 존재 집합으로 만든다. 쓸 개념/단위·NULL 필터와 제외 집합 anti join 후, 사람·날짜·성분별로 먼저 MIN을 구하고 기간표에 연결한다. 없는 반대 성분은 NULL로 남기며 두 성분 모두 없는 날짜는 만들지 않는다.
- **같아야 할 출력:** `(hospital VARCHAR, person_id VARCHAR, as_of DATE, bp_date DATE, systolic_min DOUBLE NULL, diastolic_min DOUBLE NULL)`. 키는 앞4열이며 기간 시작~끝과 입원 양 끝을 포함한다. 해당 날짜와 일치하지 않는 다른 입원이 있어도 제외된 날을 살려서는 안 된다.
- **전제:** 기간의 `(hospital, person_id, as_of)`와 `(hospital, person_id, as_of_label)`가 각각 유일하고, 라벨→실제 날짜는 이 fixture의 사람별 측정 연도에서 한 가지다. 개념 seed의 `(concept_set,concept_id)`가 유일하다. 조건을 깨면 입력/키 검사에서 실패하며 MIN/ DISTINCT로 감추지 않는다.

### Q2 · 대상 사람과 마지막 날(D1·D2·D5~D7 / 0001·0003·0010)

- **기준:** 고정 `fct_bp_person.sql`의 나이18~85세, 고혈압 진단 시작일≤해당 연도6/30 및≤as_of, 진단 종료일NULL 또는≥연초, 연초~period_end_day 외래 방문 EXISTS로 대상 키를 고른다. Q1의 daily를 전체 키로 나눠 날짜 내림차순 순위1을 LEFT JOIN한다.
- **대안:** 같은 대상 조건을 유지하고 Q1에서 `(hospital,person_id,as_of)`별 MAX(bp_date)를 구한 뒤 그 **같은 날의 한 행**을 LEFT JOIN한다. 날짜가 없으면 NULL, 그날 한 성분만 있으면 반대 성분은 NULL이다. 대상 판단을 조건/방문 행의 일반 JOIN으로 곱하지 않는다.
- **같아야 할 출력:** 기존 사람별 열과 의미. `hospital/person_id/as_of_label`은 VARCHAR, `as_of/last_bp_date`는 DATE(마지막 날짜 NULL 허용), 혈압은 DOUBLE NULL, controlled INTEGER 0/1, reason VARCHAR. 없는 혈압→부분값→수축기140 이상→이완기90 이상→조절됨의 기존 사유 순서를 유지한다.
- **키/비교:** `(hospital,person_id,as_of)`가 fact 키다. 같은 열/자료형의 기준/대안 다중집합을 양방향 EXCEPT ALL로 비교하고 **각각** 수기 예상 행/키/값과도 비교한다. 두 질의가 같은 오답을 낼 수 있으므로 질의 간 차이0만으로 끝내지 않는다. DOUBLE 비교는 양쪽/수기 CSV를 같은 명시 자료형으로 읽고 NULL·날짜·문자열을 정확히 비교하며 임의 허용 오차를 추가하지 않는다.

기준 SQL은 `3e99c30`의 고정 계산 파일과 현재 파일이 같다는 기존 보호 계약을 전제로 한다. 기준/대안의 의미 연산은 서로 다른 질의 파일로 작성하고, 입출력 비교기를 공유하더라도 같은 처리 함수를 네 질의의 답 생성기로 재사용하지 않는다. 실행 전 입력 해시·기준 SQL 원문/변환 차이·후보 SHA를 별도로 기록하고 수용된 수기 기대값을 먼저 고정한다.

## 3. 차원 모델 계약안(D1·D2·D6 / 0003·0005·0007·0013)

아래는 **별도 실험 DB 안에서만 만들 후보**다. 작은 입력은 출처3·사람8·기준일별 기간16·daily19·대상 fact12행이다. `p1` 등은 가상의 전체 키다. A_PRIME과 A를 같은 사람 차원 행으로 합치지 않는다.

| 후보 관계 | 한 행/키 | 최소 열/연결 | 수기 기본 건수 |
|---|---|---|---:|
| dim_source | 논리 출처, PK hospital | hospital VARCHAR; derived_from VARCHAR NULL 자기 FK. A_PRIME→A, A/B는 NULL | 3 |
| dim_person | 출처 안의 원천 사람, PK(hospital,person_id) | 원천 키 VARCHAR; fixture OMOP id INTEGER 유일; 측정/출생 연도 INTEGER. source FK | 8 |
| dim_date | 실제 달력 날짜, PK as_of DATE | 연/월/일. 라벨은 날짜의 대체 키로 사용하지 않음 | 6 |
| source_as_of_scope | 입력에 사람이 있는 출처×실제 기준일, PK(hospital,as_of) | as_of_label VARCHAR, measurement_year INTEGER; source/date FK. **대상 fact에서 도출하지 않음** | 8 |
| fct_bp_person_as_of | 대상 사람의 기준일 상태, PK(hospital,person_id,as_of) | source/person/date와 source_as_of_scope FK; as_of_label; last_bp_date; systolic/diastolic; controlled/reason; denominator_contribution INTEGER=1; numerator_contribution INTEGER=controlled | 12 |
| bp_summary_by_date | 출처×실제 기준일 | scope를 LEFT JOIN; 분자/분모 INTEGER, rate DOUBLE NULL. 0명도 행 유지 | 8 |
| bp_summary_by_label | 기존 호환 출처×라벨 | 설정/사람 기간에서 출처×라벨6행을 먼저 만들고 fact를 같은 출처/라벨로 연결. 날짜 scope8행을 라벨만으로 붙이지 않음 | 6 |

fact의 전체 키는 기간표16행의 `(hospital,person_id,as_of)`에도 존재해야 한다. B/2031 사람을 B/2032 시점에 붙이는 것은 날짜 차원에 그 날짜가 있더라도 거부한다. 여기의 기준일은 임상 기간의 기준 시점이며 수신시각/수정 이력의 시간여행이나 dbt snapshot을 구현하는 것이 아니다(기록일 계약0006 유지).

사람은 모두 있으나 대상이 없는 B/2032 두 날짜도 scope에 남는다. fact의 가짜 ‘대상0명 사람’ 행이나 NULL 사람 키로 채우지 않는다. 한 출처에 사람 자체가0명일 때 행 보장은 기존 수용 범위 밖이다. birth/measurement 연도의 이력관리(SCD)·새 관찰기간 추론·환자 동일성 연결은 이 실험에서 다루지 않는다.

실제 기준일별 결과와 **기존 라벨 호환 결과를 다른 이름으로** 제공한다. B의 라벨 요약은 사람별 기준 연도를 모은 기존 정의다. 서로 다른 실제 연도를 공통 달력 코호트로 소개하지 않으며, 실제 날짜 요약의 비율을 더하거나 평균해서 라벨 비율을 만들지 않는다. 기획의 수기 표에서 B/2032는0/0/NULL, 기존 B/sep30은1/1·dec31은0/1이다.

출처 하나·실제 기준일 하나에서 서로 겹치지 않는 사람의 분자/분모 기여만 가산 가능하다. 사람 수는 시점 간 비가산, 혈압/마지막 날짜/비율은 비가산이다. A와 A_PRIME 동시 선택은0013에 따라 `DERIVED_SOURCE_OVERLAP`으로 거부할 실험 계약안이다. 범위 검사는 조상/파생 동시 선택을 먼저 확인하며, 나머지 복수 출처도 첫 실험에서는 지원하지 않는다. 첫 실험의 집계 입력은 한 출처씩으로 제한하며, 다른 출처끼리라도 환자 겹침을 모르는 통합 지표는 제공하지 않는다. 이것은 새 제품 집계 API를 만들겠다는 뜻이 아니다.

## 4. 파일·DB 경계와 검토 책임

아래 **구현 후보는 아직 만들지 않았다**. 지금 쓰는 파일은 이 글·기존 Personal 기획5절·입구 README뿐이다.

| 후보 경로(저장소 root 기준) | 미래 역할/한계 |
|---|---|
| `experiments/sql_modeling_04/fixtures/{sources,persons,conditions,visits,measurements}.csv` | 기획의 수기 입력만 전사. 개념 seed는 고정본을 읽기만 함. 원본 FHIR/DB에서 새 입력 생성 안 함 |
| `experiments/sql_modeling_04/expected_manual/{daily,person,summary_by_date,summary_by_label}.csv` | 별도 사전 검수로 수용한 수기 예상 결과만 전사. 제품/기준/대안 SQL 출력을 기대값 생성에 사용하지 않음 |
| `experiments/sql_modeling_04/queries/{q1_daily_reference,q1_daily_alternative,q2_last_reference,q2_last_alternative}.sql` | Q1/Q2 각 한 쌍. 실제 SQL 작성은 이후 실행 승인 범위 |
| `experiments/sql_modeling_04/{schema.sql,run.py}` | 격리 테이블/차원/연결과 명시 실행 입구. 기존 dbt 모델 검색/검사/quickstart에 편입하지 않음 |
| `.local/FHIR-LINE-SQL-04/experiment.duckdb` | 쓰기 허용 DB는 이 하나. 제품 `.local/FHIR-LINE-02/` DB를 열거나 attach하지 않음 |
| `.local/FHIR-LINE-SQL-04/{tmp,runs/<run_id>}` | 후보 출력/비교 결과/실패 보고·캐시. 현재 성공으로 이전 성공을 오인하지 않게 run별 분리 |

입력 CSV의 열 계약도 다음으로 한정한다. 모든 날짜는 ISO 날짜→DATE, 정수는 INTEGER, 값은 DOUBLE이며 CSV의 빈 셀은 NULL이다. NULL을0으로 바꾸지 않는다. 이 최소 입력을 별도 DB의 읽기 view에서 기존 OMOP 열 이름으로 투영한다(`omop_person_id`→OMOP `person_id`, 원천 사람 키는 `person_source_value`). 공식 OMOP 전체 적합성 시험을 대신하지 않는다.

| fixture | 열(앞의 식별 열로 중복/고아를 검사) |
|---|---|
| sources | hospital, derived_from |
| persons | hospital, person_id(원천 VARCHAR), omop_person_id, measurement_year, year_of_birth |
| conditions | hospital, source_row_key, omop_person_id, condition_concept_id, condition_start_date, condition_end_date(NULL 허용) |
| visits | hospital, source_row_key, omop_person_id, visit_concept_id, visit_start_date, visit_end_date |
| measurements | hospital, source_row_key, omop_person_id, measurement_concept_id, measurement_date, value_as_number(NULL 허용), unit_concept_id |

source_row_key는 앞 기획의 원천 사건/성분 키를 손실 없이 문자열로 만든다. 사람 FK는 `(hospital,omop_person_id)`와 `(hospital,person_id)` 관계를 통해 확인한다. 사건의 키는 `(hospital,source_row_key)`이고, 사람 밖/다른 출처 사람에게 붙인 사건은 고아로 거부한다. 의도적으로NULL인 값/진단 종료일 외의 모든 입력 열은 필수이며 sources.derived_from은 A/B만 NULL이다. 입력 변형은 별도 case에서 한 가지씩 바꾼다.

새 소형 실험 실행 승인 뒤에도 기본 원천88행·입력 변형4개 이하(각128행 이내), requirements.lock에 고정된 DuckDB1.4.3/Python 표준 라이브러리·threads1·memory_limit128MB·nice10·무거운 실행1개만을 제안한다. 실험 증가512MiB/프로젝트 전체5GB 중 먼저 닿는 한도에서 중단한다. tmp/cache도 위 폴더 안이다. 지금은 DB/실험 디렉터리/SQL/CSV/패키지를 만들지 않는다.

기존 `expected/answer_key/expected_a_prime/answer_key_a_prime/`와 원본·공식 OMOP DDL·기존 설계/ADR은 불변이다. `FROZEN_BASE=3e99c30`, L4~L6 및 indicator_concepts/as_of_labels, scripts/check.sh·dbt_project.yml·요구 패키지·제품 DB도 그대로다. 새 파일을 frozen 폴더에 추가하거나 기준을 비워 우회하지 않는다. 안전한 출력 경계는 R02의 ‘금지 경로 확인 후 새 실행 보고’ 원칙을 참고하되 기존 코드 재구현/제품 변경으로 범위를 넓히지 않는다.

예상 결과 작성자는 의료 Codex(이 문서/기획)다. 방법 감독의 다른 세션 검토 위치 후보는 Personal `builds/method/thinking/exchange/REQ-medical-sql-modeling-04/pre-review.md`이며 아직 검수/작성 완료가 아니다. 감독은 선언 입력과0001/0003/0010/0013으로 행·키·NULL·사유를 직접 다시 센다. 독립 검수 뒤 입력·기대 CSV·계약/명세의 정확한 hash를 고정한 다음 후보 질의를 구현하는 순서를 제안한다. 기존 SQL 시험의 관측값이나 같은 작성자의 수기표를 새 독립 기대 결과로 소개하지 않는다.

## 5. 종료 조건과 반례(모두 미실행)

| ID/정의 | 뒤집어 볼 오류 | 수기 기준/실패해야 할 차이 |
|---|---|---|
| S01 D4 | m1/m2 중 한 측정 전체를 고름 | A* p1/9월30일은135/75. 145/75 또는135/95면 실패 |
| S02 D5·D7 | 마지막 완전한 쌍 또는 성분별 마지막 값을 섞음 | 12월31일 상태는12월20일121/NULL/부분값 사유. 12월1일124/92 또는121/92면 실패 |
| S03 D3·D5 | raw 최댓날짜를 먼저 골라 NULL만 있는 m8을 채택 | m8은 daily0행. 마지막 날은12월20일이어야 함 |
| S04 D3 | 제외 기간의 끝을 빼거나 한 입원 밖이면 허용 | 10/1·10/2·12/30은 daily0행. 다른 입원과의 불일치로 해당 날을 살리면 실패 |
| S05 D2 | 진단2×외래2의 JOIN으로 대상 증폭 | A* p1은 시점당1행. 값이 같아도4행이면 실패; DISTINCT로 사후 숨김 금지 |
| S06 D1·0005 | 출처 없이 p1을 연결/순위 분할 | A/A_PRIME/B의 서로 다른 연도·값이 섞이면 실패. 실제 복합 키로 비교 |
| S07 D1·0010 | 기준 시점 없이 MAX하거나 B scope를 라벨만으로 연결 | 9월에12월 값 금지. B/2032 두 시점은0명이어야 함 |
| S08 L2·0010 | 격리 입력 개념목록에 (systolic,3004249)1행 추가(보호 seed 수정 아님) | 중복키1개/해당키 count2로 입력검사 실패. MIN 때문에 최종값이 같아도 통과 금지 |
| S09 0005·0007 | A/p1 사람 행을1번 복사, 또는 A의 omop_person_id=999·유효 개념/단위/날짜/값을 가진 측정1행 추가(각 별도 변형) | 중복은 자연키1그룹(count2)·OMOP id1그룹(count2), 고아 변형은 고아1행을 보고 결과 채택 실패 |
| S10 D2·D6 | B/p1 진단1행 제거 | B fact0행; 날짜 요약4행/라벨요약2행은 모두0/0/NULL. scope를 fact에서 만들면 실패 |
| S11 0013 | A와 A_PRIME을 같이 집계 범위로 지정 | 조상/파생 출처 중복 오류. 9월2/4·0.5를 정상 지표로 채택하지 않음 |
| S12 D1·D6 | 시점별 분모/비율을 더하거나 B를2025로 덮음 | A의2+3은 고유3명 아님. B는2031/2032 실제 날짜 유지; 라벨 호환 출력과 구분 |

소형 입력을 바꾸는 경우는 S08 한 개, S09 두 개, S10 한 개의 **4변형**뿐이다. 나머지는 기본 수기 입력에서 잘못된 질의/범위 지정을 비교하는 반례다. 고아·중복 입력 검사는 후보 실행 전이다. 입력 오류 사례를 정상 데이터의 임의 dedupe나0건 성공으로 처리하지 않는다. 변형은 고정된 기본 CSV/seed를 수정하지 않고 격리 case의 복사본/추가 행에서만 적용한다. 고아1행의 source_row_key는 새 값이고 나머지 FK/형식은 유효하므로 원인을 하나로 제한한다.

미래 실행의 완료는 (1) 검수된 수기 입력/기대값 hash 일치 (2) Q1 19행/Q2 12행의 키·모든 셀/NULL·자료형 일치 (3) 양방향 EXCEPT ALL 각각0 (4) 차원/관계/범위 키 유일·고아0, 요약8/6행과 분모0 변형 일치 (5)12반례의 기대한 거부/차이 확인 (6) 기존 보호 경로 Git diff/변경 목록 불변과 디스크/보고 한계 확인이다. 먼저 다르면 실행을 실패로 끝내고 기대값을 SQL 결과에 맞춰 고치지 않는다. 서로 다른 실행의 성공 보고를 덮어쓰지 않는다. 같은 실패3회를 넘겨 반복하지 않고 총 실행2시간 이내다.

지금 준비 완료의 근거는 글/수기 표/참조 경로·변경 diff뿐이다. check.sh/기존 회귀/새 DB/질의/EXPLAIN ANALYZE는 실행하지 않았고 실행 성공으로 표시하지 않는다. 코드 이해용 그림과 생성기도 만들지 않는다.

## 6. 선택과 미결정

| 구분 | 정한 범위/남기는 결정 |
|---|---|
| 기존 수용 | A′완료·D1~D7·원값/계보·미만 경계·실제 기준일·분모0/NULL·제품 고정 유지. 이 사실을 사용자에게 다시 고르게 하지 않음 |
| 이번 설계안 | 위8사람 입력·두 비교/한 격리DB·차원/범위/fact5관계와 두 요약·12반례. 성능 실험/마트제품 편입 없이 작은 의미 동등성만 확인하는 후보 |
| 다른 세션 사전 검수 | 수기 행/키/값과 기준/대안의 의미·범위, 입력변형의 오류 개수·독립성 확인. 검수 위치/작성 여부는 앞4절 |
| 사용자 결정 E01 | 설계 검수 뒤 **이 작은 실험 구현·실행을 시작할지**. 지금 준비 작업의 재승인 질문이 아니며 이 문서 자체는 실행 지시가 아님 |
| 별도 후속 E02 | EXPLAIN ANALYZE/성능 입력·최적화/제품 채택 여부. 실행량·변경 경로를 정한 새 요청 없이 하지 않음 |
| 사실 미확인 | 대안 질의의 실제 동등성/실행계획·성능은 미측정. KCD 개별 매핑·MT056 소수 규칙·새 관할/규정 적합성도 이 설계로 닫지 않음 |

## 7. 읽은 근거와 설계 이유

- [결정0001](../decisions/0001-indicator-definition-d1-d7.md), [0003](../decisions/0003-hospital-b-three-definitions.md), [0010](../decisions/0010-definition-rules-in-calculation-layer.md), [0013](../decisions/0013-a-prime-derived-source-and-precision.md): 학습용 정의·환자별 연도·계산 위치·파생 출처와 다음 실험 경계.
- 제품78f87a2의 `models/intermediate/int_person_period.sql:2`, `int_bp_daily.sql:2`, `models/marts/fct_bp_person.sql:2`, `dim_as_of.sql:2`, `models/reports/bp_summary.sql:2`: 실제 기간·존재 조건·성분 최솟값·마지막 날·빈 분모 유지. SQL 원문을 읽었고 새 실행은 하지 않음.
- `tests/test_a_prime.py:254`, `tests/test_m1_models.py:252`·`:322`: 기존 수기 시험의 날짜/부분값/분모0 계약. 이 저장 출력 자체를 새 수기 기대값이라고 하지 않음.
- [M3 설계01](01-m3-omop.md)과 요청07 §3/기존 반환의 ME-02: 원래 행/키와 같은 열의 다중집합 비교를 본보기로 재사용.
- Personal 기획5절의 REQ-53/REQ-60 원문·검수 한계 링크를 그대로 재사용. unique_key와 유일성 검사, 실패와 자동 복구를 구분하며 새 분석/공통 양식/도구 도입은 없음.

고른 이유는 고정 계산과 실험을 별도로 두고, 작은 반례에서 의미부터 확인하기 위해서다. 같은 DB/고정 marts에 새 테이블을 더하는 안은 기존 보호와 충돌한다. 원본 반복 복제로 큰 성능 입력부터 만드는 안은 동등성 질문을 가리고 실행 승인도 없다. 날짜만 있는 fact는 출처/사람을 잃고, 라벨만 있는 fact는 B의 다른 실제 연도를 잃으므로 선택하지 않았다.
