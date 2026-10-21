#!/bin/sh
# L0 / decision 0012: validate existing originals before downloading or generating.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
export PYTHONDONTWRITEBYTECODE=1
exec python3 scripts/source_data.py get "$@"
