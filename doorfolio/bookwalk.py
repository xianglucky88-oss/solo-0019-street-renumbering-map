"""Evidence-aware daily walk over a partially delivered folio.

Same-day rules still never chain, odd/even and reversed spans keep the old
semantics.  A rule only emits a branch when the exact pair offset has been
delivered on its page; a catalogue rule that covers the address but whose page
is still missing records a pending witness instead of a fake answer.
"""
from dataclasses import asdict

from .folio import day_groups

MAX_PATHS = 512


def book_walk(booklet, point, reverse=False):
    groups = day_groups(booklet.catalogue, booklet.start, booklet.end)
    states = {(point, ())}
    pending = {}

    def note(missing_page, notice, address):
        witness = (missing_page, notice.identity,
                   asdict(address)['street'], asdict(address)['number'])
        if witness not in pending:
            pending[witness] = {
                'page': missing_page,
                'notice_id': notice.identity,
                'effective': notice.effective.isoformat(),
                'at': asdict(address),
            }

    for _, rules in reversed(groups) if reverse else groups:
        next_states = set()
        for address, path in states:
            matched = False
            for rule in rules:
                source_side = 'after' if reverse else 'before'
                source = rule.after if reverse else rule.before
                offset = source.index(address)
                if offset is None:
                    continue
                matched = True
                if booklet.offset_pending(rule.identity, source_side, offset):
                    note(rule.page, rule, address)
                    continue
                destination = rule.translate(address, reverse)
                next_states.add((destination, path + ((rule.identity, rule.page),)))
            if not matched:
                next_states.add((address, path))
            if len(next_states) > MAX_PATHS:
                raise ValueError('notice paths exceed 512; narrow date range')
        states = next_states

    candidates = {}
    for address, path in sorted(states):
        candidates.setdefault(address, []).append([
            {'notice_id': nid, 'page': pid} for nid, pid in path])
    return candidates, [pending[k] for k in sorted(pending)]
