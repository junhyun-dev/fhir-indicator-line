"""L1/L2: append-only arrivals; first appearance of each content hash is its revision."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from .bundles import entries
from .runtime import connect, ensure_space, writable_path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS raw_resources (
    batch_id INTEGER NOT NULL CHECK(batch_id > 0),
    resource_type VARCHAR NOT NULL,
    id VARCHAR NOT NULL,
    full_url VARCHAR,
    payload_json VARCHAR NOT NULL CHECK(json_valid(payload_json)),
    payload_hash VARCHAR NOT NULL CHECK(payload_hash = sha256(payload_json)),
    source_file VARCHAR NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(batch_id, resource_type, id)
);
CREATE VIEW IF NOT EXISTS latest_resources AS
WITH versions AS (
    SELECT resource_type, id, payload_hash, min(batch_id) AS change_batch_id
    FROM raw_resources GROUP BY resource_type, id, payload_hash
), ranked AS (
    SELECT r.*, v.change_batch_id,
           row_number() OVER(PARTITION BY r.resource_type, r.id
                             ORDER BY v.change_batch_id DESC, r.batch_id ASC) AS choice
    FROM raw_resources r JOIN versions v USING(resource_type, id, payload_hash)
)
SELECT batch_id, resource_type, id, full_url, payload_json, payload_hash, source_file,
       received_at, change_batch_id
FROM ranked WHERE choice = 1;
'''


def initialize(connection):
    connection.execute(SCHEMA)


def append_rows(connection, rows):
    """L2: reject changed same-batch keys atomically; retries retain original received_at."""
    connection.execute('BEGIN TRANSACTION')
    try:
        connection.execute('CREATE TEMP TABLE incoming AS SELECT * FROM raw_resources WHERE false')
        connection.executemany('INSERT INTO incoming VALUES (?, ?, ?, ?, ?, ?, ?, ?)', rows)
        bad = connection.execute('''SELECT count(*) FROM (
            SELECT batch_id, resource_type, id FROM incoming GROUP BY ALL
            HAVING count(*)>1
        )''').fetchone()[0]
        bad += connection.execute('''SELECT count(*) FROM incoming i JOIN raw_resources r
            USING(batch_id,resource_type,id) WHERE i.payload_hash<>r.payload_hash
            OR i.full_url IS DISTINCT FROM r.full_url''').fetchone()[0]
        if bad:
            raise ValueError('L2 duplicate or conflicting same-batch identity; append aborted')
        before = connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0]
        connection.execute('''INSERT INTO raw_resources
            SELECT DISTINCT * FROM incoming i WHERE NOT EXISTS (
              SELECT 1 FROM raw_resources r WHERE r.batch_id=i.batch_id
              AND r.resource_type=i.resource_type AND r.id=i.id)
            ON CONFLICT DO NOTHING''')
        after = connection.execute('SELECT count(*) FROM raw_resources').fetchone()[0]
        connection.execute('DROP TABLE incoming')
        connection.execute('COMMIT')
        return {'attempted_rows':len(rows), 'inserted_rows':after-before,
                'raw_rows':after, 'latest_rows':connection.execute('SELECT count(*) FROM latest_resources').fetchone()[0]}
    except BaseException:
        connection.execute('ROLLBACK')
        raise


def load(folder, database):
    folder, database = Path(folder).resolve(), writable_path(database)
    manifest = json.loads((folder/'manifest.json').read_text())
    received_at = dt.datetime.now(dt.timezone.utc)
    rows, counts = [], {}
    for file in manifest['files']:
        path = (folder/file['path']).resolve()
        if not path.is_relative_to(folder):
            raise ValueError('Manifest file escapes batch folder')
        content = path.read_bytes()
        if len(content)!=file['bytes'] or hashlib.sha256(content).hexdigest()!=file['sha256']:
            raise ValueError('L1 batch file differs from its manifest')
        file_count = 0
        for entry, _, payload in entries(content.decode('utf-8')):
            resource = entry['resource']
            typ, rid = resource['resourceType'], resource['id']
            rows.append((manifest['batch_id'],typ,rid,entry.get('fullUrl'),payload,
                         hashlib.sha256(payload.encode('utf-8')).hexdigest(),file['source_file'],received_at))
            counts[typ] = counts.get(typ,0)+1
            file_count += 1
        if file_count != file['resource_count']:
            raise ValueError('L1 file count differs from manifest')
    if counts != manifest['resource_counts'] or len(rows)!=manifest['resource_count']:
        raise ValueError('L1 resource counts differ from manifest')
    if not rows:
        raise ValueError('Empty batch')
    ensure_space(sum(len(r[4].encode('utf-8')) for r in rows)*2+30_000_000)
    with connect(database) as connection:
        initialize(connection)
        return {'batch_id':manifest['batch_id'], **append_rows(connection,rows)}
