"""L0-L2 / decision 0012: offline reuse, source integrity and safe quickstart setup."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quickstart_sources', ROOT / 'scripts/source_data.py')
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class QuickstartInputs(unittest.TestCase):
    def setUp(self):
        base = ROOT / '.cache/FHIR-LINE-08/tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        self.addCleanup(self.cleanup)
        for path in ('expected/sources', 'scripts'):
            (self.root / path).mkdir(parents=True)
        for name in ('source_data.py', 'get_sources.sh', 'quickstart.sh'):
            shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        self.inputs = {'a': {'patient.json': b'{"entry":[]}', 'institution.json': b'{"entry":[]}'},
                       'b': {'hosp/patients.csv.gz': b'fixture'}}
        for kind, files in self.inputs.items():
            manifest = self.root / 'expected/sources' / sources.MANIFESTS[kind]
            manifest.write_text(''.join(f'{hashlib.sha256(body).hexdigest()}  {name}\n'
                                        for name, body in files.items()))
        (self.root / 'expected/sample.csv').write_text('value\n1\n')
        expected_files = sorted(p for p in (self.root / 'expected').rglob('*') if p.is_file())
        (self.root / 'expected/SHA256SUMS').write_text(''.join(
            f'{digest(path)}  {path.relative_to(self.root / "expected")}\n' for path in expected_files))

    def cleanup(self):
        for folder in [self.root, *self.root.rglob('*')]:
            if folder.is_dir() and not folder.is_symlink():
                folder.chmod(stat.S_IMODE(folder.stat().st_mode) | 0o700)
        self.temp.cleanup()

    def write_inputs(self, kinds=('a', 'b')):
        for kind in kinds:
            folder = self.root / (sources.A_PATH if kind == 'a' else sources.B_PATH)
            for name, body in self.inputs[kind].items():
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)

    def command(self, *args, shell=False):
        argv = (['sh', str(self.root / 'scripts/get_sources.sh')] if shell else
                [sys.executable, str(self.root / 'scripts/source_data.py')])
        return subprocess.run([*argv, *args], cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=20)

    def test_0012_L0_reuse_twice_without_download_or_jvm_or_source_changes(self):
        self.write_inputs()
        paths = [self.root / sources.A_PATH / name for name in self.inputs['a']]
        before = [(p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in paths]
        with patch.object(sources, 'generate_a', side_effect=AssertionError('No JVM')) as java, \
             patch.object(sources, 'obtain_b', side_effect=AssertionError('No download')) as network, \
             contextlib.redirect_stdout(io.StringIO()):
            for _ in range(2):
                result = sources.get_sources(self.root)
                self.assertEqual(result['new_artifact_bytes'], 0)
                self.assertTrue(all(row['reused'] for row in result['sources'].values()))
            java.assert_not_called()
            network.assert_not_called()
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in paths])

    def test_0012_L0_shell_entry_works_from_another_cwd_offline(self):
        self.write_inputs()
        result = self.command('--offline', shell=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['new_artifact_bytes'], 0)
        self.assertFalse((self.root / '.local/quickstart/downloads').exists())

    def test_0012_L0_changed_copy_stops_before_any_download_and_is_not_overwritten(self):
        self.write_inputs(('b',))
        path = self.root / sources.B_PATH / 'hosp/patients.csv.gz'
        path.write_bytes(b'CHANGED_COPY')
        before = path.read_bytes()
        with patch.object(sources, 'generate_a', side_effect=AssertionError('No JVM')) as java:
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                sources.get_sources(self.root)
            java.assert_not_called()
        result = self.command('--offline', shell=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('SHA256', result.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / '.local/quickstart/downloads').exists())

    def test_0012_L0_offline_missing_source_cannot_generate(self):
        result = self.command('--offline', shell=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('--offline', result.stderr)
        self.assertFalse((self.root / '.local/quickstart').exists())

    def test_0012_L0_extra_a_json_is_rejected(self):
        self.write_inputs()
        (self.root / sources.A_PATH / 'extra.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, '파일 집합'):
            sources.verify_source('a', self.root / sources.A_PATH, self.root)

    def test_0012_L0_source_symlink_is_rejected(self):
        self.write_inputs()
        path = self.root / sources.A_PATH / 'patient.json'
        path.unlink()
        path.symlink_to(self.root / sources.A_PATH / 'institution.json')
        with self.assertRaisesRegex(ValueError, 'Unsafe source'):
            sources.verify_source('a', self.root / sources.A_PATH, self.root)

    def test_0012_L0_manifest_traversal_is_rejected(self):
        manifest = self.root / 'bad.sha256'
        manifest.write_text('0' * 64 + '  ../outside\n')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            sources.read_manifest(manifest)

    def test_0012_L2_clone_expectations_lock_only_after_validating_hashes(self):
        file = self.root / 'expected/sample.csv'
        before = file.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            sources.prepare_expected(self.root)
            sources.prepare_expected(self.root)
        self.assertEqual(file.read_bytes(), before)
        self.assertTrue(all(not path.stat().st_mode & 0o222
                            for path in [self.root / 'expected', *(self.root / 'expected').rglob('*')]))

    def test_0012_L2_bad_expectations_stop_before_chmod_or_package_install(self):
        path = self.root / 'expected/sample.csv'
        path.write_text('changed\n')
        mode = path.stat().st_mode
        result = subprocess.run(['sh', str(self.root / 'scripts/quickstart.sh')], cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn('기대결과', result.stderr)
        self.assertEqual(path.stat().st_mode, mode)
        self.assertFalse((self.root / '.venv').exists())

    def test_0012_L2_existing_workspace_expectations_are_not_chmoded(self):
        self.write_inputs()
        file = self.root / 'expected/sample.csv'
        mode = file.stat().st_mode
        with self.assertRaisesRegex(ValueError, '기존 작업실'):
            sources.prepare_expected(self.root)
        self.assertEqual(file.stat().st_mode, mode)

    def test_0012_L0_zip_traversal_or_symlink_stops_before_extraction(self):
        for malicious in ('../outside', 'symlink'):
            with self.subTest(malicious=malicious):
                archive = self.root / 'bad.zip'
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr('good.csv', 'good')
                    entry = zipfile.ZipInfo(malicious)
                    if malicious == 'symlink':
                        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    bundle.writestr(entry, 'target')
                destination = self.root / 'unpacked'
                destination.mkdir(exist_ok=True)
                with self.assertRaises(ValueError):
                    sources.extract_zip(archive, destination)
                self.assertEqual(list(destination.iterdir()), [])

    def test_0012_L0_tar_symlink_cannot_escape(self):
        archive = self.root / 'bad.tar'
        with tarfile.open(archive, 'w') as bundle:
            entry = tarfile.TarInfo('link')
            entry.type = tarfile.SYMTYPE
            entry.linkname = '../../outside'
            bundle.addfile(entry)
        with self.assertRaises(tarfile.FilterError):
            sources.extract_tar(archive, self.root / 'tar-unpacked')
        self.assertFalse((self.root / 'outside').exists())

    def test_0012_L0_generation_uses_pinned_java_original_flags_and_verifies_before_publish(self):
        java_content = b'fixture-portable-java'
        def fixture_download(url, destination, size, sha, root):
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.name == sources.JDK_NAME:
                self.assertEqual(sha, sources.JDK_SHA)
                with tarfile.open(destination, 'w:gz') as bundle:
                    entry = tarfile.TarInfo('jdk-17.0.20.1+1/bin/java')
                    entry.size = len(java_content)
                    entry.mode = 0o755
                    bundle.addfile(entry, io.BytesIO(java_content))
            else:
                self.assertEqual(sha, sources.JAR_SHA)
                destination.write_bytes(b'fixture-jar')
            return 0
        def generation(argv, **kwargs):
            self.assertEqual(Path(argv[0]), self.root / '.local/FHIR-LINE-01/tools/jdk-17.0.20.1+1/bin/java')
            for option in ('-Xmx2g', '-XX:ActiveProcessorCount=2', '-Duser.timezone=UTC'):
                self.assertIn(option, argv)
            self.assertEqual(argv[argv.index('-s') + 1], '12345')
            self.assertEqual(argv[argv.index('-cs') + 1], '67890')
            self.assertEqual(argv[argv.index('-r') + 1], '20251231')
            self.assertEqual(argv[argv.index('-e') + 1], '20251231')
            self.assertEqual(argv[argv.index('-p') + 1], '30')
            self.assertEqual(kwargs['env']['TMPDIR'], str(self.root / '.cache/FHIR-LINE-01/tmp'))
            output = Path(next(arg.split('=', 1)[1] for arg in argv if arg.startswith('--exporter.baseDirectory=')))
            for name, body in self.inputs['a'].items():
                path = output / 'fhir' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(sources, 'download', side_effect=fixture_download), \
             patch.object(sources, 'ensure_space', return_value=0), \
             patch.object(sources.subprocess, 'run', side_effect=generation):
            self.assertEqual(sources.generate_a(self.root), 0)
        self.assertEqual(sources.verify_source('a', self.root / sources.A_PATH, self.root)['files'], 2)
        self.assertFalse((self.root / sources.A_PATH / 'patient.json').stat().st_mode & 0o222)

    def test_0012_L0_mimic_checks_every_official_file_before_readonly_publication(self):
        def fixture_download(url, destination, size, sha, root):
            self.assertEqual(url, sources.MIMIC_URL)
            destination.parent.mkdir(parents=True, exist_ok=True)
            prefix = sources.B_PATH.name + '/'
            files = dict(self.inputs['b'], extra=b'not-used-but-official')
            sums = ''.join(f'{hashlib.sha256(body).hexdigest()}  {name}\n' for name, body in files.items())
            with zipfile.ZipFile(destination, 'w') as bundle:
                for name, body in files.items():
                    bundle.writestr(prefix + name, body)
                bundle.writestr(prefix + 'SHA256SUMS.txt', sums)
            return 0
        with patch.object(sources, 'download', side_effect=fixture_download), \
             patch.object(sources, 'ensure_space', return_value=0):
            self.assertEqual(sources.obtain_b(self.root), 0)
        self.assertTrue((self.root / sources.B_PATH / 'extra').is_file())
        self.assertFalse((self.root / sources.B_PATH).stat().st_mode & 0o222)
        self.assertEqual(sources.verify_source('b', self.root / sources.B_PATH, self.root)['files'], 1)

    def test_0012_L0_bad_cached_artifact_is_not_redownloaded(self):
        path = self.root / 'download.jar'
        path.write_bytes(b'bad')
        with patch.object(sources.subprocess, 'run', side_effect=AssertionError('No network')):
            with self.assertRaisesRegex(ValueError, 'Cached artifact mismatch'):
                sources.download('https://example.invalid/file', path, 3, '0' * 64, self.root)
        self.assertEqual(path.read_bytes(), b'bad')

    def test_0012_L0_resumed_artifact_is_published_only_after_checksum(self):
        destination = self.root / 'download.jar'
        destination.with_suffix('.jar.part').write_bytes(b'par')
        def curl(argv, **kwargs):
            Path(argv[argv.index('-o') + 1]).write_bytes(b'complete')
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(sources, 'ensure_space', return_value=0), \
             patch.object(sources.subprocess, 'run', side_effect=curl) as runner, \
             contextlib.redirect_stdout(io.StringIO()):
            size = sources.download('https://example.invalid/file', destination, 8,
                                    hashlib.sha256(b'complete').hexdigest(), self.root)
        self.assertEqual(size, 5)
        self.assertEqual(destination.read_bytes(), b'complete')
        argv = runner.call_args.args[0]
        self.assertIn('-C', argv)
        self.assertEqual(argv[argv.index('--retry') + 1], '3')

    def test_0012_L0_failed_checksum_does_not_publish_partial_download(self):
        destination = self.root / 'bad.jar'
        def curl(argv, **kwargs):
            Path(argv[argv.index('-o') + 1]).write_bytes(b'wrong')
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(sources, 'ensure_space', return_value=0), \
             patch.object(sources.subprocess, 'run', side_effect=curl), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'SHA256/size'):
                sources.download('https://example.invalid/file', destination, 5, '0' * 64, self.root)
        self.assertFalse(destination.exists())

    def test_0012_L2_budget_stops_before_five_gb(self):
        with patch.object(sources, 'allocated', return_value=4_900_000_000):
            with self.assertRaisesRegex(RuntimeError, '용량 상한'):
                sources.ensure_space(self.root, 100_000_000)

    def test_0012_L2_independent_scripts_write_temp_and_cmp_six_files(self):
        folder = self.root / 'answer_key'
        folder.mkdir()
        names = [('make_expected.py', sources.ANSWER_FILES[:2]),
                 ('make_expected_b.py', sources.ANSWER_FILES[2:4]),
                 ('make_expected_omop.py', sources.ANSWER_FILES[4:])]
        for script, files in names:
            for name in files:
                (self.root / 'expected' / name).write_text(name + '\n')
            (folder / script).write_text('import sys\nfrom pathlib import Path\n'
                'output=Path(sys.argv[-1]); output.mkdir(exist_ok=True)\n'
                'assert "expected" not in output.parts\n'
                f'for name in {files!r}: (output/name).write_text(name+"\\n")\n')
        with contextlib.redirect_stdout(io.StringIO()):
            sources.compare_answers(self.root)
        path = self.root / 'expected/person_A.csv'
        path.write_text('different\n')
        with self.assertRaisesRegex(ValueError, '기대 결과가 틀린 것 같다'), \
             contextlib.redirect_stdout(io.StringIO()):
            sources.compare_answers(self.root)
        self.assertEqual(path.read_text(), 'different\n')
        self.assertFalse(list((self.root / '.cache/quickstart/tmp').glob('answer-key-*')))


if __name__ == '__main__':
    unittest.main()
