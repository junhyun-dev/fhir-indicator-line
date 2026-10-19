#!/bin/sh
# 검사 명령 하나(커밋 전에 꼭 · 하나라도 실패하면 멈춤): 기대 결과 잠금 · 테스트 · 층 방향 · 확인 사다리
# --strict: 기다림도 실패로 봐요(요청 03부터 · 계산 모델이 없으면 끝난 게 아니에요)
set -e
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1

echo "== 기대 결과: 해시와 읽기 전용"
(cd expected && sha256sum -c --quiet SHA256SUMS)
if [ -n "$(find expected -perm -u+w)" ]; then echo "expected/에 쓰기 권한이 있어요"; exit 1; fi

echo "== 테스트"
.venv/bin/python -m unittest discover -s tests

echo "== 확인 사다리(층 방향 포함)"
.venv/bin/python -m fhir_line check --strict > /dev/null || { cat .local/FHIR-LINE-02/summaries/verification-ladder.md; exit 1; }
cat .local/FHIR-LINE-02/summaries/verification-ladder.md
