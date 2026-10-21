# 기대 결과를 따로 세는 스크립트(answer key)

`expected/`의 파일 여섯은 파이프라인 코드와 **따로** 원천을 읽어 센 값이에요. 이 폴더의 스크립트 셋이 그것을 만들어요 — 파이썬 표준 라이브러리만 쓰고, dbt 모델 · DB를 읽지 않아요.

| 스크립트 | 읽는 원천 | 만드는 파일 |
|---|---|---|
| `make_expected.py` | 병원 A 합성 FHIR 묶음 38개 | `person_A.csv` · `summary_A.csv` |
| `make_expected_b.py` | 병원 B MIMIC-IV 데모 2.2 CSV | `person_B.csv` · `summary_B.csv` |
| `make_expected_omop.py` | 위 둘 | `omop_counts.csv`(병원 × OMOP 표 행 수) · `omop_follow.csv`(끝까지 따라갈 혈압 4행) |

다시 세서 `expected/`와 바이트까지 같은지 보는 법은 저장소 README의 「기대 결과를 직접 다시 세기」예요. 지표 정의는 `docs/decisions/0001` · `0003`, OMOP으로 옮기는 규칙은 `docs/design/01-m3-omop.md` · `docs/decisions/0004` ~ `0011`이에요.

이 폴더와 `expected/`는 구현 쪽(코딩 에이전트)이 고치지 않아요(`AGENTS.md`). 스크립트 머리 주석의 「그림 24」 같은 이름은 이 프로젝트를 설계한 작업 노트의 그림 번호예요.
