#!/bin/sh
# 검사 명령 하나(커밋 전에 꼭 · 하나라도 실패하면 멈춤): 기대 결과 잠금 · 테스트 · 층 방향 · 확인 사다리
# --strict: 기다림도 실패로 봐요(요청 03부터 · 계산 모델이 없으면 끝난 게 아니에요)
set -e
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1

echo "== 기대 결과: 해시와 읽기 전용"
(cd expected && sha256sum -c --quiet SHA256SUMS)
if [ -n "$(find expected -perm -u+w)" ]; then echo "expected/에 쓰기 권한이 있어요"; exit 1; fi

echo "== 바뀌면 안 되는 층(표준 과정 v1.11 · 기준 커밋은 마일스톤마다 요청서에서 바꿔요)"
FROZEN_BASE=                                          # M3 요청 07: 결정 0004로 계산 층을 OMOP으로 옮기는 중 — 07이 커밋되면 그 커밋으로
FROZEN_PATHS="models/intermediate models/marts models/reports"
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
