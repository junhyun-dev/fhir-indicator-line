# 0007 · OMOP id 만드는 법

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: Claude(설계 글 3절 · 관문 밖)

## 맥락

OMOP id는 정수(공식 DDL `integer`)이고, 병원 A의 사람 id는 UUID예요. dbt-synthea는 `row_number()`로 번호를 매기는데, 사람이 하나 늘면 뒤 번호가 밀려요.

## 결정

- `person_id` = `병원 + ':' + 원래 id`의 md5에서 만든 양의 32비트 정수(DuckDB `md5_number(...) % 2147483647`처럼 버전에 따라 바뀌지 않는 함수). 겹침은 검사기(⑥ 모양)와 dbt `unique` 테스트로 봐요. 원래 id는 `person_source_value`.
- 사건 표 id(`visit_occurrence_id` · `condition_occurrence_id` · `measurement_id` · `observation_period_id`)는 `row_number()`를 정해진 순서(병원, 원래 행 id)로 — 같은 입력이면 같은 번호, 행을 가리킬 때는 `*_source_value`를 써요.

## 이유와 대안

- 사건 표까지 md5 32비트로 하면 measurement 약 2만 행에서 겹칠 확률이 약 9%(생일 문제) — 그래서 사람만 해시.
- 대안: BIGINT id(공식 DDL과 형식이 달라짐).

## 참고한 것

CDM 5.4 `person_id` 관례(「정수가 아니면 새 번호」) · dbt-synthea `int__person.sql`(`row_number()`).

## 결과

◆ 사람 136명 · 번호 겹침 0 · 범위 23,382,658 ~ 2,119,464,705 · 「사람을 더해 다시 빌드해도 기존 번호 그대로」 테스트 통과 · 사건 번호는 `omop_event_rows`에서 한 번(`c8ea151`). MIMIC 공식 OMOP 0.9도 해시 id(64비트)를 씀 ●.

카드로 되돌림: 없음.
