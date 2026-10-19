"""L2 and L0/D1: replay, immutability, lossless payloads, and layer direction."""
import datetime as dt
import hashlib
import json
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

from fhir_line.batches import resource_date, split
from fhir_line.bundles import entries, replace_entries
from fhir_line.layers import validate
from fhir_line.runtime import connect
from fhir_line.store import append_rows, initialize, load
from fhir_line.ladder import assess_counts, compare_expected
from fhir_line import ladder
from fhir_line.runtime import CACHE, ROOT, writable_path


def row(batch, values, kind='Observation', rid='test-observation'):
    payload = json.dumps({'resourceType':kind,'id':rid,**values}, separators=(',',':'))
    return (batch,kind,rid,'urn:uuid:'+rid,payload,hashlib.sha256(payload.encode()).hexdigest(),
            'test-fixture.json',dt.datetime(2026,1,batch,tzinfo=dt.timezone.utc))


def bp(systolic):
    return {'code':{'coding':[{'system':'http://loinc.org','code':'85354-9'}]},
            'component':[{'code':{'coding':[{'code':'8480-6'}]},'valueQuantity':{'value':systolic}},
                         {'code':{'coding':[{'code':'8462-4'}]},'valueQuantity':{'value':75}}]}


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect(':memory:')
        initialize(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_L2_16_old_record_does_not_overwrite(self):
        old, new = row(1,bp(145)),row(2,bp(135))
        for incoming in ([old],[new],[old]):
            append_rows(self.connection,incoming)
        values = self.connection.execute("SELECT json_extract(payload_json,'$.component[0].valueQuantity.value'),change_batch_id FROM latest_resources").fetchone()
        self.assertEqual(values,('135',2))
        self.assertEqual(self.connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0],2)

    def test_L2_identical_patient_has_one_version(self):
        append_rows(self.connection,[row(1,{},'Patient','test-person')])
        append_rows(self.connection,[row(2,{},'Patient','test-person')])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0],2)
        self.assertEqual(self.connection.execute('SELECT count(*),min(change_batch_id) FROM latest_resources').fetchone(),(1,1))

    def test_L2_known_old_content_in_new_batch_is_not_new_revision(self):
        for incoming in (row(1,bp(145)),row(2,bp(135)),row(3,bp(145))):
            append_rows(self.connection,[incoming])
        self.assertEqual(self.connection.execute('SELECT change_batch_id FROM latest_resources').fetchone()[0],2)

    def test_L2_out_of_order_arrival_and_received_time_are_independent(self):
        new = row(2,bp(135))
        append_rows(self.connection,[new])
        append_rows(self.connection,[row(1,bp(145))])
        replay = (*new[:-1],dt.datetime(2027,1,1,tzinfo=dt.timezone.utc))
        append_rows(self.connection,[replay])
        self.assertEqual(self.connection.execute('SELECT change_batch_id,received_at FROM latest_resources').fetchone(),(2,new[-1]))

    def test_L2_same_batch_changed_content_rolls_back(self):
        old = row(1,bp(145))
        append_rows(self.connection,[old])
        with self.assertRaisesRegex(ValueError,'conflicting'):
            append_rows(self.connection,[row(1,bp(135)),row(2,{},'Patient','new-person')])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0],1)
        self.assertEqual(self.connection.execute('SELECT payload_hash FROM raw_resources').fetchone()[0],old[5])

    def test_L2_duplicate_keys_inside_one_batch_are_rejected(self):
        old=row(1,bp(145))
        with self.assertRaisesRegex(ValueError,'duplicate'):
            append_rows(self.connection,[old,old])
        self.assertEqual(self.connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0],0)

    def test_L0_L1_resource_substring_is_unchanged(self):
        raw = '{ "resourceType" : "Patient", "id":"fixture", "x":[1, {"text":"a}한글"}] }'
        bundle = '{"resourceType":"Bundle","entry":[{"fullUrl":"urn:uuid:fixture","resource":'+raw+'}]}'
        parsed = list(entries(bundle))
        self.assertEqual(parsed[0][2],raw)
        self.assertEqual(parsed[0][0]['resource']['id'],'fixture')
        wrapped=replace_entries(bundle,[parsed[0][1]])
        self.assertEqual(list(entries(wrapped))[0][2],raw)

    def test_L0_D1_written_date_is_not_shifted(self):
        mapping={'Observation':['effectiveDateTime'],'Patient':[]}
        self.assertEqual(resource_date({'resourceType':'Observation','effectiveDateTime':'2025-09-30T23:59:00-09:00'},mapping),('2025-09-30','effectiveDateTime'))
        self.assertEqual(resource_date({'resourceType':'Patient','birthDate':'1970-01-01'},mapping),(None,None))

    def test_L0_L1_expected_and_original_reject_output_paths(self):
        for path in (ROOT/'expected/forbidden.duckdb',ROOT/'.local/FHIR-LINE-01/forbidden.duckdb'):
            self.assertFalse(path.exists())
            with self.assertRaisesRegex(ValueError,'read-only'):
                writable_path(path)
            with self.assertRaisesRegex(ValueError,'read-only'):
                connect(path)
            self.assertFalse(path.exists())

    def test_L0_L1_L2_split_load_replay_and_source_preservation(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder:
            root=Path(folder);source=root/'source';source.mkdir()
            rs=[{'resourceType':'Patient','id':'fixture-person'},
                {'resourceType':'Observation','id':'before','effectiveDateTime':'2025-09-30T23:59:00-09:00'},
                {'resourceType':'Observation','id':'at-cutoff','effectiveDateTime':'2025-10-01T00:00:00+00:00'}]
            input_file=source/'fixture.json'
            original=json.dumps({'resourceType':'Bundle','type':'transaction','entry':[{'fullUrl':'urn:uuid:'+r['id'],'resource':r} for r in rs]},indent=2).encode()
            input_file.write_bytes(original)
            batches=root/'batches';result=split(source,batches)
            self.assertEqual(result['batch_counts'],{'1':2,'2':2})
            self.assertEqual(result['duplicated_across_batches'],1)
            self.assertEqual(json.loads((batches/'batch_1/source_01.json').read_bytes())['type'],'transaction')
            database=root/'test.duckdb'
            self.assertEqual(load(batches/'batch_1',database)['inserted_rows'],2)
            self.assertEqual(load(batches/'batch_2',database)['latest_rows'],3)
            self.assertEqual(load(batches/'batch_1',database)['inserted_rows'],0)
            self.assertEqual(split(source,batches),result)
            self.assertEqual(input_file.read_bytes(),original)
            file=batches/'batch_1/source_01.json'
            file.write_bytes(file.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'manifest'):
                load(batches/'batch_1',database)


class LayerTests(unittest.TestCase):
    def manifest(self):
        def node(name,layer_name,deps,sql):
            return {'name':name,'resource_type':'model','original_file_path':f'models/{layer_name}/{name}.sql','depends_on':{'nodes':deps},'raw_code':sql}
        return {'sources':{'source.fhir.latest_resources':{'name':'latest_resources','resource_type':'source'}},
                'nodes':{'model.stg':node('stg','staging',['source.fhir.latest_resources'],"select * from {{ source('fhir','latest_resources') }}"),
                         'model.int':node('int','intermediate',['model.stg'],"with x as (select * from {{ ref('stg') }}) select * from x"),
                         'model.fct':node('fct','marts',['model.int'],"select * from {{ ref('int') }}")}}

    def test_L2_layers_empty_and_correct_graph_pass(self):
        self.assertEqual(validate({})['status'],'통과')
        self.assertEqual(validate(self.manifest())['issues'],[])

    def test_L2_layers_reject_reverse_ref(self):
        m=self.manifest();m['nodes']['model.stg']['depends_on']['nodes']=['model.fct']
        self.assertEqual(validate(m)['status'],'실패')

    def test_L2_layers_reject_direct_raw_even_without_ref(self):
        m=self.manifest();m['nodes']['model.fct']['raw_code']='select * from main.raw_resources'
        self.assertTrue(any('raw_resources' in e for e in validate(m)['issues']))

    def test_L2_layers_reject_comma_raw_but_ignore_literals_and_comments(self):
        m=self.manifest();m['nodes']['model.fct']['raw_code']="select * from {{ ref('int') }} x, main.raw_resources r"
        self.assertEqual(validate(m)['status'],'실패')
        m['nodes']['model.fct']['raw_code']="select 'text from raw_resources' as note from {{ ref('int') }} -- raw_resources\n"
        self.assertEqual(validate(m)['issues'],[])

    def test_L2_layers_reject_intermediate_source_bypass(self):
        m=self.manifest();m['nodes']['model.int']['depends_on']['nodes']=['source.fhir.latest_resources']
        self.assertEqual(validate(m)['status'],'실패')


class LadderTests(unittest.TestCase):
    def test_L2_layer_failure_cannot_reuse_previous_success_report(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder:
            root=Path(folder);(root/'summaries').mkdir()
            report=root/'summaries/verification-ladder.json'
            report.write_text('{"status":"통과"}')
            with patch.object(ladder,'ARTIFACTS',root),patch.object(ladder,'check_layers',return_value={'status':'실패'}):
                self.assertEqual(ladder.check(root/'unused')['status'],'실패')
            self.assertEqual(json.loads(report.read_text())['ladder'],[])

    def test_L2_ladder_counts_every_batch_arrival_and_deduplicates_latest(self):
        result=assess_counts(2,{'1':2,'2':1},1,3,2)
        self.assertEqual(result['status'],'통과')
        self.assertTrue(result['L1_key_contract_satisfied'])
        self.assertEqual(result['expected_raw_rows'],3)
        self.assertEqual(result['expected_latest_rows'],2)
        self.assertEqual(result['shared_resource_keys'],1)

    def test_L2_ladder_rejects_missing_raw_arrival_or_latest_resource(self):
        for raw,latest in ((2,2),(3,1)):
            with self.subTest(raw=raw,latest=latest):
                self.assertEqual(assess_counts(2,{'1':2,'2':1},1,raw,latest)['status'],'실패')

    def test_L2_ladder_expected_cells_and_read_only_failure(self):
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CACHE) as folder, connect(':memory:') as connection:
            connection.execute('CREATE TABLE fct_bp_person(person_id VARCHAR,as_of DATE,systolic DOUBLE,controlled BOOLEAN)')
            connection.execute("INSERT INTO fct_bp_person VALUES ('fixture','2025-12-31',124.0,true)")
            file=Path(folder)/'person_2025-12-31.csv'
            fixture=b'person_id,systolic,controlled\nfixture,124,True\n'
            file.write_bytes(fixture)
            self.assertEqual(compare_expected(connection,Path(folder))['status'],'통과')
            connection.execute('UPDATE fct_bp_person SET systolic=125')
            self.assertEqual(compare_expected(connection,Path(folder))['status'],'실패')
            self.assertEqual(file.read_bytes(),fixture)


if __name__=='__main__':
    unittest.main()
