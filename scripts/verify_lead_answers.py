#!/usr/bin/env python3
"""D1-D7 / ADR0010,0013: verify public copies before complete validation."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fhir_line.lead_answers import verify

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path)
parser.add_argument('--prepare', action='store_true')
args = parser.parse_args()
try:
    result = verify(source_root=args.source_root, prepare=args.prepare)
except (OSError, ValueError) as error:
    print('리드 기대 결과 검사 실패:', type(error).__name__, str(error), file=sys.stderr)
    raise SystemExit(1)
print(f"리드 기대 결과 사본: {result['files']}파일 해시 확인 · 읽기 전용")
print(result['detail'])
