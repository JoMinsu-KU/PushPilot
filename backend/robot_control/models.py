"""Explicit installation, receiver and observation bindings for physical commissioning."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(strict=True)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ReceiverBinding(StrictModel):
    session_id: str = Field(min_length=1, max_length=80)
    seq: int = Field(ge=1, strict=True)
    profile_id: str = Field(min_length=1, max_length=80)


class Installation(StrictModel):
    scope: Literal["board"] = "board"
    installation_id: str = Field(min_length=1, max_length=80)
    map_id: str = Field(min_length=1, max_length=80)
    map_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    calibration_id: str = Field(min_length=1, max_length=80)
    tcp_id: str = Field(min_length=1, max_length=80)
    tool_id: str = Field(min_length=1, max_length=80)
    review_reference: str = Field(min_length=10, max_length=500)
    qualified: bool = Field(default=False, strict=True)
    workspace_min_mm: list[Number] = Field(min_length=3, max_length=3)
    workspace_max_mm: list[Number] = Field(min_length=3, max_length=3)
    min_tcp_z_mm: Number
    raised_tcp_z_mm: Number
    max_step_mm: Number = Field(default=30, gt=0, le=100)
    max_speed_mm_s: Number = Field(default=15, gt=0, le=100)
    max_accel_mm_s2: Number = Field(default=30, gt=0, le=500)
    observation_max_age_seconds: Number = Field(default=10, gt=0, le=60)
    camera_epoch: str = Field(min_length=1, max_length=100)
    registration_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounds(self):
        if not all(-10000 <= a < b <= 10000 for a, b in zip(self.workspace_min_mm, self.workspace_max_mm)):
            raise ValueError("Installation bounds must be finite ordered BASE limits.")
        if not self.workspace_min_mm[2] <= self.min_tcp_z_mm < self.raised_tcp_z_mm <= self.workspace_max_mm[2]:
            raise ValueError("Measured work and raised TCP heights must lie inside the installation.")
        return self


class LocalBaseInstallation(StrictModel):
    """A reviewed free-XY teaching envelope, independent of any board fit.

    Small software ceilings do not qualify this volume. The supplied review
    must cover the actual tool, arm, cable and surrounding installation.
    """
    scope: Literal["local_base_commissioning"]
    installation_id: str = Field(min_length=1, max_length=80)
    tcp_id: str = Field(min_length=1, max_length=80)
    tcp_definition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tool_id: str = Field(min_length=1, max_length=80)
    payload_kg: Number = Field(ge=0, le=10000)
    review_reference: str = Field(min_length=10, max_length=500)
    qualified: bool = Field(default=False, strict=True)
    on_site_review: bool = Field(default=False, strict=True)
    workspace_min_mm: list[Number] = Field(min_length=3, max_length=3)
    workspace_max_mm: list[Number] = Field(min_length=3, max_length=3)
    fixed_tcp_z_mm: Number
    fixed_orientation_deg: list[Number] = Field(min_length=3, max_length=3)
    tcp_clearance_margin_mm: Number = Field(default=0, ge=0)
    inflated_keepout_boxes_base_mm: list[list[Number]] = Field(max_length=16)
    max_step_mm: Number = Field(default=1, gt=0, le=20)
    max_speed_mm_s: Number = Field(default=1, gt=0, le=10)
    max_accel_mm_s2: Number = Field(default=2, gt=0, le=20)

    @model_validator(mode="after")
    def local_bounds(self):
        margin = self.tcp_clearance_margin_mm
        if not all(-10000 <= a < b <= 10000 and b - a <= 200 and a + 2 * margin < b
                   for a, b in zip(self.workspace_min_mm, self.workspace_max_mm)):
            raise ValueError("Local BASE bounds must be ordered, span at most 200 mm per axis and retain the reviewed clearance margin.")
        if not self.workspace_min_mm[2] + margin <= self.fixed_tcp_z_mm <= self.workspace_max_mm[2] - margin:
            raise ValueError("The measured fixed TCP height must lie inside the reviewed local BASE envelope.")
        if not all(-180 <= angle <= 180 for angle in self.fixed_orientation_deg):
            raise ValueError("Use the reviewed literal -180..180 TCP orientation; no normalization is performed.")
        if any(len(box) != 6 or any(not -10000 <= number <= 10000 for number in box)
               or any(box[index] > box[index + 3] for index in range(3))
               for box in self.inflated_keepout_boxes_base_mm):
            raise ValueError("Local keepouts must be explicit ordered six-number inflated BASE boxes.")
        if self.qualified and not self.on_site_review:
            raise ValueError("Local qualification requires explicit actual on-site review.")
        return self


class LocalContactInstallation(LocalBaseInstallation):
    """A reviewed experimental contact envelope, not board-qualified control."""
    scope: Literal["local_contact_commissioning"]
    car_id: str = Field(min_length=1, max_length=80)
    surface_id: str = Field(min_length=1, max_length=80)
    reported_car_dimensions_mm: list[Number] = Field(min_length=3, max_length=3)
    contact_trials_authorized: bool = Field(strict=True)
    trial_max_step_mm: Number = Field(default=1, gt=0, le=20)

    @model_validator(mode="after")
    def contact_limits(self):
        if not all(0 < value <= 500 for value in self.reported_car_dimensions_mm):
            raise ValueError("Report positive bounded car length, width and height in millimetres.")
        if self.qualified and not self.contact_trials_authorized:
            raise ValueError("Contact qualification requires explicit current on-site contact-trial authorization.")
        return self


class TeachingOrientation(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    rxyz_deg: list[Number] = Field(min_length=3, max_length=3)


class TeachingRotationAnchor(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    xyz_base_mm: list[Number] = Field(min_length=3, max_length=3)
    site_verified: bool = Field(strict=True)
    review_reference: str = Field(min_length=10, max_length=500)
    position_window_mm: Number = Field(ge=0, le=20)
    max_in_place_correction_mm: Number = Field(ge=0, le=20)
    window_and_correction_reviewed: bool = Field(strict=True)


class TeachingRotationEdge(StrictModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)
    id: str = Field(min_length=1, max_length=80)
    from_orientation: str = Field(alias="from", min_length=1, max_length=80)
    to: str = Field(min_length=1, max_length=80)
    anchor_id: str = Field(min_length=1, max_length=80)
    site_verified: bool = Field(strict=True)
    review_reference: str = Field(min_length=10, max_length=500)
    expected_source_joint_deg: list[Number] = Field(min_length=6, max_length=6)
    expected_target_joint_deg: list[Number] = Field(min_length=6, max_length=6)
    wrist_only: bool = Field(default=False, strict=True)
    joint_path_reviewed: bool = Field(default=False, strict=True)


class TeachingRotationRuntime(StrictModel):
    verified: bool = Field(strict=True)
    primitive: Literal["moveLinear_tcp", "moveJoint_wrist"]
    controller_version: str = Field(min_length=1, max_length=100)
    argument_semantics: str = Field(min_length=1, max_length=500)
    speed_argument: Number = Field(ge=0, le=10)
    accel_argument: Number = Field(ge=0, le=20)
    completion_timeout_s: Number = Field(ge=0, le=300)
    review_reference: str = Field(min_length=10, max_length=500)


class PlanarTeachingInstallation(StrictModel):
    """Reviewed car-removed BASE teaching, without a board/contact qualification.

    Software ceilings are not measurements. Rotation requires separately
    reviewed fixed-XYZ anchors, finite poses and inherited receiver preflight.
    """
    scope: Literal["planar_teaching"]
    installation_id: str = Field(min_length=1, max_length=80)
    tcp_id: str = Field(min_length=1, max_length=80)
    tcp_definition_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tool_id: str = Field(min_length=1, max_length=80)
    payload_kg: Number = Field(ge=0, le=10000)
    review_reference: str = Field(min_length=10, max_length=500)
    qualified: bool = Field(default=False, strict=True)
    on_site_review: bool = Field(default=False, strict=True)
    car_removed: bool = Field(strict=True)
    noncontact_teaching_authorized: bool = Field(strict=True)
    workspace_min_mm: list[Number] = Field(min_length=3, max_length=3)
    workspace_max_mm: list[Number] = Field(min_length=3, max_length=3)
    fixed_tcp_z_mm: Number
    fixed_roll_pitch_deg: list[Number] = Field(min_length=2, max_length=2)
    tcp_clearance_margin_mm: Number = Field(default=0, ge=0)
    inflated_keepout_boxes_base_mm: list[list[Number]] = Field(max_length=16)
    orientations: list[TeachingOrientation] = Field(min_length=1, max_length=8)
    rotation_anchors: list[TeachingRotationAnchor] = Field(max_length=8)
    rotation_edges: list[TeachingRotationEdge] = Field(max_length=32)
    rotation_runtime: TeachingRotationRuntime
    max_step_mm: Number = Field(default=1, gt=0, le=20)
    max_speed_mm_s: Number = Field(default=1, gt=0, le=10)
    max_accel_mm_s2: Number = Field(default=2, gt=0, le=20)

    @model_validator(mode="after")
    def teaching_limits(self):
        lower, upper, margin = self.workspace_min_mm, self.workspace_max_mm, self.tcp_clearance_margin_mm
        if not all(-10000 <= a < b <= 10000 and b-a <= (1000 if i < 2 else 2)
                   and a+2*margin < b for i, (a, b) in enumerate(zip(lower, upper))):
            raise ValueError("Supply reviewed finite BASE bounds, XY span <=1000 mm and fixed-Z slab <=2 mm.")
        if not lower[2]+margin <= self.fixed_tcp_z_mm <= upper[2]-margin:
            raise ValueError("Fixed Z must lie within the reviewed slab.")
        poses = {pose.id: pose.rxyz_deg for pose in self.orientations}
        if len(poses) != len(self.orientations) or any(
            pose[:2] != self.fixed_roll_pitch_deg or any(not -180 <= a <= 180 for a in pose)
            for pose in poses.values()
        ):
            raise ValueError("Finite unique orientations must retain the reviewed literal roll/pitch.")
        if any(all(abs((a-b+180) % 360-180) <= .6 for a, b in zip(first, second))
               for index, first in enumerate(poses.values()) for second in list(poses.values())[index+1:]):
            raise ValueError("Orientation tolerance regions must not overlap.")
        if any(len(box) != 6 or any(not -10000 <= a <= 10000 for a in box)
               or any(box[i] > box[i+3] for i in range(3)) for box in self.inflated_keepout_boxes_base_mm):
            raise ValueError("Supply ordered inflated six-number BASE keepouts.")
        anchors = {anchor.id: anchor for anchor in self.rotation_anchors}
        if len(anchors) != len(self.rotation_anchors):
            raise ValueError("Rotation anchors need unique IDs.")
        for anchor in anchors.values():
            if (not anchor.site_verified or not anchor.window_and_correction_reviewed
                or anchor.max_in_place_correction_mm > anchor.position_window_mm
                or anchor.xyz_base_mm[2] != self.fixed_tcp_z_mm
                or any(not lower[i]+margin <= value <= upper[i]-margin
                       for i, value in enumerate(anchor.xyz_base_mm))):
                raise ValueError("Each fixed-Z rotation anchor needs its actual swept-window review.")
        if len({edge.id for edge in self.rotation_edges}) != len(self.rotation_edges):
            raise ValueError("Rotation edges need unique IDs.")
        runtime = self.rotation_runtime
        if runtime.verified and not (runtime.speed_argument > 0 and runtime.accel_argument > 0
                                     and runtime.completion_timeout_s > 0):
            raise ValueError("Verified rotation runtime needs measured positive argument semantics.")
        for edge in self.rotation_edges:
            if (not runtime.verified or not edge.site_verified or edge.anchor_id not in anchors
                or edge.from_orientation not in poses or edge.to not in poses or edge.from_orientation == edge.to
                or any(not -360 <= a <= 360 for a in edge.expected_source_joint_deg+edge.expected_target_joint_deg)):
                raise ValueError("Each directed rotation edge needs reviewed runtime, anchor, poses and joints.")
            if runtime.primitive == "moveJoint_wrist":
                if (not edge.wrist_only or not edge.joint_path_reviewed
                    or edge.expected_source_joint_deg[:5] != edge.expected_target_joint_deg[:5]
                    or not 0 < abs(edge.expected_source_joint_deg[5]-edge.expected_target_joint_deg[5]) <= 90
                    or runtime.completion_timeout_s < 15):
                    raise ValueError("Wrist-only edges retain inherited joint, path and <=90 degree limits.")
            elif any(abs(a-b) >= 180 for a, b in zip(poses[edge.from_orientation], poses[edge.to])):
                raise ValueError("Linear rotation cannot cross an Euler branch.")
        if self.qualified and not (self.on_site_review and self.car_removed and self.noncontact_teaching_authorized):
            raise ValueError("Teaching qualification requires actual site review, removed car and explicit noncontact authorization.")
        return self


class LocalContactTurnInstallation(LocalContactInstallation):
    """Opt-in contact experiments with finite reviewed wrist edges.

    The inherited fixed_orientation_deg is the fresh handoff baseline, not a
    promise that every experiment keeps that orientation. Full literal Euler
    vectors are reviewed because tool-local yaw can change all three angles.
    A reviewed experiment is not a qualified car turn or board registration.
    """
    scope: Literal["local_contact_turn_commissioning"]
    contact_turn_trials_authorized: bool = Field(default=False, strict=True)
    max_rotation_increment_deg: Number = Field(default=10, gt=0, le=90)
    orientations: list[TeachingOrientation] = Field(min_length=1, max_length=8)
    rotation_anchors: list[TeachingRotationAnchor] = Field(max_length=8)
    rotation_edges: list[TeachingRotationEdge] = Field(max_length=32)
    rotation_runtime: TeachingRotationRuntime

    @model_validator(mode="after")
    def contact_turn_limits(self):
        if self.qualified and not self.contact_turn_trials_authorized:
            raise ValueError("Contact-turn commissioning needs explicit current experimental turn authorization.")
        poses = {pose.id: pose.rxyz_deg for pose in self.orientations}
        if (len(poses) != len(self.orientations) or self.fixed_orientation_deg not in poses.values()
            or any(any(not -180 <= value <= 180 for value in pose) for pose in poses.values())):
            raise ValueError("Supply unique bounded full Euler poses including the exact fresh handoff orientation.")
        if any(all(abs((a-b+180) % 360-180) <= .6 for a, b in zip(first, second))
               for index, first in enumerate(poses.values()) for second in list(poses.values())[index+1:]):
            raise ValueError("Reviewed orientation tolerance regions must not overlap.")
        anchors = {anchor.id: anchor for anchor in self.rotation_anchors}
        if len(anchors) != len(self.rotation_anchors):
            raise ValueError("Contact-turn anchors need unique IDs.")
        lower, upper, margin = self.workspace_min_mm, self.workspace_max_mm, self.tcp_clearance_margin_mm
        for anchor in anchors.values():
            if (not anchor.site_verified or not anchor.window_and_correction_reviewed
                or anchor.max_in_place_correction_mm > anchor.position_window_mm
                or anchor.xyz_base_mm[2] != self.fixed_tcp_z_mm
                or any(not lower[i]+margin <= value <= upper[i]-margin for i, value in enumerate(anchor.xyz_base_mm))):
                raise ValueError("Each fixed-Z anchor needs its actual tool, arm, cable and contact swept-window review.")
        if len({edge.id for edge in self.rotation_edges}) != len(self.rotation_edges):
            raise ValueError("Contact-turn directed edges need unique IDs.")
        runtime = self.rotation_runtime
        if (not runtime.verified or runtime.primitive != "moveJoint_wrist"
            or not 0 < runtime.speed_argument <= self.max_speed_mm_s
            or not 0 < runtime.accel_argument <= self.max_accel_mm_s2
            or not 15 <= runtime.completion_timeout_s <= 300):
            raise ValueError("Contact-turn experiments retain the reviewed bounded wrist-only runtime semantics.")
        for edge in self.rotation_edges:
            if (not edge.site_verified or not edge.wrist_only or not edge.joint_path_reviewed
                or edge.anchor_id not in anchors or edge.from_orientation not in poses or edge.to not in poses
                or edge.from_orientation == edge.to
                or any(not -360 <= value <= 360 for value in edge.expected_source_joint_deg+edge.expected_target_joint_deg)
                or edge.expected_source_joint_deg[:5] != edge.expected_target_joint_deg[:5]
                or not 0 < abs(edge.expected_source_joint_deg[5]-edge.expected_target_joint_deg[5]) <= self.max_rotation_increment_deg):
                raise ValueError("Each experiment needs a reviewed directed wrist-only edge within its explicit increment limit.")
        return self


class RobotCommand(StrictModel):
    request_id: UUID
    kind: Literal["inspect_current", "inspect_ik", "profile_update", "translate", "rotate"]
    purpose: Literal["commissioning", "push", "tool_reposition", "contact_trial", "contact_turn_trial"] = "commissioning"
    installation_id: str | None = Field(default=None, max_length=80)
    expected_receiver: ReceiverBinding
    target: list[Number] | None = Field(default=None, min_length=6, max_length=6)
    edge_id: str | None = Field(default=None, max_length=80)
    profile: dict | None = None
    timeout_seconds: Number = Field(default=180, gt=0, le=610)
    admission_timeout_seconds: Number = Field(default=30, gt=0, le=120)
    expected_visual: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def fields(self):
        if self.kind in {"translate", "rotate", "inspect_ik"} and self.target is None:
            raise ValueError("This operation requires an explicit BASE TCP target.")
        if self.kind == "profile_update" and self.profile is None:
            raise ValueError("Profile updates require a complete reviewed profile.")
        if self.kind != "profile_update" and self.profile is not None:
            raise ValueError("Only a profile update accepts a profile.")
        if (self.kind == "rotate") != (self.edge_id is not None):
            raise ValueError("Only wrist rotation requires a reviewed directed edge.")
        if self.purpose == "push" and (self.kind != "translate" or not self.expected_visual.strip()):
            raise ValueError("A push requires translation and a visible expected outcome.")
        if self.purpose == "contact_trial" and (self.kind != "translate" or not self.expected_visual.strip()):
            raise ValueError("An experimental contact trial requires translation and an explicit expected visual outcome.")
        if self.purpose == "contact_turn_trial" and (self.kind not in {"translate", "rotate"} or not self.expected_visual.strip()):
            raise ValueError("An experimental contact-turn trial requires one translation or rotation and an explicit expected visual outcome.")
        return self


class Observation(StrictModel):
    observation_id: UUID
    source: Literal["operator", "detector", "external_meta_bridge"]
    installation_id: str = Field(min_length=1, max_length=80)
    map_id: str = Field(min_length=1, max_length=80)
    map_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    calibration_id: str = Field(min_length=1, max_length=80)
    camera_epoch: str = Field(min_length=1, max_length=100)
    registration_id: str = Field(min_length=1, max_length=100)
    frame_id: str = Field(min_length=1, max_length=100)
    frame_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: Number = Field(gt=0)
    view_status: Literal["fixed", "marker_occluded", "view_changed", "unregistered"]
    marker_count: int = Field(ge=0, le=32, strict=True)
    car_visible: bool = Field(strict=True)
    car_pose: list[Number] | None = Field(default=None, min_length=3, max_length=3)


class ControlChange(StrictModel):
    installation_id: str = Field(min_length=1, max_length=80)
    expected_receiver: ReceiverBinding
    reason: str = Field(min_length=10, max_length=500)


class Review(StrictModel):
    review_id: UUID
    observation_id: UUID
    source: Literal["operator", "external_meta_bridge"]
    verdict: Literal["PASS", "FAIL", "REOBSERVE", "UNKNOWN"]
    summary: str = Field(min_length=1, max_length=1000)
    provider_receipt_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def receipt(self):
        if self.source == "external_meta_bridge" and not self.provider_receipt_id:
            raise ValueError("External model reviews need their original provider receipt identity.")
        return self


class Reconciliation(ControlChange):
    measured_outcome: Literal["confirmed_completed", "confirmed_not_executed", "partial"]
