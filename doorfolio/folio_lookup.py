"""Folio query reducers: authorized forward and reverse evidence lookups."""
from dataclasses import asdict

from .bookwalk import book_walk
from .registry import get_booklet
from .segment import Address


def _query(data, reverse):
    booklet = get_booklet(data)
    point = Address.load(data['address'])
    if not booklet.in_scope(point):
        return {'status': 'out_of_scope', 'candidates': [], 'pending': [],
                'reason': 'address is outside the authorized street blocks of this folio'}
    found, pending = book_walk(booklet, point, reverse=reverse)
    candidates = [{**asdict(address), 'paths': proofs}
                  for address, proofs in found.items()]
    if pending:
        status = 'incomplete'
    elif len(candidates) > 1:
        status = 'ambiguous'
    elif candidates and candidates[0]['paths'] != [[]]:
        status = 'mapped'
    else:
        status = 'unchanged'
    return {'status': status, 'candidates': candidates, 'pending': pending}


def booklet_forward(data):
    return _query(data, False)


def booklet_reverse(data):
    return _query(data, True)
