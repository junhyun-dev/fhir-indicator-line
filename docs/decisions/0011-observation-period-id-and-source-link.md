# 0011 · 0007 보충 — `observation_period_id`는 `person_id` · 사건 행의 원래 id는 옆 표 `omop_source_link`

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: Claude(요청 06 사전 검토 R2 · R3에서 · 관문 밖)
- 0007을 대체하지 않고 보충해요(0007의 「사건 표 id」에서 `observation_period_id`만 예외).

## 맥락

요청 06 사전 검토(Codex)가 둘을 짚었어요. R2: 요청서는 `observation_period_id = person_id`, 0007은 `row_number()` — 서로 달라요. R3: 설계 글의 완료 조건 4 「원래 id가 `*_source_value`에 남는다」는 사건 표에서는 지켜지지 않아요 — `visit_source_value`는 방문 종류, `condition_source_value`는 진단 코드, `measurement_source_value`는 성분 코드라서, 같은 코드가 되풀이되면 어느 원천 행인지 가릴 수 없어요.

## 결정

1. `observation_period_id = person_id`(한 사람에 기간 하나).
2. 사건 행(방문 · 진단 · 혈압 값)의 원래 행 키는 옆 표 `omop_source_link(omop_table VARCHAR, omop_id INTEGER, hospital VARCHAR, source_row_key VARCHAR)`에 남겨요. 사건 행 하나 = 한 줄. 키는 A 자원 id(혈압은 + 성분 코드) · B 원천 복합 키(진단 `subject_id:hadm_id:seq_num:icd_version:icd_code` · 입원 `hadm_id` · `omr` 날 · ICU 행 키 + 성분). 공식 표의 칸에 id를 섞어 넣거나 공식 표에 열을 더하지 않아요.
3. 그래서 `omop` 층 안에서 모델끼리 읽어도 돼요(사건 행에 번호를 한 번 매기고, 공식 표 · 옆 표 · 기간 · 건수가 그 결과를 같이 읽음 · dbt-synthea의 intermediate → omop과 같은 짜임). 층 검사(`fhir_line/layers.py`)를 그렇게 바꿔요. `omop`이 `common`을 읽는 것은 여전히 안 돼요.

## 이유와 대안

- 대안: 사건 id를 원래 키의 md5 정수로 — 약 2만 행에서 32비트 겹침 확률 약 9%(0007) · 원래 id 보존을 staging까지로만 줄이기 — 완료 조건 4를 약하게 고쳐야 함.
- All of Us는 OMOP 행과 원천을 잇는 `_mapping_` 표 · 확장 표를 공식 표 옆에 둬요 ◆ · 카드 FC-03 「원본 보존」.

## 참고한 것

요청 06 사전 검토 `.local/FHIR-LINE-06/summaries/FHIR-LINE-06.review.md`(R2 · R3) · 0005 · 0007 · FC-03.

## 결과

◆ `omop_source_link` 22,901행 = 방문 3,253 + 진단 110 + 혈압 값 19,538 · 사건 행마다 꼭 한 줄 · 키 겹침 0(사다리 ⑥ 원래 행) · `observation_period_id = person_id` 136행(`c8ea151`).

카드로 되돌림: FC-03(바꿈).
