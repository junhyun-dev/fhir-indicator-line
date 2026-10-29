질문: 손 계산 표를 한 셀도 바꾸지 않고 CSV로 옮기면, 파일마다 선언된 행 수와 같나요?
주제: OMOP CDM 임상 지표 파이프라인 · E01 수기 입력과 기대 결과
날짜와 누가: 2026-10-27 · 만들기 · 의료 · E01 기대 결과 · Codex(직접)
쓰인 곳: E01 구현 전 수기 표 전사 검토와 기대 결과 고정

# E01 손 계산 표를 CSV로 옮겼어요

글: 만들기 · 의료 · E01 기대 결과 · Codex · 2026-10-27

파일 아홉 개의 행 수가 모두 선언과 같아요. 입력은 80행, 기대 결과는 45행이에요. 행 수는 CSV 헤더를 빼고 셌어요. 수기 표에 적힌 값만 옮겼고, 지표를 새로 계산하지 않았어요.

[요청서](../../thinking/exchange/REQ-medical-e01-expected-1027/REQUEST.md)의 범위에 따라 이 폴더에만 결과를 뒀어요. 수기 표의 최초 작성자는 의료 Codex이고, 10/22에 다른 세션이 수기 검수를 했다는 기록은 [준비 점검 ①](../../thinking/exchange/REQ-medical-e01-readiness-1027/REPLY.md)에 있어요. 이번 작업은 구현 세션과 분리된 CSV 전사예요. 리드의 전사 검수 수용은 아직 받지 않았어요.

## 파일별 행 수와 옮긴 위치

아래 기획 줄 번호는 [기획 5절](../../thinking/research/a-prime-and-sql-plan-1021.md)을 가리켜요. 설계 줄 번호는 [설계 04](/home/junhyun/dev/projects/fhir-indicator-line/docs/design/04-sql-equivalence-and-dimensional-grain.md)를 가리켜요.

| 파일 | 선언한 행 수 | CSV에서 센 행 수 | 옮긴 줄 | 대조 결과 |
|---|---:|---:|---|---|
| [fixtures/sources.csv](fixtures/sources.csv) | 3 | 3 | 기획 135줄, 설계 04 50줄 | 같아요 |
| [fixtures/persons.csv](fixtures/persons.csv) | 8 | 8 | 기획 139~143줄 | 같아요 |
| [fixtures/conditions.csv](fixtures/conditions.csv) | 9 | 9 | 기획 139~143·145줄 | 같아요 |
| [fixtures/visits.csv](fixtures/visits.csv) | 14 | 14 | 기획 139~145줄 | 같아요 |
| [fixtures/measurements.csv](fixtures/measurements.csv) | 46 | 46 | 기획 145·149~163줄 | 같아요 |
| [expected_manual/daily.csv](expected_manual/daily.csv) | 19 | 19 | 기획 171~182줄 | 같아요 |
| [expected_manual/person.csv](expected_manual/person.csv) | 12 | 12 | 기획 145·186·190~196줄 | 같아요 |
| [expected_manual/summary_by_date.csv](expected_manual/summary_by_date.csv) | 8 | 8 | 기획 206~211줄 | 같아요 |
| [expected_manual/summary_by_label.csv](expected_manual/summary_by_label.csv) | 6 | 6 | 기획 206~209·213줄 | 같아요 |

입력 80행에 제품의 기존 개념 목록 8행을 더하면 기획의 논리 입력 88행이에요. 개념 목록과 기준 라벨 파일은 이 폴더에 복사하지 않았어요.

## A*를 펼친 위치

- 기획 139~141줄의 사람과 진단·외래 방문은 각각 A와 A_PRIME으로 펼쳤어요. OMOP 사람 번호는 표에 적힌 101~103과 201~203을 각각 옮겼어요. 145줄의 입원 두 기간도 두 출처에 각각 남겼어요.
- 측정 표 149~158줄의 A* panel 10개는 출처별로 펼치고, 각 panel의 수축기·이완기를 성분 두 행으로 옮겼어요. B의 159~161줄은 각각 한 출처로 옮겼어요.
- daily 표 171~177줄은 14행으로, person 표 190~194줄은 10행으로, 날짜 요약 206~207줄은 4행으로 펼쳤어요. B 행을 더한 결과가 위 파일별 행 수예요.
- 라벨 요약은 213줄의 문장을 따랐어요. A와 A_PRIME은 2025년 날짜 요약의 두 값을 각각 옮겼어요. B의 sep30은 1/1·1.0000, dec31은 0/1·0.0000이에요. 날짜 요약에서 B의 2032년 두 행을 더하거나 비율을 다시 계산하지 않았어요.

## 열과 자료형

CSV는 UTF-8이고 줄바꿈은 LF예요. 첫 행이 열 이름이며 NULL은 빈 셀이에요. 날짜는 `YYYY-MM-DD`, 정수는 INTEGER, 혈압과 rate는 DOUBLE로 읽는 계약이에요. 출처·원천 사람 키·라벨·사유·원천 행 키는 VARCHAR예요. CSV 자체에는 DB 자료형 정보가 없어요.

fixture의 열 이름과 순서는 설계 04 83~87줄을 따랐어요. daily의 여섯 열은 23·37줄, person의 아홉 열은 30·38·54줄에 적힌 이름을 사용했어요. 요약의 `numerator`는 분자, `denominator`는 분모예요. 설계 55~56줄은 이 두 항목을 한국어로 적고 있어 영어 열 이름과 순서는 여기 CSV 헤더에 명시했어요. 날짜 요약의 키는 `hospital,as_of`, 라벨 요약의 키는 `hospital,as_of_label`이에요.

| 파일 | NULL을 허용하는 열 | 데이터 행의 키 |
|---|---|---|
| sources | derived_from(A·B만) | hospital |
| persons | 없어요 | hospital,person_id / omop_person_id도 유일해요 |
| conditions | condition_end_date | hospital,source_row_key |
| visits | 없어요 | hospital,source_row_key |
| measurements | value_as_number | hospital,source_row_key |
| daily | systolic_min,diastolic_min | hospital,person_id,as_of,bp_date |
| person | last_bp_date,systolic,diastolic | hospital,person_id,as_of |
| summary_by_date | rate | hospital,as_of |
| summary_by_label | rate | hospital,as_of_label |

원천 행 키는 설계 89줄에 따라 원래 식별 항목을 `|`로 이어 적었어요. measurements는 `출처|사람|panel 키|성분 개념 번호`예요(예: `A|p1|m1|3004249`). 진단과 방문에는 표가 별도 사건 번호를 주지 않으므로 진단은 `출처|사람|condition|개념 번호|시작일`, 방문은 `출처|사람|visit|개념 번호|시작일|종료일`로 적었어요. 이 표의 식별 항목에는 `|`가 없으며 원래 식별 항목을 다시 나눠 읽을 수 있어요. A와 A_PRIME을 같은 키로 합치지 않았어요.

## NULL과 원문을 대조했어요

- measurements의 값이 빈 셀인 성분은 6행이에요. A와 A_PRIME에 각각 m6의 이완기 1행, m8의 두 성분 2행이 있어요. NULL을 0으로 바꾸지 않았어요.
- 109.51과 76.761, 0.5000·0.3333·1.0000·0.0000을 표의 문자열 그대로 남겼어요. 사유도 표의 `조절됨`, `혈압 없음`, `마지막 날에 한쪽 값만`, `수축기 140 이상`을 그대로 옮겼어요.
- B의 2032-09-30과 2032-12-31은 날짜 요약에 각각 한 행이며, 분자 0·분모 0·rate 빈 셀이에요. person에는 B/p2 행을 만들지 않았어요.
- 각 CSV의 행 수·열 수·날짜·숫자 형식·키 유일성·사람 참조와 원문 전사 값을 확인했어요. 기대 결과를 입력에서 다시 계산하는 코드는 만들거나 실행하지 않았어요. 제품에서 읽은 것은 지정된 설계 04 문서뿐이고 제품 코드·DB·SQL은 열거나 실행하지 않았어요.

## 다름과 모호한 곳

수기 표와 설계의 값·자료형·NULL 의미가 다른 곳은 발견하지 못했어요. 위에 명시한 영어 요약 열 이름, 열 순서와 원천 행 키의 문자열 표기는 전사를 위해 적은 표현이에요. 뜻을 고르지 못해 멈춘 곳은 없어요. 이 표현까지 포함한 전사 검수는 리드가 확인할 부분이에요.

## 해시와 확인 방법

[SHA256SUMS](SHA256SUMS)는 CSV 아홉 개만 대상으로 해요. 경로는 이 폴더를 기준으로 한 상대 파일 이름이며 절대 경로는 없어요. 이 폴더에서 `sha256sum -c SHA256SUMS`로 확인할 수 있어요. README와 알림은 CSV 해시 목록에 포함하지 않았어요.

읽은 원문 전체의 SHA256은 아래와 같아요. CSV 해시와 구분해서 남겨요.

- 요청서: `e0b4548ae2c82e1d07a7fd0d4f7efdbdda2cf0437db764c9fbbb9b46c0555276`
- 기획 5절을 포함한 파일: `993cd886428c6e7a7b2a6692b704c44e2176f02fe15f5b824ca4010f2ff9787b`
- 설계 04: `8e1072362838ff8e57d041f94b5abd09ecb76f09f4240b327cdd065d78dfb947`
- 준비 점검: `a7b8871b4c06febdd8be02801a0990632df5c94ae952422303aab94b8f8c2977`

돌아보기: 수기 결과를 다시 계산하지 않고 표의 행을 그대로 펼치니 NULL과 0명인 기준일을 함께 보존하며 대조할 수 있었어요.

## 리드 검수(전사 · 10/27)

검수: 만들기 · 의료(Claude 리드) · 2026-10-27 · **받아들임.**

- **기대 결과 네 파일:** 기획 5절의 손 계산 표(Q1 daily · Q2 fact · 실제 기준일 요약 · 라벨 요약)를 표에서 직접 읽어, A*를 A · A_PRIME 두 행으로 펼친 뒤 CSV와 칸까지 견줬어요. `daily.csv` 19행 · `person.csv` 12행(`as_of_label` 칸은 기준일과 짝이 맞음) · `summary_by_date.csv` 8행 · `summary_by_label.csv` 6행 모두 같았어요. 병원 B 2032년 두 기준일의 0 · 0 · 빈 비율도 그대로예요.
- **입력 다섯 파일:** 행 수(3 · 8 · 9 · 14 · 46 = 80)와 값이 빈 측정 6행만 확인했어요. 칸 단위 대조는 하지 않았어요 — 입력을 잘못 옮겼다면 E01의 두 SQL 결과가 위 기대 결과와 어긋나서 시험에서 드러나요.
- **해시:** `sha256sum -c SHA256SUMS` 통과(이 검수 절을 더하기 전 · README는 해시 목록에 없음).
- E01 실험 만들기(`REQ-medical-e01-build-1027`)는 이 줄을 보고 시작해요.

## 고친 내역 — WP-5(10/29)

고침: 만들기 · OMOP 임상 지표(Claude 리드) · 2026-10-29

- **`person.csv` 두 행만 바뀌었어요:** `A,p1,dec31`과 `A_PRIME,p1,dec31`. 사용자 10/29 결정(의료 임시 노트 「정한 것」 9 ③)으로 수축기 · 이완기가 둘 다 있는 날만 혈압 측정일로 쳐요. 12/20은 수축기만 있어 빠지고, 12/1의 124/92가 남아 「이완기 90 이상」이에요(분자 0 그대로라 요약 두 파일은 그대로).
- **값은 손으로 쓰지 않았어요:** 검수된 [WP-5 기대 결과](../wp5-bp-days-both-values/README.md)의 `expected.json`에서 스크립트로 옮겼고(숫자는 같은 파일의 다른 행처럼 정수), `SHA256SUMS`를 다시 만들었어요. 옛 값은 Git 기록에 있어요(`0df176546`).
