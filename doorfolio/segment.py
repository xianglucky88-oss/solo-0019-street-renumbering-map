"""Translate a renumbering notice without enumerating every door."""
from dataclasses import dataclass
from datetime import date

from .contract import integer, key, obj, rows


def day(value):
    text = key(value)
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise ValueError('date must take YYYY-MM-DD form')
    return parsed


@dataclass(frozen=True, order=True)
class Address:
    street: str
    number: int

    @classmethod
    def load(cls, raw):
        row = obj(raw)
        return cls(key(row['street']), integer(row['number'], 1, 10**9))


@dataclass(frozen=True)
class Span:
    street: str
    first: int
    last: int
    step: int

    @classmethod
    def load(cls, raw):
        row = obj(raw)
        first, last = (integer(row[k], 1, 10**9) for k in ('first', 'last'))
        stride = integer(row['stride'], 1, 2)
        if (last - first) % stride:
            raise ValueError('last door must be a member of its span')
        return cls(key(row['street']), first, last, stride if first <= last else -stride)

    @property
    def count(self):
        return (self.last - self.first) // self.step + 1

    def index(self, a):
        if a.street != self.street:
            return None
        offset, remainder = divmod(a.number - self.first, self.step)
        return offset if remainder == 0 and 0 <= offset < self.count else None

    def at(self, offset):
        return Address(self.street, self.first + offset * self.step)

    def common_door(self, other):
        if self.street != other.street:
            return None
        low = max(min(self.first, self.last), min(other.first, other.last))
        high = min(max(self.first, self.last), max(other.first, other.last))
        for n in range(low, min(high + 1, low + 2)):
            point = Address(self.street, n)
            if self.index(point) is not None and other.index(point) is not None:
                return point
        return None


@dataclass(frozen=True)
class Notice:
    identity: str
    effective: date
    before: Span
    after: Span

    def translate(self, point, reverse=False):
        source, dest = (self.after, self.before) if reverse else (self.before, self.after)
        offset = source.index(point)
        return dest.at(offset) if offset is not None else None


def notices(data):
    result = []
    for identity, row in rows(data, 'notices', 128):
        before, after = Span.load(row['before']), Span.load(row['after'])
        if before.count != after.count:
            raise ValueError(f'unequal span cardinality: {identity}')
        result.append(Notice(identity, day(row['effective']), before, after))
    return sorted(result, key=lambda n: (n.effective, n.identity))
