# 0004 · OMOP 표가 공통 테이블을 대신한다

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: 사용자(M3 관문 1 · 추천안) · 초안 Claude
- 설계 글: [`docs/design/01-m3-omop.md`](../design/01-m3-omop.md) 2 · 3절

## 맥락

M2까지 병원 사이의 공통 모양은 우리가 지은 공통 테이블 넷(`models/common/`)이었어요. 공고의 일은 「병원 원천을 OMOP CDM으로 변환」이고, OMOP을 옆에 하나 더 두면 같은 뜻이 두 벌이 돼요.

## 결정

병원 staging → **OMOP CDM 5.4 표**(`person` · `observation_period` · `visit_occurrence` · `condition_occurrence` · `measurement` · `cdm_source`) → 계산 층(L4 ~ L6) → reports. 요청을 둘로 나눠요: 06 「더하기」(OMOP을 공통 테이블 옆에 · 계산 층 0줄) → 07 「갈아타기」(계산 층이 OMOP을 읽고 `common` · `code_map`을 지움 · 숫자 그대로 · 끝나면 `FROZEN_BASE`를 07 커밋으로).

## 이유와 대안

- 대안: OMOP은 내보내기만 하고 계산은 공통 테이블 그대로(계산 층 0줄 · 같은 뜻이 두 벌).
- dbt-synthea도 OMOP이 마지막 층이고 분석은 그 위에서 해요.

## 참고한 것

카드 FC-03 · OHDSI CommonDataModel 5.4 DDL(`vendor/omop/` · `f6d2738`) · dbt-synthea `33fdbfa` · 결정 0002.

## 결과

◆ 요청 06(`c8ea151`)으로 OMOP을 공통 테이블 옆에 만들고(계산 층 0줄), 요청 07(`3e99c30`)로 계산 층이 OMOP · `indicator_concepts`만 읽게 바꾼 뒤 `models/common/` · `code_map.csv`를 지움. 두 병원 숫자 그대로(A 3/5 → 4/6 · B 4/9 → 3/9 · 사다리 ④ ●) · 갈아타기 전후 `int_bp_daily` 413행 · `fct_bp_person` 29행 두 방향 EXCEPT ALL 0 · 0 ● · 계산 층 바뀐 줄: `int_person_period` +18 · `int_bp_daily` +21/−16 · `fct_bp_person` +15/−13 · `dim_as_of` +2/−2 · `bp_summary` 0. 바뀌면 안 되는 층 기준을 `3e99c30`으로 옮기고 지표 개념 seed도 넣음(`7326906`).

카드로 되돌림: ME-02(07 확인을 바꿈).
