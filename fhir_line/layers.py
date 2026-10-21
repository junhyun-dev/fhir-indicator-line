"""L2/D1-D7 boundary: validate dbt lineage before the verification ladder."""
import json
import re
import subprocess
from pathlib import Path

from .runtime import ARTIFACTS, ROOT, environment

ALLOWED = {'staging':{'source','seed'},          # L3 병원마다(staging/hospital_a · hospital_b): 그 병원의 모양만 앎
           'common':{'staging','seed'},           # 공통 표(M2 요청 04): 병원 줄을 이어 붙이고 코드 매핑 표로 표준 뜻에 · M3 요청 07에서 지움
           'omop':{'staging','seed'},             # M3 결정 0004: OMOP CDM 5.4 표 + person_ext · 표준 번호는 seed에서
           'intermediate':{'common','omop','seed'}, 'marts':{'intermediate','common','omop','seed'},
           'reports':{'marts'}}  # L6 reports: summaries read only finished marts (request 03 review R1)


def layer(node):
    parts = Path(node.get('original_file_path','')).parts
    return parts[1] if len(parts)>2 and parts[0]=='models' else None


def direct_relations(sql):
    # Remove comments, then substitute only literal, declared dbt dependency calls.
    sql = re.sub(r"'(?:''|[^'])*'|/\*.*?\*/|--[^\n]*|\{#.*?#\}",
                 lambda m:m.group() if m.group().startswith("'") else ' ',sql,flags=re.S)
    sql = re.sub(r"\{\{\s*(?:ref|source)\s*\(\s*['\"][^'\"]+['\"](?:\s*,\s*['\"][^'\"]+['\"])?\s*\)\s*\}\}",
                 '__declared_dbt_input__', sql, flags=re.I)
    sql = re.sub(r"'(?:''|[^'])*'", "''", sql)
    ctes = {x.lower() for x in re.findall(r'(?:\bwith\s+|,\s*)([A-Za-z_]\w*)\s+as\s*\(',sql,re.I)}
    allowed = ctes | {'__declared_dbt_input__','lateral','unnest','json_each','json_tree','range','generate_series'}
    errors = []
    # Reserve the physical raw relation name, including comma joins and quoted names.
    if re.search(r'\braw_resources\b',sql,re.I):
        errors.append('raw_resources')
    for match in re.finditer(r'\b(?:from|join)\s+([\w."`]+|\{\{)', sql, re.I):
        relation = match.group(1).strip('"`').lower()
        if relation not in allowed:
            errors.append(relation)
    return errors


def validate(manifest):
    nodes = manifest.get('nodes', {})
    sources = manifest.get('sources', {})
    issues = []
    models = [n for n in nodes.values() if n.get('resource_type')=='model']
    for node in models:
        own = layer(node)
        name = node.get('name','<unnamed>')
        if own not in ALLOWED:
            issues.append(f'{name}: model must be in staging/common/omop/intermediate/marts/reports')
            continue
        for dep_id in node.get('depends_on',{}).get('nodes',[]):
            dep = nodes.get(dep_id) or sources.get(dep_id)
            if dep is None:
                issues.append(f'{name}: unresolved dependency')
                continue
            dep_layer = dep['resource_type'] if dep.get('resource_type') in ('source','seed') else layer(dep)
            if dep_layer not in ALLOWED[own]:
                issues.append(f'{name}: {own} cannot read {dep_layer}')
            if own != 'staging' and dep.get('name')=='raw_resources':
                issues.append(f'{name}: raw_resources is forbidden above staging')
        for relation in direct_relations(node.get('raw_code','')):
            issues.append(f'{name}: undeclared direct relation {relation}; use source/ref')
    return {'status':'통과' if not issues else '실패', 'models_checked':len(models), 'issues':issues}


def check():
    log = ARTIFACTS/'logs/layers-dbt-parse.log'
    log.parent.mkdir(parents=True,exist_ok=True)
    cmd = [str(ROOT/'.venv/bin/dbt'),'parse','--no-partial-parse']
    with log.open('w') as output:
        result = subprocess.run(cmd,cwd=ROOT,env=environment(),stdout=output,stderr=subprocess.STDOUT)
    if result.returncode:
        result = {'status':'실패','models_checked':0,'issues':['dbt parse failed; see local parse log']}
    else:
        manifest = json.loads((ARTIFACTS/'dbt-target/manifest.json').read_text())
        result = validate(manifest)
    (ARTIFACTS/'summaries').mkdir(parents=True,exist_ok=True)
    (ARTIFACTS/'summaries/layer-check.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    return result
