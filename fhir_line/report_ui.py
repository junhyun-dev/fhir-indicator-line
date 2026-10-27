"""D1-D7 / ADR0010,0011,0013: read-only snapshot export; no patient IDs in browser files."""
from __future__ import annotations
import argparse,collections,csv,datetime as dt,fcntl,hashlib,io,json,math,os,re,secrets,subprocess
from pathlib import Path
from decimal import Decimal
import duckdb,jinja2,yaml
from . import definition,ladder
from .runtime import ROOT,DATABASE,ARTIFACTS,ensure_space

BASE=ROOT/'.local/FHIR-LINE-V1-1027'
EXPECTED_V1=Path(os.environ.get('FHIR_V1_EXPECTED_ROOT', str(ROOT/'answer_key_lead/v1')))
STAGES=(('expected_lock','기대 결과의 해시와 읽기 전용 상태'),('a_prime_lock','A′ 고정 기대 결과'),
        ('frozen_layers','바뀌면 안 되는 층'),('tests','테스트'),('dbt_quality','dbt 빌드와 데이터 품질 검사'),('ladder','확인 사다리'))
REASONS=set(ladder.PUBLIC_REASONS)
CODE_LABELS={'omr_systolic':'OMR 혈압','omr_diastolic':'OMR 혈압','8480-6':'FHIR Observation','8462-4':'FHIR Observation','220179':'MIMIC 중환자실 측정','220180':'MIMIC 중환자실 측정'}

class ReportError(ValueError):pass

def reviewed_expected(folder=EXPECTED_V1):
    folder=Path(folder);readme=(folder/'README.md').read_text()
    match=re.search(r'^## 리드 검수[^\n]*\n(.*?)(?=^## |\Z)',readme,re.M|re.S)
    if not match or not re.search(r'^검수:.*Claude 리드.*\*\*받아들임\.\*\*',match[1],re.M):raise ReportError('LEAD_REVIEW_REQUIRED')
    expected_files={'README.md','notification.md','code_set_manifest_expected.json','screens_expected.json'}
    verified={};hashes={}
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not m or m[2] not in expected_files or m[2] in hashes:raise ReportError('EXPECTED_MANIFEST_INVALID')
        body=(folder/m[2]).read_bytes()
        if definition.digest(body)!=m[1]:raise ReportError('EXPECTED_HASH_MISMATCH')
        hashes[m[2]]=m[1]
        if m[2].endswith('.json'):verified[m[2]]=json.loads(body)['expected']
    if set(hashes)!=expected_files:raise ReportError('EXPECTED_MANIFEST_INVALID')
    return verified,hashes

def cell_preflight():
    if os.environ.get('FHIR_SKIP_EXTERNAL_CELL_CASES')=='1':raise ReportError('EXTERNAL_CASES_REQUIRED')
    file=Path(os.environ.get('FHIR_CELL_DIFF_CASES',str(ROOT/'answer_key_lead/cell_diff/cases.json')))
    body=file.read_bytes();hashes={}
    for line in file.with_name('SHA256SUMS').read_text().splitlines():
        checksum,name=line.split(maxsplit=1);hashes[name.lstrip('*')]=checksum
    digest=definition.digest(body)
    if hashes.get(file.name)!=digest or {r['case'] for r in json.loads(body)['cases']}!=set(range(5)):raise ReportError('CELL_CASE_HASH_MISMATCH')
    return {'external_cell_cases_required':True,'skip_means_success':False,'external_cases_sha256':digest,'scope':'외부 다섯 사례 파일의 존재와 해시 확인. 실행은 전체 검사와 별도예요.'}

def guarded(path,base=BASE):
    path=Path(path).absolute();base=Path(base).absolute()
    if not path.is_relative_to(base) or not path.resolve().is_relative_to(base):raise ReportError('UNSAFE_OUTPUT')
    for p in (path,*path.parents):
        if p==ROOT.parent:break
        if p.is_symlink() or (p.is_file() and p.stat().st_nlink!=1):raise ReportError('UNSAFE_OUTPUT')
    return path

def json_write(path,value):
    path=guarded(path);temp=guarded(path.with_name(path.name+'.'+secrets.token_hex(4)+'.tmp'))
    with temp.open('xb') as f:f.write(definition.canonical(value))
    os.replace(temp,path)

def rows(con,sql,args=()):
    cur=con.execute(sql,args);names=[x[0] for x in cur.description]
    return [dict(zip(names,r)) for r in cur.fetchall()]

def value(v):
    if v is None:return None
    if isinstance(v,(dt.date,dt.datetime)):return v.isoformat()
    if isinstance(v,str):return v
    n=float(v)
    if not math.isfinite(n):raise ReportError('NONFINITE_NUMBER')
    return int(n) if n.is_integer() else n

def numeric_value(v):
    if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float,Decimal))):raise ReportError('NUMBER_CONTRACT')
    return value(v)

def stage_list():return [{'stage_id':i,'label':n,'status':'미실행'} for i,n in STAGES]

def verify_stage(stage,work):
    try:work();stage['status']='통과'
    except Exception:stage['status']='실패' # Never export free-form exceptions or file paths.

def expected_lock():
    folder=ROOT/'expected'
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        h,p=line.split(maxsplit=1);file=folder/p.lstrip('*')
        if not file.resolve().is_relative_to(folder) or definition.digest(file.read_bytes())!=h:raise ReportError('EXPECTED_LOCK')
    if any(p.stat().st_mode&0o200 for p in [folder,*folder.rglob('*')]):raise ReportError('EXPECTED_LOCK')

def a_prime_lock():
    from .a_prime_checks import frozen_checker
    if not frozen_checker().verify_lock(ROOT/'expected_a_prime').get('ok'):raise ReportError('A_PRIME_LOCK')

def frozen_layers():
    cmd=['git','diff','--quiet','3e99c30','--','models/intermediate','models/marts','models/reports','seeds/indicator_concepts.csv','seeds/as_of_labels.csv']
    if subprocess.run(cmd,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:raise ReportError('FROZEN_LAYERS')

def quality(con):
    schema=yaml.safe_load((ROOT/'models/omop/schema.yml').read_text())
    text=(ROOT/'macros/test_dqd.sql').read_text()
    text=re.sub(r'{%\s*test\s+(\w+)\s*\(',r'{% macro test_\1(',text)
    text=re.sub(r'{%\s*endtest\s*%}','{% endmacro %}',text)
    module=jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(text).module
    output=[]
    for section in ('models','seeds'):
        for model in schema.get(section,[]):
            for item in model.get('data_tests',[]):
                if not isinstance(item,dict):continue
                for generic,spec in item.items():
                    if not generic.startswith('dqd_'):continue
                    args=dict(spec.get('arguments',{}))
                    for k,v in args.items():
                        if isinstance(v,str) and (m:=re.fullmatch(r"ref\('([^']+)'\)",v)):args[k]=m[1]
                    sql=str(getattr(module,'test_'+generic)(model=model['name'],**args))
                    found=rows(con,sql);warn=spec.get('config',{}).get('severity')=='warn'
                    allowed=('hospital','measurement_concept_id','violation_count','denominator','violation_percent','not_carried')
                    safe=[{k:(r[k] if k=='hospital' else numeric_value(r[k])) for k in allowed if k in r and (k!='hospital' or r[k] in ('A','B','A_PRIME'))} for r in found]
                    output.append({'check':spec['name'],'status':('warn' if warn else 'error') if found else 'pass','result_rows':len(found),'details':safe,'kind':'미매핑 경고' if warn else 'DQD 참고 검사'})
    return output

def history(folder=ARTIFACTS/'runs'):
    file=Path(folder)/'index.csv'
    if not file.exists():return []
    with file.open(newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=list(ladder.INDEX_FIELDS):raise ReportError('INDEX_CONTRACT')
        out=[]
        for r in reader:
            if None in r or any(x is None for x in r.values()):raise ReportError('INDEX_CONTRACT')
            if r['status'] not in ('통과','실패') or not re.fullmatch(r'[0-9a-f]{40}',r['product_commit']):raise ReportError('INDEX_CONTRACT')
            try:dt.datetime.fromisoformat(r['run_at'].replace('Z','+00:00'))
            except ValueError:raise ReportError('INDEX_CONTRACT') from None
            if any(int(r[k])<0 for k in ladder.DIFFERENCE_KINDS):raise ReportError('INDEX_CONTRACT')
            out.append({k:r[k] for k in ('run_at','product_commit','status')}|{k:int(r[k]) for k in ladder.DIFFERENCE_KINDS})
    return out[-20:]

def saved_dbt_summary(file=ARTIFACTS/'dbt-target/run_results.json'):
    if not file.exists():return {'status':'미확인','bound_to_current_snapshot':False}
    raw=json.loads(file.read_text());counts={k:0 for k in ('pass','warn','error','skipped')}
    date=raw.get('metadata',{}).get('generated_at')
    if date is not None:dt.datetime.fromisoformat(date.replace('Z','+00:00'))
    mapping={'success':'pass','pass':'pass','warn':'warn','error':'error','fail':'error','skipped':'skipped'}
    for result in raw.get('results',[]):
        status=mapping.get(result.get('status'))
        if status is None:raise ReportError('DBT_RESULT_CONTRACT')
        counts[status]+=1
    return {'recorded_at':date,'counts':counts,'status':'미확인','bound_to_current_snapshot':False}

def previous_success(base):
    pointer=base/'latest-success.json'
    if not pointer.exists():return None
    saved=json.loads(pointer.read_text());run_id=saved.get('run_id','')
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{8}',run_id) or saved.get('status')!='통과':raise ReportError('ARTIFACT_BINDING')
    manifest=json.loads(guarded(base/run_id/'run-manifest.json').read_text())
    if manifest!=saved or not saved.get('artifact_hashes'):raise ReportError('ARTIFACT_BINDING')
    for name,digest in saved['artifact_hashes'].items():
        if name not in {'S01.html','S02.html','S03.html','S04.html','S05.html','data.json','report.js','report.css'}:raise ReportError('ARTIFACT_BINDING')
        if definition.digest(guarded(base/run_id/name).read_bytes())!=digest:raise ReportError('ARTIFACT_BINDING')
    payload=json.loads(guarded(base/run_id/'data.json').read_text())
    validate_bindings(payload)
    if payload['run'].get('database_sha256')!=saved.get('database_sha256') or payload['run'].get('run_id')!=run_id:raise ReportError('ARTIFACT_BINDING')
    return saved['finished_at']

def safe_person(row,number,comparison):
    if row['hospital'] not in ('A','B') or row['as_of_label'] not in ('sep30','dec31') or row['reason'] not in REASONS:raise ReportError('PERSON_CONTRACT')
    for field in ('systolic','diastolic','controlled'):numeric_value(row[field])
    out={k:value(row[k]) for k in ('hospital','as_of_label','as_of','last_bp_date','systolic','diastolic','controlled','reason')}
    if out['controlled'] not in (0,1):raise ReportError('PERSON_CONTRACT')
    for date in ('as_of','last_bp_date'):
        if out[date] is not None:dt.date.fromisoformat(out[date])
    return out|{'patient_number':number,'patient_label':f'환자 {number}','control_label':'조절됨' if out['controlled'] else '조절 안 됨','comparison_label':comparison}

def trace_rows(con,row):
    """Candidate component rows; exact source link is private, MIN selection remains unverified."""
    if row['last_bp_date'] is None:return []
    selected=rows(con,'''SELECT m.measurement_source_value,m.measurement_date,m.measurement_concept_id,
        m.value_as_number,m.unit_concept_id,m.unit_source_value,link.source_row_key
        FROM measurement m JOIN omop_people p ON p.person_id=m.person_id
        LEFT JOIN omop_source_link link ON link.omop_table='measurement' AND link.omop_id=m.measurement_id AND link.hospital=p.hospital
        WHERE p.hospital=? AND p.source_person_id=? AND m.measurement_date=? AND m.unit_concept_id=8876
          AND ((m.measurement_concept_id=3004249 AND m.value_as_number=?) OR (m.measurement_concept_id=3012888 AND m.value_as_number=?))
        ORDER BY m.measurement_source_value,m.measurement_id''',[row['hospital'],row['person_id'],row['last_bp_date'],row['systolic'],row['diastolic']])
    result=[]
    for x in selected:
        if x['measurement_source_value'] not in CODE_LABELS:raise ReportError('SOURCE_CODE_CONTRACT')
        result.append({k:(numeric_value(x[k]) if k in ('measurement_concept_id','value_as_number','unit_concept_id') else value(x[k])) for k in ('measurement_source_value','measurement_date','measurement_concept_id','value_as_number','unit_concept_id')}|{'hospital':row['hospital'],'unit_display':'mm[Hg]','source_link_status':'미확인','source_type':CODE_LABELS[x['measurement_source_value']],'original_unit_written':x['unit_source_value'] if x['unit_source_value'] in (None,'mm[Hg]','mmHg') else None})
    return result

def write_differences(path,report,run_id):
    fields=('run_at','table','hospital','as_of_label','row_key','column','expected','actual','kind')
    with guarded(path).open('x',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader()
        for kind,label in zip(ladder.DIFFERENCE_KINDS,('다른 칸','빠진 행','남는 행')):
            for item in report[kind]:
                w.writerow({'run_at':run_id,'table':item['table'],'hospital':item['row'].get('hospital',''),'as_of_label':item['row'].get('as_of_label',''),'row_key':json.dumps(item['row'],ensure_ascii=False),'column':item.get('column',''),'expected':item.get('expected',''),'actual':item.get('actual',''),'kind':label})

def read_differences(path,run_id,aliases,public=False):
    result=[]
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            if r['run_at']!=run_id or r['kind'] not in ('다른 칸','빠진 행','남는 행'):raise ReportError('DIFF_BINDING')
            if r['hospital'] not in ('A','B') or r['as_of_label'] not in ('sep30','dec31') or r['table'] not in ladder.ROW_KEYS:raise ReportError('DIFF_CONTRACT')
            if r['column'] and r['column'] not in ladder.TYPE_CONTRACT[r['table']]:raise ReportError('DIFF_CONTRACT')
            numeric=r['column'] in ('numerator','denominator','rate','systolic','diastolic','controlled')
            clean={}
            for key in ('expected','actual'):
                x=ladder.public_cell(r['column'],r[key]) if r['column'] else None
                clean[key]=value(float(x)) if numeric and x not in (None,'','비공개') else x
            key=json.loads(r['row_key']);number=None if public or r['kind']!='다른 칸' or r['table']!='fct_bp_person' else aliases.get((r['hospital'],key.get('person_id')))
            result.append({k:r[k] for k in ('kind','hospital','as_of_label','table','column')}|clean|{'column_display':{'numerator':'분자','denominator':'분모','rate':'조절률'}.get(r['column'],r['column']),'patient_number':number,'patient_detail_link':number is not None})
    return result

def snapshot(con,run_id,private,meta,public=False):
    person=ladder.compare_expected(con,ROOT/'expected');summary=ladder.compare_summary(con,ROOT/'expected');types=ladder.check_types(con)
    comparison=ladder.combine(사람별=person,요약=summary,자료형=types)
    differences={k:person.get(k,[])+summary.get(k,[]) for k in ladder.DIFFERENCE_KINDS}
    raw={'status':comparison['status'],**differences};write_differences(private/'cell-diff.csv',raw,run_id)
    facts=rows(con,"SELECT hospital,as_of_label,person_id,as_of,last_bp_date,systolic,diastolic,controlled,reason FROM fct_bp_person WHERE hospital IN ('A','B') ORDER BY hospital,person_id,as_of_label")
    unique=collections.defaultdict(set)
    for f in facts:unique[f['hospital']].add(f['person_id'])
    aliases={(h,p):i for h,ps in unique.items() for i,p in enumerate(sorted(ps),1)}
    changed_people={(x['row'].get('hospital'),x['row'].get('as_of_label'),x['row'].get('person_id')) for kind in ladder.DIFFERENCE_KINDS for x in person.get(kind,[])}
    changed_summary={(x['row'].get('hospital'),x['row'].get('as_of_label')) for kind in ladder.DIFFERENCE_KINDS for x in summary.get(kind,[])}
    payload={'summaries':[],'checks':{},'errors':read_differences(private/'cell-diff.csv',run_id,aliases,public)}
    for r in rows(con,"SELECT hospital,as_of_label,denominator,numerator,rate FROM bp_summary WHERE hospital IN ('A','B') ORDER BY hospital,as_of_label DESC"):
        if r['as_of_label'] not in ('sep30','dec31'):raise ReportError('SUMMARY_CONTRACT')
        rate=numeric_value(r['rate']);out={k:(numeric_value(r[k]) if k in ('denominator','numerator','rate') else r[k]) for k in ('hospital','as_of_label','denominator','numerator','rate')}
        dates={value(f['as_of']) for f in facts if f['hospital']==r['hospital'] and f['as_of_label']==r['as_of_label']}
        display=(next(iter(dates)) if len(dates)==1 else '미확인') if r['hospital']=='A' else '환자별 기준 연도의 '+('9월 말' if r['as_of_label']=='sep30' else '연말')
        payload['summaries'].append(out|meta|{'as_of_display':display,'percent_display':('대상 없음' if out['denominator']==0 else '미확인') if rate is None else f'{rate*100:.2f}%','uncontrolled_count':out['denominator']-out['numerator'],'comparison_label':'기대 결과와 다름' if (r['hospital'],r['as_of_label']) in changed_summary else '기대 결과와 같음'})
    if not public:
        payload['people']=[];payload['traces']=[]
        for row in facts:
            item=safe_person(row,aliases[(row['hospital'],row['person_id'])],'기대 결과와 다름' if (row['hospital'],row['as_of_label'],row['person_id']) in changed_people else '기대 결과와 같음')
            candidates=trace_rows(con,row);types={r['source_type'] for r in candidates}
            payload['people'].append(item);payload['traces'].append({'patient':item,'standard_rows':candidates,'connection_status':'원천 연결 미확인','selected_source_type':next(iter(types)) if len(types)==1 else '원천 종류 미확인'})
    checks=payload['checks'];checks.update(status=comparison['status'],scope='④ A/B 사람별·요약·자료형 및 같은 스냅샷의 품질 SELECT',comparison=ladder.public_report(comparison),**{k:len(differences[k]) for k in ladder.DIFFERENCE_KINDS})
    checks['quality']=quality(con)
    if any(x['status']=='error' for x in checks['quality']):checks['status']='실패'
    checks['index_display']='runs/index.csv';checks['current_index_status']='이번 실행 이력 없음';checks['historical_row_confirms_current_run']=False
    checks['saved_dbt']=saved_dbt_summary();checks['history']=history();checks['last_success']=next((r['run_at'] for r in reversed(checks['history']) if r['status']=='통과'),None)
    # IDs stay in private CSV only. No names, source keys, raw JSON, source files or fallback IDs.
    private_ids={str(f['person_id']) for f in facts}
    assert_private_free(payload,private_ids)
    return payload,private_ids

def validate_bindings(payload):
    run=payload['run']
    manifest,h=definition.context()
    expected=definition.metadata(manifest,h,run['run_id'])
    for actual in [run,*payload['summaries']]:
        if any(actual.get(k)!=v for k,v in expected.items()):raise ReportError('MIXED_DEFINITION')

def assert_private_free(payload,private_ids=()):
    forbidden={'person_id','person_source_value','subject_id','source_row_key','reference','name','age','source_filename','source_path','raw_json','filename','omop_person_id'}
    def walk(x):
        if isinstance(x,dict):
            if forbidden.intersection(x):raise ReportError('PRIVATE_FIELD')
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(payload);text=json.dumps(payload,ensure_ascii=False,default=str)
    if re.search(r'(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',text):raise ReportError('PRIVATE_IDENTIFIER')
    for ident in private_ids:
        # Reject full IDs, prefixes, and patient-derived hash aliases, even in arbitrary strings.
        if len(ident)>=8 and any(s in text for s in (ident,ident[:8],hashlib.sha256(ident.encode()).hexdigest())):raise ReportError('PRIVATE_IDENTIFIER')

def render(database=DATABASE,public=False,output_root=None):
    base=guarded(output_root or BASE/'ui-runs'/('public' if public else 'local'))
    for path in (base,base/'latest.json',base/'latest-success.json',base/'run.lock',BASE/'private-runs',BASE/'tmp'):guarded(path)
    base.mkdir(parents=True,exist_ok=True);(BASE/'private-runs').mkdir(parents=True,exist_ok=True);(BASE/'tmp').mkdir(parents=True,exist_ok=True)
    run_id=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+secrets.token_hex(4)
    state={'run_id':run_id,'status':'실패','started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'stages':stage_list(),'validation_scope':'읽기 전용 조회의 검증. 전체 check.sh 실행과 별도예요.'}
    stage={r['stage_id']:r for r in state['stages']}
    with guarded(base/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        folder=guarded(base/run_id);folder.mkdir();private=guarded(BASE/'private-runs'/run_id);private.mkdir()
        json_write(base/'latest.json',state);json_write(folder/'run-manifest.json',state)
        try:
            _,contracts=reviewed_expected();state['contract_hashes']=contracts
            state['preflight']=cell_preflight()
            state['previous_success_at']=previous_success(base)
            manifest,digest=definition.context();meta=definition.metadata(manifest,digest,run_id)
            state.update(meta);state['product_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();state['product_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True))
            state['definition_inputs']=manifest['files'];verify_stage(stage['expected_lock'],expected_lock);verify_stage(stage['a_prime_lock'],a_prime_lock);verify_stage(stage['frozen_layers'],frozen_layers)
            path=Path(database).absolute()
            if not path.resolve().is_relative_to(ROOT) or path.is_symlink() or path.suffix!='.duckdb' or not path.exists():raise ReportError('UNSAFE_DATABASE')
            before=definition.digest(path.read_bytes());state['database_sha256']=before
            with duckdb.connect(str(path),read_only=True,config={'memory_limit':'2GB','threads':2,'temp_directory':str(BASE/'tmp'),'autoinstall_known_extensions':False,'autoload_known_extensions':False}) as con:
                con.execute('BEGIN TRANSACTION')
                payload,ids=snapshot(con,run_id,private,meta,public)
                con.execute('COMMIT')
            if definition.digest(path.read_bytes())!=before:raise ReportError('DATABASE_CHANGED')
            stage['ladder'].update(status=payload['checks']['status'],scope=payload['checks']['scope'])
            stage['dbt_quality']['note']='dbt 빌드는 이번 조회 명령에서 미실행. 품질 SELECT는 같은 DB 스냅샷에서 실행했어요.'
            stage['tests']['note']='이번 조회 명령에서 미실행. 과거 성공을 이번 성공으로 사용하지 않아요.'
            state['status']='실패' if any(x['status']=='실패' for x in state['stages']) else payload['checks']['status']
            state['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();state['last_verified_at']=state['finished_at']
            state['index_binding']='이번 실행 이력 없음';payload['run']=dict(state)
            validate_bindings(payload)
            if reviewed_expected()[1]!=contracts:raise ReportError('EXPECTED_CHANGED')
            assert_private_free(payload,ids)
            from .ui import write_site
            write_site(folder,payload,public,guarded)
            for f in folder.iterdir():
                if f.suffix in ('.html','.json','.js','.css') and f.name!='run-manifest.json':assert_private_free({'text':f.read_text()},ids)
            state['artifact_hashes']={f.name:definition.digest(f.read_bytes()) for f in folder.iterdir() if f.is_file() and f.name!='run-manifest.json'}
            ensure_space();json_write(folder/'run-manifest.json',state);json_write(base/'latest.json',state)
            if state['status']=='통과':json_write(base/'latest-success.json',state)
            return state,folder
        except Exception as exc:
            state.update(status='실패',finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),error=type(exc).__name__)
            if isinstance(exc,definition.DefinitionError):
                state['definition_status']='정의 버전 미고정'
                for key in ('definition_version','code_set_version','definition_manifest_sha256'):state.pop(key,None)
            json_write(folder/'run-manifest.json',state);json_write(base/'latest.json',state)
            return state,folder

def main(argv=None):
    parser=argparse.ArgumentParser(description='S01~S05: local read-only DB snapshot and verification report')
    parser.add_argument('--db',type=Path,default=DATABASE);parser.add_argument('--public',action='store_true');args=parser.parse_args(argv)
    try:state,folder=render(args.db,args.public)
    except Exception:print('실패: 출력 경로나 실행 잠금을 확인하세요.');return 1
    print(json.dumps({'status':state['status'],'run_id':state['run_id'],'entry':str(folder/'S01.html') if (folder/'S01.html').exists() else None,'scope':'읽기 전용 조회 검증 · 전체 check.sh와 별도'},ensure_ascii=False))
    return 0 if state['status']=='통과' else 1
