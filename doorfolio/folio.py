"""Offline folio domain: scope-limited notices, offset math and page delivery.

A folio is a partial, offline copy of the municipal ledger restricted to a set
of authorized street blocks (``scopes``) and one fixed date window.  Its
catalogue notices are never copied wholesale: ``needs`` computes the exact
offset ranges reachable along forward/reverse paths from the scopes, and
delivered pages may only contain position-aligned fragments of those ranges.

All range work is integer arithmetic on (lo, hi, step) inclusive intervals;
door numbers of a long span are never enumerated.
"""
from dataclasses import dataclass, field
from itertools import groupby

from .contract import array, key, obj, rows
from .segment import Span, day

MAX_SCOPE_ROWS = 64
MAX_CATALOGUE = 128
MAX_FRAGMENTS = 128
MAX_REGISTRY = 32
MAX_REACH_SPANS = 2048


# --- inclusive integer ranges (lo, hi, step); lo and hi share step parity ---

def range_intersect(a, b):
    """Intersect two (lo, hi, step) ranges; return None when they do not meet."""
    lo_a, hi_a, step_a = a
    lo_b, hi_b, step_b = b
    low, high = max(lo_a, lo_b), min(hi_a, hi_b)
    if low > high:
        return None
    if step_a == 1 or step_b == 1:
        step = max(step_a, step_b)
        first = low + ((-low) % step)
        return (first, high, step) if first <= high else None
    if step_a != step_b:
        return None
    if (lo_b - lo_a) % step_a:
        return None
    if (low - lo_a) % step_a:
        low += step_a - ((low - lo_a) % step_a)
    return (low, high, step_a) if low <= high else None


def range_subtract(r, covered):
    """Subtract the covered ranges (same step as r); returns disjoint ranges."""
    pieces = [r]
    for cov_lo, cov_hi, cov_step in covered:
        cut = range_intersect(r, (cov_lo, cov_hi, cov_step))
        if cut is None:
            continue
        c_lo, c_hi, step = cut
        remaining = []
        for lo, hi, _ in pieces:
            before = (lo, min(hi, c_lo - step), step) if lo <= c_lo - step else None
            after = (max(lo, c_hi + step), hi, step) if c_hi + step <= hi else None
            remaining.extend(p for p in (before, after) if p is not None)
        pieces = remaining
    return pieces


def merge_ranges(ranges):
    """Merge ranges with equal step and parity that overlap or touch."""
    merged = []
    for step in sorted({r[2] for r in ranges}):
        current = None
        for lo, hi, _ in sorted(r for r in ranges if r[2] == step):
            if current is None:
                current = [lo, hi, step]
            elif lo <= current[1] + step and (lo - current[0]) % step == 0:
                current[1] = max(current[1], hi)
            else:
                merged.append(tuple(current))
                current = [lo, hi, step]
        if current is not None:
            merged.append(tuple(current))
    return merged


def range_has(ranges, value):
    return any(lo <= value <= hi and (value - lo) % step == 0
               for lo, hi, step in ranges)


def span_overlap(a, b):
    """Overlap of two spans expressed in offset ranges of span a (no enumeration)."""
    if a.street != b.street or a.step != b.step:
        return []
    a_lo, a_hi = min(a.first, a.last), max(a.first, a.last)
    b_lo, b_hi = min(b.first, b.last), max(b.first, b.last)
    door = range_intersect((a_lo, a_hi, abs(a.step)), (b_lo, b_hi, abs(b.step)))
    if door is None:
        return []
    lo, door_hi, _ = door
    offset_lo, rem = divmod(lo - a.first, a.step)
    offset_hi = (door_hi - a.first) // a.step
    assert rem == 0 and offset_lo >= 0 and offset_hi >= 0
    return [(min(offset_lo, offset_hi), max(offset_lo, offset_hi), 1)]


# --- catalogue and needs ----------------------------------------------------

@dataclass(frozen=True)
class CatalogueNotice:
    identity: str
    effective: object
    before: Span
    after: Span
    page: str

    def translate(self, point, reverse=False):
        source, dest = (self.after, self.before) if reverse else (self.before, self.after)
        offset = source.index(point)
        return dest.at(offset) if offset is not None else None


@dataclass
class Booklet:
    booklet_id: str
    start: object
    end: object
    scopes: list
    catalogue: list
    needs: dict
    # keyed by (notice_id, side); each value is a list of delivered offset ranges
    delivered: dict = field(default_factory=dict)

    def in_scope(self, point):
        return any(span.index(point) is not None for span in self.scopes)

    def notice(self, identity):
        found = [n for n in self.catalogue if n.identity == identity]
        return found[0] if found else None

    def covered_offsets(self, identity, side):
        return merge_ranges(list(self.delivered.get((identity, side), ())))

    def offset_pending(self, identity, side, offset):
        if not range_has(self.needs.get(identity, []), offset):
            return False
        return not range_has(self.covered_offsets(identity, side), offset)

    def expected_pages(self):
        return sorted({n.page for n in self.catalogue if self.needs.get(n.identity)})

    def notice_complete(self, notice):
        required = self.needs.get(notice.identity)
        if not required:
            return False
        for side in ('before', 'after'):
            covered = self.covered_offsets(notice.identity, side)
            if any(range_subtract(r, covered) for r in required):
                return False
        return True

    def delivered_pages(self):
        pages = set()
        for notice in self.catalogue:
            if self.notice_complete(notice):
                pages.add(notice.page)
        return sorted(pages)

    def missing_pages(self):
        return sorted(set(self.expected_pages()) - set(self.delivered_pages()))


def load_scopes(data):
    scopes = []
    for value in array(data['scopes'], MAX_SCOPE_ROWS):
        scopes.append(Span.load(obj(value)))
    if not scopes:
        raise ValueError('at least one scope block is required')
    return scopes


def load_catalogue(data):
    result = []
    for identity, row in rows(data, 'notices', MAX_CATALOGUE):
        before, after = Span.load(row['before']), Span.load(row['after'])
        if before.count != after.count:
            raise ValueError(f'unequal span cardinality: {identity}')
        result.append(CatalogueNotice(identity, day(row['effective']),
                                      before, after, key(row['page'])))
    return sorted(result, key=lambda n: (n.effective, n.identity))


def day_groups(catalogue, start, end):
    return [(d, list(rs)) for d, rs in groupby(catalogue, key=lambda r: r.effective)
            if start < d <= end]


def compute_needs(booklet_data):
    """Reachable offset ranges per notice along both path directions."""
    start, end = day(booklet_data['from']), day(booklet_data['to'])
    if start > end:
        raise ValueError('from must be no later than to')
    scopes, catalogue = load_scopes(booklet_data), load_catalogue(booklet_data)
    needs = {n.identity: [] for n in catalogue}
    groups = day_groups(catalogue, start, end)

    def run(reverse):
        reach = list(scopes)
        ordered = reversed(groups) if reverse else groups
        for _, rules in ordered:
            next_reach = []
            for span in reach:
                next_reach.append(span)
                for rule in rules:
                    source = rule.after if reverse else rule.before
                    destination = rule.before if reverse else rule.after
                    # offsets must be relative to the catalogue notice, so source goes first
                    for offset_range in span_overlap(source, span):
                        needs[rule.identity].append(offset_range)
                        lo, hi, step = offset_range
                        next_reach.append(Span(destination.street,
                                               destination.first + lo * destination.step,
                                               destination.first + hi * destination.step,
                                               destination.step * step))
            reach = merge_reachable(next_reach)
            if len(reach) > MAX_REACH_SPANS:
                raise ValueError('reachable span set exceeds limit; narrow the folio scope')

    run(False)
    run(True)
    compact = {}
    for identity, ranges in needs.items():
        merged = merge_ranges(ranges)
        if merged:
            compact[identity] = merged
    return start, end, scopes, catalogue, compact


def merge_reachable(spans):
    unique = {(s.street, s.first, s.last, s.step) for s in spans}
    merged = []
    for street in sorted({u[0] for u in unique}):
        same = sorted(u for u in unique if u[0] == street)
        bucket = []
        for _, first, last, step in same:
            bucket.append((first, last, step))
        for r in merge_ranges(bucket):
            merged.append(Span(street, r[0], r[1], r[2]))
    return merged


def span_dict(span):
    return {'street': span.street, 'first': span.first,
            'last': span.last, 'stride': abs(span.step)}


def needs_payload(needs):
    out = {}
    for identity, ranges in sorted(needs.items()):
        out[identity] = [{'offset_first': lo, 'offset_last': hi, 'offset_step': step}
                         for lo, hi, step in ranges]
    return out


# --- delivery validation ----------------------------------------------------

def validate_fragment(booklet, entry):
    row = obj(entry)
    identity = key(row['notice_id'])
    notice = booklet.notice(identity)
    if notice is None:
        raise ValueError(f'unknown catalogue notice: {identity}')
    required = booklet.needs.get(identity)
    if not required:
        raise ValueError(f'notice carries no pair needed by this folio: {identity}')
    side = key(row['side'])
    if side not in ('before', 'after'):
        raise ValueError("fragment side must be 'before' or 'after'")
    fragment = Span.load(row['span'])
    source = getattr(notice, side)
    if fragment.street != source.street or abs(fragment.step) != abs(source.step):
        raise ValueError(f'fragment is not position-aligned with notice {identity}')
    off_lo, rem = divmod(fragment.first - source.first, source.step)
    if rem != 0 or not 0 <= off_lo < source.count:
        raise ValueError(f'fragment is not position-aligned with notice {identity}')
    off_hi = (fragment.last - source.first) // source.step
    if not 0 <= off_lo <= off_hi < source.count:
        raise ValueError(f'fragment escapes notice span: {identity}')
    offset_range = (off_lo, off_hi, 1)
    if range_subtract(offset_range, required):
        raise ValueError(f'fragment contains pairs outside the folio need set: {identity}')
    already = booklet.covered_offsets(identity, side)
    if any(range_intersect(r, offset_range) for r in already):
        raise ValueError(f'fragment overlaps an already delivered pair: {identity}')
    return identity, side, offset_range
