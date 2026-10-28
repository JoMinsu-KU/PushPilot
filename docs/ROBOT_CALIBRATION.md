<sub>[PushPilot](../README.md) / Engineering / Robot calibration</sub>

# Measure the relationship before compiling a route.

The user requested agent-driven robot testing, coordinate collection and wheel-less-car pushing to Villa, Hanok and Office Building on October 28, 2026. The fixed Pizza start is a repeatable scenario condition; its printed rectangle is not a measured BASE pose. The existing camera homography supplies image-to-drawing display geometry. This implementation adds a separate measured drawing-to-BASE XY fit and a current-coordinate collector. Neither starts a robot motion or qualifies a contact turn.

## Acquire current robot coordinates independently

```sh
python tools/read_robot_pose.py \
  --runtime <private-hash-verified-receiver-directory> \
  --output-dir <private-teaching-directory> \
  --label pizza-contact --samples 3
```

The tool loads the hash-verified inherited runtime, then calls only Native FC03 `snapshot`. It does not require a pendant session, start a host, touch receiver/session/mailbox files, generate a profile or change TCP settings. Each acquisition writes a new private JSON record with current TCP, joints, program/flags, quantized speeds and per-sample UTC/monotonic timestamps. Input failures retain diagnostic evidence without retrying or substituting historical values.

Two or more coherent samples, unchanged eligible flags, exact reported zero speed and at most 0.2 mm/degree pairwise drift admit a stationary teaching observation. These limits describe telemetry consistency at Native's 0.1-unit quantization, not endpoint accuracy or collision clearance. A stationary program register value alone never establishes readiness. Ineligible controller flags, moving data and single samples remain diagnostics. The collector does not read the selected TCP definition or certify that a measured TCP is the physical contact point.

## Establish the same physical reference in both frames

Record at least three non-collinear pairs spread across the intended working area, with a fourth independently captured check point. Prefer references surrounding the intended routes; several tiny probes at Pizza are useful for initial local response, but do not verify the whole A3 sheet. Additional checks at the far destination fronts and intersection turn region remain necessary before route commissioning.

Each pair describes one physical reference point in drawing millimetres and robot BASE millimetres, with the measured probe/TCP offset already accounted for. Do not pair the visible car roof centre with a TCP touching its rear. Elevated roof/pad pixels can have parallax relative to the paper-plane homography. Preserve one TCP definition, literal orientation and measured reference height during collection; independently check that the print plane is parallel to BASE XY. A tilted plane needs a separately measured 3D model, not a more permissive XY fit.

Bind every sample to map ID/version/geometry hash, camera epoch and registration ID, TCP ID/definition hash and tool ID. Paper replacement or an identity change invalidates the old fit. Repeated image frames and old POC slot poses are not new measurements.

## Fit and independently check XY

```sh
python tools/calibrate_robot_board.py \
  --pairs <private-measured-pairs.json> \
  --output <new-private-calibration-report.json>
```

Input uses `pushpilot.measured-board-base-pairs.v1` with `calibration_id`, shared `identity`, `domain`, explicit metrology `policy`, `fit_points` and one `independent_check`. Each point contains `measurement_id`, two-number `drawing_xy_mm`, two-number `base_xy_mm`, its own `evidence_reference` and explicit `source: "measured"`. The schema is demonstrated using synthetic data in [the CLI tests](../tests/test_calibrate_robot_board.py). It accepts no stored arbitrary transformation matrix.

The standard-library implementation fits an equal-weight planar rigid transform over all paired points. Declare drawing axes explicitly: the current print grows right/down, while BASE XY is right-handed. The algorithm normalizes the declared Y convention, rejects an unexpected mirror, checks measured scale without applying scale correction, and rejects narrow/near-collinear geometry or excessive residuals. It never drops an inconvenient outlier or hides print distortion in an affine warp. Thresholds are explicit metrology policy, not universal pushing tolerances.

Forward and inverse transforms require the exact current identity and remain inside the declared drawing domain. The domain bounds mathematical use; it is not an assertion that all interior positions were physically tested. The independent check uses a different measurement ID, evidence capture and spatially separate point. Its failure is saved as failure without refitting. Both reports retain the original pairs, fit/check errors, scale estimate and `physical_qualified: false`. Outputs remain private and cannot overwrite an existing report.

## Keep four qualifications separate

| Evidence | What it establishes | What remains separate |
|---|---|---|
| Native teaching observation | Fresh consistent controller coordinates | Tool definition, paper clearance and robot readiness |
| Image homography | Fixed image/drawing correspondence | BASE geometry and elevated-object parallax |
| Measured XY fit plus independent check | Tested planar drawing/BASE relationship at the captured references | Contact Z, pusher offset, workspace/cable clearance and route coverage |
| Endpoint receipt plus fresh car outcome | One observed bounded action | Repeatability, another turn direction and complete destination success |

Initial local BASE probe commissioning must be scoped separately from map-qualified pushing. The unchanged persistent receiver still requires a genuinely reviewed local physical profile before BEGIN. A valid profile does not prove paper registration. The HTTP service must refuse route/push operations under a local-only scope; later installation of a board-bound qualification is a separate, explicit transition.

`LocalBaseInstallation` uses `scope: "local_base_commissioning"` and deliberately has no map, calibration or camera fields. It records the current TCP definition hash, tool, payload, measured BASE envelope, fixed Z/orientation and actual site review. Its entire envelope spans at most 20 mm per axis, with software ceilings of 5 mm per trial, 5 mm/s and 10 mm/s². These limits do not establish physical clearance. At runtime the HTTP admission layer accepts only same-Z, fixed-literal-orientation `translate` commands with purpose `commissioning`; it rejects pushes, tool repositioning, rotation and profile updates. The inherited receiver retains its original generic BASE policy and protocol checks. Use only the single-owner commissioning API; these additional scope restrictions are not a newly installed pendant feature.

Native baseline coordinates have 0.1 mm/degree quantization, while pendant HELLO supplies full precision. The baseline comparison permits at most one Native unit of representation difference; it is not a permitted motion or per-step drift. Every command's Z and orientation must still equal the current full-precision source exactly. The initial profile's narrow Z envelope accommodates readback representation only and does not admit vertical trials through the API.

```sh
python tools/prepare_local_commissioning.py \
  --installation <private-measured-local-base-review.json> \
  --robot-state <fresh-private-pose-and-joints.json> \
  --output <new-private-local-profile.json> \
  --receiver-root <private-hash-verified-receiver-directory> \
  --on-site-review
```

The explicit invocation flag records an already completed actual review; it cannot create that review. Both the input's local qualification/review and this flag are required. The helper validates the original receiver policy offline, writes a new private profile only, and never starts a listener, arms the API or publishes a command. No actual local profile has been established merely by adding this tool. Paper/contact/arm/cable clearance must be reviewed at the current pose before these flags can be truthful.

After that foundation, collect short straight-push response, measured retraction/recontact, left/right contact-turn response and mandatory stop/signal approaches. Compile the three graph routes from physically qualified primitives, then run and record each destination separately. Preserve the distinction between TCP/wrist rotation and actual vehicle yaw change. See [Contact pushing](PUSH_ALIGNMENT.md) and [Robot control](ROBOT_CONTROL.md).
