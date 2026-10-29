"""D1-D7 / ADR0010,0013,0015: verify lead copies and the reviewed WP-5 transcription.

This module uses only the standard library so a fresh clone can lock its copies
before creating the Python environment. It never writes the private originals.
"""
from pathlib import Path, PurePosixPath
import csv
import hashlib
import io
import json
import os
import re

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = ('cell_diff', 'e01', 'v1', 'wp5-bp-days-both-values')


def wp5_e01_transcription(contents, wp5_body):
    """ADR0015: serialize only reviewed replacements, independently of product results."""
    name = 'expected_manual/person.csv'
    reader = csv.DictReader(io.StringIO(contents[name].decode(), newline=''))
    rows = list(reader)
    changes = [c for c in json.loads(wp5_body)['cases'] if c['group'] == 'E01' and c['changed']]
    if {c['id'] for c in changes} != {'E01-A-p1-dec31', 'E01-A_PRIME-p1-dec31'}:
        raise ValueError('WP5_E01_CASE_SET')
    for case in changes:
        matching = [r for r in rows if (r['hospital'], r['person_id'], r['as_of_label']) ==
                    (case['hospital'], case['person'], case['as_of_label'])]
        if len(matching) != 1:
            raise ValueError('WP5_E01_ROW_KEY')
        row = matching[0]
        for key in ('last_bp_date', 'systolic', 'diastolic', 'controlled', 'reason'):
            old, new = case['current_expected'][key], case['new_expected'][key]
            actual = row[key] or None
            if actual is not None and key in ('systolic', 'diastolic', 'controlled'):
                actual = float(actual)
            if actual != old:
                raise ValueError('WP5_E01_ORIGIN_CHANGED')
            if new != old:
                row[key] = '' if new is None else str(new)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    result = dict(contents)
    result[name] = stream.getvalue().encode()
    # Preserve the original list and every other file hash.
    result['SHA256SUMS'] = ''.join(
        hashlib.sha256(result[path]).hexdigest() + '  ' + path + '\n'
        for line in contents['SHA256SUMS'].decode().splitlines()
        for _, path in [line.split('  ', 1)]).encode()
    return result


def _files(folder):
    paths = [folder, *folder.rglob('*')]
    if any(p.is_symlink() for p in paths):
        raise ValueError('LEAD_REFERENCE_SYMLINK')
    return {p.relative_to(folder).as_posix(): p for p in paths
            if p.is_file() and '__pycache__' not in p.parts}


def verify(root=ROOT, source_root=None, *, prepare=False):
    root = Path(root)
    folder = root / 'answer_key_lead'
    listing = folder / 'SHA256SUMS'
    if not folder.is_dir() or folder.is_symlink() or listing.is_symlink():
        raise ValueError('LEAD_REFERENCE_MISSING_OR_UNSAFE')
    hashes = {}
    for line in listing.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('LEAD_REFERENCE_MANIFEST')
        digest, name = match.groups()
        path = PurePosixPath(name)
        if not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or name in hashes:
            raise ValueError('LEAD_REFERENCE_MANIFEST')
        if path.parts[0] not in BUNDLES:
            raise ValueError('LEAD_REFERENCE_MANIFEST')
        hashes[name] = digest
    files = _files(folder)
    if {PurePosixPath(name).parts[0] for name in hashes} != set(BUNDLES):
        raise ValueError('LEAD_REFERENCE_MISSING_BUNDLE')
    if not hashes or set(files) != set(hashes) | {'SHA256SUMS'}:
        raise ValueError('LEAD_REFERENCE_FILE_SET')
    for name, digest in hashes.items():
        if hashlib.sha256(files[name].read_bytes()).hexdigest() != digest:
            raise ValueError('LEAD_REFERENCE_HASH_MISMATCH')
    source = Path(source_root if source_root is not None else os.environ.get(
        'FHIR_LEAD_ANSWER_SOURCE_ROOT', str(Path.home() / 'personal/builds/medical-data-hands-on/answer-key')))
    present = source.exists()
    if present:
        if source.is_symlink() or not source.is_dir():
            raise ValueError('LEAD_ORIGIN_UNSAFE')
        for bundle in BUNDLES:
            original = source / bundle
            if not original.is_dir() or original.is_symlink():
                raise ValueError('LEAD_ORIGIN_MISSING_BUNDLE')
            origin_files = _files(original)
            copied = {name.removeprefix(bundle + '/'): files[name]
                      for name in hashes if name.startswith(bundle + '/')}
            origin_bytes = {name: path.read_bytes() for name, path in origin_files.items()}
            if bundle == 'e01' and 'expected_manual/person.csv' in origin_bytes:
                origin_bytes = wp5_e01_transcription(
                    origin_bytes, (source / 'wp5-bp-days-both-values/expected.json').read_bytes())
            if set(origin_bytes) != set(copied) or any(
                    origin_bytes[name] != copied[name].read_bytes() for name in copied):
                raise ValueError('LEAD_ORIGIN_BYTES_MISMATCH')
    paths = [folder, *folder.rglob('*')]
    if prepare:
        # Only the verified product copies are changed; never the lead's originals.
        for path in reversed(paths):
            path.chmod(0o555 if path.is_dir() else 0o444)
    if any(p.stat().st_mode & 0o222 for p in paths):
        raise ValueError('LEAD_REFERENCE_WRITABLE')
    return {'files': len(hashes), 'source_compared': present,
            'detail': '리드 원본 대조: 같은 바이트예요(E01의 WP-5 전사는 검수된 JSON과 대조해요).' if present else
                      '원본 대조 건너뜀(이 컴퓨터에 원본 없음)'}
