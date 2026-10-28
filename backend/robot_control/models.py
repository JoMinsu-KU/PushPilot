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
    trial_max_step_mm: Number = Field(default=1, gt=0, le=5)

    @model_validator(mode="after")
    def contact_limits(self):
        if not all(0 < value <= 500 for value in self.reported_car_dimensions_mm):
            raise ValueError("Report positive bounded car length, width and height in millimetres.")
        if self.qualified and not self.contact_trials_authorized:
            raise ValueError("Contact qualification requires explicit current on-site contact-trial authorization.")
        return self


class RobotCommand(StrictModel):
    request_id: UUID
    kind: Literal["inspect_current", "inspect_ik", "profile_update", "translate", "rotate"]
    purpose: Literal["commissioning", "push", "tool_reposition", "contact_trial"] = "commissioning"
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
