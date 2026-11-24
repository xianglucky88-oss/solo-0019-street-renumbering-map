"""Verify the offline folio workflow: open, partial delivery, gaps, completion."""
import json
from io import BytesIO
from pathlib import Path
from wsgiref.util import setup_testing_defaults

from doorfolio import registry
from doorfolio.app import PREFIX, application

BASE = Path(__file__).resolve().parent


def request(op, data):
    content = json.dumps(data, ensure_ascii=False).encode('utf-8')
    env = {}
    setup_testing_defaults(env)
    env.update(PATH_INFO=f'/{PREFIX}/{op}', REQUEST_METHOD='POST',
               CONTENT_TYPE='application/json', CONTENT_LENGTH=str(len(content)),
               **{'wsgi.input': BytesIO(content)})
    status = []
    response = json.loads(b''.join(application(env, lambda code, _: status.append(int(code.split()[0])))))
    return status[0], response


def frag(notice_id, side, street, first, last, stride=2):
    return {'notice_id': notice_id, 'side': side,
            'span': {'street': street, 'first': first, 'last': last, 'stride': stride}}


def main():
    registry.reset()
    opened = json.loads((BASE / 'folio.open.json').read_text(encoding='utf-8'))
    code, res = request('booklet_open', opened)
    if code != 200:
        raise RuntimeError((code, res))
    assert res['expected_pages'] == ['P1', 'P2', 'P3', 'P4']
    assert res['needs']['N1'] == [{'offset_first': 0, 'offset_last': 3, 'offset_step': 1}]

    query = {'booklet_id': 'demo-folio', 'address': {'street': '旧栈巷', 'number': 2}}

    # Nothing delivered yet: both day-one branches are pending, named by page.
    code, res = request('booklet_forward', query)
    assert code == 200 and res['status'] == 'incomplete'
    assert {p['page'] for p in res['pending']} == {'P1', 'P2'}
    assert res['candidates'] == []

    # Deliver only the 过渡街 route pages P1 and P3, in separate requests.
    code, _ = request('booklet_deliver', {'booklet_id': 'demo-folio', 'page': 'P1', 'fragments': [
        frag('N1', 'before', '旧栈巷', 2, 8), frag('N1', 'after', '过渡街', 20, 26)]})
    assert code == 200
    code, _ = request('booklet_deliver', {'booklet_id': 'demo-folio', 'page': 'P3', 'fragments': [
        frag('N3', 'before', '过渡街', 20, 26), frag('N3', 'after', '新港街', 100, 106)]})
    assert code == 200

    # One proven route; the surviving route must not be reported as a full answer.
    code, res = request('booklet_forward', query)
    assert code == 200 and res['status'] == 'incomplete'
    assert [p['page'] for p in res['pending']] == ['P2']
    candidate = res['candidates'][0]
    assert (candidate['street'], candidate['number']) == ('新港街', 100)
    assert [(h['notice_id'], h['page']) for h in candidate['paths'][0]] == [
        ('N1', 'P1'), ('N3', 'P3')]

    # Explicit reverse lookup is incomplete as well and names P4.
    code, res = request('booklet_reverse',
                        {'booklet_id': 'demo-folio',
                         'address': {'street': '新港街', 'number': 100}})
    assert code == 200 and res['status'] == 'incomplete'
    assert [p['page'] for p in res['pending']] == ['P4']

    # The transit street is visible as an intermediate hop but cannot be queried alone.
    code, res = request('booklet_forward',
                        {'booklet_id': 'demo-folio',
                         'address': {'street': '过渡街', 'number': 20}})
    assert code == 200 and res['status'] == 'out_of_scope'

    # Smuggling an unneeded pair, or a foreign page's notice, is rejected.
    code, res = request('booklet_deliver', {'booklet_id': 'demo-folio', 'page': 'P1', 'fragments': [
        frag('N1', 'after', '过渡街', 28, 28)]})
    assert code == 400
    code, res = request('booklet_deliver', {'booklet_id': 'demo-folio', 'page': 'P1', 'fragments': [
        frag('N2', 'before', '旧栈巷', 2, 2)]})
    assert code == 400

    # Complete the 渡口街 route; both provenance paths then resolve together.
    code, _ = request('booklet_deliver', {'booklet_id': 'demo-folio', 'page': 'P2', 'fragments': [
        frag('N2', 'before', '旧栈巷', 2, 8), frag('N2', 'after', '渡口街', 40, 46)]})
    assert code == 200
    code, delivered = request('booklet_deliver', {'booklet_id': 'demo-folio', 'page': 'P4', 'fragments': [
        frag('N4', 'before', '渡口街', 40, 46), frag('N4', 'after', '新港街', 100, 106)]})
    assert code == 200 and delivered['complete'] is True

    code, res = request('booklet_forward', query)
    assert code == 200 and res['status'] == 'mapped' and not res['pending']
    paths = {tuple((h['notice_id'], h['page']) for h in p)
             for p in res['candidates'][0]['paths']}
    assert paths == {(('N1', 'P1'), ('N3', 'P3')), (('N2', 'P2'), ('N4', 'P4'))}

    code, state = request('booklet_status', {'booklet_id': 'demo-folio'})
    assert code == 200 and state['complete'] is True and state['missing_pages'] == []
    print(json.dumps({'final_forward': res, 'status': state}, ensure_ascii=False, indent=2))
    print('FOLIO WORKFLOW CHECKS PASSED')


if __name__ == '__main__':
    main()
