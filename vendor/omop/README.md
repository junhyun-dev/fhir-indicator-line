# OMOP CDM 5.4 공식 DDL(DuckDB)

`OMOPCDM_duckdb_5.4_ddl.sql`은 OHDSI CommonDataModel 저장소 `inst/ddl/5.4/duckdb/`의 파일을 고치지 않고 그대로 복사한 거예요(커밋 `f6d2738a40af64a8c0dddf23d56680ac29edb52f` · 라이선스 Apache-2.0 — 저장소 DESCRIPTION). 검사기(`fhir_line/omop.py`)가 이 DDL을 빈 메모리 DB에 그대로 만들어 우리 OMOP 표의 열 이름 · 순서 · 형식 · 필수 칸과 비교해요(결정 0004). 손으로 고치지 않아요.
