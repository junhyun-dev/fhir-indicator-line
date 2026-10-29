# fhir-indicator-line

모양이 다른 두 병원 기록(합성 FHIR · MIMIC-IV 데모)을 공통 데이터 모델(OMOP CDM 5.4)로 옮기고, 같은 정의로 혈압 조절률을 계산합니다. 출처별 처리는 전처리(staging)와 코드 매핑에 두고, 출처를 추가해도 계산 모델이 유지되는지 검사합니다.

| 병원 · 원천 | 9월 말 · 조절/대상 | 연말 · 조절/대상 |
|---|---|---|
| A · Synthea FHIR | **3/5 · 60%** | **4/6 · 66.67%** |
| B · MIMIC-IV 데모 | **4/9 · 44.44%** | **3/9 · 33.33%** |
| A′ · A의 파생 입력 | **3/5 · 60%** | **4/6 · 66.67%** |

- 파이프라인과 독립적으로 센 기대 결과(expected output)와 환자별 값·요약·자료형을 비교합니다.
- 원천에서 센 OMOP 행 수, 혈압 예시의 값, 원래 행으로 이어지는 키를 확인합니다.
- 계산 모델과 지표 개념표가 고정된 기준 이후 바뀌면 검사가 실패합니다.

A′는 A에서 파생한 문자열 입력입니다. 원래 SNOMED·LOINC·UCUM 코드와 체계를 보존하고 같은 계산을 재사용합니다. 독립 환자 집단으로 A와 합산하지 않습니다. KCD 후보는 미확인 주석이며 KCD 연동은 구현하지 않았습니다.

## 돌려 보기

Linux x64, **Python 3.12**와 venv, Git, curl, coreutils(cmp·sha256sum·du 등)가 필요합니다. 저장소의 전체 Git 이력이 있어야 합니다. JDK와 Python 의존성은 프로젝트 안에 설치하고, 시스템 설정은 바꾸지 않습니다.

저장소 root에서 명령 하나를 실행합니다.

```sh
sh scripts/quickstart.sh
```

완료 검증은 저장소에 함께 둔 `answer_key_lead/`를 기본으로 읽어요. 리드가 제품 밖에서 정하고 검수한 기대 결과를 사용하며, 원본은 리드가 따로 보관해요. WP-5의 E01 두 행은 검수된 JSON에서 옮겼고, 나머지는 원본과 같은 바이트예요. quickstart는 해시를 확인한 뒤 이 사본을 읽기 전용으로 잠가요. 아래의 ‘셀 단위 비교와 실행 이력’에서 부분 시험과 완료 검증을 구분해요.

받기 → 고정 해시 확인 → FHIR 생성 → 배치 나누기와 적재 → A′ 입력 생성 → 전체 검사 → 독립 재계산을 차례로 실행합니다. 처음에는 인터넷이 필요합니다. Temurin **17.0.20.1+1**, Synthea **v4.0.0**, MIMIC-IV demo **2.2**를 고정하며, Python 패키지는 requirements.lock의 해시와 대조합니다. 이미 해시가 맞는 원천은 받거나 생성하지 않고 재사용합니다.

아래 받기·디스크·시간은 A/B 판(2026-10-21)의 측정 기록입니다. A′는 기존 설치와 원천을 사용하며 새 패키지를 추가하지 않습니다.

- 받는 양: **약 453MB** — Temurin JDK 193MB · Synthea jar 201MB · Python 의존성 약 43MB · MIMIC-IV 데모 zip 16MB.
- 디스크: 새 복제본에서 두 번 돌린 뒤 **약 1.43GB**(압축본 · JDK · venv · 생성 FHIR · DB · 캐시 포함) · 상한 5GB를 스크립트가 확인합니다.
- 시간(2026-10-21 · 리눅스 노트북에서 실제로 잰 값): Python 의존성 · JDK · Synthea 받기와 병원 A FHIR 생성 **약 1분 40초**, 그 뒤 적재 · 전체 검사 · 독립 재계산 **약 1분 40초**, 원천이 이미 있는 두 번째 실행 **약 1분 30초**(받기 0).
- **PhysioNet이 느릴 때:** 2026-10-21에는 PhysioNet 전송이 초당 약 1KB여서 zip을 끝까지 받지 못했습니다(이어받기는 동작). 다른 경로로 받은 같은 zip을 `.local/public-data/mimic-iv-demo-2.2/download/mimic-iv-clinical-database-demo-2.2.zip`에 두면 받기를 건너뛰고, zip 안의 공식 `SHA256SUMS.txt`와 고정 해시로 확인한 뒤 씁니다.
- JVM은 최대 heap 2GB·CPU 2개, DuckDB는 512MB·thread 2개로 제한하고 생성과 검사를 순서대로 실행합니다.

완료 화면의 결과 형식은 다음과 같습니다. 실행시간은 해당 실행에서 측정한 값으로 표시됩니다.

```text
완료: check.sh 종료 0
독립 재계산: 6파일 모두 같음(cmp)
A′ 독립 재계산: 4파일 모두 같음(cmp)
| 병원 | 기준 시점 | 분자/분모 | 조절률 |
|---|---|---|---|
| A | sep30 | 3/5 | 0.6 |
| A | dec31 | 4/6 | 0.6667 |
| A_PRIME | sep30 | 3/5 | 0.6 |
| A_PRIME | dec31 | 4/6 | 0.6667 |
| B | sep30 | 4/9 | 0.4444 |
| B | dec31 | 3/9 | 0.3333 |
```

실패하면 단계와 로컬 로그 경로를 표시하고 중단합니다. 해시가 다르면 기존 원천을 덮어쓰지 않습니다. FHIR의 비임상 실행 metadata는 실행마다 달라지며 고정 해시 대상은 FHIR 38파일입니다. 환자는 생존 30명과 사망 6명이고, 기관·의료인 Bundle을 더해 38파일입니다.

## 셀 단위 비교와 실행 이력

글: 만들기 · 의료 · Codex · 2026-10-27

`sh scripts/check.sh`의 검사 ④는 A/B의 사람별 결과와 요약에서 다른 열의 기대값·실제값을 알려 줍니다. 사람별 행 키는 `(hospital, as_of_label, person_id)`, 요약은 `(hospital, as_of_label)`입니다. 같은 키가 양쪽에 하나씩 있으면 셀을 비교하고, 키가 중복되면 같은 행을 중복 횟수만큼 제외한 뒤 빠진 행·남는 행을 기록합니다. 숫자는 기존 정규화 규칙으로 비교하므로 `4`와 `4.0`은 같습니다.

비교 전에 기대 CSV와 DB 양쪽에 필수 행 키가 모두 있는지 확인해요. 하나라도 빠지면 열 계약 실패와 빠진 열 이름을 반환하며, 일부 키만으로 비교를 계속하지 않아요.

- 최신 결과는 기존 `.local/FHIR-LINE-02/summaries/verification-ladder.md`와 `.json`에 계속 씁니다.
- 매 검사 보고마다 `.local/FHIR-LINE-02/runs/<UTC 시각>/cell-diff.csv`를 새로 만들고 `runs/index.csv`에 실행 시각·현재 Git 커밋·통과/실패·셀 차이/빠진 행/남는 행 수를 덧붙입니다. 통과 시 CSV에는 헤더만 남습니다. 이전 실행 CSV는 덮어쓰지 않습니다.
- 전체 행 키와 원래 오류 설명은 Git 밖의 로컬 CSV/JSON에만 보존해요. Markdown과 `python -m fhir_line check`는 같은 허용 목록으로 병원·기준 시점·표·열·공개 가능한 기대값/실제값·건수·상태를 새로 구성해요. 설명 문자열에 ID가 들어 있어도 그 원문을 화면으로 보내지 않아요. 알 수 없는 설명·필드는 제외하고, 식별자 열의 셀값이나 허용하지 않은 문자열은 비공개로 표시해요. 로컬 JSON의 `run.product_dirty`는 기록한 커밋에 미커밋 변경이 있었는지 알려 줘요.
- `index.csv`는 파일 잠금 안에서 기존 머리줄의 순서·열 수와 각 행의 열 수를 확인해요. 계약이 다르면 기존 파일을 덧쓰지 않고 오류를 반환하며, 이번 실행의 CSV는 남겨요. 최신 JSON/Markdown도 실패로 바꿔 이전 성공을 이번 결과로 오인하지 않도록 해요. 강제 종료 중 여러 파일의 갱신을 하나의 트랜잭션으로 보장하는 기능은 아니에요.
- 이 CSV의 셀 상세 범위는 검사 ④의 A/B 두 결과 테이블입니다. 자료형·OMOP·A′ 등 기존 검사도 전체 통과/실패에는 포함되므로 셀 차이 0개만으로 전체 통과를 판단하지 않습니다.

리드가 제품 밖에서 고정한 다섯 경우의 시험은 `answer_key_lead/cell_diff/cases.json`과 같은 폴더의 `SHA256SUMS`를 읽어요. `FHIR_CELL_DIFF_CASES`로 다른 고정 파일을 지정할 수도 있어요. 파일이 없거나 해시가 다르면 기본 시험과 완료 검증이 실패해요. 기대 결과를 제품 실행값에서 만들지 않아요. 사본에는 비교에 필요한 사람 식별값도 있으므로 데이터 출처와 공개 범위는 [NOTICE](NOTICE)에 명시해요.

다른 복제본에서 외부 다섯 사례를 의도적으로 빼고 **부분 시험만** 하려면 아래처럼 명시해요. 출력에는 `건너뜀 · 완료 검증 아님`이 나와요. 이 환경변수로 `check.sh`를 실행하면 바로 실패하며 완료 검증을 우회하지 못해요.

```sh
FHIR_SKIP_EXTERNAL_CELL_CASES=1 .venv/bin/python -m unittest discover -s tests
```

## DQD를 참고한 품질 검사

글: 만들기 · 의료 · Codex · 2026-10-27

`sh scripts/check.sh`는 OMOP 8개 테이블에 닿는 품질 검사 9개도 실행해요. 개념의 도메인과 유효성, NULL과 미매핑, 날짜 순서, 출생 연도 하한, 혈압 단위를 확인해요. 기준값은 `models/omop/schema.yml`에 있고, 별도 패키지 없이 직접 쓴 generic test를 사용해요. [검사 목록과 분모·한계](docs/design/05-dbt-quality.md)를 함께 봐요.

원천에서 옮기지 못한 진단 수는 병원별로 따로 경고해요. 이미 옮겨진 진단에서 개념 0이 없다는 것만으로 전체 매핑이 완전하다고 보지 않아요. 이 경고는 기본 실행을 실패로 바꾸지 않으며, 지표 모델과 출력 테이블은 그대로예요.

## 로컬 조회 화면 v1

글: 만들기 · 의료 · Codex · 2026-10-27

기존 설치와 DB가 있으면 명령 하나로 S01 지표 현황·S02 대상 환자·S03 상세·S04 품질 검사·S05 오류내역을 만들어요. 서버나 로그인은 필요하지 않아요.

```sh
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 --quiet nice -n 10 .venv/bin/python -B scripts/render_report.py
```

명령이 알려 준 `S01.html`을 브라우저에서 열어요. 결과는 `.local/FHIR-LINE-V1-1027/ui-runs/local/<run_id>/`에 있어요. `latest.json`은 이번 시도, `latest-success.json`은 마지막으로 생성·검증한 묶음이에요. 실패한 시도와 과거 성공을 구분하고, 기존 결과는 덮어쓰지 않아요.

DB는 읽기 전용 트랜잭션으로 읽어요. `--db <사본 폴더>/fhir.duckdb`로 사본을 읽을 때도 파일명은 유지해야 해요. 기존 뷰가 `fhir` catalog를 참조하므로 사본을 다른 이름으로 바꾸면 조회가 실패해요. 같은 스냅샷에서 A/B 사람별·요약·자료형과 품질 SELECT를 확인하고, 저장된 수치로 화면을 만들어요. expected의 값을 실제값으로 채우거나 rate를 다시 계산하지 않아요. **이 조회 검증의 통과는 `check.sh` 전체 실행 통과와 달라요.** 이번 명령에서 실행하지 않은 Python 시험·dbt 빌드는 미실행이며, 과거 dbt 결과와 `runs/index.csv`는 현재 DB와 연결 미확인인 과거 기록으로 구분해요. 기존 전체 검사 이력에 부분 검증의 성공을 추가하지 않아요.

현재 정의는 `config/indicator_definitions/v2/manifest.json`으로 등록했어요. [결정 0015](docs/decisions/0015-bp-days-require-both-components.md)에 따라 수축기·이완기가 모두 있는 날 중 마지막 날을 사용해요. 그날이 없으면 날짜·두 값은 NULL, 이유는 「혈압 없음」, 분자는 0이며 분모에는 남아요. 일별 부분값은 보존해요. 코드 목록은 v1이며 기존 seed의 A/B 진단 코드 다섯 개와 A′의 같은 SNOMED 의미를 유지해요. 등록된 해시와 실제 정의 파일이 다르면 완료 처리하지 않아요. 기존 v1 manifest는 과거 등록 자료로 보존하며 현재 계산을 v1로 표시하지 않아요. DB의 열·키와 실제 A·A′·B 지표 수치는 같아요.

환자 번호는 병원·실행 안에서만 사용하고 두 시점과 필터에서 유지돼요. 원래 사람 ID·앞부분·해시·나이·원문·파일 경로는 브라우저 HTML·JSON·링크에 내보내지 않아요. 상세의 표준 행은 성분별 후보이며, 같은 날짜·값만으로 원천 선택을 확정하지 않아 **원천 연결 미확인**으로 표시해요. 동률 후보와 부분값을 보존해요.

`--public`은 별도 `ui-runs/public/`에 집계·검증 화면만 생성하고 사람별 객체와 S02/S03 파일을 만들지 않아요. 이 옵션은 게시 승인이 아니며 push나 배포를 하지 않아요. 원래 행 키가 필요한 차이 CSV는 브라우저 폴더 밖 `private-runs/`에만 남겨요.

조회 화면 v1의 완료 검증에는 `answer_key_lead/v1/`의 두 JSON·README와 SHA256SUMS가 필요해요. E01의 수기 입력·기대 결과는 `answer_key_lead/e01/`에 있어요. 별도 위치는 `FHIR_V1_EXPECTED_ROOT`·`FHIR_E01_EXPECTED_ROOT` 또는 E01의 `--expected-root`로 지정해요. 없거나 해시/검수 문구가 다르면 실패해요. 이 자료를 새 실행값으로 만들거나 자동으로 보충하지 않아요. 화면 시험은 `tests/test_v1_report.py`이며 기존 셀 비교 다섯 경우와 E01 시험도 유지해요. 화면 버전과 지표 정의 버전은 구분해요. S00 로그인·S06/S07 제품 변경 이력·AI·공개 게시·고혈압 코드 목록 확대는 범위 밖이에요.

`sh scripts/check.sh`는 제품 사본의 전체 해시와 읽기 전용 상태를 먼저 확인해요. 리드 원본이 있는 컴퓨터에서는 파일 집합과 바이트도 대조해요. E01의 사람별 CSV와 해시 목록은 원래 E01에 검수된 `wp5-bp-days-both-values/expected.json`의 두 변경 행만 반영한 결과와 대조해요. 원본이 없는 컴퓨터에서는 사본 해시로 검사하고 ‘원본 대조 건너뜀(이 컴퓨터에 원본 없음)’을 표시해요. 원본 위치를 바꾸려면 `FHIR_LEAD_ANSWER_SOURCE_ROOT`를 지정해요. 원본이 없다는 이유로 사본의 해시 검사를 건너뛰지는 않아요. WP-5의 43사례는 M1·E01·A′·B·OMOP·화면 시험에서 각각 대조해요.

## A′ 임상 보존 검사

A′ 원래 임상 의미 보존 범위는 2026-10-22 방법 감독의 최종 검수로 완료했습니다(수용 대상 `52726ab`). 초기 실패 처리 R02·코드 이해 C01·실제 저장값 독립 대조 A01/A02를 포함하며, 수용 범위와 근거는 [결정 0013](docs/decisions/0013-a-prime-derived-source-and-precision.md#최종-수용2026-10-22)에 기록했습니다. KCD 연결은 계속 보류합니다.

`data/a_prime/`의 CSV 넷과 manifest는 A 원본에서 생성하는 실행 입력이며 Git에서 제외합니다. 비교 기준인 `expected_a_prime/`의 사람별·임상 행과 manifest, 별도 계산기인 `answer_key_a_prime/`는 Git에서 추적합니다. 따라서 합성 개인별 기록이 모두 저장소 밖에 있는 것은 아닙니다. 사람36명·진단1,455행·방문2,144행·BP555묶음/1,110성분을 보존하고 소수10성분을 반올림하지 않습니다. `109.51/76.761`은 프로젝트 소수 확장이며 보험청구 형식 전체 준수를 뜻하지 않습니다.

```sh
.venv/bin/python -m fhir_line aprime-generate
.venv/bin/python scripts/dbt.py build
.venv/bin/python -m fhir_line aprime-check
```

검사 ⑦은 생성 입력과 staging에서 각각 추출한 원천 사실4,745개, OMOP 자연 키별3,372행과 사람별/요약 출력을 비교합니다. 원본이나 기대값을 실제 결과로 복사하지 않습니다. 원래 코드/system이 승인된 쌍일 때만 기존 임상 의미를 붙이고, 다른 체계의 같은 코드·KCD 후보로 보충하지 않습니다. 기존 A/B의 보호와 계산 층 고정도 함께 검사합니다.

`expected_a_prime/SHA256SUMS`는 루트 기준8파일의 해시입니다. 파일/목록은0444, 디렉터리는0555로 고정했고 모든 제품 비교에서 `verify_lock`을 먼저 확인합니다. 새 Git 복제본에서는 해시가 맞는지 확인한 뒤 쓰기 비트를 제거합니다. 고정된 README/manifest의 준비 단계 문구는 작성 시점의 snapshot이고, 현재 고정 상태는 실제 해시/권한 검사로 판단합니다.

기존 설치와 고정 원천을 이미 갖춘 환경은 `FHIR_OFFLINE=1 sh scripts/quickstart.sh`로 받기 없이 확인할 수 있습니다. 기존 작업실의 기대값 권한을 자동으로 바꾸지 않습니다. 파생 출처·namespace·소수/날짜·미대응의 계약은 [설계03](docs/design/03-a-prime-preserve-all.md)에 있습니다. `ok=true`는 원래 임상 경로의 보존 비교이며 KCD 매핑이나 의료적 적합성 수용이 아닙니다.

2026-10-22에는 로컬 새 복제본에서 기존 원천 43파일과 설치된 Python 환경을 재사용해 이 오프라인 명령을 두 번 확인했습니다. 각각 **101.38초·100.03초**, 최대 RSS **1,045,808·1,075,140KiB**, 추가 다운로드 **0바이트**였고 두 번 모두 전체 검사와 독립 재계산 10파일 비교를 통과했습니다. 두 번째 실행에서 A′ 입력 5파일의 해시·바이트·수정 시각도 같았습니다. 정리 직전 복제본은 약 **476MB**, 원래 작업실을 포함한 디스크 할당량은 약 **3.04GB**로 확인했습니다. 위 A/B 판의 인터넷 설치 측정과 구분되는 재사용 검증입니다.

## 기대 결과를 직접 다시 세기

[answer_key/](answer_key/README.md)의 스크립트 셋은 Python 표준 라이브러리로 원천을 읽고, dbt 모델·DuckDB를 사용하지 않습니다. quickstart는 별도 임시 디렉터리에서 실행해 아래 여섯 파일을 `cmp`로 비교합니다. expected/에는 쓰지 않습니다.

설치와 원천 준비가 끝난 뒤 이 비교만 다시 실행할 수 있습니다.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/source_data.py answers
```

기존 여섯 대상은 person_A.csv · summary_A.csv · person_B.csv · summary_B.csv · omop_counts.csv · omop_follow.csv입니다. 추가로 고정된 A′ 계산기를 별도 임시 폴더에서 실행해 person.csv·summary.csv·omop_facts.csv·manifest.json 네 파일도 비교하며 고정 파일에는 쓰지 않습니다. 상세 호출은 scripts/source_data.py의 compare_answers에 있습니다.

원천을 다시 받지 않고 해시만 확인하려면 다음을 실행합니다.

```sh
sh scripts/get_sources.sh --offline
```

## 구조

```text
A: FHIR → 배치 분리·원문 적재 → A staging ─┐
                                        ├→ OMOP CDM 5.4 → 일별 혈압·대상 계산 → 요약
B: CSV.gz ─────────────────→ B staging ─┤
A에서 파생한 CSV·혈압 문자열 → A′ staging ─┘
                            코드 매핑 ↗      지표 개념표 ↗
```

데이터 추출·변환·적재(ETL) 중 병원별 코드와 날짜 해석은 staging이 맡습니다. OMOP 표준 개념 번호(concept_id)를 붙인 뒤 계산 모델은 병원별 원천 코드를 읽지 않습니다.

- [파이프라인과 검증](docs/pipeline.md): 층별 역할, 한 행의 의미, 날짜·혈압 규칙
- [설계](docs/design/): OMOP 전환과 실행 환경
- [결정 기록](docs/decisions/): 받아들인 제약과 선택의 이유
- [전체 검사](scripts/check.sh): 기대 결과·테스트·고정 범위·단계별 검증

## 데이터와 라이선스

글: 만들기 · 의료 · Codex · 2026-10-27

- **Synthea:** [공식 프로젝트](https://github.com/synthetichealth/synthea)에서 생성한 합성 기록이며 실제 환자 자료가 아닙니다.
- **MIMIC-IV Clinical Database Demo 2.2:** [PhysioNet 공식 배포](https://physionet.org/content/mimic-iv-demo/2.2/), [DOI 10.13026/dp1f-ex47](https://doi.org/10.13026/dp1f-ex47). ODbL 1.0이며 원본 배포의 LICENSE.txt와 인용 안내를 따릅니다. 공개된 비식별 데모 100명 자료입니다.
- **OMOP DDL:** OHDSI CommonDataModel의 공식 DuckDB DDL, Apache-2.0. [vendor/omop](vendor/omop/README.md)에 버전과 출처가 있습니다.
- **이 저장소 코드:** [Apache-2.0](LICENSE). MIMIC 데모 유래 데이터와 수치의 ODbL 1.0은 코드 라이선스와 구분합니다. 인용 안내와 해당 파일 목록은 [NOTICE](NOTICE)에 있습니다.

원문 파일과 실행 중 생성한 입력·DB·캐시는 Git에서 제외합니다. `.local/`의 받은 원문과 화면 생성물, `data/batches/`·`data/a_prime/`의 생성 입력, `data/fhir.duckdb`가 여기에 해당합니다. Git에서 추적하는 검증 자료는 다음과 같습니다.

| 추적 경로 | 들어 있는 내용 |
|---|---|
| `expected/person_A.csv`·`summary_A.csv` | Synthea 합성 기록에서 따로 계산한 사람별·요약 기대 결과입니다. |
| `expected/person_B.csv`·`summary_B.csv` | 공개 MIMIC 데모의 사람별 식별값·임상 값과 요약 기대 결과입니다. |
| `expected/omop_counts.csv`·`omop_follow.csv` | A/B의 건수와 원래 행을 따라가는 예시입니다. MIMIC 데모의 사람 식별값과 혈압 값도 들어 있습니다. |
| `expected_a_prime/` | A에서 파생한 합성 사람별·임상 행, 요약과 원천 사실 해시를 담은 manifest입니다. |
| `answer_key/`·`answer_key_a_prime/` | 원천에서 기대 결과를 별도로 계산하는 코드와 설명입니다. `answer_key/make_expected_omop.py`에는 대조할 MIMIC 데모 사람 식별값도 있습니다. |
| `answer_key_lead/` | 리드가 따로 검수한 셀 비교·E01·화면 v1·WP-5 기대 결과예요. E01 두 행은 WP-5 JSON에서 옮겼고 나머지는 원본과 같은 바이트예요. 합성 식별값과 MIMIC 데모 식별값·임상 예시·요약도 포함해요. |

이 자료의 데이터 이용조건은 각 원천을 따릅니다. MIMIC 데모 유래 값이 들어 있는 문서와 시험 예시도 NOTICE의 목록에 포함했습니다. 원문 파일을 제외한다는 말은 검증용 개인별 행까지 제외한다는 뜻이 아닙니다.

## 범위와 한계

학습용 고혈압·혈압 조절 정의이며 CMS165 전체를 구현하지 않습니다. 제외 대상 전체를 적용하지 않았고, OHDSI 도구(ATLAS·Achilles·DQD)는 실행하지 않았습니다.

늦게 들어온 기록은 OMOP의 임상 날짜만으로 구분할 수 없습니다. 원래 기록일과 임상 날짜가 다른 입력은 staging 날짜 검사에서 멈추며, 수신시각을 임상시각 대신 쓰지 않습니다. 같은 날 성분별 최솟값, 입원·응급 기간 제외, 마지막 유효 혈압 선택을 적용합니다. 이 결과로 진료 판단을 내리는 기능은 없습니다.

Linux x64/Python 3.12 이외 환경, FHIR 서버, 운영 서비스와 삭제 전파는 지원 범위 밖입니다.
