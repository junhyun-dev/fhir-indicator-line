/* D1-D7 / ADR0010,0011: show stored values; no clinical calculation or raw identifiers. */
'use strict';
const D=JSON.parse(document.getElementById('payload').textContent),app=document.getElementById('app');
const E=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text===null?'—':String(text);if(cls)n.className=cls;return n;};
const add=(tag,text,cls,parent=app)=>{const n=E(tag,text,cls);parent.append(n);return n;};
const table=(headers,data,parent=app)=>{const t=E('table'),head=E('thead'),tr=E('tr');headers.forEach(x=>tr.append(E('th',x)));head.append(tr);t.append(head);const b=E('tbody');for(const row of data){const r=E('tr');for(const v of row){const td=E('td');td.append(v instanceof Node?v:document.createTextNode(v===null||v===undefined?'—':String(v)));r.append(td);}b.append(r);}t.append(b);parent.append(t);return t;};
const link=(text,target)=>{const n=E('a',text);n.href=target;return n;};
const label=x=>x==='sep30'?'9월 말':'연말';
const uri=p=>'S03.html?hospital='+encodeURIComponent(p.hospital)+'&patient='+p.patient_number+'&as_of_label='+p.as_of_label;
const status=add('div',`이번 조회 검증: ${D.run.status} · 실행 ${D.run.run_id}`,'banner '+(D.run.status==='실패'?'bad':''));
add('p',D.run.validation_scope,'note');
function overview(){
 const m=add('div',undefined,'metrics');for(const r of D.summaries){const c=add('div',undefined,'card',m);add('small',r.hospital+' · '+label(r.as_of_label),undefined,c);add('b',`${r.numerator} / ${r.denominator}`,undefined,c);add('span',r.percent_display,undefined,c);}
 add('h2','혈압 조절률');table(['병원','기준 시점','실제 기준일','대상','조절','조절률','기대 결과 비교'],D.summaries.map(r=>[r.hospital,label(r.as_of_label),r.as_of_display,r.denominator,r.numerator,r.percent_display,r.comparison_label]));
 add('p','학습용 계산(제외 대상 안 뺌 · D7)');add('p','A′는 A의 파생 출처로 별도 보존하며, A와 합산하지 않아요. 두 병원을 합친 비율도 만들지 않아요.','note');
 add('h2','정의와 코드 목록');table(['지표 정의','정의 버전','코드 목록 버전','같은 실행의 검증 시각'],[[D.run.definition_id,D.run.definition_version,D.run.code_set_version,D.run.last_verified_at]]);add('p','정의 manifest SHA256: '+D.run.definition_manifest_sha256,'hash');
}
function people(){
 if(!D.people){add('p','공개 모드에는 사람별 객체를 만들지 않아요.');return;}
 const f=add('div',undefined,'filters');const select=(title,options)=>{const l=add('label',title,undefined,f),s=E('select');options.forEach(([v,n])=>{const o=E('option',n);o.value=v;s.append(o);});l.append(s);return s;};
 const h=select('병원',[['A','병원 A'],['B','병원 B']]),d=select('기준 시점',[['dec31','연말'],['sep30','9월 말']]),control=select('조절 여부',[['all','전체'],['0','조절 안 됨'],['1','조절됨']]);const region=add('div');
 function draw(){region.replaceChildren();const selected=D.people.filter(p=>p.hospital===h.value&&p.as_of_label===d.value&&(control.value==='all'||String(p.controlled)===control.value));add('p',`${selected.length}행 · 번호는 두 시점과 필터에서 유지돼요.`,'note',region);table(['환자 번호','실제 기준일','마지막 혈압일','수축기','이완기','판정','사유','기대 결과 비교'],selected.map(p=>[link(p.patient_label,uri(p)),p.as_of,p.last_bp_date,p.systolic,p.diastolic,p.control_label,p.reason,p.comparison_label]),region);}
 [h,d,control].forEach(s=>s.addEventListener('change',draw));draw();
}
function detail(){
 const q=new URLSearchParams(location.search),h=q.get('hospital')||'B',n=Number(q.get('patient')||2),day=q.get('as_of_label')||'dec31';
 const trace=(D.traces||[]).find(t=>t.patient.hospital===h&&t.patient.patient_number===n&&t.patient.as_of_label===day);
 if(!trace){add('p','상세 연결 미확인','empty');return;}const p=trace.patient;
 add('h2',`병원 ${p.hospital} · ${p.patient_label} · ${label(p.as_of_label)}`);table(['실제 기준일','마지막 혈압일','수축기','이완기','판정','사유'],[[p.as_of,p.last_bp_date,p.systolic,p.diastolic,p.control_label,p.reason]]);
 add('p','기존 계산 결과를 표시해요. 화면에서 대상 조건·MIN·조절 여부를 다시 계산하지 않아요.','note');
 add('h2','선택된 성분 값과 같은 표준 행 후보');table(['원천 종류','임상 날짜','원래 성분 코드','표준 개념','값','표준 단위','원문 단위','선택 근거 연결'],trace.standard_rows.map(r=>[r.source_type,r.measurement_date,r.measurement_source_value,r.measurement_concept_id,r.value_as_number,r.unit_display,r.original_unit_written,r.source_link_status]));
 add('div','원천 연결 미확인','banner');add('p','같은 날짜·성분·값의 후보를 모두 보여 줘요. 동률이 있으면 하나로 합치지 않으며, 수축기와 이완기가 같은 측정 묶음이었다고 추정하지 않아요. 원래 행 키는 내보내지 않아요.','note');add('p','수축기 < 140 · 이완기 < 90이라는 기존 정의를 참고해요. 판정은 위의 저장된 결과예요.');
}
function checks(){
 add('h2','이번 조회의 검증 단계');const stages=[...D.run.stages].sort((a,b)=>(b.status==='실패')-(a.status==='실패'));table(['단계','상태','범위'],stages.map(s=>[s.label,s.status,s.scope||s.note||'이번 명령에서 확인했어요.']));
 add('h2','기대 결과와 비교');table(['범위','다른 칸','빠진 행','남는 행'],[[D.checks.scope,D.checks.cell_diffs,D.checks.missing_rows,D.checks.unexpected_rows]]);
 add('h2','같은 스냅샷의 데이터 품질 SELECT');add('p','DQD를 참고한 검사 9개와 미매핑 경고를 별도로 보여 줘요. 경고를 기대값 일치로 처리하지 않아요.','note');table(['검사','갈래','상태','결과 행','검출 결과의 위반 수 / 분모 (경고는 건수)'],D.checks.quality.map(x=>[x.check,x.kind,x.status,x.result_rows,x.details.map(r=>(r.hospital||r.measurement_concept_id||'')+': '+(r.not_carried!==undefined?r.not_carried:(r.violation_count+' / '+r.denominator))).join(' · ')||'결과 없음 · 위반 수/분모 미표시']));
 add('h2','과거 dbt 저장 결과');add('p','현재 DB 스냅샷과의 연결은 미확인이에요. 이번 품질 SELECT와 구분해요.','note');if(D.checks.saved_dbt.counts)table(['기록 시각','pass','warn','error','skipped'],[[D.checks.saved_dbt.recorded_at,...['pass','warn','error','skipped'].map(k=>D.checks.saved_dbt.counts[k])]]);
 add('h2','검증 실행 이력');add('p','이전 화면 생성 성공: '+(D.run.previous_success_at||'없음')+' · 이번 시도: '+D.run.started_at,'note');add('p',D.checks.current_index_status+' · 현재 조회 결과는 위의 이번 실행 manifest에 기록해요. 과거 index 행으로 이번 성공을 표시하지 않아요.','note');add('p','runs/index.csv · 마지막 과거 성공: '+(D.checks.last_success||'없음'),'note');table(['과거 실행 시각','제품 커밋','당시 상태','다른 칸','빠진 행','남는 행'],D.checks.history.slice(-8).reverse().map(r=>[r.run_at,r.product_commit.slice(0,7),r.status,r.cell_diffs,r.missing_rows,r.unexpected_rows]));
}
function errors(){
 const c=D.checks;add('p',c.cell_diffs+c.missing_rows+c.unexpected_rows===0?(D.run.status==='통과'?'모두 통과':'셀 차이 없음 · 전체 상태는 위에서 확인해요.'):`다른 칸 ${c.cell_diffs}개 · 빠진 행 ${c.missing_rows}개 · 남는 행 ${c.unexpected_rows}개`,c.status==='실패'?'bad':'ok');
 add('p','A/B 검사 ④의 셀 차이만 표시해요. 다른 품질 검사 결과는 데이터 품질 검사에서 확인해요.','note');
 if(D.errors.length)table(['분류','병원','기준 시점','테이블','열','기대','실제','환자 번호'],D.errors.map(r=>[r.kind,r.hospital,r.as_of_label,r.table,r.column_display,r.expected,r.actual,r.patient_detail_link?link('환자 '+r.patient_number,uri({hospital:r.hospital,patient_number:r.patient_number,as_of_label:r.as_of_label})):null]));else add('div','다른 칸·빠진 행·남는 행이 없어요.','empty');
 add('p','DQD 집계 실패는 위반 수·분모를 확인하는 검사이며, 환자 행 목록은 없어요.','note');
}
({S01:overview,S02:people,S03:detail,S04:checks,S05:errors}[document.body.dataset.screen]||overview)();
