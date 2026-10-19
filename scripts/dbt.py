#!/usr/bin/env python3
"""L2 boundary: run dbt with local profiles, cache, logs and telemetry disabled."""
import sys
import subprocess
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fhir_line.runtime import ROOT, environment

if __name__ == '__main__':
    raise SystemExit(subprocess.call([str(ROOT/'.venv/bin/dbt'),*sys.argv[1:]],cwd=ROOT,env=environment()))
