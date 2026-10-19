"""L2: project-local runtime paths, storage and database resource limits."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.local/FHIR-LINE-02'
CACHE = ROOT / '.cache/FHIR-LINE-02'
ORIGINAL = ROOT / '.local/FHIR-LINE-01/runs/original/fhir'
DATABASE = ROOT / 'data/fhir.duckdb'


def writable_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Output must stay in this project')
    if any(path.is_relative_to(protected) for protected in (ROOT/'expected',ROOT/'.local/FHIR-LINE-01')):
        raise ValueError('Expected answers and original experiment are read-only')
    return path


def environment():
    env = os.environ.copy()
    for directory in ('tmp', 'xdg', 'duckdb', 'extensions'):
        (CACHE / directory).mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / 'logs/dbt').mkdir(parents=True, exist_ok=True)
    env.update(TMPDIR=str(CACHE/'tmp'), XDG_CACHE_HOME=str(CACHE/'xdg'),
               PYTHONDONTWRITEBYTECODE='1', DBT_SEND_ANONYMOUS_USAGE_STATS='false',
               DBT_PROFILES_DIR=str(ROOT), DBT_LOG_PATH=str(ARTIFACTS/'logs/dbt'),
               DBT_TARGET_PATH=str(ARTIFACTS/'dbt-target'),
               FHIR_DB_PATH=str(DATABASE), FHIR_DUCKDB_TEMP=str(CACHE/'duckdb'),
               FHIR_DUCKDB_EXTENSIONS=str(CACHE/'extensions'))
    return env


def connect(path=DATABASE, read_only=False):
    import duckdb
    if str(path) != ':memory:':
        path = Path(path).resolve() if read_only else writable_path(path)
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only, config={
        'threads':2, 'memory_limit':'512MB', 'temp_directory':str(CACHE/'duckdb'),
        'extension_directory':str(CACHE/'extensions'),
        'autoinstall_known_extensions':False, 'autoload_known_extensions':False,
    })


def allocated_bytes():
    return sum(p.lstat().st_blocks*512 for p in [ROOT, *ROOT.rglob('*')])


def ensure_space(additional=0):
    if allocated_bytes()+additional >= 5_000_000_000:
        raise RuntimeError('Project storage would exceed the approved 5GB limit')
