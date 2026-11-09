"""Dimensionless path weights with the original selected-seed vote budget."""
import math


def local_mean_factors(path, scores):
    """Return mean-one factors on the frozen ordered candidate list.

    Rescale by max first to avoid underflow/overflow in arbitrary score units.
    This does not change the relative weights or add a fitted coefficient.
    """
    if len(set(path)) != len(path):
        raise ValueError('Selected path chunk IDs must be unique')
    if not path:
        return {}
    values = [float(scores[cid]) for cid in path]
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Path chunk weights must be finite and nonnegative')
    maximum = max(values)
    if maximum <= 0:
        raise ValueError('Selected path chunk weights cannot all be zero')
    scaled = [v / maximum for v in values]
    total = math.fsum(scaled)
    factors = [len(path) * (v / total) for v in scaled]
    if not math.isclose(math.fsum(factors), len(path), rel_tol=1e-12, abs_tol=1e-12):
        raise ArithmeticError('Calibrated path weights changed the seed vote budget')
    return dict(zip(path, factors))
