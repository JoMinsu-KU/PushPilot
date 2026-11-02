"""Immutable teaching coordinates with an explicit, stationary session readback.

This is not automatic calibration. A private, Native-evidenced connection
record may resolve at most 0.005 mm/degree of START readback precision. Teaching
files, route vertices and safety limits remain the source of authority.
"""
from copy import deepcopy
import math
import re

from .mission_catalog import content_hash
from .wrist_commissioning import local_wrist_pose

MAX_START_READBACK_DIFFERENCE = .005


def apply_start_reference(packet, review, reference, packet_sha, review_sha):
    required = {"schema", "session_id", "packet_sha256", "review_sha256", "nominal_start",
                "observed_start", "native_snapshot", "review_reference", "operator_request"}
    if (not isinstance(reference, dict) or set(reference) != required
            or reference["schema"] != "pushpilot.stationary-start-reference.v1"
            or not re.fullmatch(r"[0-9a-f]{32}", reference["session_id"])
            or reference["packet_sha256"] != packet_sha or reference["review_sha256"] != review_sha):
        raise ValueError("The stationary START reference must bind its exact session and original teaching files.")
    nominal, actual = reference["nominal_start"], reference["observed_start"]
    for p in (nominal, actual):
        if (not isinstance(p, list) or len(p) != 6
                or any(type(x) not in (float, int) or not math.isfinite(x) for x in p)):
            raise ValueError("Use finite START poses.")
    if any(abs(a-b) > MAX_START_READBACK_DIFFERENCE for a, b in zip(nominal, actual)):
        raise ValueError("START readback differs beyond the precision-only allowance; do not rebase the route.")
    native = reference["native_snapshot"]
    if (native.get("session_id") != reference["session_id"] or native.get("tcp_base") != actual
            or native.get("held_disarmed_idle") is not True
            or not re.fullmatch(r"[0-9a-f]{64}", native.get("native_evidence_sha256", ""))
            or len(native.get("native_tcp_base", [])) != 6
            or any(abs(a-b) > .100001 for a, b in zip(native["native_tcp_base"], actual))):
        raise ValueError("Require the retained independent stationary Native START proof.")
    if any(packet["contexts"][r["start_context_id"]]["pose_base"] != nominal for r in packet["routes"].values()):
        raise ValueError("All recipes must retain the same original common START.")
    # The existing taught family is departure, one -89.999 J6 turn and two
    # -89.999 turns. Preserve that directed family, never infer Euler wrapping.
    old_family, new_family = [nominal], [actual]
    for _ in range(2):
        old_family.append(local_wrist_pose(old_family[-1], -89.999))
        new_family.append(local_wrist_pose(new_family[-1], -89.999))

    def pose(p):
        matches = [n[3:] for o, n in zip(old_family, new_family)
                   if max(abs(a-b) for a, b in zip(p[3:], o[3:])) < 1e-6]
        if len(matches) != 1:
            raise ValueError("Unknown taught orientation; no guessed posture mapping.")
        # Only the common START source resolves to its current measured point.
        # Every other road/contact vertex keeps its original literal BASE XY.
        xy = actual[:2] if p[:2] == nominal[:2] else p[:2]
        return list(xy) + [actual[2]] + list(matches[0])

    effective = deepcopy(packet)
    for c in effective["contexts"].values():
        c["pose_base"] = pose(c["pose_base"])
    for row in effective["primitives"].values():
        for s in row["stages"]:
            s["start_base"], s["target_base"] = pose(s["start_base"]), pose(s["target_base"])
        contacts = [s for s in row["stages"] if s["phase"] == "contact"]
        original_contacts = [s for s in packet["primitives"][row["id"]]["stages"] if s["phase"] == "contact"]
        if len(contacts) == 2 and original_contacts[0]["start_base"] == nominal:
            # Keep the final contact endpoint and the original subdivision
            # ratio so START precision cannot bend a straight push internally.
            a, middle, end = (original_contacts[0]["start_base"], original_contacts[0]["target_base"], original_contacts[1]["target_base"])
            ratio = math.dist(a[:2], middle[:2]) / math.dist(a[:2], end[:2])
            current_start, current_end = contacts[0]["start_base"], contacts[1]["target_base"]
            split = [current_start[i] + ratio*(current_end[i]-current_start[i]) for i in range(2)] + current_start[2:]
            if any(abs(split[i]-middle[i]) > MAX_START_READBACK_DIFFERENCE for i in range(2)):
                raise ValueError("The straight-push subdivision exceeds the precision-only allowance.")
            contacts[0]["target_base"], contacts[1]["start_base"] = split, list(split)
        row["geometry_sha256"] = content_hash({"kind": row["kind"],
            "stages": [{k: s[k] for k in ("phase", "start_base", "target_base")} for s in row["stages"]],
            "source": row["source_context_id"], "target": row["target_context_id"],
            "contact_travel_limit_mm": row.get("contact_travel_limit_mm", 20.)})
        row["repeatability_qualified"] = False
    effective_review = deepcopy(review)
    effective_review["site"]["fixed_tcp_z_mm"] = actual[2]
    effective_review["review_reference"] = reference["review_reference"]
    effective_review["operator_authorization_sha256"] = content_hash(reference)
    effective_review["allowed_geometry_sha256"] = sorted({r["geometry_sha256"] for r in effective["primitives"].values()})
    return effective, effective_review
