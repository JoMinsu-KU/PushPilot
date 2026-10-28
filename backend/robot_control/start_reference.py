"""Pure fixed-setup coordinate evidence, independent of vehicle visibility.

An operator may establish a repeatable initial setup while the car is covered.
This records the current robot, not a detected car pose or a contact model.
No reference authorizes motion, resets a car, or proves a later push outcome.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

NATIVE_QUANTUM = 0.100000001  # Existing FC03 0.1 mm/degree resolution.
MAX_AGE_SECONDS = 2.0


class StartReferenceError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise StartReferenceError(reason)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value):
    _require(type(value) in (list, tuple) and len(value) == 6
             and all(_number(v) and abs(v) <= 10000 for v in value), "INVALID_ROBOT_VECTOR")
    return tuple(float(v) for v in value)


def _digest(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _text(value):
    return type(value) is str and 0 < len(value) <= 128 and value == value.strip()


def _near(first, second):
    # Literal Euler values, never a modulo-360 equivalence or a nearest branch.
    return all(abs(a - b) <= NATIVE_QUANTUM for a, b in zip(first, second))


@dataclass(frozen=True)
class StartIdentity:
    map_id: str
    map_version: str
    map_hash: str
    tcp_id: str
    tcp_definition_sha256: str
    tool_id: str

    def __post_init__(self):
        _require(all(_text(value) for value in vars(self).values()), "INVALID_START_IDENTITY")
        _require(_digest(self.map_hash) and _digest(self.tcp_definition_sha256), "INVALID_START_DIGEST")


@dataclass(frozen=True)
class FixedStartReference:
    identity: StartIdentity
    captured_at: float
    receiver_captured_at: float
    session_id: str
    seq: int
    profile_id: str
    tcp_mm_deg: tuple[float, ...]
    joint_deg: tuple[float, ...]
    native_tcp_mm_deg: tuple[float, ...]
    native_joint_deg: tuple[float, ...]
    native_sample_times: tuple[float, ...]

    def to_dict(self):
        return {"schema": "pushpilot.fixed-start-reference.v1", **asdict(self),
                "robot_source": "receiver_idle_and_native_fc03_readonly",
                "car_initial_source": "operator_fixed_setup",
                "operator_fixed_setup_acknowledged": True,
                "car_pose_measured": False, "contact_model_measured": False,
                "geometry_qualified": False, "motion_issued": False,
                "native_resolution_mm_or_deg": 0.1,
                "scope": "Fixed initial setup evidence only; no motion authority or car return verification."}


def _observe(receiver, native_samples, receiver_captured_at, now):
    _require(_number(now) and _number(receiver_captured_at)
             and 0 <= now - receiver_captured_at <= MAX_AGE_SECONDS, "RECEIVER_OBSERVATION_STALE")
    _require(type(receiver) is dict and receiver.get("connected") is True
             and receiver.get("idle") is True and receiver.get("reason") == "RECEIVER_IDLE",
             "CURRENT_RECEIVER_IDLE_REQUIRED")
    _require(type(receiver.get("session_id")) is str and len(receiver["session_id"]) == 32
             and all(c in "0123456789abcdef" for c in receiver["session_id"])
             and type(receiver.get("seq")) is int and receiver["seq"] >= 1
             and _digest(receiver.get("profile_id")), "INVALID_RECEIVER_BINDING")
    pose, joint = _vector(receiver.get("actual_pose")), _vector(receiver.get("actual_joint"))
    _require(all(-180 <= v <= 180 for v in pose[3:]), "INVALID_LITERAL_ORIENTATION")
    _require(type(native_samples) in (list, tuple) and 2 <= len(native_samples) <= 10,
             "TWO_TO_TEN_NATIVE_SAMPLES_REQUIRED")
    rows, stamps = [], []
    for sample in native_samples:
        _require(type(sample) is dict and _number(sample.get("captured_at"))
                 and 0 <= now - sample["captured_at"] <= MAX_AGE_SECONDS,
                 "NATIVE_OBSERVATION_STALE")
        stamp, row = sample["captured_at"], sample.get("snapshot")
        _require(not stamps or stamp > stamps[-1], "NATIVE_SAMPLES_MUST_BE_DISTINCT_AND_ORDERED")
        _require(type(row) is dict and all(type(row.get(k)) is list for k in
                 ("program_before", "program_after", "flags")), "INVALID_NATIVE_REGISTERS")
        _require(len(row["program_before"]) == 1 and row["program_before"] == row["program_after"]
                 and all(type(v) is int and 0 <= v <= 65535 for v in row["program_before"])
                 and len(row["flags"]) == 6 and all(type(v) is int for v in row["flags"])
                 and row["flags"][0] == 1 and row["flags"][1] in (0, 1)
                 and row["flags"][2:] == [0, 0, 0, 0], "NATIVE_STATE_REQUIRES_INSPECTION")
        native_pose, native_joint = _vector(row.get("pose")), _vector(row.get("joint"))
        _require(all(-180 <= v <= 180 for v in native_pose[3:]), "INVALID_LITERAL_ORIENTATION")
        _require(all(v == 0 for v in _vector(row.get("speed"))), "ROBOT_NOT_STATIONARY")
        _require(_near(pose, native_pose) and _near(joint, native_joint), "RECEIVER_NATIVE_DISAGREEMENT")
        for previous in rows:
            _require(row["program_after"] == previous["program_after"]
                     and row["flags"] == previous["flags"], "NATIVE_STATE_CHANGED")
            _require(_near(native_pose, previous["pose"]) and _near(native_joint, previous["joint"]),
                     "NATIVE_COORDINATES_CHANGED")
        rows.append(row)
        stamps.append(float(stamp))
    return pose, joint, _vector(rows[-1]["pose"]), _vector(rows[-1]["joint"]), tuple(stamps)


def freeze_start(identity, receiver, native_samples, *, receiver_captured_at, now,
                 operator_fixed_setup):
    """Freeze current stationary coordinates; a visible car is not a prerequisite."""
    _require(type(identity) is StartIdentity, "EXPLICIT_START_IDENTITY_REQUIRED")
    _require(operator_fixed_setup is True, "OPERATOR_FIXED_SETUP_ACKNOWLEDGEMENT_REQUIRED")
    values = _observe(receiver, native_samples, receiver_captured_at, now)
    return FixedStartReference(identity, float(now), float(receiver_captured_at),
                               receiver["session_id"], receiver["seq"], receiver["profile_id"], *values)


def verify_start(reference, identity, receiver, native_samples, *, receiver_captured_at, now):
    """Compare fresh robot readback only; never send a return or infer car reset."""
    _require(type(reference) is FixedStartReference and type(identity) is StartIdentity
             and reference.identity == identity, "START_IDENTITY_CHANGED")
    _require(_number(receiver_captured_at) and receiver_captured_at >= reference.captured_at,
             "FRESH_RECEIVER_VERIFICATION_REQUIRED")
    pose, joint, _, _, _ = _observe(receiver, native_samples, receiver_captured_at, now)
    _require(all(sample["captured_at"] > reference.native_sample_times[-1] for sample in native_samples),
             "NEW_NATIVE_VERIFICATION_REQUIRED")
    return {"robot_matches_start": _near(pose, reference.tcp_mm_deg) and _near(joint, reference.joint_deg),
            "tcp_literal_delta_mm_deg": [a - b for a, b in zip(pose, reference.tcp_mm_deg)],
            "joint_delta_deg": [a - b for a, b in zip(joint, reference.joint_deg)],
            "car_initial_source": "operator_fixed_setup", "car_current_source": "unobserved",
            "car_return_verified": False, "geometry_qualified": False, "motion_issued": False}
