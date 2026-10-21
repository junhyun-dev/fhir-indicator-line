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

(반복이 끝나면 적어요.)
