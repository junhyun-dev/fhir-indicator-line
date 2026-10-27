# 05 · DQD를 참고한 dbt 품질 검사

글: 만들기 · 의료 · Codex · 2026-10-27

D1~D3 · 결정 0004, 0008, 0009, 0011을 유지하면서 OMOP 8개 테이블에 품질 검사 9개와 진단 미매핑 경고 1개를 더해요. 모델 SQL과 seed, 지표 정의, 결과 테이블의 값과 열은 바꾸지 않아요.

## 어떤 검사를 골랐나

| DQD 검사 이름 | 갈래 | 우리 대상 | 실패 조건과 기준값 | 고른 까닭 |
|---|---|---|---|---|
| `fkDomain` | 모양이 맞나(Conformance) | measurement.unit_concept_id → concept | 알려진 단위 개념이 없거나 Unit 도메인이 아닌 비율 > 0% | 개념 번호가 있어도 다른 도메인의 번호일 수 있어요. |
| `isStandardValidConcept` | 모양이 맞나 | source_to_concept_map.target_concept_id → concept | S가 아니거나 invalid_reason이 있는 비율 > 0% | 기존 관계 검사는 개념이 존재하는지만 확인해요. |
| `measureValueCompleteness` | 빠진 게 없나(Completeness) | cdm_source.cdm_source_name | NULL 비율 > 0% | 기존 not_null과 겹치지만, 출처 메타데이터도 같은 비율·기준값 형식으로 확인해요. |
| `standardConceptRecordCompleteness` | 빠진 게 없나 | measurement.unit_concept_id | 개념 0 또는 원래 단위가 있는데 NULL인 비율 > 0% | 단위 미매핑을 보이게 해요. 결정 0008·0009의 혈압 단위에 맞춘 프로젝트 기준값이에요. DQD 기본값은 5%, dbt-synthea 예시는 7%예요. |
| `standardConceptRecordCompleteness` | 빠진 게 없나 | condition_occurrence.condition_concept_id | 개념 0의 비율 > 5% | 이미 옮긴 진단의 개념 완전성이에요. 옮기기 전에 빠진 진단은 아래 경고로 따로 봐요. |
| `plausibleValueLow` | 말이 되나(Plausibility) | person.year_of_birth | 1850 미만인 비율 > 1% | DQD의 고정 하한을 가져왔어요. 날짜가 이동된 MIMIC에 현재 연도 상한을 새로 적용하지 않아요. |
| `plausibleStartBeforeEnd` | 말이 되나 | observation_period 시작일·종료일 | 시작일이 종료일보다 늦은 비율 > 0% | 결정 0011의 관찰 기간이 역전되면 안 돼요. 같은 날은 허용해요. |
| `plausibleStartBeforeEnd` | 말이 되나 | visit_occurrence 시작일·종료일 | 시작일이 종료일보다 늦은 비율 > 0% | 방문이 연결돼 있어도 날짜 순서는 별도예요. |
| `plausibleUnitConceptIds` | 말이 되나 | measurement의 혈압 두 개념 | 각 혈압 개념에서 알려진 단위가 8876이 아닌 비율 > 5% | 두 개념을 합쳐서 한쪽의 오류 비율을 희석하지 않아요. 허용 단위는 DQD CDM5.4 개념 설정과 같아요. |

기준값은 `models/omop/schema.yml`의 `arguments.threshold`에 있어요. 검사에는 `dqd_quality` 태그를 달았고, 직접 쓴 generic test는 `macros/test_dqd.sql`에 있어요. 새 패키지는 필요하지 않아요.

```sh
.venv/bin/python scripts/dbt.py test --select tag:dqd_quality
```

전체 완료 검증에서는 기존 `sh scripts/check.sh`가 모든 품질 검사를 함께 실행해요. 선택 실행은 전체 검증을 대신하지 않아요.

## 분모와 판정

`위반 수 × 100 > 기준값 × 분모`일 때만 실패해요. 기준값과 정확히 같으면 통과하며, 표시할 소수 자릿수와 관계없이 계산한 비율로 판정해요. 단위의 개념 0과 NULL은 완전성 검사에서 다루고, 단위가 적절한지 보는 검사는 DQD처럼 개념 0을 위반으로 다시 세지 않아요.

완전성 검사의 분모는 개념이 있거나 원래 단위가 있는 행이에요. 원래 단위도 없고 개념도 없는 행은 이 검사만으로 판정하지 않아요. 날짜 순서는 두 날짜가 있는 행을 보고, 출생 연도 하한은 연도가 있는 행을 봐요. 필수 필드의 NULL은 기존 not_null 검사도 계속 확인해요. 도메인 검사는 0이 아닌 알려진 번호를 보고, DQD의 도메인 검사에 더해 연결되지 않는 번호도 검출해요. 매핑의 표준·유효성 검사는 개념 0을 제외하며, 개념이 아예 없는 경우는 기존 relationships가 맡아요.

실패 SQL은 위반 수·분모·비율만 반환해요. 단위 적절성은 혈압 개념 번호도 포함해요. 환자 식별자는 실패 결과에 넣지 않아요. 실패하지 않은 검사에서도 전체 원천이 보존됐다고 결론 내릴 수 없어요.

## 옮기지 못한 진단은 경고로 남겨요

`omop_load_counts`의 병원별 condition_occurrence.not_carried가 YAML 기준값 0을 넘으면 `severity: warn`, `warn_if: '> 0'`으로 알려요. 이는 건수 기준이며 DQD 내장 검사가 아닌 프로젝트 검사예요. 해당 경고 때문에 기본 dbt 실행을 실패로 바꾸지 않아요. 호출자가 별도로 `--warn-error`를 주면 경고를 실패로 올릴 수 있어요.

옮겨진 진단의 개념 0 비율이 0%여도 원천 진단의 매핑이 완전하다는 뜻은 아니에요. 개념을 찾지 못한 진단은 결정 0009에 따라 condition_occurrence에 없을 수 있어요. 실제 건수와 경고를 함께 읽어야 해요.

## 반례와 기존 시험

`tests/test_dbt_quality.py`는 메모리 안 DuckDB에 작은 수제 테이블을 만들고 실제 generic test SQL과 YAML 설정을 읽어요. 정상 입력을 확인한 뒤 검사마다 잘못된 값 하나를 넣어 검출하는지 봐요. 1%와 같은 경계, 빈 분모, 원래 단위의 존재 여부, NULL인 표준 개념 표시, 개념별 분모도 별도로 확인해요.

기존 A·OMOP·A′ 모델 시험에는 단위 kPa가 개념 0으로 남는지 확인하는 입력이 있어요. 그 시험들의 dbt build에서 새 단위 완전성 검사 하나만 제외해 원래 보존 동작을 계속 확인해요. 나머지 품질 검사와 기존 단언은 유지해요. 새 반례 시험은 이 검사도 실행하고, 실제 자료를 검증하는 `scripts/check.sh`의 dbt build에서는 제외하는 검사가 없어요.

## 참고한 원문과 한계

- DQD는 [고정 커밋 b9d2a9b4](https://github.com/OHDSI/DataQualityDashboard/tree/b9d2a9b4a4736f7ea81415d974c72119b6f0bd11)의 CDM5.4 Field_Level·Concept_Level CSV와 해당 검사 SQL을 읽었어요. 로컬 사본의 현재 HEAD와 구분해서 그 커밋의 원문을 사용했어요.
- dbt-synthea [measurement.yml:168](https://github.com/OHDSI/dbt-synthea/blob/33fdbfa9b354f00def5ee6e45525cb2da80e0ddf/models/omop/_models/measurement.yml#L168)과 `tests/generic/concept_record_completeness.sql`의 YAML 기준값·직접 쓴 검사 구성을 참고했어요.
- DQD 실행기, R 의존성, 화면, NA 판정 전체를 이식한 것은 아니에요. 분모가 비면 이 SQL은 위반 행을 만들지 않으며, 전체 행 수는 기존 사다리가 별도로 확인해요.
- 방문 날짜가 관찰 기간 안인지 보는 검사나 혈압 수치의 새 정상 범위는 이번에 정하지 않았어요. 혈압 두 개념의 DQD 설정에는 허용 단위가 있지만 수치 상·하한이 없어서 임의의 의료 범위를 만들지 않았어요.
