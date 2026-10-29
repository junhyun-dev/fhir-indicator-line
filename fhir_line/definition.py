"""D1-D7 / ADR0001,0003,0010,0013,0015: registered learning definition with complete BP days."""
import csv
import hashlib
import json
from pathlib import Path
from .runtime import ROOT

REGISTERED = {'v2': '054d929194309e2ffdb78d4cbc3eb9701ed4836177d106cb7d3dd7dc763b9f46'}
FILES = ('docs/decisions/0001-indicator-definition-d1-d7.md',
         'docs/decisions/0003-hospital-b-three-definitions.md',
         'docs/decisions/0010-definition-rules-in-calculation-layer.md',
         'docs/decisions/0015-bp-days-require-both-components.md',
         'models/intermediate/int_bp_daily.sql','models/intermediate/int_person_period.sql',
         'models/marts/dim_as_of.sql','models/marts/fct_bp_person.sql','models/reports/bp_summary.sql',
         'seeds/as_of_labels.csv','seeds/concept.csv','seeds/indicator_concepts.csv','seeds/source_to_concept_map.csv')
SYSTEMS = {'hospital_a_dx': ('A','SNOMED'), 'hospital_b_icd10': ('B','ICD-10'), 'hospital_b_icd9': ('B','ICD-9')}

class DefinitionError(ValueError):
    pass

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def digest(body):
    return hashlib.sha256(body).hexdigest()

def generated_manifest(root=ROOT):
    root=Path(root)
    with (root/'seeds/indicator_concepts.csv').open(newline='') as f:
        selected={int(r['concept_id']) for r in csv.DictReader(f) if r['concept_set']=='essential_hypertension'}
    with (root/'seeds/source_to_concept_map.csv').open(newline='') as f:
        mapping=list(csv.DictReader(f))
    codes=[]
    for row in mapping:
        vocabulary=row['source_vocabulary_id']
        if vocabulary in SYSTEMS and int(row['target_concept_id']) in selected:
            hospital,system=SYSTEMS[vocabulary]
            codes.append(dict(hospital=hospital,source_system=system,source_vocabulary_id=vocabulary,
                source_code=row['source_code'],target_concept_id=int(row['target_concept_id']),target_vocabulary_id=row['target_vocabulary_id']))
    codes.sort(key=lambda x:tuple(x[k] for k in ('hospital','source_system','source_code','source_vocabulary_id')))
    a={(x['source_code'],x['target_concept_id']) for x in codes if x['hospital']=='A'}
    ap={(x['source_code'],int(x['target_concept_id'])) for x in mapping if x['source_vocabulary_id']=='hospital_a_prime_dx_snomed' and int(x['target_concept_id']) in selected}
    if a!=ap:raise DefinitionError('DERIVED_MEMBERSHIP_MISMATCH')
    return dict(definition_id='bp-control-learning',definition_version='v2',
        code_set_id='essential-hypertension-learning',code_set_version='v1',source_codes=codes,
        files=[{'path':p,'sha256':digest((root/p).read_bytes())} for p in sorted(FILES)])

def context(version='v2', root=ROOT):
    if version not in REGISTERED:raise DefinitionError('UNREGISTERED_DEFINITION')
    manifest_path=Path(root)/'config/indicator_definitions'/version/'manifest.json'
    body=manifest_path.read_bytes()
    if digest(body)!=REGISTERED[version] or body!=canonical(generated_manifest(root)):
        raise DefinitionError('DEFINITION_HASH_MISMATCH')
    return json.loads(body),digest(body)

def member(manifest,hospital,system,code):
    hospital='A' if hospital=='A_PRIME' and system=='SNOMED' else hospital
    return any((x['hospital'],x['source_system'],x['source_code'])==(hospital,system,code) for x in manifest['source_codes'])

def metadata(manifest,hash_value,run_id):
    if not run_id or manifest.get('definition_version')!='v2' or manifest.get('code_set_version')!='v1' or hash_value!=REGISTERED['v2'] or digest(canonical(manifest))!=hash_value:
        raise DefinitionError('UNREGISTERED_DEFINITION')
    return {k:manifest[k] for k in ('definition_id','definition_version','code_set_version')} | {
        'definition_manifest_sha256':hash_value,'run_id':run_id}
