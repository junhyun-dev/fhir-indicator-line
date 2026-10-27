#!/usr/bin/env python3
"""D1-D7 / ADR0010,0013: one command, read-only DB snapshot -> local static S01-S05."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fhir_line.report_ui import main
if __name__=='__main__':raise SystemExit(main())
