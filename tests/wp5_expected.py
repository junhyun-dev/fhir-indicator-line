"""D5,D6 / ADR0015: read reviewed WP-5 values; never derive expectations from SQL."""
import hashlib
import json

from fhir_line.runtime import ROOT

FIELDS = ('last_bp_date', 'systolic', 'diastolic', 'controlled', 'reason')
EXPECTED_SHA256 = 'd175f6415ddd840af6a1c374d5c9a54b457b39317186687e103deaa31c484600'


def expected():
    body = (ROOT / 'answer_key_lead/wp5-bp-days-both-values/expected.json').read_bytes()
    if hashlib.sha256(body).hexdigest() != EXPECTED_SHA256:
        raise ValueError('WP5_EXPECTED_HASH_MISMATCH')
    return json.loads(body)


def cases(group):
    return [case for case in expected()['cases'] if case['group'] == group]


def person_values(case):
    return tuple(case['new_expected'][key] for key in FIELDS)
