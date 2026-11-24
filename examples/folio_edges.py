"""Long-span arithmetic folio and partial-delivery isolation checks."""
import json
from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsgiref.util import setup_testing_defaults

from doorfolio.app import application, PREFIX
from doorfolio import registry


def call(op, data):
    content = json.dumps(data, ensure_ascii=False).encode('utf-8')
    env = {}
    setup_testing_defaults(env)
    env.update(PATH_INFO=f'/{PREFIX}/{op}', REQUEST_METHOD='POST',
               CONTENT_TYPE='application/json', CONTENT_LENGTH=str(len(content)),
               **{'wsgi.input': BytesIO(content)})
    code = []
    body = b''.join(application(env, lambda s, _h: code.append(int(s.split()[0]))))
    return code[0], json.loads(body)


def frag(notice_id, side, street, first, last, stride=2):
    return {'notice_id': notice_id, 'side': side,
            'span': {'street': street, 'first': first, 'last': last, 'stride': stride}}


def main():
    registry.reset()

    # N6 spans a million doors; the folio only walks a four-door slice of it.
    notices = [{
        'id': 'N6', 'effective': '1971-05-01',
        'before': {'street': '旧栈巷', 'first': 2, 'last': 2_000_000, 'stride': 2},
        'after': {'street': '长港路', 'first': 1002, 'last': 2_001_000, 'stride': 2},
        'page': 'P9',
    }]
    payload = {
        'booklet_id': 'LONG', 'from': '1971-04-30', 'to': '1971-05-01',
        'scopes': [{'street': '旧栈巷', 'first': 100, 'last': 106, 'stride': 2}],
        'notices': notices,
    }
    code, res = call('booklet_open', payload)
    assert code == 200, (code, res)
    need = res['needs']['N6']
    # Only four offsets survive; the million-door span is never materialized.
    assert need == [{'offset_first': 49, 'offset_last': 52, 'offset_step': 1}], need

    # A fragment trying to smuggle a neighbouring pair is rejected.
    code, bad = call('booklet_deliver', {'booklet_id': 'LONG', 'page': 'P9', 'fragments': [
        frag('N6', 'before', '旧栈巷', 100, 108),
        frag('N6', 'after', '长港路', 1100, 1106)]})
    assert code == 400, bad
    # Exact sub-span delivery (the only pairs the path needs) succeeds.
    code, ok = call('booklet_deliver', {'booklet_id': 'LONG', 'page': 'P9', 'fragments': [
        frag('N6', 'before', '旧栈巷', 100, 106),
        frag('N6', 'after', '长港路', 1100, 1106)]})
    assert code == 200 and ok['complete'] is True, (code, ok)
    code, res = call('booklet_forward', {'booklet_id': 'LONG',
                                         'address': {'street': '旧栈巷', 'number': 104}})
    assert res['status'] == 'mapped', res
    assert res['candidates'][0] == {'street': '长港路', 'number': 1104,
                                    'paths': [[{'notice_id': 'N6', 'page': 'P9'}]]}, res
    print('LONG SPAN OK')

    # Two independent segments on one page's notice: a gap on one must not block the other.
    registry.reset()
    two = [
        {'id': 'A', 'effective': '1971-05-01',
         'before': {'street': '旧栈巷', 'first': 2, 'last': 4, 'stride': 2},
         'after': {'street': '渡口街', 'first': 20, 'last': 22, 'stride': 2}, 'page': 'PA'},
        {'id': 'B', 'effective': '1971-05-01',
         'before': {'street': '旧栈巷', 'first': 10, 'last': 12, 'stride': 2},
         'after': {'street': '渡口街', 'first': 30, 'last': 32, 'stride': 2}, 'page': 'PB'},
    ]
    code, res = call('booklet_open', {
        'booklet_id': 'SPLIT', 'from': '1971-04-30', 'to': '1971-05-01',
        'scopes': [{'street': '旧栈巷', 'first': 2, 'last': 12, 'stride': 2}],
        'notices': two})
    assert code == 200, (code, res)
    # Deliver page PA only; PB stays missing.
    code, ok = call('booklet_deliver', {'booklet_id': 'SPLIT', 'page': 'PA', 'fragments': [
        frag('A', 'before', '旧栈巷', 2, 4), frag('A', 'after', '渡口街', 20, 22)]})
    assert code == 200, ok
    code, res = call('booklet_forward', {'booklet_id': 'SPLIT',
                                         'address': {'street': '旧栈巷', 'number': 2}})
    assert res['status'] == 'mapped', res
    assert res['candidates'][0]['street'] == '渡口街'
    code, res = call('booklet_forward', {'booklet_id': 'SPLIT',
                                         'address': {'street': '旧栈巷', 'number': 10}})
    assert res['status'] == 'incomplete', res
    assert [p['page'] for p in res['pending']] == ['PB'], res
    print('SEGMENT ISOLATION OK')

    # Invalid contracts all remain 400.
    code, res = call('booklet_status', {'booklet_id': 'NOPE'})
    assert code == 400, res
    code, res = call('booklet_forward', {'booklet_id': 'SPLIT'})  # missing address
    assert code == 400, res
    code, res = call('booklet_forward', {'booklet_id': 'NOPE',
                                         'address': {'street': 'x', 'number': 1}})
    assert code == 400, res
    print('CONTRACT OK')
    print('ALL EDGE CHECKS PASSED')


if __name__ == '__main__':
    main()
