#!/usr/bin/env python3
"""L0-L2 / decision 0012: verified, project-local quickstart inputs; no indicator logic."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
A_PATH = Path('.local/FHIR-LINE-01/runs/original/fhir')
B_PATH = Path('.local/public-data/mimic-iv-demo-2.2/extracted/mimic-iv-clinical-database-demo-2.2')
MANIFESTS = {'a': 'hospital_a_fhir.sha256', 'b': 'mimic_iv_demo_2.2_used.sha256'}
JDK_NAME = 'OpenJDK17U-jdk_x64_linux_hotspot_17.0.20.1_1.tar.gz'
JDK_URL = 'https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/' + JDK_NAME
JDK_SHA = '3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e'
JAR_URL = 'https://github.com/synthetichealth/synthea/releases/download/v4.0.0/synthea-with-dependencies.jar'
JAR_SHA = 'ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1'
MIMIC_URL = 'https://physionet.org/static/published-projects/mimic-iv-demo/mimic-iv-clinical-database-demo-2.2.zip'
ANSWER_FILES = ('person_A.csv', 'summary_A.csv', 'person_B.csv', 'summary_B.csv',
                'omop_counts.csv', 'omop_follow.csv')
LIMIT = 5_000_000_000


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative_name(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe relative file path')
    return path


def read_manifest(path):
    rows = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix('*')
        relative_name(name)
        if not re.fullmatch('[0-9a-f]{64}', digest) or name in rows:
            raise ValueError('Invalid or duplicate checksum entry')
        rows[name] = digest
    if not rows:
        raise ValueError('Empty checksum manifest')
    return rows


def verify_manifest(directory, manifest, *, exact_json=False, private=False):
    directory = Path(directory)
    rows = read_manifest(manifest)
    if exact_json and {p.name for p in directory.glob('*.json')} != set(rows):
        raise ValueError('A FHIR 파일 집합이 고정 목록과 다릅니다(누락 또는 추가 파일)')
    size = 0
    for index, (name, digest) in enumerate(rows.items(), 1):
        path = directory / name
        label = f'FHIR 파일 #{index}' if private else name
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError(f'Unsafe source path: {label}')
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f'SHA256 불일치 또는 파일 없음: {label}; 덮어쓰지 않습니다')
        size += path.stat().st_size
    return {'files': len(rows), 'bytes': size}


def verify_source(kind, directory, root=ROOT):
    return verify_manifest(directory, root / 'expected/sources' / MANIFESTS[kind],
                           exact_json=kind == 'a', private=kind == 'a')


def lock_tree(directory):
    # Only newly installed data / verified clone expectations call this function.
    paths = [directory, *directory.rglob('*')]
    if any(path.is_symlink() for path in paths):
        raise ValueError('Refusing to change permissions through a symlink')
    for path in reversed(paths):
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o222:
            path.chmod(mode & ~0o222)


def prepare_expected(root=ROOT):
    folder = root / 'expected'
    verify_manifest(folder, folder / 'SHA256SUMS')
    if any(path.stat().st_mode & 0o222 for path in [folder, *folder.rglob('*')]):
        if any((root / path).exists() for path in
               (A_PATH, B_PATH, Path('data/fhir.duckdb'), Path('data/batches'))):
            raise ValueError('기존 작업실 expected 권한은 변경하지 않습니다; 새 복제본에서 시작하세요')
        lock_tree(folder)
    print('expected: 고정 해시 확인 · 읽기 전용')
    if (root / 'fhir_line/report_ui.py').exists():
        subprocess.run([sys.executable, str(root / 'scripts/verify_lead_answers.py'), '--prepare'],
                       cwd=root, check=True)
    # ADR0013: a clone loses write-bit protection; verify every byte before chmod.
    prime = root / 'expected_a_prime'
    if not prime.exists() and not (root/'fhir_line/a_prime.py').exists():
        return  # Legacy isolated source-helper fixture, not a complete project checkout.
    listing = prime / 'SHA256SUMS'
    wanted = {'answer_key_a_prime/'+name for name in ('README.md','calculate.py','check.py','test_contract.py')}
    wanted.update('expected_a_prime/'+name for name in ('manifest.json','person.csv','summary.csv','omop_facts.csv'))
    if set(read_manifest(listing)) != wanted:
        raise ValueError('A-prime frozen file list differs')
    verify_manifest(root, listing)
    if any(path.is_symlink() for path in [prime,root/'answer_key_a_prime',listing]):
        raise ValueError('Symlink in frozen A-prime reference')
    targets=[root/name for name in wanted]+[listing,prime,root/'answer_key_a_prime']
    if any(path.stat().st_mode & 0o222 for path in targets):
        if any((root/path).exists() for path in (A_PATH,B_PATH,Path('data/fhir.duckdb'),Path('data/batches'))):
            raise ValueError('기존 작업실 A-prime 권한은 변경하지 않습니다; 새 복제본에서 시작하세요')
        for path in targets:path.chmod(0o555 if path.is_dir() else 0o444)
    spec=importlib.util.spec_from_file_location('prepared_aprime_check',root/'answer_key_a_prime/check.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    checker.verify_lock(prime)
    print('A-prime: 고정 8파일 해시 확인 · 읽기 전용')


def allocated(path):
    return int(subprocess.check_output(['du', '-s', '-B1', str(path)], text=True).split()[0])


def ensure_space(root=ROOT, additional=0):
    roots = {root.resolve()}
    if root.name in ('fhir-indicator-line', 'fhir-indicator-line-fresh'):
        roots.update(path for name in ('fhir-indicator-line', 'fhir-indicator-line-fresh')
                     if (path := root.with_name(name)).exists())
    used = sum(allocated(path) for path in roots)
    if used + additional >= LIMIT or shutil.disk_usage(root).free < additional:
        raise RuntimeError(f'용량 상한 전에 중단: 사용 {used:,} + 예상 증가 {additional:,}바이트')
    return used


def local_environment(root=ROOT, name='quickstart'):
    cache = root / '.cache' / name
    for name in ('tmp', 'home', 'xdg-cache', 'xdg-config', 'xdg-data'):
        (cache / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TMPDIR=str(cache / 'tmp'), TMP=str(cache / 'tmp'), TEMP=str(cache / 'tmp'),
               XDG_CACHE_HOME=str(cache / 'xdg-cache'), XDG_CONFIG_HOME=str(cache / 'xdg-config'),
               XDG_DATA_HOME=str(cache / 'xdg-data'), PYTHONDONTWRITEBYTECODE='1', TZ='UTC')
    return env


def download(url, destination, size, digest, root=ROOT):
    if destination.exists():
        if destination.stat().st_size != size or (digest and sha256(destination) != digest):
            raise ValueError(f'Cached artifact mismatch: {destination.name}')
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + '.part')
    prior = part.stat().st_size if part.exists() else 0
    if prior > size:
        raise ValueError(f'Partial artifact is too large: {destination.name}')
    ensure_space(root, size - prior + 1_000_000)
    print(f'받기 전 크기: {destination.name} {size:,}바이트', flush=True)
    with (destination.parent / 'curl.log').open('a') as log:
        subprocess.run(['curl', '-fL', '--retry', '3', '-C', '-', '--connect-timeout', '20',
                        '--max-time', '600', '--max-filesize', str(size), '-o', str(part), url],
                       cwd=root, env=local_environment(root), stdout=log, stderr=log, check=True)
    if part.stat().st_size != size or (digest and sha256(part) != digest):
        raise ValueError(f'Download SHA256/size mismatch: {destination.name}; stopped')
    part.rename(destination)
    return size - prior


def extract_zip(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        names = set()
        for member in bundle.infolist():
            relative_name(member.filename)
            if member.filename in names or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Duplicate or symlink ZIP member')
            names.add(member.filename)
            if not (destination / member.filename).resolve().is_relative_to(destination.resolve()):
                raise ValueError('ZIP path escapes extraction directory')
        bundle.extractall(destination)


def extract_tar(archive, destination):
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            relative_name(member.name)
        bundle.extractall(destination, filter='data')


def publish(directory, destination):
    if destination.exists():
        raise ValueError('Source already exists; refusing overwrite')
    destination.parent.mkdir(parents=True, exist_ok=True)
    directory.rename(destination)
    lock_tree(destination)


def generate_a(root=ROOT):
    downloads = root / '.local/FHIR-LINE-01/downloads'
    received = download(JDK_URL, downloads / JDK_NAME, 193_252_603, JDK_SHA, root)
    received += download(JAR_URL, downloads / 'synthea-with-dependencies.jar', 201_164_144, JAR_SHA, root)
    ensure_space(root, 332_109_578 + 160_000_000)
    env = local_environment(root, 'FHIR-LINE-01')
    # A fresh stage is removed even on failure; published originals are never touched.
    with tempfile.TemporaryDirectory(prefix='synthea-', dir=env['TMPDIR']) as tmp:
        stage = Path(tmp)
        tools = root / '.local/FHIR-LINE-01/tools'
        java = tools / 'jdk-17.0.20.1+1/bin/java'
        if not tools.exists():
            extract_tar(downloads / JDK_NAME, stage / 'tools')
            (stage / 'tools').rename(tools)
        if not java.is_file():
            raise ValueError('Pinned Temurin layout mismatch')
        # Verify the executable against the already SHA256-verified archive on reuse too.
        with tarfile.open(downloads / JDK_NAME) as bundle:
            with bundle.extractfile('jdk-17.0.20.1+1/bin/java') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != sha256(java):
                    raise ValueError('Installed portable Java differs from the pinned archive')
        output = stage / 'original'
        argv = [str(java), '-Xms128m', '-Xmx2g', '-XX:ActiveProcessorCount=2', '-XX:-UsePerfData',
                '-Djava.io.tmpdir=' + env['TMPDIR'],
                '-Duser.home=' + str(root / '.cache/FHIR-LINE-01/home'), '-Duser.timezone=UTC',
                '-jar', str(downloads / 'synthea-with-dependencies.jar'),
                '-s', '12345', '-cs', '67890', '-r', '20251231', '-e', '20251231', '-p', '30',
                '--exporter.fhir.export=true', '--exporter.baseDirectory=' + str(output)]
        logs = root / '.local/quickstart/logs'
        logs.mkdir(parents=True, exist_ok=True)
        run_name = f'synthea-{time.time_ns()}'
        record = {'argv': argv, 'cwd': str(root),
                  'environment': {key: env[key] for key in ('TMPDIR', 'TMP', 'TEMP', 'TZ',
                                  'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
                                  'PYTHONDONTWRITEBYTECODE')}}
        with (logs / (run_name + '.json')).open('x') as metadata:
            json.dump(record, metadata, indent=2)
        with (logs / (run_name + '.log')).open('x') as log:
            subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=log, check=True, timeout=300)
        verify_source('a', output / 'fhir', root)
        publish(output, (root / A_PATH).parent)
    return received


def obtain_b(root=ROOT):
    base = root / '.local/public-data/mimic-iv-demo-2.2'
    downloads = base / 'download'
    archive = downloads / 'mimic-iv-clinical-database-demo-2.2.zip'
    received = download(MIMIC_URL, archive, 16_189_661, None, root)
    ensure_space(root, 20_000_000)
    local_environment(root)
    with tempfile.TemporaryDirectory(prefix='mimic-', dir=root / '.cache/quickstart/tmp') as tmp:
        stage = Path(tmp)
        extract_zip(archive, stage)
        source = stage / B_PATH.name
        official = source / 'SHA256SUMS.txt'
        # The official ZIP carries its published manifest; pinned used hashes agree too.
        verify_manifest(source, official)
        published = read_manifest(official)
        pinned = read_manifest(root / 'expected/sources' / MANIFESTS['b'])
        if any(published.get(name) != digest for name, digest in pinned.items()):
            raise ValueError('Official and pinned MIMIC manifests differ')
        verify_source('b', source, root)
        sums_copy = downloads / 'SHA256SUMS.txt'
        if sums_copy.exists() and sums_copy.read_bytes() != official.read_bytes():
            raise ValueError('Existing official MIMIC manifest differs; refusing overwrite')
        if not sums_copy.exists():
            sums_copy.write_bytes(official.read_bytes())
        publish(source, root / B_PATH)
        lock_tree(base)
    return received


def get_sources(root=ROOT, offline=False):
    started = time.monotonic()
    paths = {'a': root / A_PATH, 'b': root / B_PATH}
    # Inspect every existing input before any download or generation.
    existing = {kind: verify_source(kind, path, root) for kind, path in paths.items() if path.exists()}
    missing = paths.keys() - existing.keys()
    if offline and missing:
        raise ValueError('원천이 없습니다; --offline은 다운로드·생성을 허용하지 않습니다')
    received = 0
    if 'a' in missing:
        received += generate_a(root)
    if 'b' in missing:
        received += obtain_b(root)
    result = {'sources': {kind: dict(verify_source(kind, path, root), reused=kind in existing)
                          for kind, path in paths.items()}, 'new_artifact_bytes': received,
              'seconds': round(time.monotonic() - started, 3)}
    output = root / '.local/quickstart'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sources.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    return result


def compare_answers(root=ROOT):
    env = local_environment(root)
    logs = root / '.local/quickstart/logs'
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='answer-key-', dir=env['TMPDIR']) as tmp:
        output = Path(tmp)
        calls = [('make_expected.py', root / A_PATH, output),
                 ('make_expected_b.py', root / B_PATH, output),
                 ('make_expected_omop.py', root / A_PATH, root / B_PATH, output)]
        with (logs / f'answer-key-{time.time_ns()}.log').open('x') as log:
            for script, *args in calls:
                subprocess.run([sys.executable, str(root / 'answer_key' / script), *map(str, args)],
                               cwd=root, env=env, stdout=log, stderr=log, check=True)
        for name in ANSWER_FILES:
            result = subprocess.run(['cmp', '-s', str(output / name), str(root / 'expected' / name)])
            if result.returncode:
                raise ValueError(f'기대 결과가 틀린 것 같다: 독립 재계산과 다름/비교 불가 ({name})')
    print('독립 재계산: 6파일 모두 같음(cmp)')
    if not (root/'answer_key_a_prime').exists() and not (root/'fhir_line/a_prime.py').exists():
        return  # Keep the standalone legacy A/B helper usable; full quickstart requires A-prime.
    # ADR0013: execute the immutable source-only calculator into a disposable directory.
    scratch=root/'.local/FHIR-LINE-A-PRIME'
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='quickstart-recount-',dir=scratch) as tmp:
        output=Path(tmp)
        with (logs/f'aprime-answer-key-{time.time_ns()}.log').open('x') as log:
            subprocess.run([sys.executable,str(root/'answer_key_a_prime/calculate.py'),
                '--source',str(root/A_PATH),'--output',str(output)],cwd=root,env=env,
                stdout=log,stderr=log,check=True)
        for name in ('person.csv','summary.csv','omop_facts.csv','manifest.json'):
            if subprocess.run(['cmp','-s',str(output/name),str(root/'expected_a_prime'/name)]).returncode:
                raise ValueError('A-prime independent recalculation differs: '+name)
    print('A-prime 독립 재계산: 4파일 모두 같음(cmp)')


def summary(root=ROOT):
    import duckdb
    with duckdb.connect(str(root / 'data/fhir.duckdb'), read_only=True,
                        config={'threads': 2, 'memory_limit': '512MB',
                                'autoinstall_known_extensions': False, 'autoload_known_extensions': False}) as con:
        rows = con.execute('select hospital, as_of_label, numerator, denominator, rate '
                           'from bp_summary order by hospital, as_of_label desc').fetchall()
    print('| 병원 | 기준 시점 | 분자/분모 | 조절률 |')
    print('|---|---|---|---|')
    for hospital, label, numerator, denominator, rate in rows:
        print(f'| {hospital} | {label} | {numerator}/{denominator} | {rate} |')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('get')
    get.add_argument('--offline', action='store_true')
    verify = sub.add_parser('verify')
    verify.add_argument('kind', choices=MANIFESTS)
    verify.add_argument('directory', type=Path)
    for command in ('prepare-expected', 'environment', 'budget', 'answers', 'summary'):
        sub.add_parser(command)
    args = parser.parse_args()
    try:
        if args.command == 'get':
            get_sources(offline=args.offline)
        elif args.command == 'verify':
            if not args.directory.resolve().is_relative_to(ROOT):
                raise ValueError('Verification copy must stay in this project')
            print(json.dumps(verify_source(args.kind, args.directory)))
        elif args.command == 'prepare-expected':
            prepare_expected()
        elif args.command == 'environment':
            if platform.system() != 'Linux' or platform.machine() != 'x86_64' or sys.version_info[:2] != (3, 12):
                raise ValueError('Linux x64 · Python 3.12가 필요합니다')
        elif args.command == 'budget':
            used = ensure_space(additional=max(0, 1_800_000_000 - allocated(ROOT)))
            print(f'용량: 기존+새 복제본 {used:,}바이트, 5GB 상한 확인')
        elif args.command == 'answers':
            compare_answers()
        elif args.command == 'summary':
            summary()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, tarfile.TarError,
            zipfile.BadZipFile) as error:
        print(f'중단 [{args.command}]: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
