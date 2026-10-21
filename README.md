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

## A′ 임상 보존 검사

`data/a_prime/`의 CSV 넷과 manifest는 A 원본에서 생성하며 Git에 넣지 않습니다. 사람36명·진단1,455행·방문2,144행·BP555묶음/1,110성분을 보존하고 소수10성분을 반올림하지 않습니다. `109.51/76.761`은 프로젝트 소수 확장이며 보험청구 형식 전체 준수를 뜻하지 않습니다.

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

- **Synthea:** [공식 프로젝트](https://github.com/synthetichealth/synthea)에서 생성한 합성 기록이며 실제 환자 자료가 아닙니다.
- **MIMIC-IV Clinical Database Demo 2.2:** [PhysioNet 공식 배포](https://physionet.org/content/mimic-iv-demo/2.2/), [DOI 10.13026/dp1f-ex47](https://doi.org/10.13026/dp1f-ex47). ODbL 1.0이며 원본 배포의 LICENSE.txt와 인용 안내를 따릅니다. 공개된 비식별 데모 100명 자료입니다.
- **OMOP DDL:** OHDSI CommonDataModel의 공식 DuckDB DDL, Apache-2.0. [vendor/omop](vendor/omop/README.md)에 버전과 출처가 있습니다.
- **이 저장소 코드:** [Apache-2.0](LICENSE). 원천 데이터는 저장소에 넣지 않으며 위 각 원천의 라이선스를 따릅니다.

원천과 생성 데이터·DB·캐시를 Git에 넣지 않습니다.

## 범위와 한계

학습용 고혈압·혈압 조절 정의이며 CMS165 전체를 구현하지 않습니다. 제외 대상 전체를 적용하지 않았고, OHDSI 도구(ATLAS·Achilles·DQD)는 실행하지 않았습니다.

늦게 들어온 기록은 OMOP의 임상 날짜만으로 구분할 수 없습니다. 원래 기록일과 임상 날짜가 다른 입력은 staging 날짜 검사에서 멈추며, 수신시각을 임상시각 대신 쓰지 않습니다. 같은 날 성분별 최솟값, 입원·응급 기간 제외, 마지막 유효 혈압 선택을 적용합니다. 이 결과로 진료 판단을 내리는 기능은 없습니다.

Linux x64/Python 3.12 이외 환경, FHIR 서버, 운영 서비스와 삭제 전파는 지원 범위 밖입니다.
