"""D1-D7 / ADR0010,0013: public copies work without a private HOME; tampering fails."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fhir_line import lead_answers


class LeadAnswerCopies(unittest.TestCase):
    def setUp(self):
        cache = lead_answers.ROOT / '.cache/lead-answer-tests'
        cache.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(self.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'origin'
        self.root = self.base / 'product'
        for bundle in lead_answers.BUNDLES:
            folder = self.source / bundle
            folder.mkdir(parents=True)
            (folder / 'fixture.json').write_text('{"handmade": true}\n')
            (folder / 'README.md').write_text('Handmade verifier fixture, not clinical expectations.\n')
            digest = hashlib.sha256((folder / 'fixture.json').read_bytes()).hexdigest()
            (folder / 'SHA256SUMS').write_text(digest + '  fixture.json\n')
        self.target = self.root / 'answer_key_lead'
        shutil.copytree(self.source, self.target)
        entries = [hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(self.target).as_posix()
                   for p in sorted(self.target.rglob('*')) if p.is_file()]
        (self.target / 'SHA256SUMS').write_text('\n'.join(entries) + '\n')

    def cleanup(self):
        # Only this handmade temporary fixture is unlocked for deletion.
        for p in [Path(self.temp.name), *Path(self.temp.name).rglob('*')]:
            if p.is_dir() and not p.is_symlink():
                p.chmod(0o755)
        self.temp.cleanup()

    def test_D1_0010_same_origin_bytes_and_readonly_copies(self):
        result = lead_answers.verify(self.root, self.source, prepare=True)
        self.assertTrue(result['source_compared'])
        self.assertEqual(result['files'], 3 * len(lead_answers.BUNDLES))
        self.assertTrue(all(not p.stat().st_mode & 0o222
                            for p in [self.target, *self.target.rglob('*')]))

    def test_D1_0010_empty_HOME_uses_verified_copy_and_marks_origin_absent(self):
        empty = self.base / 'empty-home'
        empty.mkdir()
        environment = dict(os.environ, HOME=str(empty))
        environment.pop('FHIR_LEAD_ANSWER_SOURCE_ROOT', None)
        with patch.dict(os.environ, environment, clear=True):
            result = lead_answers.verify(self.root, prepare=True)
        self.assertFalse(result['source_compared'])
        self.assertEqual(result['detail'], '원본 대조 건너뜀(이 컴퓨터에 원본 없음)')

    def test_D1_0010_changed_copy_fails_even_without_origin(self):
        (self.target / 'cell_diff/fixture.json').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            lead_answers.verify(self.root, self.base / 'absent', prepare=True)

    def test_D1_0010_unlisted_README_is_covered_by_delivery_manifest(self):
        (self.target / 'e01/README.md').write_text('Changed review text\n')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            lead_answers.verify(self.root, self.source, prepare=True)

    def test_D1_0010_changed_origin_fails_without_altering_copy(self):
        original = (self.target / 'v1/README.md').read_bytes()
        (self.source / 'v1/README.md').write_text('A different original\n')
        with self.assertRaisesRegex(ValueError, 'ORIGIN_BYTES_MISMATCH'):
            lead_answers.verify(self.root, self.source, prepare=True)
        self.assertEqual((self.target / 'v1/README.md').read_bytes(), original)

    def test_D1_0015_rehashed_copy_still_must_match_independent_origin(self):
        file=self.target/'e01/fixture.json';file.write_text('{"handmade": false}\n')
        listing=self.target/'SHA256SUMS'
        listing.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(self.target).as_posix()+'\n'
            for p in sorted(self.target.rglob('*')) if p.is_file() and p!=listing))
        with self.assertRaisesRegex(ValueError,'ORIGIN_BYTES_MISMATCH'):
            lead_answers.verify(self.root,self.source,prepare=True)

    def test_D1_0010_extra_copy_is_rejected(self):
        (self.target / 'v1/extra.json').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'FILE_SET'):
            lead_answers.verify(self.root, self.source, prepare=True)

    def test_D1_0010_missing_copy_is_rejected(self):
        (self.target / 'v1/fixture.json').unlink()
        with self.assertRaisesRegex(ValueError, 'FILE_SET'):
            lead_answers.verify(self.root, self.source, prepare=True)

    def test_D1_0010_symlink_copy_is_rejected(self):
        file = self.target / 'v1/fixture.json'
        file.unlink()
        file.symlink_to(self.source / 'v1/fixture.json')
        with self.assertRaisesRegex(ValueError, 'SYMLINK'):
            lead_answers.verify(self.root, self.source, prepare=True)
