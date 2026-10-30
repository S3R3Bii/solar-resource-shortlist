"""Six simple history-only scores for a finite solar-resource shortlist."""

import math, statistics
from fractions import Fraction as Q

CONFIGS = ["persistence", "mean3", "mean5", "mean10", "median10", "q20_10"]


def predict(history, config):
    assert len(history) >= 10
    if config == "persistence":
        return history[-1]
    if config.startswith("mean"):
        n = int(config[4:])
        return sum(history[-n:], Q()) / n
    if config == "median10":
        return statistics.median(history[-10:])
    if config == "q20_10":
        return sorted(history[-10:])[1]
    raise ValueError(config)


def rank(values):
    return {
        k: Q(1)
        + sum(v > values[k] for v in values.values())
        + Q(sum(v == values[k] for v in values.values()) - 1, 2)
        for k in values
    }


def shortlist(values):
    return sorted(values, key=lambda k: (-values[k], k))[:2]


def correlation(a, b):
    assert set(a) == set(b)
    x = rank(a)
    y = rank(b)
    n = len(x)
    mx = sum(x.values(), Q()) / n
    my = sum(y.values(), Q()) / n
    cov = sum((x[k] - mx) * (y[k] - my) for k in x)
    vx = sum((v - mx) ** 2 for v in x.values())
    vy = sum((v - my) ** 2 for v in y.values())
    return float(cov) / math.sqrt(float(vx * vy)) if vx and vy else None


def boundary_ties(values):
    chosen = shortlist(values)
    score = values[chosen[-1]]
    tied = sorted(k for k in values if values[k] == score)
    above = sum(v > score for v in values.values())
    return tied, above + len(tied) > 2
