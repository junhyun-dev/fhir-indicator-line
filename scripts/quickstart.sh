#!/bin/sh
# L0-L2 / decision 0012: one local entry point; indicator and checker logic stay unchanged.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
phase=환경
log=
trap 'status=$?; if [ "$status" -ne 0 ]; then printf "중단: %s (종료 %s) · 로그 %s\n" "$phase" "$status" "$log" >&2; fi' 0
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/source_data.py environment
phase=용량
python3 scripts/source_data.py budget
phase=기대결과
python3 scripts/source_data.py prepare-expected

mkdir -p .cache/quickstart/tmp .cache/quickstart/pip .cache/quickstart/xdg .local/quickstart/logs
log="$root/.local/quickstart/logs/quickstart-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
export TMPDIR="$root/.cache/quickstart/tmp"
export XDG_CACHE_HOME="$root/.cache/quickstart/xdg"
export PIP_CACHE_DIR="$root/.cache/quickstart/pip"
export PIP_CONFIG_FILE=/dev/null
export PIP_DISABLE_PIP_VERSION_CHECK=1
unset PIP_EXTRA_INDEX_URL PIP_TARGET PIP_PREFIX PIP_USER PIP_FIND_LINKS
export MIMIC_SOURCE_DIR="$root/.local/public-data/mimic-iv-demo-2.2/extracted/mimic-iv-clinical-database-demo-2.2"
started=$(date +%s)

phase=가상환경
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv >> "$log" 2>&1; fi
if [ "${FHIR_OFFLINE:-0}" = 1 ]; then
  .venv/bin/python -m pip install --no-index --only-binary=:all: --require-hashes --no-input \
    -r requirements.lock >> "$log" 2>&1
else
  .venv/bin/python -m pip install --only-binary=:all: --require-hashes --no-input \
    --index-url https://pypi.org/simple -r requirements.lock >> "$log" 2>&1
fi
printf '완료: %s\n' "$phase"
phase=원천
if [ "${FHIR_OFFLINE:-0}" = 1 ]; then
  sh scripts/get_sources.sh --offline >> "$log" 2>&1
else
  sh scripts/get_sources.sh >> "$log" 2>&1
fi
printf '완료: %s (해시 확인)\n' "$phase"
phase=배치나누기
.venv/bin/python -m fhir_line split >> "$log" 2>&1
phase=배치1적재
.venv/bin/python -m fhir_line load data/batches/batch_1 >> "$log" 2>&1
phase=배치2적재
.venv/bin/python -m fhir_line load data/batches/batch_2 >> "$log" 2>&1
phase=A프라임생성
.venv/bin/python -m fhir_line aprime-generate >> "$log" 2>&1
phase=전체검사
sh scripts/check.sh >> "$log" 2>&1
printf '완료: check.sh 종료 0\n'
phase=독립재계산
.venv/bin/python scripts/source_data.py answers >> "$log" 2>&1
printf '독립 재계산: 6파일 모두 같음(cmp)\n'
printf 'A′ 독립 재계산: 4파일 모두 같음(cmp)\n'
phase=결과
.venv/bin/python scripts/source_data.py summary
printf '완료: %s초 · 원문 로그 %s\n' "$(( $(date +%s) - started ))" "$log"
