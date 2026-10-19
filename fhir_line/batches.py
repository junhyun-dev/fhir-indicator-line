"""L0/D1 boundary: split by the written date; do not convert time zones."""
import collections
import datetime as dt
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .bundles import entries, replace_entries
from .runtime import CACHE, ROOT, ensure_space, writable_path

DATE_CONFIG = ROOT / 'config/resource_dates.json'


def resource_date(resource, mapping):
    typ = resource['resourceType']
    if typ not in mapping:
        raise ValueError(f'No explicit L0 date mapping for {typ}')
    for field in mapping[typ]:
        value = resource
        for part in field.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        if value:
            if not isinstance(value, str):
                raise ValueError(f'Non-text L0 date in {typ}.{field}')
            dt.date.fromisoformat(value[:10])
            return value[:10], field
    return None, None


def split(source, destination, cutoff='2025-10-01', config=DATE_CONFIG):
    source, destination = Path(source).resolve(), writable_path(destination)
    dt.date.fromisoformat(cutoff)
    if not destination.is_relative_to(ROOT) or destination.is_relative_to(source):
        raise ValueError('L0 output must stay in the project and outside the read-only source')
    config_bytes = Path(config).read_bytes()
    mapping = json.loads(config_bytes)
    source_files = sorted(source.glob('*.json'))
    if not source_files:
        raise ValueError('No source FHIR files')
    input_hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    identity = {'cutoff':cutoff, 'date_config_sha256':hashlib.sha256(config_bytes).hexdigest(),
                'source_sha256':input_hashes, 'bundle_wrapper_policy':'preserve_source'}
    if destination.exists():
        prior = json.loads((destination/'split-summary.json').read_text())
        if prior['input_identity'] != identity:
            raise ValueError('Existing L0 batches have different inputs; refusing overwrite')
        for batch in (1,2):
            folder = destination/f'batch_{batch}'
            manifest = json.loads((folder/'manifest.json').read_text())
            for f in manifest['files']:
                if hashlib.sha256((folder/f['path']).read_bytes()).hexdigest() != f['sha256']:
                    raise ValueError('Existing L0 output hash mismatch')
        return prior
    ensure_space(sum(p.stat().st_size for p in source_files)*2 + 20_000_000)
    CACHE.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='batches-', dir=CACHE))
    manifests = {n:{'batch_id':n, 'cutoff':cutoff, 'files':[], 'resource_counts':collections.Counter()} for n in (1,2)}
    original_counts, undated = collections.Counter(), collections.Counter()
    field_counts = collections.defaultdict(collections.Counter)
    seen = set()
    try:
        for n in (1,2):
            (stage/f'batch_{n}').mkdir()
        for index, path in enumerate(source_files, 1):
            text = path.read_bytes().decode('utf-8')
            by_batch = {1:[], 2:[]}
            counts = {1:collections.Counter(), 2:collections.Counter()}
            for entry, entry_json, _ in entries(text):
                resource = entry['resource']
                typ, rid = resource['resourceType'], resource['id']
                if (typ,rid) in seen:
                    raise ValueError('Original has duplicate resource identity; resolve before splitting')
                seen.add((typ,rid))
                original_counts[typ] += 1
                date, field = resource_date(resource, mapping)
                field_counts[typ][field or '<undated>'] += 1
                if date is None:
                    batches = (1,2)
                    undated[typ] += 1
                else:
                    batches = (1,) if date < cutoff else (2,)
                for n in batches:
                    by_batch[n].append(entry_json)
                    counts[n][typ] += 1
            for n in (1,2):
                if not by_batch[n]:
                    continue
                output = stage/f'batch_{n}'/f'source_{index:02}.json'
                content = replace_entries(text,by_batch[n])
                output.write_bytes(content.encode('utf-8'))
                manifests[n]['files'].append({'path':output.name, 'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                    'bytes':output.stat().st_size, 'source_file':str(path.relative_to(ROOT)),
                    'resource_counts':dict(sorted(counts[n].items())), 'resource_count':sum(counts[n].values())})
                manifests[n]['resource_counts'].update(counts[n])
        for n, manifest in manifests.items():
            manifest['resource_counts'] = dict(sorted(manifest['resource_counts'].items()))
            manifest['resource_count'] = sum(manifest['resource_counts'].values())
            manifest['file_count'] = len(manifest['files'])
            (stage/f'batch_{n}'/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        summary = {'input_identity':identity, 'source_file_count':len(source_files), 'source_resource_counts':dict(sorted(original_counts.items())),
                   'source_resource_count':sum(original_counts.values()), 'undated_resource_counts':dict(sorted(undated.items())),
                   'duplicated_across_batches':sum(undated.values()),
                   'date_fields_used':{t:dict(v) for t,v in sorted(field_counts.items())},
                   'batch_counts':{str(n):m['resource_count'] for n,m in manifests.items()}}
        assert sum(summary['batch_counts'].values())-summary['duplicated_across_batches']==summary['source_resource_count']
        (stage/'split-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        destination.parent.mkdir(parents=True,exist_ok=True)
        stage.rename(destination)
        return summary
    except BaseException:
        shutil.rmtree(stage)
        raise
