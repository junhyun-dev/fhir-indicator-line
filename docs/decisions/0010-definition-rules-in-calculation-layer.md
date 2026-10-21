# 0010 · 지표 정의의 날짜 · 개념 규칙은 계산 층 한 곳에

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: Claude(0004의 갈아타기 요청 07에서)

## 맥락

지금 「1/1 ~ 12/31 · 6/30」이 병원 A · B staging에 두 번 있어요(`stg_a_person_period` · `stg_b_person_period`). 병원이 늘면 같은 정의를 병원마다 다시 적게 돼요. 단위 mm[Hg] 거르기(D3)는 매핑 join이 하고 있어요.

## 결정

병원 staging은 병원이 아는 사실(원래 코드 · 날짜 · 측정 연도 · 태어난 해)만 내놓고, 측정 기간 · 6/30 · 기준 시점 날짜 · 18 ~ 85세 · 개념 묶음 · mm[Hg] 거르기는 계산 층(L4 ~ L6)과 `seeds/indicator_concepts.csv`에 한 번만 둬요. 나이 = `measurement_year − year_of_birth`(A: 태어난 해 · B: `anchor_year − anchor_age` → 측정 연도 말 나이가 `anchor_age`).

## 참고한 것

결정 0001 · 0003 · 회사 책 4장 07 「바뀔 결정이 한곳에 감춰져 있나」.

## 결과

◆ 1/1 · 6/30 · 12/31과 나이 계산이 있는 파일은 `int_person_period.sql` 하나(`test_M3_boundary`가 봄) · 병원 staging은 사람 하나 = 한 행의 사실만(`3e99c30`).

카드로 되돌림: 없음.
