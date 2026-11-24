"""End-to-end scenario from the two-day two-road convergence requirement."""
import json
from io import BytesIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsgiref.util import setup_testing_defaults

from doorfolio.app import application, PREFIX
from doorfolio import registry

# Day 1: 旧栈巷 even numbers split to 过渡街 (N1) and 渡口街 (N2).
# Day 2: both roads converge onto the same 新港街 even numbers (N3, N4).
NOTICES = [
    {
        'id': 'N1', 'effective': '1971-04-01',
        'before': {'street': '旧栈巷', 'first': 2, 'last': 8, 'stride': 2},
        'after': {'street': '过渡街', 'first': 20, 'last': 26, 'stride': 2},
        'page': 'P1',
    },
    {
        'id': 'N2', 'effective': '1971-04-01',
        'before': {'street': '旧栈巷', 'first': 2, 'last': 8, 'stride': 2},
        'after': {'street': '渡口街', 'first': 40, 'last': 46, 'stride': 2},
        'page': 'P2',
    },
    {
        'id': 'N3', 'effective': '1971-04-02',
        'before': {'street': '过渡街', 'first': 20, 'last': 26, 'stride': 2},
        'after': {'street': '新港街', 'first': 100, 'last': 106, 'stride': 2},
        'page': 'P3',
    },
    {
        'id': 'N4', 'effective': '1971-04-02',
        'before': {'street': '渡口街', 'first': 40, 'last': 46, 'stride': 2},
        'after': {'street': '新港街', 'first': 100, 'last': 106, 'stride': 2},
        'page': 'P4',
    },
]

OPEN = {
    'booklet_id': 'B1',
    'from': '1971-03-31',
    'to': '1971-04-02',
    'scopes': [
        {'street': '旧栈巷', 'first': 2, 'last': 8, 'stride': 2},
        {'street': '新港街', 'first': 100, 'last': 106, 'stride': 2},
    ],
    'notices': NOTICES,
}


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
    code, res = call('booklet_open', OPEN)
    assert code == 200, (code, res)
    print('OPEN:', json.dumps(res, ensure_ascii=False, indent=1))
    needs = res['needs']
    # Every catalogue notice is needed in full along the forward/reverse paths.
    assert set(needs) == {'N1', 'N2', 'N3', 'N4'}, needs
    assert res['expected_pages'] == ['P1', 'P2', 'P3', 'P4']

    code, status = call('booklet_status', {'booklet_id': 'B1'})
    assert status['delivered_pages'] == [] and status['missing_pages'] == ['P1', 'P2', 'P3', 'P4']

    # Query before any page arrives: complete evidence missing on every branch.
    code, res = call('booklet_forward', {'booklet_id': 'B1',
                                         'address': {'street': '旧栈巷', 'number': 2}})
    assert code == 200 and res['status'] == 'incomplete', (code, res)
    assert {p['page'] for p in res['pending']} == {'P1', 'P2'}, res
    assert res['candidates'] == [], res
    print('EMPTY FWD:', json.dumps(res, ensure_ascii=False))

    # Deliver P1 and P3 (the 过渡街 route only), each in two batches.
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P1', 'fragments': [
        frag('N1', 'before', '旧栈巷', 2, 4), frag('N1', 'after', '过渡街', 20, 24)]})
    assert code == 200, r
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P1', 'fragments': [
        frag('N1', 'before', '旧栈巷', 6, 8), frag('N1', 'after', '过渡街', 26, 26)]})
    assert code == 200, r
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P3', 'fragments': [
        frag('N3', 'before', '过渡街', 20, 26), frag('N3', 'after', '新港街', 100, 106)]})
    assert code == 200, r

    # Overlap re-delivery must be rejected.
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P1', 'fragments': [
        frag('N1', 'before', '旧栈巷', 4, 6)]})
    assert code == 400, r
    # Pair not needed by this folio (a door outside scope paths) must be rejected.
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P1', 'fragments': [
        frag('N1', 'after', '过渡街', 28, 28)]})
    assert code == 400, r
    # Page P2 fragment cannot ride in under P1's delivery.
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P1', 'fragments': [
        frag('N2', 'before', '旧栈巷', 2, 2)]})
    assert code == 400, r

    # Now forward query: one route provable, the other names the missing page P2.
    code, res = call('booklet_forward', {'booklet_id': 'B1',
                                         'address': {'street': '旧栈巷', 'number': 2}})
    assert code == 200, (code, res)
    print('PARTIAL FWD:', json.dumps(res, ensure_ascii=False, indent=1))
    assert res['status'] == 'incomplete'
    assert [p['page'] for p in res['pending']] == ['P2'], res
    cand = res['candidates']
    assert len(cand) == 1 and cand[0]['street'] == '新港街' and cand[0]['number'] == 100
    hops = cand[0]['paths'][0]
    assert [(h['notice_id'], h['page']) for h in hops] == [('N1', 'P1'), ('N3', 'P3')]
    # Intermediate address on the not-open street is visible inside the proven path.
    assert any(h['notice_id'] == 'N1' for h in hops)

    # Explicit reverse lookup is also not allowed to claim completeness.
    code, res = call('booklet_reverse', {'booklet_id': 'B1',
                                         'address': {'street': '新港街', 'number': 100}})
    assert code == 200 and res['status'] == 'incomplete', (code, res)
    print('PARTIAL REV:', json.dumps(res, ensure_ascii=False, indent=1))
    assert [p['page'] for p in res['pending']] == ['P4'], res
    assert len(res['candidates']) == 1
    rev = res['candidates'][0]
    assert rev['street'] == '旧栈巷' and rev['number'] == 2
    assert [(h['notice_id'], h['page']) for h in rev['paths'][0]] == [('N3', 'P3'), ('N1', 'P1')]

    # Unauthorized direct query on the transit street: out_of_scope, distinct state.
    code, res = call('booklet_forward', {'booklet_id': 'B1',
                                         'address': {'street': '过渡街', 'number': 20}})
    assert code == 200 and res['status'] == 'out_of_scope', (code, res)
    print('OUT OF SCOPE:', json.dumps(res, ensure_ascii=False))

    # An unaffected segment that does not need P2/P4 is fully answerable:
    # open a second folio scoped only to an unchanged block.
    code, r2 = call('booklet_open', {
        'booklet_id': 'B2', 'from': '1971-03-31', 'to': '1971-04-02',
        'scopes': [{'street': '静宁里', 'first': 1, 'last': 3, 'stride': 2}],
        'notices': NOTICES})
    assert code == 200 and r2['needs'] == {} and r2['expected_pages'] == [], r2
    code, res = call('booklet_forward', {'booklet_id': 'B2',
                                         'address': {'street': '静宁里', 'number': 1}})
    assert code == 200 and res['status'] == 'unchanged', (code, res)
    print('UNCHANGED:', json.dumps(res, ensure_ascii=False))

    # Complete the missing pages of B1.
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P2', 'fragments': [
        frag('N2', 'before', '旧栈巷', 2, 8), frag('N2', 'after', '渡口街', 40, 46)]})
    assert code == 200, r
    code, r = call('booklet_deliver', {'booklet_id': 'B1', 'page': 'P4', 'fragments': [
        frag('N4', 'before', '渡口街', 40, 46), frag('N4', 'after', '新港街', 100, 106)]})
    assert code == 200 and r['complete'] is True and r['missing_pages'] == [], r
    code, status = call('booklet_status', {'booklet_id': 'B1'})
    assert status['complete'] is True

    # Both routes now required: same final address carries two distinct provenance paths.
    code, res = call('booklet_forward', {'booklet_id': 'B1',
                                         'address': {'street': '旧栈巷', 'number': 2}})
    assert res['status'] == 'mapped' and not res['pending'], res
    print('COMPLETE FWD:', json.dumps(res, ensure_ascii=False, indent=1))
    addr = {(c['street'], c['number']): c['paths'] for c in res['candidates']}
    assert set(addr) == {('新港街', 100)}, addr
    paths = addr[('新港街', 100)]
    signed = {tuple((h['notice_id'], h['page']) for h in p) for p in paths}
    assert signed == {(('N1', 'P1'), ('N3', 'P3')), (('N2', 'P2'), ('N4', 'P4'))}, signed

    # Reverse now reports both registration paths back to the same old door.
    code, res = call('booklet_reverse', {'booklet_id': 'B1',
                                         'address': {'street': '新港街', 'number': 102}})
    assert res['status'] == 'mapped', res
    origins = {(c['street'], c['number']) for c in res['candidates']}
    assert origins == {('旧栈巷', 4)}, (res, origins)
    assert len(res['candidates'][0]['paths']) == 2
    print('COMPLETE REV:', json.dumps(res, ensure_ascii=False, indent=1))

    # A same-numbered page in another folio cannot fill B gaps: B3 missing P3.
    code, _ = call('booklet_open', {**OPEN, 'booklet_id': 'B3'})
    assert code == 200
    code, r = call('booklet_deliver', {'booklet_id': 'B3', 'page': 'P3', 'fragments': [
        frag('N3', 'before', '过渡街', 20, 26), frag('N3', 'after', '新港街', 100, 106)]})
    assert code == 200
    code, res = call('booklet_forward', {'booklet_id': 'B3',
                                         'address': {'street': '旧栈巷', 'number': 2}})
    assert res['status'] == 'incomplete'
    assert {p['page'] for p in res['pending']} == {'P1', 'P2'}, res
    print('CROSS FOLIO ISOLATION OK')

    # Same-day rules do not chain: N1 output 过渡街20 is not re-consumed by N2.
    # Evidenced by only two candidate paths (each exactly two hops) above.
    print('ALL SCENARIO CHECKS PASSED')


if __name__ == '__main__':
    main()
