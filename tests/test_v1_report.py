"""D1-D7 / ADR0001,0003,0010,0011,0013: external v1 contracts and snapshot/privacy failures."""
import copy,csv,datetime as dt,json,re,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from fhir_line import definition,report_ui as ui
from fhir_line.runtime import ROOT


def fixture(con,screen):
    # A small test DB, loaded from fixed independent CSVs. Never a new expected result.
    con.execute('CREATE TABLE fct_bp_person (hospital VARCHAR,as_of_label VARCHAR,person_id VARCHAR,as_of DATE,last_bp_date DATE,systolic DOUBLE,diastolic DOUBLE,controlled INTEGER,reason VARCHAR)')
    con.execute('CREATE TABLE bp_summary (hospital VARCHAR,as_of_label VARCHAR,denominator INTEGER,numerator INTEGER,rate DOUBLE)')
    facts=[]
    for h in ('A','B'):
        with (ROOT/f'expected/person_{h}.csv').open(newline='') as f:
            for r in csv.DictReader(f):facts.append(tuple(r[k] or None for k in ('hospital','as_of_label','person_id','as_of','last_bp_date','systolic','diastolic','controlled','reason')))
        with (ROOT/f'expected/summary_{h}.csv').open(newline='') as f:
            for r in csv.DictReader(f):con.execute('INSERT INTO bp_summary VALUES (?,?,?,?,?)',[r[k] or None for k in ('hospital','as_of_label','denominator','numerator','rate')])
    con.executemany('INSERT INTO fct_bp_person VALUES (?,?,?,?,?,?,?,?,?)',facts)
    con.execute('CREATE TABLE omop_people AS SELECT row_number() OVER(ORDER BY hospital,person_id)::integer person_id,hospital,person_id AS source_person_id FROM (SELECT DISTINCT hospital,person_id FROM fct_bp_person)')
    con.execute('CREATE TABLE person AS SELECT person_id,1990::integer year_of_birth FROM omop_people')
    con.execute("CREATE TABLE observation_period AS SELECT '2025-01-01'::date observation_period_start_date,'2025-12-31'::date observation_period_end_date")
    con.execute("CREATE TABLE visit_occurrence AS SELECT '2025-01-01'::date visit_start_date,'2025-01-02'::date visit_end_date")
    con.execute('CREATE TABLE concept AS SELECT * FROM read_csv(?,header=true)',[str(ROOT/'seeds/concept.csv')])
    con.execute('CREATE TABLE source_to_concept_map AS SELECT * FROM read_csv(?,header=true)',[str(ROOT/'seeds/source_to_concept_map.csv')])
    con.execute('CREATE TABLE measurement (measurement_id INTEGER,person_id INTEGER,measurement_source_value VARCHAR,measurement_date DATE,measurement_concept_id INTEGER,value_as_number DOUBLE,unit_concept_id INTEGER,unit_source_value VARCHAR)')
    con.execute('CREATE TABLE omop_source_link (omop_table VARCHAR,omop_id INTEGER,hospital VARCHAR,source_row_key VARCHAR)')
    pid=con.execute("SELECT person_id FROM omop_people WHERE hospital='B' ORDER BY source_person_id LIMIT 1 OFFSET 1").fetchone()[0]
    for i,r in enumerate(screen['S03']['standard_rows'],1):
        con.execute('INSERT INTO measurement VALUES (?,?,?,?,?,?,?,NULL)',[i,pid,r['measurement_source_value'],r['measurement_date'],r['measurement_concept_id'],r['value_as_number'],r['unit_concept_id']])
        con.execute("INSERT INTO omop_source_link VALUES ('measurement',?,'B',?)",[i,'private-test-key-'+str(i)])
    con.execute('CREATE TABLE condition_occurrence AS SELECT 320128::integer condition_concept_id')
    con.execute("CREATE TABLE cdm_source AS SELECT 'test CDM'::varchar cdm_source_name")
    con.execute("CREATE TABLE omop_load_counts AS SELECT 'B'::varchar hospital,'condition_occurrence'::varchar omop_table,1::integer not_carried")


class V1Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts,_=ui.reviewed_expected();cls.code=cls.contracts['code_set_manifest_expected.json'];cls.screen=cls.contracts['screens_expected.json']
        (ui.BASE/'tmp').mkdir(parents=True,exist_ok=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ui.BASE/'tmp');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.db=self.base/'fixture.duckdb';con=duckdb.connect(str(self.db),config={'memory_limit':'2GB','threads':2});fixture(con,self.screen);con.close()

    def render(self,public=False,**kw):
        return ui.render(self.db,public,self.base/('public' if public else 'local'),**kw)

    def payload(self):
        state,folder=self.render();self.assertEqual(state['status'],'통과');return state,json.loads((folder/'data.json').read_text()),folder

    def test_D1_0010_manifest_codes_hash_and_every_registered_file(self):
        manifest,digest=definition.context();self.assertEqual(manifest,self.code['candidate_manifest']);self.assertEqual(digest,self.code['hash_contract']['definition_manifest_sha256'])
        identity=self.code['identity_rules']
        for field in ('definition_id','code_set_id'):self.assertRegex(manifest[field],identity['id_pattern'])
        for field in ('definition_version','code_set_version'):self.assertRegex(manifest[field],identity['version_pattern'])
        self.assertEqual(manifest['code_set_id']+'/'+manifest['code_set_version'],identity['list_version_id'])
        self.assertEqual(manifest['definition_id']+'/'+manifest['definition_version'],identity['definition_version_id'])
        self.assertFalse(identity['official_cms_version_claim']);self.assertTrue(identity['changes_require_review_and_new_registration'])
        membership=self.code['membership'];self.assertEqual(len(manifest['source_codes']),membership['source_code_count'])
        self.assertTrue(all(r['target_concept_id']==membership['standard_hypertension_concept_id'] and r['target_vocabulary_id']==membership['standard_vocabulary'] for r in manifest['source_codes']))
        self.assertTrue(definition.member(manifest,'A_PRIME','SNOMED',manifest['source_codes'][0]['source_code']))
        self.assertNotIn('A_PRIME',{r['hospital'] for r in manifest['source_codes']})
        self.assertEqual(definition.canonical(manifest)[-1:],b'\n');self.assertNotIn('run_id',manifest)
        self.assertEqual(definition.generated_manifest(),manifest)

    def test_D1_0010_reject_five_version_and_system_counterexamples(self):
        manifest,h=definition.context();r=self.code['rejection_examples']
        self.assertEqual(definition.member(manifest,'A','ICD-10',manifest['source_codes'][0]['source_code']),r['same_code_in_other_system_is_member'])
        with self.assertRaises(definition.DefinitionError):definition.context('v2')
        with patch.object(definition,'generated_manifest',return_value=manifest|{'definition_version':'v2'}):
            with self.assertRaises(definition.DefinitionError):definition.context()
        for change in ({'definition_version':'v2'},{'code_set_version':'v2'}):
            bad=manifest|change
            with self.assertRaises(definition.DefinitionError):definition.metadata(bad,h,'run')
        with self.assertRaises(definition.DefinitionError):definition.metadata(manifest,h,'')
        self.assertTrue(all(x is False for x in r.values()))

    def test_D1_D6_S01_all_four_rows_and_bound_metadata(self):
        state,payload,_=self.payload()
        for actual,want in zip(payload['summaries'],self.screen['S01']['rows']):
            self.assertEqual({k:actual[k] for k in want},want);self.assertEqual(actual['run_id'],state['run_id'])
        self.assertEqual(len(payload['summaries']),self.screen['S01']['row_count'])
        meta=self.code['public_summary_metadata'];self.assertEqual({k:payload['summaries'][0][k] for k in meta['fixed']},meta['fixed'])
        self.assertEqual(set(meta['added_fields']),set(meta['fixed'])|{'run_id'})
        for want in self.code['unchanged_summaries']:
            actual=next(r for r in payload['summaries'] if (r['hospital'],r['as_of_label'])==(want['hospital'],want['as_of_label']));self.assertEqual({k:actual[k] for k in want},want)
        self.assertFalse(self.screen['S01']['combined_AB_rate']);self.assertFalse(self.screen['S01']['sum_A_and_A_prime'])
        self.assertFalse(meta['db_schema_change'])

    def test_D2_D5_S02_all_15_year_end_people_and_cross_date_numbers(self):
        _,p,_=self.payload()
        for h,expected in self.screen['S02']['hospitals'].items():
            actual=[r for r in p['people'] if r['hospital']==h and r['as_of_label']=='dec31'];self.assertEqual(actual,expected['rows']);self.assertEqual(len(actual),expected['row_count'])
        aliases={}
        con=duckdb.connect(str(self.db),read_only=True);facts=ui.rows(con,'SELECT * FROM fct_bp_person ORDER BY hospital,person_id,as_of_label');con.close()
        for raw,safe in zip(facts,p['people']):
            key=(raw['hospital'],raw['person_id']);aliases.setdefault(key,safe['patient_number']);self.assertEqual(aliases[key],safe['patient_number'])
        self.assertEqual(self.screen['S02']['row_filter_values'],['전체','조절 안 됨','조절됨'])

    def test_D3_D4_D5_S03_two_standard_rows_and_A_anchor(self):
        _,p,_=self.payload();expected=self.screen['S03'];trace=next(x for x in p['traces'] if x['patient']==expected['representative'])
        self.assertEqual(len(trace['standard_rows']),expected['standard_row_count'])
        self.assertEqual([{k:r[k] for k in want} for r,want in zip(trace['standard_rows'],expected['standard_rows'])],expected['standard_rows'])
        self.assertEqual(trace['connection_status'],expected['original_record_key']['display_without_verified_link'])
        self.assertTrue(all(r['original_unit_written'] is expected['original_unit_written'] for r in trace['standard_rows']))
        self.assertIn(expected['additional_A_dec31_anchor'],p['people'])
        self.assertFalse(expected['A_124_92_standard_row_assertions_available']);self.assertFalse(expected['decision']['recalculate_in_browser'])
        self.assertFalse(expected['original_record_key']['browser_export_allowed'])
        self.assertTrue(all(expected['component_lineage'].get(k) for k in ('separate_component_provenance','ties_show_all_candidates','missing_partial_decimal_values_preserved')))
        self.assertFalse(expected['component_lineage']['assert_unique_origin_from_date_and_value'])

    def test_L2_S04_six_honest_stages_and_history_is_not_current(self):
        state,p,_=self.payload();expected=self.screen['S04'];actual=state['stages']
        self.assertEqual([(r['stage_id'],r['label']) for r in actual],[(r['stage_id'],r['label']) for r in expected['stages']])
        self.assertEqual(next(r for r in actual if r['stage_id']=='tests')['status'],'미실행')
        self.assertEqual(next(r for r in actual if r['stage_id']=='dbt_quality')['status'],'미실행')
        self.assertEqual(p['checks']['current_index_status'],expected['current_index_missing']);self.assertFalse(p['checks']['historical_row_confirms_current_run'])
        self.assertEqual(sum(r['kind']=='DQD 참고 검사' for r in p['checks']['quality']),expected['dbt_quality']['DQD_check_count'])
        self.assertTrue(any(r['status']=='warn' for r in p['checks']['quality']));self.assertEqual(p['checks']['comparison']['status'],'통과')
        self.assertTrue(all(r['status'] in expected['dbt_quality']['statuses'] for r in p['checks']['quality']))
        self.assertEqual(p['checks']['index_display'],expected['index_display'])

    def test_D6_S05_baseline_has_no_difference_or_patient_link(self):
        _,p,_=self.payload();expected=self.screen['S05']['baseline']
        self.assertEqual(p['checks']['status'],expected['status']);self.assertEqual(p['errors'],expected['rows'])
        for k in ('cell_diffs','missing_rows','unexpected_rows'):self.assertEqual(p['checks'][k],expected[k])
        self.assertFalse(self.screen['S05']['raw_row_key_export_allowed'])

    def test_D6_case2_real_db_cell_change_drives_S01_S04_S05_failure(self):
        case=self.screen['case_2_summary_numerator_mismatch'];con=duckdb.connect(str(self.db));con.execute("UPDATE bp_summary SET numerator=4 WHERE hospital='B' AND as_of_label='dec31'");con.close()
        state,folder=self.render();p=json.loads((folder/'data.json').read_text());self.assertEqual(state['status'],case['S04']['status'])
        self.assertEqual(len(p['errors']),case['S05']['row_count']);self.assertEqual(p['errors'][0],case['S05']['row'])
        actual=next(r for r in p['summaries'] if r['hospital']=='B' and r['as_of_label']=='dec31');wanted=case['S01_actual_summary'];self.assertEqual({k:actual[k] for k in wanted if k!='recompute_rate_in_ui'},{k:v for k,v in wanted.items() if k!='recompute_rate_in_ui'})
        self.assertEqual(p['checks']['comparison']['요약']['status'],case['S04']['summary_comparison']);self.assertEqual(p['checks']['comparison']['사람별']['status'],case['S04']['person_comparison'])
        for k in ('cell_diffs','missing_rows','unexpected_rows'):self.assertEqual(p['checks'][k],case['S04'][k])
        self.assertEqual(next(x for x in state['stages'] if x['stage_id']=='ladder')['status'],'실패')
        self.assertIn('S04',self.screen['delivery']['local_screens'])

    def test_D1_D6_zero_denominator_is_null_and_not_recomputed(self):
        con=duckdb.connect(str(self.db));con.execute("UPDATE bp_summary SET denominator=0,numerator=0,rate=NULL WHERE hospital='B' AND as_of_label='dec31'");con.close()
        _,folder=self.render();p=json.loads((folder/'data.json').read_text());r=next(r for r in p['summaries'] if r['hospital']=='B' and r['as_of_label']=='dec31');zero=self.screen['S01']['zero_denominator'];self.assertEqual((r['numerator'],r['denominator'],r['rate'],r['percent_display']),(zero['numerator'],zero['denominator'],zero['rate'],zero['display']))

    def test_0011_component_ties_partial_values_and_missing_links_are_not_fabricated(self):
        con=duckdb.connect(str(self.db));con.execute('INSERT INTO measurement SELECT 99,person_id,measurement_source_value,measurement_date,measurement_concept_id,value_as_number,unit_concept_id,unit_source_value FROM measurement WHERE measurement_id=1');con.execute('DELETE FROM omop_source_link');con.close()
        _,p,_=self.payload();trace=next(x for x in p['traces'] if x['patient']==self.screen['S03']['representative']);self.assertEqual(len(trace['standard_rows']),3);self.assertTrue(all(x['source_link_status']=='미확인' for x in trace['standard_rows']))
        con=duckdb.connect(str(self.db));con.execute("UPDATE fct_bp_person SET systolic=109.51,diastolic=NULL,reason='마지막 날에 한쪽 값만' WHERE hospital='B' AND as_of_label='dec31'");con.close()
        _,folder=self.render();p=json.loads((folder/'data.json').read_text());self.assertTrue(all(x['systolic']==109.51 and x['diastolic'] is None for x in p['people'] if x['hospital']=='B' and x['as_of_label']=='dec31'))

    def test_0013_all_surfaces_have_no_ids_and_public_has_no_patient_objects(self):
        _,p,folder=self.payload();privacy=self.screen['privacy'];ui.assert_private_free(p)
        forbidden=set(privacy['forbidden_fields'])
        def keys(x):
            if isinstance(x,dict):return set(x)|set().union(*(keys(v) for v in x.values()))
            if isinstance(x,list):return set().union(*(keys(v) for v in x))
            return set()
        self.assertFalse(forbidden.intersection(keys(p)))
        for f in folder.iterdir():self.assertNotRegex(f.read_text(),r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')
        state,public=self.render(True);p=json.loads((public/'data.json').read_text());self.assertNotIn('people',p);self.assertNotIn('traces',p);self.assertFalse((public/'S02.html').exists());self.assertFalse((public/'S03.html').exists())
        self.assertEqual(self.screen['delivery']['type'],'정적 HTML');self.assertFalse(self.screen['delivery']['server_required']);self.assertFalse(self.screen['delivery']['public_patient_objects_allowed'])
        for bad in ({'person_id':'secret'},{'text':'12345678'},{'text':'</script><script>alert(1)</script>'}):
            if '12345678' in str(bad):
                with self.assertRaises(ui.ReportError):ui.assert_private_free(bad,{'12345678'})
            elif 'person_id' in bad:
                with self.assertRaises(ui.ReportError):ui.assert_private_free(bad)
        self.assertNotIn('innerHTML',(ROOT/'fhir_line/ui/report.js').read_text())
        from fhir_line.ui import write_site
        escaped=self.base/'escaped';escaped.mkdir();probe=copy.deepcopy(p);probe['run']['validation_scope']='</script><img src=x onerror=alert(1)>'
        write_site(escaped,probe,False,ui.guarded)
        self.assertNotIn('</script><img',(escaped/'S01.html').read_text());self.assertIn('\\u003c/script\\u003e',(escaped/'S01.html').read_text())
        con=duckdb.connect(str(self.db));con.execute("UPDATE fct_bp_person SET reason='</script><img src=x onerror=alert(1)>' WHERE hospital='B'");con.close()
        failed,new=self.render();self.assertEqual(failed['status'],'실패');self.assertFalse((new/'S01.html').exists())

    def test_L2_failed_attempt_does_not_reuse_or_delete_previous_success(self):
        state,folder=self.render();latest=folder.parent/'latest-success.json';previous=latest.read_bytes()
        with patch.object(ui,'reviewed_expected',side_effect=ui.ReportError('LEAD_REVIEW_REQUIRED')):failed,new=self.render()
        self.assertEqual(failed['status'],'실패');self.assertEqual(json.loads((folder.parent/'latest.json').read_text())['status'],'실패');self.assertEqual(latest.read_bytes(),previous);self.assertFalse((new/'S01.html').exists())
        index=self.base/'history';index.mkdir();(index/'index.csv').write_text('bad,header\n')
        with self.assertRaises(ui.ReportError):ui.history(index)
        with self.assertRaises(ui.ReportError):ui.guarded(ROOT/'expected/anything')
        with tempfile.TemporaryDirectory(dir=ui.BASE/'tmp') as x:
            path=Path(x);(path/'link').symlink_to(ROOT/'expected',target_is_directory=True)
            with self.assertRaises(ui.ReportError):ui.render(self.db,output_root=path/'link'/'bad')
        with patch.object(definition,'generated_manifest',side_effect=ValueError('private text')):
            failed,new=self.render();self.assertEqual(failed['status'],'실패');self.assertNotIn('private text',(new/'run-manifest.json').read_text())

    def test_D1_0010_mixed_versions_and_unbound_run_or_snapshot_fail(self):
        _,p,folder=self.payload()
        for field,bad in [('definition_version','v2'),('code_set_version','v2'),('run_id','unbound')]:
            broken=copy.deepcopy(p);broken['summaries'][0][field]=bad
            with self.assertRaises(ui.ReportError):ui.validate_bindings(broken)
        latest=folder.parent/'latest-success.json';saved=json.loads(latest.read_text());saved['database_sha256']='0'*64
        ui.json_write(latest,saved);ui.json_write(folder/'run-manifest.json',saved)
        with self.assertRaises(ui.ReportError):ui.previous_success(folder.parent)
        state,new=self.render();self.assertEqual(state['status'],'실패');self.assertFalse((new/'S01.html').exists())

    def test_D3_quality_failures_show_aggregate_counts_separately_from_comparison(self):
        con=duckdb.connect(str(self.db));con.execute("UPDATE concept SET domain_id='Measurement' WHERE concept_id=8876");con.close()
        state,folder=self.render();p=json.loads((folder/'data.json').read_text());self.assertEqual(state['status'],'실패');self.assertEqual(p['checks']['comparison']['status'],'통과')
        failed=[r for r in p['checks']['quality'] if r['status']=='error'];self.assertEqual(len(failed),1);self.assertEqual(failed[0]['details'][0]['violation_count'],2);self.assertEqual(failed[0]['details'][0]['denominator'],2)
        stored=self.base/'run_results.json';stored.write_text(json.dumps({'metadata':{'generated_at':'2026-10-27T09:00:00Z'},'results':[{'status':s} for s in ('pass','warn','error','skipped')]}))
        actual=ui.saved_dbt_summary(stored);self.assertEqual(actual['counts'],dict.fromkeys(('pass','warn','error','skipped'),1));self.assertFalse(actual['bound_to_current_snapshot'])

    def test_L2_missing_review_hash_and_links_stop_without_modifying_protected_files(self):
        with patch.object(Path,'read_text',return_value='not approved'):
            with self.assertRaises(ui.ReportError):ui.reviewed_expected()
        original=Path.read_bytes
        with patch.object(Path,'read_bytes',autospec=True,side_effect=lambda p:b'changed' if p.name=='screens_expected.json' else original(p)):
            with self.assertRaises(ui.ReportError):ui.reviewed_expected()
        source=self.base/'source';source.write_text('unchanged');hard=self.base/'hard';hard.hardlink_to(source)
        with self.assertRaises(ui.ReportError):ui.guarded(hard)
        self.assertEqual(source.read_text(),'unchanged')
        state,folder=self.render();self.assertEqual(state['status'],'통과');second,_=self.render();self.assertEqual(second['previous_success_at'],state['finished_at'])

    def test_L2_concurrent_writer_and_midrun_definition_change_cannot_publish_success(self):
        import fcntl
        base=self.base/'locked';base.mkdir();lock=(base/'run.lock').open('a');self.addCleanup(lock.close);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with self.assertRaises(BlockingIOError):ui.render(self.db,output_root=base)
        self.assertFalse((base/'latest.json').exists())
        context=definition.context()
        with patch.object(definition,'context',side_effect=[context,definition.DefinitionError('DEFINITION_HASH_MISMATCH')]):state,folder=self.render()
        self.assertEqual(state['status'],'실패');self.assertEqual(state['definition_status'],self.code['public_summary_metadata']['unregistered_or_hash_mismatch_display']);self.assertNotIn('definition_version',state);self.assertFalse((folder/'S01.html').exists())

    def test_L2_external_five_cases_are_required_and_cannot_be_skipped(self):
        with patch.dict('os.environ',{'FHIR_SKIP_EXTERNAL_CELL_CASES':'1'}):
            with self.assertRaises(ui.ReportError):ui.cell_preflight()
        with patch.dict('os.environ',{'FHIR_CELL_DIFF_CASES':str(self.base/'absent.json')}):
            with self.assertRaises(FileNotFoundError):ui.cell_preflight()
        state,_,_=self.payload();expected=self.screen['S04']['preflight']
        self.assertEqual({k:state['preflight'][k] for k in expected},expected)

    def test_D5_S05_all_categories_link_only_one_actual_person_row(self):
        kinds=self.screen['S05']['categories']
        mutations=[("UPDATE fct_bp_person SET systolic=systolic+1 WHERE hospital='A' AND as_of_label='dec31' AND person_id=(SELECT min(person_id) FROM fct_bp_person WHERE hospital='A')",kinds[0],True),
          ("DELETE FROM fct_bp_person WHERE hospital='A' AND as_of_label='dec31' AND person_id=(SELECT min(person_id) FROM fct_bp_person WHERE hospital='A')",kinds[1],False),
          ("INSERT INTO fct_bp_person SELECT * FROM fct_bp_person WHERE hospital='A' AND as_of_label='dec31' ORDER BY person_id LIMIT 1",kinds[2],False)]
        for i,(sql,kind,linked) in enumerate(mutations):
            with self.subTest(kind=kind):
                db=self.base/f'case{i}.duckdb';con=duckdb.connect(str(db),config={'memory_limit':'2GB','threads':2});fixture(con,self.screen);con.execute(sql);con.close()
                state,folder=ui.render(db,output_root=self.base/f'case{i}')
                self.assertEqual(state['status'],'실패');p=json.loads((folder/'data.json').read_text());self.assertEqual(len(p['errors']),1);self.assertEqual(p['errors'][0]['kind'],kind);self.assertEqual(p['errors'][0]['patient_detail_link'],linked)
                if not linked:self.assertIsNone(p['errors'][0]['patient_number'])

    def test_R1_D1_numeric_columns_cannot_export_free_form_strings(self):
        row=dict(self.screen['S03']['representative']);row['systolic']='a private free-form string'
        with self.assertRaises(ui.ReportError):ui.safe_person(row,2,'기대 결과와 다름')
        with self.assertRaises(ui.ReportError):ui.numeric_value('a private free-form string')
        con=duckdb.connect(str(self.db));con.execute('ALTER TABLE fct_bp_person ALTER COLUMN systolic TYPE VARCHAR');con.execute("UPDATE fct_bp_person SET systolic='a private free-form string'");con.close()
        state,folder=self.render();self.assertEqual(state['status'],'실패');self.assertFalse((folder/'S01.html').exists());self.assertNotIn('a private free-form string',(folder/'run-manifest.json').read_text())

    def test_D1_D6_dates_come_from_DB_and_unknown_rate_is_not_zero_denominator(self):
        con=duckdb.connect(str(self.db));con.execute("UPDATE fct_bp_person SET as_of='2026-12-31' WHERE hospital='A' AND as_of_label='dec31'");con.execute("UPDATE bp_summary SET rate=NULL WHERE hospital='A' AND as_of_label='dec31'");con.close()
        state,folder=self.render();p=json.loads((folder/'data.json').read_text());row=next(r for r in p['summaries'] if r['hospital']=='A' and r['as_of_label']=='dec31');self.assertEqual(row['as_of_display'],'2026-12-31');self.assertEqual(row['denominator'],6);self.assertEqual(row['percent_display'],'미확인');self.assertEqual(state['status'],'실패')

if __name__=='__main__':unittest.main()
