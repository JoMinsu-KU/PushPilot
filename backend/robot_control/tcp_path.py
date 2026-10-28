"""Pure subdivision of a taught TCP line; no endpoint or car qualification.

Coordinates must already share a robot frame. This utility neither establishes
that frame nor checks workspace, contact, clearance, execution or vehicle motion.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Pose = tuple[float, float, float, float, float, float]


def _pose(value: Sequence[float]) -> Pose:
    try:
        items = tuple(value)
    except TypeError as error:
        raise ValueError("A TCP pose needs six finite numbers.") from error
    if len(items) != 6 or any(type(x) not in (int, float) or not math.isfinite(x) for x in items):
        raise ValueError("A TCP pose needs six finite numbers.")
    return tuple(float(x) for x in items)


def split_fixed_pose_tcp_segment(
    start_pose6: Sequence[float], end_pose6: Sequence[float], max_step_mm: float,
) -> tuple[Pose, ...]:
    """Return line targets excluding start, including exact end, at fixed Z/angles.

    At most 1,000 targets are returned. Literal orientation equality is required;
    equivalent wrapped angles are not silently substituted. No dispatch occurs.
    """
    start, end = _pose(start_pose6), _pose(end_pose6)
    if type(max_step_mm) not in (int, float) or not math.isfinite(max_step_mm) or not 0 < max_step_mm <= 20:
        raise ValueError("max_step_mm must be finite, positive and at most 20.")
    if start[2:] != end[2:]:
        raise ValueError("TCP Z and literal orientation must stay unchanged.")
    distance = math.dist(start[:2], end[:2])
    if distance == 0:
        return ()
    ratio = distance / max_step_mm
    if not math.isfinite(ratio) or ratio > 1000:
        raise ValueError("Segment exceeds the 1,000-target budget.")
    count = math.ceil(ratio)
    # Compute each point from the original endpoints, never accumulated deltas.
    # One extra subdivision can resolve rounding at an exact step boundary.
    for size in (count, count + 1):
        if size > 1000:
            break
        targets = tuple(
            (start[0] + (end[0] - start[0]) * i / size,
             start[1] + (end[1] - start[1]) * i / size, *start[2:])
            for i in range(1, size)
        ) + (end,)
        pairs = zip((start,) + targets[:-1], targets)
        if all(a != b and math.dist(a[:2], b[:2]) <= max_step_mm for a, b in pairs):
            return targets
    raise ValueError("Coordinate precision cannot preserve the step bound within the budget.")
