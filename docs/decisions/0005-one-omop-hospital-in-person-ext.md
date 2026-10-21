# 0005 · 두 병원을 OMOP 하나에 · 병원과 측정 연도는 옆 표 `person_ext`

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: 사용자(M3 관문 2 · 3의 앞쪽 · 추천안)

## 맥락

OMOP 공식 표에는 「어느 병원에서 왔나」와 「사람마다 측정 연도」(병원 A 2025 · 병원 B `anchor_year` · 결정 0003)를 둘 칸이 없어요.

## 결정

두 병원을 한 OMOP에 담고, 공식 표는 그대로 둔 채 옆 표 `person_ext(person_id INTEGER, hospital VARCHAR, measurement_year INTEGER)` 하나에 병원과 측정 연도를 둬요(사람 하나 = 한 행 · `person`과 1:1). 측정 기간(1/1 ~ 12/31)과 6/30 · 기준 시점 날짜는 계산 층이 `measurement_year`에서 만들어요(결정 0010).

## 이유와 대안

- 대안: 병원마다 OMOP 하나씩(OHDSI 네트워크 방식 · 빌드 · 검사가 병원 수만큼 · M4 후보) · `care_site`에 병원(공식 칸이지만 뜻이 「주로 진료받는 곳」).
- All of Us는 병원(src_id)을 확장 표에 둬요 ◆ · OHDSI 포럼 「확장은 1:1 옆 표로」 ◆.

## 참고한 것

All of Us EHR 확장 표 `src_id`(지원 문서 · 검색 요약) · OHDSI 포럼 「Extending the CDM with additional source columns」 · CDM 5.4 `observation_period` 관례(기록이 있는 기간이라 측정 기간으로 쓰지 않음).

## 결과

(반복이 끝나면 적어요.)
