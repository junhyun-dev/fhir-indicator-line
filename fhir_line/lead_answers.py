"""D1-D7 / ADR0010,0013: verify byte-identical lead-owned reference copies.

This module uses only the standard library so a fresh clone can lock its copies
before creating the Python environment. It never writes the private originals.
"""
from pathlib import Path, PurePosixPath
import hashlib
import os
import re

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = ('cell_diff', 'e01', 'v1')


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
            if set(origin_files) != set(copied) or any(
                    origin_files[name].read_bytes() != copied[name].read_bytes() for name in copied):
                raise ValueError('LEAD_ORIGIN_BYTES_MISMATCH')
    paths = [folder, *folder.rglob('*')]
    if prepare:
        # Only the verified product copies are changed; never the lead's originals.
        for path in reversed(paths):
            path.chmod(0o555 if path.is_dir() else 0o444)
    if any(p.stat().st_mode & 0o222 for p in paths):
        raise ValueError('LEAD_REFERENCE_WRITABLE')
    return {'files': len(hashes), 'source_compared': present,
            'detail': '리드 원본 대조: 같은 바이트예요.' if present else
                      '원본 대조 건너뜀(이 컴퓨터에 원본 없음)'}
