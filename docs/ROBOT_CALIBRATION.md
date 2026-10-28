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

For an operator-established fixed start with a connected idle receiver, capture the full-precision pose without requiring a vehicle image:

```sh
python tools/capture_fixed_start.py \
  --map-path backend/data/seoul-city-a3.json \
  --installation <current-private-local-installation.json> \
  --runtime <private-hash-verified-receiver-directory> \
  --token-file <private-control-token-file> \
  --output <new-private-fixed-start.json> \
  --operator-fixed-start
```

Capture requires a disarmed/inactive API, unchanged current installation/TCP/tool binding, stable receiver identity across the read and fresh stationary Native samples. It performs GET/FC03 only and never sends the robot back. The record labels the initial setup as operator-established; it does not assert that an occluded car was detected or that returning the robot resets the car. See [fixed start and overlap](PUSH_ALIGNMENT.md#fixed-start-and-expected-overlap).

Two or more coherent samples, unchanged eligible flags, exact reported zero speed and at most 0.2 mm/degree pairwise drift admit a stationary teaching observation. These limits describe telemetry consistency at Native's 0.1-unit quantization, not endpoint accuracy or collision clearance. A stationary program register value alone never establishes readiness. Ineligible controller flags, moving data and single samples remain diagnostics. The collector does not read the selected TCP definition or certify that a measured TCP is the physical contact point.

## Establish the same physical reference in both frames

Record at least three non-collinear pairs spread across the intended working area, with a fourth independently captured check point. Prefer references surrounding the intended routes; several tiny probes at Pizza are useful for initial local response, but do not verify the whole A3 sheet. Additional checks at the far destination fronts and intersection turn region remain necessary before route commissioning.

Each pair describes one physical reference point in drawing millimetres and robot BASE millimetres, with the measured probe/TCP offset already accounted for. Do not pair the visible car roof centre with a TCP touching its rear. Elevated roof/pad pixels can have parallax relative to the paper-plane homography. Preserve one TCP definition, literal orientation and measured reference height during collection; independently check that the print plane is parallel to BASE XY. A tilted plane needs a separately measured 3D model, not a more permissive XY fit.

Bind every sample to map ID/version/geometry hash, camera epoch and registration ID, TCP ID/definition hash and tool ID. Paper replacement or an identity change invalidates the old fit. Repeated image frames and old POC slot poses are not new measurements.

### Use printed references instead of repeated broad-pad ruler readings

The operator clarified on October 28 that the broad, nonuniform pusher underside makes repeated ruler estimates inconsistent. The intended acquisition method is now to align one explicitly identified physical tool reference with known printed marker centres, record the actual stationary BASE pose, and calculate intermediate coordinates from that fixed relationship. This is work-frame registration, not a requirement to detect the markers during every motion.

Use widely spaced reachable references. Three non-collinear correspondences can establish a candidate; reserve a fourth reference for an independent check and check additional interior road points before expanding route coverage. The marker centres have their own drawing coordinates and must not be replaced by nominal paper corners. A marker disappearing beneath a broad pad does not establish that the active TCP is over its centre. A clearly identifiable tool point, or a rigid temporary pointer with an accounted-for TCP offset, resolves that alignment ambiguity. Retain the current TCP definition unless a separately measured change is explicitly installed.

For a level print and fixed working height, the model is `b = R F d + t`, where `d` is drawing XY, `b` is BASE XY, and `F = diag(1, -1)` normalizes the drawing's downward Y axis. For a fixed measured start, a displacement can be evaluated as `b_target = b_start + R F (d_target - d_start)`. Do not introduce an empirical image-height scale into this metric displacement. A tilted print needs a measured spatial frame and a contact-height plan rather than silently changing the fixed working Z.

Industrial work-frame teaching uses the same principle: ABB's [TeachSaver guide](https://library.e.abb.com/public/451003a080e2d11bc125766d003a35f9/TeachSaver_PowerPac_1.1_Users_Guide_English.pdf) describes matching three robot-taught points with corresponding workpiece geometry using a calibrated tool. [Horn's absolute-orientation paper](https://people.csail.mit.edu/bkph/papers/Absolute_Orientation_Scanned.pdf) provides the least-squares coordinate-registration foundation. These references support the method, not the accuracy of this particular installation.

### Current physical evidence, October 28

Deliberate commissioning on the final `2026-10-28.4` print has now completed eight free-XY translations: two 2 mm axis trials, five 20 mm trials and one 10 mm trial. Their endpoint receipts use the inherited persistent receiver with independent Native readback. All retained the same literal contact Z and orientation. Two no-motion local-profile renewals retained the same receiver session; no new pendant script or repeated PLAY was required. Five additional IK/FK queries were read-only and establish neither a runnable sweep nor actual wrist rotation.

Four operator ruler pairs were preserved exactly. Their metric inconsistencies were retained as a failed provisional registration; no scale correction, discarded point or relaxed fit threshold was used to create an installation. Six distinct stationary positions spanning a local 20 x 60 mm BASE patch were also recorded with unchanged native images and fixed camera registration. An offline red-contour detector identified the same elevated pad corners across these images. Three images were reserved for checking the feature-motion relationship fitted to the other three. The resulting relative axis direction was consistent near 22 degrees, while feature-height-dependent apparent scale remained separate from physical paper millimetres.

This is evidence of connected coordinate-based robot translation and local relative-axis diagnostics. It is not accepted absolute TCP-to-paper registration, full-sheet accuracy, a learned car-pushing response, a wrist/contact turn, signal operation or arrival at any of the three destinations. Raw robot poses, profiles, ruler readings, endpoint receipts and native images remain private outside the repository. Hardware state must always be inspected freshly; this paragraph is a historical record, not a command or restart instruction.

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

`LocalBaseInstallation` uses `scope: "local_base_commissioning"` and deliberately has no map, calibration or camera fields. It records the current TCP definition hash, tool, payload, reviewed BASE envelope, fixed Z/orientation and actual site review. The user authorized wider free-XY coordinate teaching after reporting current tool/arm/hose clearance on October 28. Software ceilings are now 200 mm of envelope span per axis, 20 mm per trial, 10 mm/s and 20 mm/s²; defaults remain 1 mm, 1 mm/s and 2 mm/s². Each actual installation and profile must still specify its narrower reviewed bounds and limits. Raising a schema ceiling does not apply a profile, grant clearance outside that review or establish drawing-to-BASE calibration.

At runtime the HTTP admission layer accepts only same-Z, fixed-literal-orientation `translate` commands with purpose `commissioning`; it rejects pushes, tool repositioning and rotation. Envelope Z bounds allow readback representation and never permit vertical travel. Free-XY teaching must use actual reviewed paths clear of the car and physical obstacles; it cannot relabel a vehicle push as teaching. A separate held profile-renewal path below applies a new actual local review without motion or arming. The inherited receiver retains its original generic BASE policy and protocol checks. Use only the single-owner commissioning API; these additional scope restrictions are not a newly installed pendant feature.

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

### Renew a current local review without reconnecting Rodi

Paper replacement or another physical installation change requires a new actual review. With the existing persistent receiver connected and idle, acquire a fresh full-precision TCP and joint baseline, prepare the reviewed local installation and profile, then use the authenticated commissioning API:

1. `POST /v1/installation` with the new `LocalBaseInstallation`. This disarms the service and requires no active or unresolved command.
2. `POST /v1/hold` to keep later motion inhibited.
3. `POST /v1/commands` with `kind: "profile_update"`, `purpose: "commissioning"`, the new installation ID, current exact receiver session/sequence/profile binding and complete candidate profile. Include no target or rotation edge.
4. Wait for the bound `profile_applied_verified` receipt and refreshed idle state. The receiver session remains the same; sequence and profile identity change. Refresh never arms the service. Any unknown outcome requires reconciliation, with no automatic republication.
5. A subsequent local trial requires a separate current-binding `POST /v1/arm` and its own admitted bounded translation.

Renewal is accepted only while explicitly disarmed **and** held. Its installation ID and review reference must differ from the current profile's review; TCP definition, tool and payload must remain identical. The candidate must bind the new review exactly, keep all local volume/step/speed/acceleration ceilings and disabled rotation fields, and contain no board or camera qualification. Its expected TCP and joints must equal the receiver's fresh full-precision values. The new fixed Z and literal orientation must equal that exact current pose, rather than merely fit a quantization tolerance. Admission checks run again immediately before publication, so a changed baseline, identity or hold state rejects the renewal before the mailbox is written.

The unchanged inherited protocol performs its idle `profile_prepare` / `profile_ready` / `profile_commit` / `profile_applied` exchange and repeated Native checks. Profile update contains no motion target and does not use the motion PREPARE/GO path. No pendant script replacement, repeated PLAY, receiver restart or direct mailbox access is required by this application workflow. A renewed local profile still does not qualify pushing, vehicle turns, vertical travel or drawing-to-BASE geometry.

After that foundation, collect short straight-push response, measured retraction/recontact, left/right contact-turn response and mandatory stop/signal approaches. Compile the three graph routes from physically qualified primitives, then run and record each destination separately. Preserve the distinction between TCP/wrist rotation and actual vehicle yaw change. See [Contact pushing](PUSH_ALIGNMENT.md) and [Robot control](ROBOT_CONTROL.md).
