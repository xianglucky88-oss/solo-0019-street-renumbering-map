from dataclasses import asdict
from itertools import combinations

from .segment import Address, day, notices
from .walk import walk


def lookup(data, reverse=False):
    point = Address.load(data['address'])
    start, end = day(data['from']), day(data['to'])
    if start > end:
        raise ValueError('from must be no later than to')
    answers = walk(point, start, end, notices(data), reverse)
    result = [{**asdict(address), 'paths': proofs} for address, proofs in answers.items()]
    status = 'ambiguous' if len(result) > 1 else 'unchanged' if result[0]['paths'] == [[]] else 'mapped'
    return {'status': status, 'candidates': result}


def forward(data):
    return lookup(data)


def reverse(data):
    return lookup(data, reverse=True)


def inspect(data):
    report = []
    for a, b in combinations(notices(data), 2):
        if a.effective != b.effective:
            continue
        for direction in ('before', 'after'):
            point = getattr(a, direction).common_door(getattr(b, direction))
            if point is not None:
                report.append({'side': direction, 'notice_ids': [a.identity, b.identity],
                               'effective': a.effective.isoformat(), 'witness': asdict(point)})
    return {'overlaps': report}
