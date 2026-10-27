#!/bin/sh
# 검사 명령 하나(커밋 전에 꼭 · 하나라도 실패하면 멈춤): 기대 결과 잠금 · 테스트 · 층 방향 · 확인 사다리
# --strict: 기다림도 실패로 봐요(요청 03부터 · 계산 모델이 없으면 끝난 게 아니에요)
set -e
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1

echo "== 필수 외부 기대 입력(셀 차이 다섯 사례)"
if [ "${FHIR_SKIP_EXTERNAL_CELL_CASES:-0}" = 1 ]; then
  echo "실패: 건너뜀 · 완료 검증 아님. check.sh에서는 외부 사례가 필수예요."
  exit 1
fi
external_cases="${FHIR_CELL_DIFF_CASES:-$HOME/personal/builds/medical-data-hands-on/answer-key/cell_diff/cases.json}"
if [ ! -f "$external_cases" ]; then
  echo "실패: 필수 외부 기대 입력 cases.json이 없어요. FHIR_CELL_DIFF_CASES로 고정 파일을 지정하세요."
  exit 1
fi

echo "== 기대 결과: 해시와 읽기 전용"
(cd expected && sha256sum -c --quiet SHA256SUMS)
if [ -n "$(find expected -perm -u+w)" ]; then echo "expected/에 쓰기 권한이 있어요"; exit 1; fi
echo "== A′ 고정 기대 결과(결정 0013)"
.venv/bin/python -m fhir_line aprime-verify-lock

echo "== 바뀌면 안 되는 층(표준 과정 v1.11 · 기준 커밋은 마일스톤마다 요청서에서 바꿔요)"
FROZEN_BASE=3e99c30                                   # M3: 계산이 OMOP 위로 옮겨진 뒤(요청 07 · 결정 0004) — 새 병원 · 새 출처는 L4 ~ L6과 지표 개념을 0줄로
FROZEN_PATHS="models/intermediate models/marts models/reports seeds/indicator_concepts.csv seeds/as_of_labels.csv"
if [ -z "$FROZEN_BASE" ]; then
  echo "건너뜀: 결정 0004 · 요청 07로 L4 ~ L6을 바꾸는 반복이에요(숫자는 ④가 셀마다 봐요)"
elif ! git diff --quiet "$FROZEN_BASE" -- $FROZEN_PATHS; then
  echo "L4 ~ L6이 $FROZEN_BASE 뒤로 바뀌었어요(경계가 틀렸거나, 바꾸기로 한 마일스톤이면 기준 커밋을 고쳐요)"
  git diff --stat "$FROZEN_BASE" -- $FROZEN_PATHS; exit 1
fi

echo "== 테스트"
.venv/bin/python -m unittest discover -s tests

echo "== 확인 사다리(층 방향 포함)"
.venv/bin/python scripts/dbt.py build
.venv/bin/python -m fhir_line check --strict > /dev/null || { cat .local/FHIR-LINE-02/summaries/verification-ladder.md; exit 1; }
cat .local/FHIR-LINE-02/summaries/verification-ladder.md
