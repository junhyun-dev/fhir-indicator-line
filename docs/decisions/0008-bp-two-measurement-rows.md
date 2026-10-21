# 0008 · 혈압 한 번 = measurement 두 행

- 날짜 · 상태: 2026-10-21 · 받아들임 · 정함: Claude

## 결정

혈압 한 번은 수축기(3004249) · 이완기(3012888) 두 행이에요. 묶음 행(85354-9)은 만들지 않아요. 날짜는 두 행 모두. 원래 글자는 `measurement_source_value`(A `8480-6` · `8462-4` · B `omr_systolic` · `omr_diastolic` · `220179` · `220180`)와 `value_source_value`(B `omr`의 「140/60」 · ICU `value`), 단위 글자는 `unit_source_value`에.

## 이유와 대안

- dbt-synthea와 OHDSI 포럼(55284-4 질문)이 두 행.
- 대안: HL7 FHIR to OMOP IG 1.0.0의 예시 맵(묶음 행 + 두 성분 = 세 행) — 「experimental」이고 성분 행에 날짜가 없어요.

## 참고한 것

HL7 FHIR to OMOP IG 1.0.0 `ConceptMap-BloodPressureCodes` · `StructureMap-BloodPressureVitalSignsMap` · dbt-synthea `int__measurement_observations`.

## 결과

(반복이 끝나면 적어요.)
