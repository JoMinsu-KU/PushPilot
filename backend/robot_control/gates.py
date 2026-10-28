"""Pure commissioning admission checks; no I/O, fitting, or motion authority.

These checks supplement the installed receiver's policy and physical review.
They do not replace its READY/GO, kinematics, cable-clearance or endpoint checks.
"""
from __future__ import annotations

import math

from .models import LocalBaseInstallation, LocalContactInstallation

# Native FC03 uses 0.1 mm / degree registers while pendant HELLO retains full
# precision. This allowance compares two representations of the same baseline;
# it never permits a commanded Z or orientation delta from the current pose.
NATIVE_BASELINE_COMPARISON_QUANTIZATION = 0.100000001


class GuardError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise GuardError(code, message)


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _text(value) -> bool:
    return type(value) is str and 0 < len(value.strip()) <= 256


def _vector(value, count: int, code: str) -> list:
    _require(type(value) is list and len(value) == count
             and all(_number(item) and abs(item) <= 10000 for item in value),
             code, f"A finite {count}-number vector is required.")
    return value


def _installation_limits(installation: dict) -> tuple[list, list]:
    for key in ("installation_id", "map_id", "map_hash", "calibration_id", "tcp_id",
                "tool_id", "review_reference", "camera_epoch", "registration_id"):
        _require(_text(installation.get(key)), "INSTALLATION_INVALID", f"Installation {key} is required.")
    lower = _vector(installation.get("workspace_min_mm"), 3, "INSTALLATION_INVALID")
    upper = _vector(installation.get("workspace_max_mm"), 3, "INSTALLATION_INVALID")
    _require(all(a < b for a, b in zip(lower, upper)), "INSTALLATION_INVALID",
             "Installation workspace must have positive finite dimensions.")
    minimum, raised = installation.get("min_tcp_z_mm"), installation.get("raised_tcp_z_mm")
    _require(_number(minimum) and _number(raised) and lower[2] <= minimum < raised <= upper[2],
             "INSTALLATION_INVALID", "Reviewed working and raised TCP heights must fit the workspace.")
    for key, default, ceiling in (("max_step_mm", 30, 100), ("max_speed_mm_s", 15, 100),
                                 ("max_accel_mm_s2", 30, 500),
                                 ("observation_max_age_seconds", 10, 60)):
        value = installation.get(key, default)
        _require(_number(value) and 0 < value <= ceiling, "INSTALLATION_INVALID",
                 f"Installation {key} exceeds its finite software ceiling.")
    return lower, upper


def _inside(pose: list, installation: dict, lower: list, upper: list) -> None:
    _require(all(a <= value <= b for value, a, b in zip(pose[:3], lower, upper)),
             "OUTSIDE_WORKSPACE", "TCP position is outside the reviewed installation workspace.")
    _require(pose[2] >= installation["min_tcp_z_mm"], "BELOW_WORKING_Z",
             "TCP position is below the reviewed minimum TCP height.")


def _profile(profile, installation: dict, *, candidate: bool, lower: list, upper: list) -> dict:
    _require(type(profile) is dict, "PROFILE_REQUIRED", "An explicit receiver profile is required.")
    _require(profile.get("scope", "board") == "board", "PROFILE_SCOPE",
             "A local BASE commissioning profile cannot authorize board operations.")
    _require(profile.get("tcp_id") == installation["tcp_id"], "TCP_MISMATCH",
             "The receiver profile TCP differs from the reviewed installation.")
    _require(profile.get("allow_motion") is True and profile.get("site_verified") is True,
             "PROFILE_UNQUALIFIED", "The receiver profile must explicitly allow reviewed physical motion.")
    for field, key, default in (("translation_speed_mm_s", "max_speed_mm_s", 15),
                                ("translation_accel_mm_s2", "max_accel_mm_s2", 30)):
        value = profile.get(field)
        _require(_number(value) and 0 < value <= installation.get(key, default),
                 "PROFILE_LIMIT", f"Receiver {field} exceeds the installation limit.")
    if candidate:
        bounds = _vector(profile.get("tcp_bounds_base_mm"), 6, "PROFILE_BOUNDS")
        _require(all(lower[i] <= bounds[i] < bounds[i + 3] <= upper[i] for i in range(3)),
                 "PROFILE_BOUNDS", "Candidate profile bounds exceed the installation workspace.")
    return profile


def _profile_installation_binding(profile: dict, installation: dict) -> None:
    binding = profile.get("installation_binding")
    _require(type(binding) is dict and binding.get("site_review_explicit") is True,
             "PROFILE_INSTALLATION_BINDING", "The profile must record an explicit review of this measured installation.")
    for key in ("installation_id", "map_id", "map_hash", "calibration_id", "tcp_id", "tool_id",
                "camera_epoch", "registration_id"):
        _require(type(binding.get(key)) is type(installation[key]) and binding.get(key) == installation[key],
                 "PROFILE_INSTALLATION_BINDING", f"Profile {key} differs from the current measured installation.")


def _observation(observation, installation: dict, now: float) -> None:
    if type(observation) is not dict:
        raise GuardError("WAIT_OBSERVATION", "A fresh visible-car observation is required.", True)
    for key in ("installation_id", "map_id", "map_hash", "calibration_id", "camera_epoch", "registration_id"):
        _require(observation.get(key) == installation[key], "OBSERVATION_BINDING",
                 f"Observation {key} differs from the current installation.")
    _require(observation.get("view_status") in {"fixed", "marker_occluded"}, "VIEW_CHANGED",
             "The observation does not belong to an unchanged fixed camera view.")
    for key in ("observation_id", "frame_id"):
        _require(_text(observation.get(key)), "OBSERVATION_INVALID", f"Observation {key} is required.")
    digest = observation.get("frame_sha256")
    _require(type(digest) is str and len(digest) == 64
             and all(character in "0123456789abcdef" for character in digest),
             "OBSERVATION_INVALID", "An original-frame SHA-256 is required.")
    count = observation.get("marker_count")
    _require(type(count) is int and 0 <= count <= 1024, "OBSERVATION_INVALID",
             "Marker count must be a nonnegative integer.")
    captured_at = observation.get("captured_at")
    if (not _number(captured_at) or not _number(now) or captured_at > now
            or now - captured_at > installation.get("observation_max_age_seconds", 10)):
        raise GuardError("WAIT_OBSERVATION", "The car observation is missing, stale or future-dated.", True)
    pose = observation.get("car_pose")
    if (observation.get("car_visible") is not True or type(pose) is not list or len(pose) != 3
            or any(not _number(value) or abs(value) > 10000 for value in pose)):
        raise GuardError("WAIT_OBSERVATION", "The current car pose is not readable. Reobserve without replaying motion.", True)
    # Marker visibility is deliberately not an admission condition. With the
    # installed fixed rig, even zero decoded markers may accompany a usable car
    # observation; the exact registration identity remains mandatory above.


def local_profile_binding(installation: dict) -> dict:
    """The exact local review identity, carrying no drawing or camera claim."""
    return {
        "scope": "local_base_commissioning", "source": "measured_local_base_review",
        **{key: installation[key] for key in (
            "installation_id", "tcp_id", "tcp_definition_sha256", "tool_id", "payload_kg",
            "review_reference", "fixed_tcp_z_mm", "fixed_orientation_deg")},
        "site_review_explicit": True, "board_registration_qualified": False,
        "vehicle_control_qualified": False, "rotation_qualified": False, "car_turn_qualified": False,
    }


def validate_local_profile(installation: dict, receiver: dict) -> dict:
    """Validate the limited local review/profile, including before arming.

    This is additional application admission. The original receiver still
    performs its independent bounds, Native, kinematic and READY/GO checks.
    """
    try:
        local = LocalBaseInstallation.model_validate(installation).model_dump(mode="json")
    except (ValueError, TypeError):
        raise GuardError("LOCAL_INSTALLATION_INVALID", "Use an explicit measured local BASE installation without board identities.") from None
    _require(local["qualified"] is True and local["on_site_review"] is True,
             "INSTALLATION_UNQUALIFIED", "The actual local BASE envelope must have an explicit on-site review.")
    _require(receiver.get("physical_execution") is True, "PHYSICAL_RECEIVER_REQUIRED",
             "The receiver must explicitly report physical execution enabled.")
    profile = receiver.get("profile")
    _require(type(profile) is dict, "PROFILE_REQUIRED", "A local reviewed receiver profile is required.")
    _require(profile.get("scope") == "local_base_commissioning", "PROFILE_SCOPE",
             "Local commissioning needs its own current scoped profile.")
    _require(profile.get("allow_motion") is True and profile.get("site_verified") is True,
             "PROFILE_UNQUALIFIED", "The local profile must record genuine measured site qualification.")
    _require(profile.get("tcp_id") == local["tcp_id"], "TCP_MISMATCH",
             "The local profile TCP differs from the reviewed current TCP.")
    _require(_number(profile.get("payload_kg")) and profile["payload_kg"] == local["payload_kg"],
             "LOCAL_TOOL_BINDING", "Local payload differs from the reviewed current payload.")
    expected = local_profile_binding(local)
    binding = profile.get("installation_binding")
    _require(type(binding) is dict and set(binding) == set(expected)
             and all(type(binding[key]) is type(value) and binding[key] == value for key, value in expected.items()),
             "PROFILE_INSTALLATION_BINDING", "The profile must exactly bind this local review without claiming board calibration.")
    _require(not any(key in profile for key in (
        "map_id", "map_hash", "calibration_id", "camera_epoch", "registration_id", "board_registration_qualified")),
        "PROFILE_SCOPE", "A local profile cannot include drawing registration or board qualification fields.")
    lower, upper = local["workspace_min_mm"], local["workspace_max_mm"]
    bounds = _vector(profile.get("tcp_bounds_base_mm"), 6, "PROFILE_BOUNDS")
    _require(all(lower[i] <= bounds[i] < bounds[i + 3] <= upper[i] for i in range(3)),
             "PROFILE_BOUNDS", "The local profile cannot exceed the measured BASE envelope.")
    _require(profile.get("tcp_clearance_margin_mm") == local["tcp_clearance_margin_mm"]
             and profile.get("inflated_keepout_boxes_base_mm") == local["inflated_keepout_boxes_base_mm"],
             "LOCAL_CLEARANCE_BINDING", "The local profile must retain the reviewed margin and inflated keepouts.")
    for field, key in (("translation_speed_mm_s", "max_speed_mm_s"),
                       ("translation_accel_mm_s2", "max_accel_mm_s2"), ("max_translation_mm", "max_step_mm")):
        _require(_number(profile.get(field)) and 0 < profile[field] <= local[key],
                 "PROFILE_LIMIT", f"Local receiver {field} exceeds its measured commissioning limit.")
    _require(profile.get("orientations") == [{"id": "measured_current", "rxyz_deg": local["fixed_orientation_deg"]}]
             and profile.get("rotation_anchors") == [] and profile.get("rotation_edges") == []
             and type(profile.get("rotation_runtime")) is dict
             and profile["rotation_runtime"].get("verified") is False,
             "LOCAL_ROTATION_FORBIDDEN", "Local commissioning permits only the reviewed fixed literal orientation.")
    source = _vector(receiver.get("actual_pose"), 6, "ROBOT_POSE_INVALID")
    margin = local["tcp_clearance_margin_mm"]
    _require(all(bounds[i] + margin <= source[i] <= bounds[i + 3] - margin for i in range(3)),
             "OUTSIDE_WORKSPACE", "The current TCP lies outside the measured local profile envelope.")
    _require(abs(source[2] - local["fixed_tcp_z_mm"]) <= NATIVE_BASELINE_COMPARISON_QUANTIZATION,
             "LOCAL_Z_CHANGED", "Local commissioning must retain the reviewed current TCP height.")
    _require(all(abs(a - b) <= NATIVE_BASELINE_COMPARISON_QUANTIZATION
                 for a, b in zip(source[3:], local["fixed_orientation_deg"])),
             "ORIENTATION_CHANGED", "The current literal TCP orientation differs from the local review.")
    return local


def _admit_local(command: dict, installation: dict, receiver: dict) -> None:
    _require(command.get("kind") == "translate" and command.get("purpose") == "commissioning",
             "LOCAL_OPERATION_FORBIDDEN", "Local BASE commissioning permits only fixed-height translation trials; no push, route, rotation or profile update.")
    local = validate_local_profile(installation, receiver)
    source, target = receiver["actual_pose"], _vector(command.get("target"), 6, "TARGET_INVALID")
    _require(command.get("installation_id") == local["installation_id"], "INSTALLATION_MISMATCH",
             "The command must bind the current measured local BASE installation.")
    bounds = receiver["profile"]["tcp_bounds_base_mm"]
    margin = local["tcp_clearance_margin_mm"]
    _require(all(bounds[i] + margin <= target[i] <= bounds[i + 3] - margin for i in range(3)),
             "OUTSIDE_WORKSPACE", "The target TCP lies outside the measured local profile envelope.")
    _require(target[2] == source[2],
             "LOCAL_Z_CHANGED", "Local commissioning does not permit lifting, lowering or combined XYZ travel.")
    _require(source[3:] == target[3:],
             "ORIENTATION_CHANGED", "Local trials must preserve the reviewed literal TCP orientation.")
    _require(0 < math.dist(source[:3], target[:3]) <= min(local["max_step_mm"], receiver["profile"]["max_translation_mm"]) + 1e-9,
             "STEP_LIMIT", "Local trials need one nonzero bounded step inside the reviewed local volume.")


def _admit_local_profile_refresh(command: dict, installation: dict, receiver: dict,
                                *, armed: bool, held: bool) -> None:
    """Refresh a genuinely reviewed local envelope without issuing motion.

    This is the only local mutation admitted while held. It cannot change the
    tool, establish a board installation or arm the subsequent translation.
    The inherited receiver independently applies its idle profile handshake.
    """
    _require(armed is False and held is True, "LOCAL_REFRESH_REQUIRES_HOLD",
             "A local profile refresh requires an explicitly disarmed, held service.")
    _require(command.get("purpose") == "commissioning"
             and command.get("target") is None and command.get("edge_id") is None,
             "LOCAL_OPERATION_FORBIDDEN", "A local profile refresh must contain no movement or contact operation.")
    _require(command.get("installation_id") == installation.get("installation_id"),
             "INSTALLATION_MISMATCH", "Refresh must bind the newly reviewed current local installation.")
    current, candidate = receiver.get("profile"), command.get("profile")
    _require(type(current) is dict and current.get("scope") == "local_base_commissioning",
             "PROFILE_SCOPE", "Local refresh cannot import a board or unscoped receiver profile.")
    _require(type(candidate) is dict, "PROFILE_REQUIRED", "A complete newly reviewed local profile is required.")
    local = validate_local_profile(installation, {**receiver, "profile": candidate})
    for key in ("schema", "coordinate_frame", "pose_type", "tcp_id", "payload_kg", "allow_motion"):
        _require(type(candidate.get(key)) is type(current.get(key)) and candidate.get(key) == current.get(key),
                 "LOCAL_TOOL_BINDING", f"Local refresh cannot change the current {key}.")
    binding = current.get("installation_binding")
    _require(type(binding) is dict and binding.get("scope") == "local_base_commissioning"
             and all(type(binding.get(key)) is type(local[key]) and binding.get(key) == local[key]
                     for key in ("tcp_id", "tcp_definition_sha256", "tool_id", "payload_kg")),
             "LOCAL_TOOL_BINDING", "The current and renewed review must describe the same physical TCP, tool and payload.")
    _require(binding.get("installation_id") != local["installation_id"]
             and binding.get("review_reference") != local["review_reference"],
             "LOCAL_REFRESH_NEW_REVIEW_REQUIRED", "Renewal requires a distinct current installation and explicit new site review.")
    source = _vector(receiver.get("actual_pose"), 6, "ROBOT_POSE_INVALID")
    joints = _vector(receiver.get("actual_joint"), 6, "ROBOT_JOINT_INVALID")
    _require(_vector(candidate.get("expected_start_tcp_mm_deg"), 6, "LOCAL_REFRESH_BASELINE_CHANGED") == source
             and _vector(candidate.get("expected_start_joint_deg"), 6, "LOCAL_REFRESH_BASELINE_CHANGED") == joints,
             "LOCAL_REFRESH_BASELINE_CHANGED", "Refresh needs the current full-precision TCP and joint baseline.")
    _require(local["fixed_tcp_z_mm"] == source[2] and local["fixed_orientation_deg"] == source[3:],
             "LOCAL_REFRESH_BASELINE_CHANGED", "Renewed local review must retain the exact current TCP height and literal orientation.")
    _require(candidate != current, "LOCAL_REFRESH_NO_CHANGE", "Do not publish an unchanged local profile.")


def _contact_base_fields(local: dict) -> dict:
    """Reuse bounded geometry checks only; never admit a contact as free teaching."""
    return {**{key: local[key] for key in LocalBaseInstallation.model_fields},
            "scope": "local_base_commissioning"}


def local_contact_profile_binding(local: dict) -> dict:
    return {**local_profile_binding(_contact_base_fields(local)),
            "scope": "local_contact_commissioning", "source": "reviewed_local_contact_trials",
            **{key: local[key] for key in ("car_id", "surface_id", "reported_car_dimensions_mm",
                                           "contact_trials_authorized", "trial_max_step_mm")}}


def validate_contact_profile(installation: dict, receiver: dict) -> dict:
    try:
        local = LocalContactInstallation.model_validate(installation).model_dump(mode="json")
    except (ValueError, TypeError):
        raise GuardError("CONTACT_INSTALLATION_INVALID", "Use an explicit reviewed local contact installation without board identities.") from None
    _require(local["qualified"] is True and local["on_site_review"] is True
             and local["contact_trials_authorized"] is True,
             "INSTALLATION_UNQUALIFIED", "Current actual site review and explicit contact-trial authorization are required.")
    profile = receiver.get("profile")
    _require(type(profile) is dict and profile.get("scope") == "local_contact_commissioning",
             "PROFILE_SCOPE", "Experimental contact trials need their own reviewed profile scope.")
    expected, binding = local_contact_profile_binding(local), profile.get("installation_binding")
    _require(type(binding) is dict and set(binding) == set(expected)
             and all(type(binding[key]) is type(value) and binding[key] == value for key, value in expected.items()),
             "PROFILE_INSTALLATION_BINDING", "Contact profile must exactly bind current car, surface, tool and trial review.")
    # The old local admission path remains unchanged. Reuse its numerical
    # bounds/tool/disabled-rotation checks after the contact-specific binding
    # has been validated, without publishing or returning this internal view.
    base = _contact_base_fields(local)
    numerical_profile = {**profile, "scope": "local_base_commissioning",
                         "installation_binding": local_profile_binding(base)}
    validate_local_profile(base, {**receiver, "profile": numerical_profile})
    return local


def _admit_contact_refresh(command: dict, installation: dict, receiver: dict,
                           *, armed: bool, held: bool) -> None:
    _require(armed is False and held is True, "LOCAL_REFRESH_REQUIRES_HOLD",
             "Contact profile handoff requires an explicitly disarmed, held service.")
    _require(command.get("purpose") == "commissioning" and command.get("target") is None
             and command.get("edge_id") is None, "LOCAL_OPERATION_FORBIDDEN",
             "Contact profile handoff must contain no movement.")
    _require(command.get("installation_id") == installation.get("installation_id"),
             "INSTALLATION_MISMATCH", "Contact handoff must bind the new actual review.")
    current, candidate = receiver.get("profile"), command.get("profile")
    scopes = {"local_base_commissioning", "local_contact_commissioning"}
    _require(type(current) is dict and current.get("scope") in scopes,
             "PROFILE_SCOPE", "Contact handoff accepts only an existing local teaching or contact profile.")
    local = validate_contact_profile(installation, {**receiver, "profile": candidate})
    for key in ("schema", "coordinate_frame", "pose_type", "tcp_id", "payload_kg", "allow_motion"):
        _require(type(candidate.get(key)) is type(current.get(key)) and candidate.get(key) == current.get(key),
                 "LOCAL_TOOL_BINDING", f"Contact handoff cannot change current {key}.")
    binding = current.get("installation_binding")
    _require(type(binding) is dict and binding.get("scope") == current["scope"]
             and all(type(binding.get(key)) is type(local[key]) and binding.get(key) == local[key]
                     for key in ("tcp_id", "tcp_definition_sha256", "tool_id", "payload_kg")),
             "LOCAL_TOOL_BINDING", "Contact handoff must retain the current TCP definition, tool and payload.")
    _require(binding.get("installation_id") != local["installation_id"]
             and binding.get("review_reference") != local["review_reference"],
             "LOCAL_REFRESH_NEW_REVIEW_REQUIRED", "Contact handoff requires a distinct genuine current site review.")
    source = _vector(receiver.get("actual_pose"), 6, "ROBOT_POSE_INVALID")
    joints = _vector(receiver.get("actual_joint"), 6, "ROBOT_JOINT_INVALID")
    _require(_vector(candidate.get("expected_start_tcp_mm_deg"), 6, "LOCAL_REFRESH_BASELINE_CHANGED") == source
             and _vector(candidate.get("expected_start_joint_deg"), 6, "LOCAL_REFRESH_BASELINE_CHANGED") == joints
             and local["fixed_tcp_z_mm"] == source[2] and local["fixed_orientation_deg"] == source[3:],
             "LOCAL_REFRESH_BASELINE_CHANGED", "Contact handoff requires the exact fresh TCP/joint baseline and fixed Z/orientation.")


def _admit_contact(command: dict, installation: dict, receiver: dict) -> None:
    purpose = command.get("purpose")
    _require(command.get("kind") == "translate" and purpose in {"commissioning", "contact_trial"},
             "CONTACT_OPERATION_FORBIDDEN", "Contact scope permits only fixed-height free approaches and explicit experimental contact trials.")
    local = validate_contact_profile(installation, receiver)
    _require(command.get("installation_id") == local["installation_id"],
             "INSTALLATION_MISMATCH", "Trial must bind the current local contact review.")
    source, target = receiver["actual_pose"], _vector(command.get("target"), 6, "TARGET_INVALID")
    bounds, margin = receiver["profile"]["tcp_bounds_base_mm"], local["tcp_clearance_margin_mm"]
    _require(all(bounds[i] + margin <= target[i] <= bounds[i + 3] - margin for i in range(3)),
             "OUTSIDE_WORKSPACE", "Contact target lies outside the current reviewed BASE envelope.")
    _require(target[2] == source[2], "LOCAL_Z_CHANGED", "Local contact trials preserve exact current TCP height.")
    _require(target[3:] == source[3:], "ORIENTATION_CHANGED", "Local contact trials preserve exact literal tool orientation.")
    limit = min(local["max_step_mm"], receiver["profile"]["max_translation_mm"])
    if purpose == "contact_trial":
        _require(type(command.get("expected_visual")) is str and bool(command["expected_visual"].strip()),
                 "CONTACT_EXPECTED_OUTCOME_REQUIRED", "An experimental contact trial needs an explicit expected outcome.")
        limit = min(limit, local["trial_max_step_mm"])
    _require(0 < math.dist(source[:3], target[:3]) <= limit + 1e-9,
             "STEP_LIMIT", "Use one bounded step within the current approach or contact-trial limit.")


def admit(command: dict, installation: dict | None, receiver: dict,
          observation: dict | None, *, armed: bool, now: float,
          require_profile_binding: bool = False, held: bool = False) -> None:
    """Raise a structured guard error unless this one command can be admitted.

    Inspection uses only receiver readiness and binding. Physical mutation also
    requires explicit arming, qualified installation and receiver policy. The
    caller still performs receiver preflight immediately before dispatch. Real
    physical mutation must enable require_profile_binding; simulation fixtures
    may leave it disabled. A matching TCP alone never migrates old geometry.
    """
    _require(type(command) is dict and type(receiver) is dict, "COMMAND_INVALID",
             "A command and receiver snapshot are required.")
    kind = command.get("kind")
    _require(kind in {"inspect_current", "inspect_ik", "profile_update", "translate", "rotate"},
             "COMMAND_INVALID", "Unsupported robot-control operation.")
    _require(receiver.get("connected") is True and (receiver.get("idle") is True
             or receiver.get("stage", receiver.get("status")) == "idle"),
             "RECEIVER_NOT_READY", "The persistent receiver must be connected and idle.")
    expected = command.get("expected_receiver")
    _require(type(expected) is dict and _text(expected.get("session_id"))
             and type(expected.get("seq")) is int and expected["seq"] >= 1
             and _text(expected.get("profile_id"))
             and all(type(expected[key]) is type(receiver.get(key)) and expected[key] == receiver.get(key)
                     for key in ("session_id", "seq", "profile_id")),
             "RECEIVER_BINDING", "Receiver session, sequence or profile changed. Refresh before creating a command.")
    if kind in {"inspect_current", "inspect_ik"}:
        if kind == "inspect_ik":
            _vector(command.get("target"), 6, "TARGET_INVALID")
        return
    if (kind == "profile_update" and type(installation) is dict
            and installation.get("scope") == "local_base_commissioning"):
        _admit_local_profile_refresh(command, installation, receiver, armed=armed, held=held)
        return
    if (kind == "profile_update" and type(installation) is dict
            and installation.get("scope") == "local_contact_commissioning"):
        _admit_contact_refresh(command, installation, receiver, armed=armed, held=held)
        return
    _require(armed is True and held is False, "NOT_ARMED", "Physical commissioning must be explicitly armed and not held.")
    _require(type(installation) is dict and installation.get("qualified") is True,
             "INSTALLATION_UNQUALIFIED", "A qualified installation is required before physical changes.")
    scope = installation.get("scope", "board")
    if scope == "local_base_commissioning":
        _admit_local(command, installation, receiver)
        return
    if scope == "local_contact_commissioning":
        _admit_contact(command, installation, receiver)
        return
    _require(scope == "board", "INSTALLATION_INVALID", "An explicit supported installation scope is required.")
    lower, upper = _installation_limits(installation)
    _require(command.get("installation_id") == installation["installation_id"], "INSTALLATION_MISMATCH",
             "The command does not match the current qualified installation.")
    _require(receiver.get("physical_execution") is True, "PHYSICAL_RECEIVER_REQUIRED",
             "The receiver must explicitly report physical execution enabled.")
    if receiver.get("profile") is not None:
        _require(type(receiver["profile"]) is dict and receiver["profile"].get("tcp_id") == installation["tcp_id"],
                 "TCP_MISMATCH", "The current receiver profile TCP differs from the installation.")
    if kind == "profile_update":
        candidate = _profile(command.get("profile"), installation, candidate=True, lower=lower, upper=upper)
        if require_profile_binding:
            _profile_installation_binding(candidate, installation)
        return
    source = _vector(receiver.get("actual_pose"), 6, "ROBOT_POSE_INVALID")
    target = _vector(command.get("target"), 6, "TARGET_INVALID")
    _inside(source, installation, lower, upper)
    _inside(target, installation, lower, upper)
    profile = _profile(receiver.get("profile"), installation, candidate=False, lower=lower, upper=upper)
    if require_profile_binding:
        _profile_installation_binding(profile, installation)
    purpose = command.get("purpose")
    _require(purpose in {"commissioning", "push", "tool_reposition"}, "COMMAND_INVALID",
             "An explicit supported command purpose is required.")
    if kind == "translate":
        _require(all(abs(a - b) <= 0.01 for a, b in zip(source[3:], target[3:])),
                 "ORIENTATION_CHANGED", "A translation must hold the current literal TCP orientation.")
        _require(math.dist(source[:3], target[:3]) <= installation.get("max_step_mm", 30) + 1e-9,
                 "STEP_LIMIT", "Translation exceeds the reviewed per-command step limit.")
        _require(not (abs(source[2] - target[2]) > 0.01 and math.dist(source[:2], target[:2]) > 0.01),
                 "LIFT_LATERAL_COMBINED", "Lift/lower and lateral translation must be separate commands.")
        if purpose == "push":
            _observation(observation, installation, now)
    else:
        _require(purpose == "tool_reposition", "ROTATION_PURPOSE",
                 "Wrist rotation is only tool repositioning, not a qualified vehicle turn.")
        _require(source[2] >= installation["raised_tcp_z_mm"] and target[2] >= installation["raised_tcp_z_mm"],
                 "ROTATION_NOT_RAISED", "Wrist rotation requires the reviewed raised TCP height.")
        _require(all(abs(a - b) <= 0.01 for a, b in zip(source[:3], target[:3])),
                 "ROTATION_TRANSLATES", "Tool rotation must hold its reviewed XYZ anchor.")
        edge_id = command.get("edge_id")
        edges = profile.get("rotation_edges")
        _require(_text(edge_id) and type(edges) is list
                 and any(type(edge) is dict and edge.get("id") == edge_id
                         and edge.get("site_verified") is True and _text(edge.get("review_reference")) for edge in edges),
                 "ROTATION_EDGE", "An explicitly reviewed receiver rotation edge is required.")
