"""Process-local folio registry.

State lives only in this worker process and never touches disk or another
service: each folio keeps its own delivered pages, so a same-numbered page of
another folio can never fill a gap here.
"""
from .contract import key
from .folio import (MAX_FRAGMENTS, MAX_REGISTRY, Booklet, compute_needs,
                    needs_payload, range_intersect, span_dict, validate_fragment)

_REGISTRY = {}


def reset():
    _REGISTRY.clear()


def open_booklet(data):
    booklet_id = key(data['booklet_id'])
    if booklet_id in _REGISTRY:
        raise ValueError(f'folio already opened: {booklet_id}')
    if len(_REGISTRY) >= MAX_REGISTRY:
        raise ValueError('folio registry is full')
    start, end, scopes, catalogue, needs = compute_needs(data)
    booklet = Booklet(booklet_id, start, end, scopes, catalogue, needs)
    _REGISTRY[booklet_id] = booklet
    return {
        'booklet_id': booklet_id,
        'from': start.isoformat(),
        'to': end.isoformat(),
        'scopes': [span_dict(span) for span in scopes],
        'expected_pages': booklet.expected_pages(),
        'needs': needs_payload(needs),
    }


def get_booklet(data):
    booklet_id = key(data['booklet_id'])
    booklet = _REGISTRY.get(booklet_id)
    if booklet is None:
        raise ValueError(f'unknown folio: {booklet_id}')
    return booklet


def deliver(data):
    booklet = get_booklet(data)
    page = key(data['page'])
    fragments = data['fragments']
    if type(fragments) is not list or not fragments or len(fragments) > MAX_FRAGMENTS:
        raise ValueError(f'expected a nonempty fragments array of at most {MAX_FRAGMENTS}')
    expected = set(booklet.expected_pages())
    if page not in expected:
        raise ValueError(f'page is not part of this folio: {page}')
    staged = {}
    for entry in fragments:
        identity, side, offset_range = validate_fragment(booklet, entry)
        if booklet.notice(identity).page != page:
            raise ValueError(f'notice {identity} is not attested by page {page}')
        staged.setdefault((identity, side), []).append(offset_range)
    for (identity, side), ranges in staged.items():
        within_batch = []
        for offset_range in ranges:
            if any(range_intersect(r, offset_range) for r in within_batch):
                raise ValueError(f'duplicate fragment inside delivery batch: {identity}')
            within_batch.append(offset_range)
        seen = booklet.covered_offsets(identity, side)
        for offset_range in ranges:
            if any(range_intersect(r, offset_range) for r in seen):
                raise ValueError(f'fragment overlaps an already delivered pair: {identity}')
            seen.append(offset_range)
        booklet.delivered.setdefault((identity, side), []).extend(ranges)
    missing = booklet.missing_pages()
    return {'booklet_id': booklet.booklet_id, 'page': page,
            'accepted_fragments': sum(len(v) for v in staged.values()),
            'complete': not missing, 'missing_pages': missing}


def status(data):
    booklet = get_booklet(data)
    expected = booklet.expected_pages()
    delivered = booklet.delivered_pages()
    return {
        'booklet_id': booklet.booklet_id,
        'from': booklet.start.isoformat(),
        'to': booklet.end.isoformat(),
        'expected_pages': expected,
        'delivered_pages': delivered,
        'missing_pages': booklet.missing_pages(),
        'complete': not booklet.missing_pages(),
    }
