# 결정 기록

결정 하나 = 파일 하나(`NNNN-짧은-이름.md`). 칸은 제목 · 날짜 · 상태 / 맥락 / 결정 / 이유와 대안 / 참고한 것 / 결과예요(Personal `builds/standard-process.md` v2 4절 ⑨). 받아들인 기록은 고치지 않고, 틀린 가정이 드러나면 새 기록을 쓰고 옛 기록의 상태만 「대체됨 → 새 번호」로 바꿔요. 커밋 메시지에 결정 번호를 적어요(예: `결정 0004`). 현재 쓰는 쪽: 의료 Codex. A′ 별도 사전/최종 검수: 방법 감독.

0001 ~ 0003은 M1 · M2에서 이미 정한 것 가운데 지금도 살아 있는 것만 10/21에 따라 적은 거예요. M3(0004 ~)부터 이 방식으로 처음 써요.

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](0001-indicator-definition-d1-d7.md) | 지표 정의 D1 ~ D7(CMS165 학습용 판) | 받아들임 |
| [0002](0002-new-hospital-own-staging-and-map-rows.md) | 새 병원은 그 병원 전용 단계와 매핑 줄로만 붙인다 | 받아들임 |
| [0003](0003-hospital-b-three-definitions.md) | 병원 B에서 「같은 뜻」 셋(측정 기간 · 고혈압 진단 시작일 · 외래 방문) | 받아들임 |
| [0004](0004-omop-replaces-common-tables.md) | OMOP 표가 공통 테이블을 대신한다 | 받아들임(사용자 · 관문 1) |
| [0005](0005-one-omop-hospital-in-person-ext.md) | 두 병원을 OMOP 하나에 · 병원과 측정 연도는 `person_ext` | 받아들임(사용자 · 관문 2 · 3) |
| [0006](0006-record-day-not-carried.md) | 기록이 들어온 날은 옮기지 않는다 | 받아들임(사용자 · 관문 3) |
| [0007](0007-omop-ids.md) | OMOP id 만드는 법 | 받아들임(Claude) |
| [0008](0008-bp-two-measurement-rows.md) | 혈압 한 번 = measurement 두 행 | 받아들임(Claude) |
| [0009](0009-concepts-small-list-no-account.md) | 표준 번호는 쓰는 것만 작은 목록으로 | 받아들임(Claude) |
| [0010](0010-definition-rules-in-calculation-layer.md) | 정의의 날짜 · 개념 규칙은 계산 층 한 곳에 | 받아들임(Claude) |
| [0011](0011-observation-period-id-and-source-link.md) | 0007 보충 — `observation_period_id` = `person_id` · 사건 행 원래 id는 `omop_source_link` | 받아들임(Claude · 사전 검토 R2 · R3) |
| [0012](0012-sources-by-script-and-hashes.md) | 데이터는 받는 스크립트 + 해시 목록으로 · 기대 결과 계산 스크립트는 저장소에 | 받아들임(Claude · 설계 02) |
| [0013](0013-a-prime-derived-source-and-precision.md) | A′는 파생 출처이며 소수 원값 전체를 보존 | 최종 검수 수용·완료 · 원래 임상 의미 보존(52726ab) |
| [0015](0015-bp-days-require-both-components.md) | 두 성분이 모두 있는 날 중 마지막 날로 혈압을 판정해요 | 리드 검수 받아들임(2026-10-29 · 답 1 ~ 3) · 합치기 전이에요 |
