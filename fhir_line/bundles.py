"""L0/L1: preserve each entry/resource JSON substring, including whitespace."""
import json

DECODER = json.JSONDecoder()


def whitespace(text, pos):
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def fields(text, start=0):
    pos = whitespace(text, start)
    if text[pos] != '{':
        raise ValueError('Expected JSON object')
    pos += 1
    while True:
        pos = whitespace(text, pos)
        if text[pos] == '}':
            return
        key, pos = DECODER.raw_decode(text, pos)
        pos = whitespace(text, pos)
        if text[pos] != ':':
            raise ValueError('Expected JSON field separator')
        begin = whitespace(text, pos+1)
        value, end = DECODER.raw_decode(text, begin)
        yield key, value, begin, end
        pos = whitespace(text, end)
        if text[pos] == '}':
            return
        if text[pos] != ',':
            raise ValueError('Expected JSON object separator')
        pos += 1


def entries(text):
    top = {key:(value, begin, end) for key,value,begin,end in fields(text)}
    if top.get('resourceType', (None,))[0] != 'Bundle':
        raise ValueError('Expected FHIR Bundle')
    if 'entry' not in top:
        return
    pos = top['entry'][1]+1
    while True:
        pos = whitespace(text, pos)
        if text[pos] == ']':
            return
        entry, end = DECODER.raw_decode(text, pos)
        resource = next((item for item in fields(text, pos) if item[0]=='resource'), None)
        if resource is None:
            raise ValueError('Bundle entry lacks resource')
        _, value, begin, finish = resource
        if not value.get('resourceType') or not value.get('id'):
            raise ValueError('Resource lacks resourceType or id')
        yield entry, text[pos:end], text[begin:finish]
        pos = whitespace(text, end)
        if text[pos] == ']':
            return
        if text[pos] != ',':
            raise ValueError('Expected JSON array separator')
        pos += 1


def replace_entries(text, selected_entries):
    """L0: keep the original Bundle wrapper; replace only its entry array."""
    entry_field = next((item for item in fields(text) if item[0]=='entry'),None)
    if entry_field is None:
        raise ValueError('Bundle lacks entry array')
    _, _, begin, end = entry_field
    return text[:begin]+'[\n'+',\n'.join(selected_entries)+'\n]'+text[end:]
