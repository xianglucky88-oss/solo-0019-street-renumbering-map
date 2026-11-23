"""Advance one day atomically; notices of the same effective day do not chain."""
from itertools import groupby


def walk(point, start, end, notices, reverse=False):
    states = {(point, ())}
    groups = [(d, list(rs)) for d, rs in groupby(notices, key=lambda r: r.effective) if start < d <= end]
    for _, rules in reversed(groups) if reverse else groups:
        next_states = set()
        for address, path in states:
            matched = False
            for rule in rules:
                dest = rule.translate(address, reverse)
                if dest is not None:
                    next_states.add((dest, path + (rule.identity,)))
                    matched = True
            if not matched:
                next_states.add((address, path))
            if len(next_states) > 512:
                raise ValueError('notice paths exceed 512; narrow date range')
        states = next_states
    answers = {}
    for address, path in sorted(states):
        answers.setdefault(address, []).append(list(path))
    return answers
