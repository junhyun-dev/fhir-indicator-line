"""D1-D3 / ADR0013: derived A-prime input, independent of the frozen reference code."""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile

from .runtime import ROOT, ORIGINAL, CACHE, ensure_space, writable_path

DEFAULT = ROOT / 'data/a_prime'
SNOMED = 'http://snomed.info/sct'
LOINC = 'http://loinc.org'
UCUM = 'http://unitsofmeasure.org'
ACT = 'http://terminology.hl7.org/CodeSystem/v3-ActCode'
FIELDS = {
    'persons': ('person_id','birth_date','gender','deceased_datetime','deceased_boolean','measurement_year','derived_from'),
    'diagnoses': ('person_id','condition_id','coding_index','original_code','original_system','start','end','recorded',
                  'clinical_status','kcd_candidate_code','kcd_candidate_edition_context','kcd_candidate_status','kcd_candidate_usage','derived_from'),
    'visits': ('person_id','encounter_id','class_code','class_system','start','end','recorded','visit_kind','derived_from'),
    'bp_details': ('person_id','observation_id','effective','status','panel_code','panel_system','panel_codings','bp_text','format_status',
                   *tuple(prefix+'_'+field for prefix in ('systolic','diastolic')
                          for field in ('code','system','original_value','unit_code','unit_system','unit_display')), 'derived_from'),
}
KEYS = {'persons':('person_id',),'diagnoses':('condition_id','coding_index'),
        'visits':('encounter_id',),'bp_details':('observation_id',)}


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'))


def numeric(value):
    if value is None or value == '':
        return ''
    if isinstance(value, bool):
        raise ValueError('Boolean BP value')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid BP number') from None
    if not number.is_finite():
        raise ValueError('Non-finite BP number')
    return format(number, 'f')


def parse_bp(text):
    """Independent product parser: preserve exact Decimal text, including fractional scale."""
    if not isinstance(text, str) or text.count('/') != 1:
        raise ValueError('BP requires exactly one slash')
    parts = text.split('/')
    for part in parts:
        if part and not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)', part):
            raise ValueError('Invalid BP component text')
    return tuple(numeric(part) for part in parts)


def calendar_day(text):
    if text:
        date.fromisoformat(text[:10])
    return text[:10]


def subject(resource):
    return resource['subject']['reference'].rsplit('/',1)[-1].rsplit(':',1)[-1]


def transform(resources):
    """Only input formatting; no eligibility, daily minima or clinical aggregation."""
    tables = {name:[] for name in FIELDS}
    for r in resources:
        kind = r.get('resourceType')
        if kind == 'Patient':
            tables['persons'].append(dict(person_id=r['id'],birth_date=r['birthDate'],gender=r.get('gender',''),
                deceased_datetime=r.get('deceasedDateTime',''),deceased_boolean=str(r.get('deceasedBoolean','')).lower(),
                measurement_year='2025',derived_from='A'))
        elif kind == 'Condition':
            for i,c in enumerate(r.get('code',{}).get('coding',[])):
                candidate = c.get('code')=='59621000' and c.get('system')==SNOMED
                tables['diagnoses'].append(dict(person_id=subject(r),condition_id=r['id'],coding_index=str(i),
                    original_code=c.get('code',''),original_system=c.get('system',''),start=r.get('onsetDateTime',''),
                    end=r.get('abatementDateTime',''),recorded=r.get('recordedDate') or r.get('onsetDateTime',''),
                    clinical_status=compact(r.get('clinicalStatus',{})),kcd_candidate_code='I109' if candidate else '',
                    kcd_candidate_edition_context='KCD-8' if candidate else '',
                    kcd_candidate_status='unverified' if candidate else 'not_assigned',
                    kcd_candidate_usage='annotation_only',derived_from='A'))
        elif kind == 'Encounter':
            cls = r.get('class',{}); period = r.get('period',{})
            tables['visits'].append(dict(person_id=subject(r),encounter_id=r['id'],class_code=cls.get('code',''),
                class_system=cls.get('system',''),start=period.get('start',''),end=period.get('end',''),
                recorded=period.get('start',''),visit_kind={'AMB':'OP','IMP':'IP','EMER':'ER','HH':'HH','VR':'VR'}.get(cls.get('code'),'UNMAPPED')
                if cls.get('system')==ACT else 'UNMAPPED',derived_from='A'))
        elif kind == 'Observation':
            pairs = [{'code':c.get('code',''),'system':c.get('system','')} for c in r.get('code',{}).get('coding',[])]
            panel = next((c for c in pairs if c['code']=='85354-9'),None)
            if panel is None:
                continue
            row = dict(person_id=subject(r),observation_id=r['id'],effective=r.get('effectiveDateTime',''),
                       status=r.get('status',''),panel_code=panel['code'],panel_system=panel['system'],
                       panel_codings=compact(pairs),derived_from='A')
            for prefix in ('systolic','diastolic'):
                row.update({prefix+'_'+field:'' for field in ('code','system','original_value','unit_code','unit_system','unit_display')})
            for component in r.get('component',[]):
                for code in component.get('code',{}).get('coding',[]):
                    prefix = {'8480-6':'systolic','8462-4':'diastolic'}.get(code.get('code'))
                    if prefix:
                        if row[prefix+'_code']:
                            raise ValueError('Duplicate BP component')
                        quantity = component.get('valueQuantity',{})
                        row.update({prefix+'_code':code['code'],prefix+'_system':code.get('system',''),
                            prefix+'_original_value':numeric(quantity.get('value')),
                            prefix+'_unit_code':quantity.get('code',''),prefix+'_unit_system':quantity.get('system',''),
                            prefix+'_unit_display':quantity.get('unit','')})
            values = [row[p+'_original_value'] for p in ('systolic','diastolic')]
            row['bp_text'] = '/'.join(values)
            row['format_status'] = 'decimal_extension' if any(v and Decimal(v)!=Decimal(v).to_integral_value() for v in values) else 'integer_pair'
            tables['bp_details'].append(row)
    validate_tables(tables)
    return tables


def validate_tables(tables):
    people = {r['person_id'] for r in tables['persons']}
    for name,rows in tables.items():
        keys = [tuple(r[k] for k in KEYS[name]) for r in rows]
        if len(keys)!=len(set(keys)):
            raise ValueError('Duplicate A-prime input key: '+name)
        for row in rows:
            if row['derived_from']!='A' or row['person_id'] not in people:
                raise ValueError('Invalid A-prime lineage/person reference')
            if name=='persons':
                calendar_day(row['birth_date'])
                if row['measurement_year']!='2025':
                    raise ValueError('Unexpected measurement year')
            if name in ('diagnoses','visits'):
                if not row['start'] or calendar_day(row['recorded'])!=calendar_day(row['start']):
                    raise ValueError('ADR0006 clinical/recorded day mismatch')
                calendar_day(row['end'])
            if name=='visits':
                expected_kind={'AMB':'OP','IMP':'IP','EMER':'ER','HH':'HH','VR':'VR'}.get(row['class_code'],'UNMAPPED') if row['class_system']==ACT else 'UNMAPPED'
                if row['visit_kind']!=expected_kind:raise ValueError('Visit kind/original namespace disagreement')
            if name=='diagnoses':
                if row['kcd_candidate_usage']!='annotation_only' or row['kcd_candidate_status'] not in ('unverified','not_assigned'):
                    raise ValueError('KCD candidate must stay unverified annotation')
            if name=='bp_details':
                if not calendar_day(row['effective']):
                    raise ValueError('Missing BP day')
                parsed = parse_bp(row['bp_text'])
                expected_format='decimal_extension' if any(value and Decimal(value)!=Decimal(value).to_integral_value() for value in parsed) else 'integer_pair'
                if row['format_status']!=expected_format:raise ValueError('BP format status disagreement')
                for index,prefix in enumerate(('systolic','diastolic')):
                    if parsed[index]!=row[prefix+'_original_value']:
                        raise ValueError('BP text/original component disagreement')
                    if not row[prefix+'_code'] and parsed[index]:
                        raise ValueError('BP value without a source component')
                pairs = json.loads(row['panel_codings'])
                first = next((p for p in pairs if p.get('code')=='85354-9'),None)
                if first!={'code':row['panel_code'],'system':row['panel_system']}:
                    raise ValueError('Original panel namespace disagreement')


def encode_tables(tables):
    result = {}
    for name,fields in FIELDS.items():
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output,fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(tables[name],key=lambda row:tuple(row[k] for k in KEYS[name])))
        result[name+'.csv'] = output.getvalue().encode('utf-8')
    return result


def export_resources(resources, output, source_files=()):
    output = writable_path(output)
    tables = transform(resources)
    contents = encode_tables(tables)
    manifest = {'contract':'a-prime-input-1','hospital':'A_PRIME','derived_from':'A','independent_population':False,
                'clinical_route':'preserved_source_clinical','kcd_mapping':'unverified',
                'source_files':sorted(source_files,key=lambda r:r['sha256']),
                'files':{name:{'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)} for name,body in contents.items()},
                'rows':{name:len(rows) for name,rows in tables.items()}}
    contents['manifest.json']=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    ensure_space(sum(map(len,contents.values()))+1_000_000)
    if output.exists():
        if {p.name for p in output.iterdir()}!=set(contents) or any((output/name).is_symlink() or (output/name).read_bytes()!=body for name,body in contents.items()):
            raise ValueError('Existing A-prime input differs; refusing overwrite')
        return {'reused':True,'rows':manifest['rows'],'bytes':sum(map(len,contents.values()))}
    output.parent.mkdir(parents=True,exist_ok=True)
    scratch = CACHE/'a-prime';scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='export-',dir=scratch) as temp:
        stage = Path(temp)/'dataset';stage.mkdir()
        for name,body in contents.items():(stage/name).write_bytes(body)
        stage.rename(output)
    return {'reused':False,'rows':manifest['rows'],'bytes':sum(map(len,contents.values()))}


def generate(source=ORIGINAL, output=DEFAULT):
    resources,files = [],[]
    for path in sorted(Path(source).glob('*.json')):
        body=path.read_bytes()
        files.append({'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)})
        bundle=json.loads(body,parse_float=Decimal)
        resources.extend(entry['resource'] for entry in bundle.get('entry',[]))
    if not resources:
        raise ValueError('No original FHIR input')
    return export_resources(resources,output,files)


def read_input(directory=DEFAULT):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT):
        raise ValueError('A-prime input must stay in this project')
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest.get('contract')!='a-prime-input-1' or manifest.get('hospital')!='A_PRIME' or manifest.get('derived_from')!='A' or manifest.get('independent_population') is not False:
        raise ValueError('Invalid A-prime input contract/lineage')
    if manifest.get('clinical_route')!='preserved_source_clinical' or manifest.get('kcd_mapping')!='unverified':
        raise ValueError('Unsupported A-prime/KCD route')
    tables={}
    if set(manifest['files'])!={name+'.csv' for name in FIELDS}:
        raise ValueError('A-prime file manifest mismatch')
    for name,fields in FIELDS.items():
        path=directory/(name+'.csv');body=path.read_bytes()
        if path.is_symlink() or hashlib.sha256(body).hexdigest()!=manifest['files'][path.name]['sha256'] or len(body)!=manifest['files'][path.name]['bytes']:
            raise ValueError('A-prime input hash mismatch: '+name)
        reader=csv.DictReader(io.StringIO(body.decode('utf-8'),newline=''))
        if reader.fieldnames!=list(fields):raise ValueError('A-prime input columns mismatch')
        rows=list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError('A-prime CSV width mismatch')
        if len(rows)!=manifest['rows'][name]:raise ValueError('A-prime row count mismatch')
        tables[name]=rows
    validate_tables(tables)
    return tables


def projection(tables):
    """Actual generated input (or staging columns) only; never FHIR or expected data."""
    for r in tables['persons']:
        yield {'kind':'person','source_row_key':r['person_id'],'facts':{k:r[k] for k in
            ('person_id','birth_date','gender','deceased_datetime','deceased_boolean','measurement_year')}}
    for r in tables['visits']:
        yield {'kind':'visit','source_row_key':r['encounter_id'],'facts':{k:r[k] for k in
            ('person_id','class_code','class_system','start','end','recorded')}}
    for r in tables['diagnoses']:
        facts={k:r[k] for k in ('person_id','condition_id','coding_index','start','end','recorded','clinical_status')}
        facts.update(code=r['original_code'],system=r['original_system'])
        yield {'kind':'diagnosis','source_row_key':r['condition_id']+':'+r['coding_index'],'facts':facts}
    for r in tables['bp_details']:
        parsed=parse_bp(r['bp_text'])
        for index,prefix in enumerate(('systolic','diastolic')):
            if not r[prefix+'_code']:continue
            facts={k:r[k] for k in ('person_id','observation_id','effective','status','panel_code','panel_system','panel_codings')}
            facts.update(code=r[prefix+'_code'],system=r[prefix+'_system'],value=parsed[index],
                unit_code=r[prefix+'_unit_code'],unit_system=r[prefix+'_unit_system'],unit_display=r[prefix+'_unit_display'])
            yield {'kind':'bp_component','source_row_key':r['observation_id']+':'+r[prefix+'_code'],'facts':facts}
