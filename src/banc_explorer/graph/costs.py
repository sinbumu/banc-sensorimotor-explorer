import math
from enum import StrEnum

import numpy as np


class PathMode(StrEnum):
    hops = "hops"
    normalized = "normalized"


def normalized_cost(norm: float, epsilon: float = 1e-12) -> float:
    if not math.isfinite(norm) or not 0 <= norm <= 1:
        raise ValueError("Normalized input contribution must be finite and in [0, 1].")
    if not math.isfinite(epsilon) or not 0 < epsilon <= 1:
        raise ValueError("epsilon must be finite and in (0, 1].")
    return -math.log(max(norm, epsilon))


def normalized_weights(counts, post_counts, epsilon: float) -> np.ndarray:
    normalized_cost(1, epsilon)
    return -np.log(np.maximum(counts / post_counts, epsilon))


def raw_count_cost(count: int) -> float:
    """Experimental alternative; not a biological likelihood and not a default mode."""
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("count must be a positive integer.")
    return 1 / math.log1p(count)


def cost_definition(mode: PathMode) -> str:
    return (
        "1 per directed edge" if mode == PathMode.hops else "-log(max(count/post_count, epsilon))"
    )
