"""Pure wrist-yaw proposals and read-only IK consistency checks.

No command publication, profile mutation, clearance qualification or motion
authority lives here. In particular, Cartesian IK query targets are not the
receiver's nineteen independently evaluated joint-path FK samples.
"""
from __future__ import annotations

import math


def _vector(value, length: int, limit: float, name: str) -> list[float]:
    if (not isinstance(value, (list, tuple)) or len(value) != length
            or any(type(item) not in (int, float) or not math.isfinite(item)
                   or abs(item) > limit for item in value)):
        raise ValueError(f"Invalid finite {name}.")
    return list(value)


def local_wrist_pose(source_pose, delta_deg: float) -> list[float]:
    """Compose R_source * R_z(delta), holding the literal source XYZ.

    With a downward-facing tool, positive J6 commonly decreases BASE RZ.
    Even a small existing tilt changes the resulting literal roll and pitch;
    adding delta to the displayed RZ is not this operation.
    """
    pose = _vector(source_pose, 6, 10000, "BASE TCP pose")
    if any(abs(angle) > 180 for angle in pose[3:]):
        raise ValueError("Source Euler angles must use -180..180 degrees.")
    if (type(delta_deg) not in (int, float) or not math.isfinite(delta_deg)
            or not -90 <= delta_deg <= 90):
        raise ValueError("One wrist proposal must remain within 90 degrees.")
    rx, ry, rz = map(math.radians, pose[3:])
    cx, sx, cy, sy, cz, sz = (math.cos(rx), math.sin(rx), math.cos(ry),
                             math.sin(ry), math.cos(rz), math.sin(rz))
    rotation = ((cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx),
                (sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx),
                (-sy, cy*sx, cy*cx))
    c, s = math.cos(math.radians(delta_deg)), math.sin(math.radians(delta_deg))
    result = [(row[0]*c+row[1]*s, -row[0]*s+row[1]*c, row[2]) for row in rotation]
    return pose[:3] + [math.degrees(math.atan2(result[2][1], result[2][2])),
                      math.degrees(math.asin(max(-1., min(1., -result[2][0])))),
                      math.degrees(math.atan2(result[1][0], result[0][0]))]


def propose_wrist_turn(source_pose, source_joint, delta_deg: float) -> dict:
    """Return an unqualified candidate and optional read-only query targets."""
    pose = _vector(source_pose, 6, 10000, "BASE TCP pose")
    joints = _vector(source_joint, 6, 360, "joint vector")
    if (type(delta_deg) not in (int, float) or not math.isfinite(delta_deg)
            or not 0 < abs(delta_deg) <= 90):
        raise ValueError("A nonzero bounded wrist joint target is required.")
    requested = delta_deg
    target_j6 = joints[5]+requested
    effective = target_j6-joints[5]
    adjusted = abs(effective) > abs(requested) or abs(effective) > 90
    if adjusted:
        # Preserve the measured source exactly. Floating addition/subtraction
        # can represent source +/-90 as an effective 90.00000000000003 step.
        # Select the adjacent inward target, never widen a guard or round source.
        target_j6 = math.nextafter(target_j6, joints[5])
        effective = target_j6-joints[5]
    if (not 0 < abs(effective) <= min(abs(requested), 90)
            or (effective > 0) != (requested > 0) or abs(target_j6) > 360):
        raise ValueError("A nonzero representable bounded wrist joint target is required.")
    target = local_wrist_pose(pose, effective)
    return {
        "schema": "pushpilot.wrist-turn-candidate.v1",
        "source_pose": pose, "target_pose": target,
        "source_joint": joints,
        "target_joint": joints[:5]+[target_j6],
        "delta_j6_deg": effective,
        "requested_delta_j6_deg": requested,
        "representable_delta_j6_deg": effective,
        "target_j6_nextafter_applied": adjusted,
        "ik_query_targets": [local_wrist_pose(pose, effective*(i/18)) for i in range(18)]+[target[:]],
        "query_targets_are_measured_fk": False,
        "receiver_nineteen_joint_fk_samples_still_required": True,
        "tool_sweep_qualified": False, "car_turn_qualified": False,
        "motion_authority": False,
    }


def verify_endpoint_ik(candidate: dict, inspection: dict) -> dict:
    """Check one actual read-only endpoint IK result against a candidate.

    This verifies a reported kinematic solution only. It cannot establish
    swept finger clearance, loaded contact geometry, car motion or permission.
    Literal comparisons retain the inherited wrist tolerances; they do not
    silently treat a different Euler or joint winding as the same command.
    """
    if (candidate.get("schema") != "pushpilot.wrist-turn-candidate.v1"
            or candidate.get("motion_authority") is not False
            or inspection.get("status") != "ok"
            or inspection.get("motion_issued") is not False):
        raise ValueError("A genuine successful read-only endpoint inspection is required.")
    comparisons = (
        ("source_joint", "source_joint", .05, 360),
        ("solution_joint", "target_joint", .05, 360),
        ("source_pose", "source_pose", .1, 10000),
        ("target_fk", "target_pose", .1, 10000),
    )
    for observed_key, expected_key, tolerance, bound in comparisons:
        observed = _vector(inspection.get(observed_key), 6, bound, observed_key)
        expected = _vector(candidate.get(expected_key), 6, bound, expected_key)
        if any(abs(a-b) > tolerance+1e-9 for a, b in zip(observed, expected)):
            raise ValueError(f"Read-only wrist endpoint differs at {observed_key}.")
    return {"endpoint_ik_consistent": True, "motion_issued": False,
            "exact_joint_path_fk_verified": False, "tool_sweep_qualified": False,
            "car_turn_qualified": False, "motion_authority": False}
