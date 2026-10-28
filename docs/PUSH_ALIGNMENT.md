<sub>[PushPilot](../README.md) / Engineering / Contact pushing</sub>

# Keep the contact height. Measure the car outcome.

The operator placed the wheel-less car and pusher on the city print on October 28, 2026 and requested retaining the current contact Z while preparing XY control and drift correction. Current Native FC03 TCP/joint snapshots are stored privately. An unchanged controller Z value is a recorded starting condition, not a measured pad-to-paper clearance or a qualified working height. No physical push or correction is established by this design.

## Coordinate and tool contract

| Frame or setting | Collection and use |
|---|---|
| Drawing | Current versioned city graph, nominal road centerlines and destination fronts |
| Camera | Existing fixed drawing homography and native unchanged images; expected marker covers do not refit it |
| BASE | Teach three non-collinear, identifiable drawing-to-TCP correspondences at one unchanged TCP definition, orientation and height; reserve a fourth independent point for validation |
| Pusher | Record the selected TCP definition/offset, tool identity and payload; measure the offset from that TCP to the actual pushing-face center |
| Car | Measure footprint length/width, contact face, height and front direction; record the actual center/yaw independently of the nominal Pizza start |

With independently verified print scale and a horizontal work plane, fit a constrained planar rigid drawing-to-BASE transform and inspect residuals on the independent point. If scale, tilt or residuals do not support that model, measure the installation before creating motion targets. Do not hide the disagreement with an unconstrained affine fit. The AR image homography is not a drawing-to-BASE calibration.

The minimum teaching target is three calibration correspondences plus one independent check, rather than every complete route. Repeatability checks and reusable push/approach/contact-turn qualification add trials. The exact count depends on measured errors and clearance. An already touching start pose is one TCP observation; it is not three independent drawing correspondences or proof of a car-center-to-TCP offset.

Changing a target TCP pose is different from changing the controller's TCP definition. Changing the definition or rotating an offset tool can change the physical pad height even if the numeric TCP Z remains fixed. Preserve the current definition and literal orientation for the first straight-push trials. Any later orientation change needs its own tool geometry and swept-clearance checks.

## Straight travel before steering

Use a broad, flat pushing face centered behind the car, where the actual rear shape permits two separated contacts or stable line contact. Avoid assuming that an arbitrary curved rear surface will align itself. Record whether the current red pad contacts the intended face, whether its lower edge clears the paper, and whether it pushes rather than squeezes, lifts or tilts the car.

Start with one short, bounded, low-speed planar push at the recorded Z and fixed orientation after the installation/profile is reviewed. Choose the distance and speed from actual available clearance and tool/receiver limits. Measure actual progress, lateral drift, yaw and contact before authorizing another step. Qualify repeatability at several starting poses, then test small left/right contact offsets separately. Do not assign an unmeasured universal millimeter/degree tolerance or steering gain.

Stable line/multiple-point contact has an established mechanics basis, but depends on contact geometry and friction: [Lynch and Mason, Stable Pushing](https://publications.ri.cmu.edu/stable-pushing-mechanics-controllability-and-planning). Feedback pusher-slider control also explicitly accounts for friction and contact modes: [Hogan and Rodriguez](https://arxiv.org/abs/1611.08268). These references motivate the proposed qualification process; they do not validate this car, pusher, surface or controller.

## Drift decisions

| Observed result after a bounded push | Next decision |
|---|---|
| Forward progress, accepted yaw/cross-track error and retained contact | Continue with another admitted short push |
| Small measured yaw or lateral error within a separately qualified correction region | Select a measured correction primitive and bound its swept footprint |
| Large yaw, lost contact, unexpected progress or corridor violation | Inhibit the next command and inspect/reconcile the current state |
| Car temporarily unreadable | Reobserve; do not manufacture a pose or repeat the last push |
| Board markers covered while the camera/board fixture remains fixed | Retain the exact mapping and independent car/signal checks |

The proposed correction cycle is `planar_retract → recontact → short_correction_push → observe`. The retract must move opposite the qualified contact normal and have clearance; it is not a blind move through the car. Keeping Z throughout is possible only if the entire tool/arm path around the car clears the installed surface and objects. If the same-Z path is blocked, ask for a revised observation/recontact strategy instead of silently changing height.

Do not steer by immediately twisting the wrist while pressed against the car or by guessing a diagonal BASE target. First identify the response to contact offset and pushing direction. Use that measured response to select correction direction and gain. A 90-degree car turn is a separately qualified sequence of small contact turns, observations and recontacts, or a sufficiently broad qualified curve. A raised wrist rotation is not a car-turn primitive.

## Core controller: choose the contact, direction and distance

The user's later clarification makes drift recovery and physical car rotation the core algorithm, rather than replaying destination TCPs. `backend/robot_control/pushing.py` implements a pure empirical one-step proposal selector. It requires measured vehicle length/width and an explicit rectangular footprint approximation; actual rounded bumpers, the pusher's finite face width and reachable contact approaches still need physical qualification.

Define the vehicle frame as right-handed: +X is forward, +Y is the vehicle's left and positive yaw is counterclockwise. A drawing whose Y grows down must be converted explicitly before using this controller. Rear left/right are vehicle-relative, not the camera's screen-left/right.

| Contact candidate | Proposed effect to measure | Main use |
|---|---|---|
| Rear centre, forward push | Translation with small yaw, where stable line contact is attainable | Straight progress |
| Rear left, forward push | Nominal clockwise torque | Correct positive heading error or begin a right turn |
| Rear right, forward push | Nominal counterclockwise torque | Correct negative heading error or begin a left turn |
| Left/right side centre, inward push | Nominal lateral translation | Reduce cross-track offset after a qualified recontact |

The torque signs follow `tau = rx * Fy - ry * Fx`; they are proposals under the stated frame convention, not a claim about this car's friction centre or actual angular response. Offset contacts lie partway along the rear face, not automatically on its sharpest corner. A wide pad may contact both sides at once and erase the intended moment. If the current tool cannot isolate a candidate contact, exclude that candidate rather than pretending a point force exists.

`fit_response` needs at least three distinct measured small-push trials per contact. It fits local body-frame forward/lateral/yaw response per millimetre of pusher travel and records empirical residuals plus the actually tested distance interval. Unmeasured contacts, mixed installation/tool/TCP/car/surface identities, excessive residuals and unsupported distances are rejected. A `measured` source label is a structured assertion; a future trusted trial recorder must validate the unique command receipt, before/after observations, uncertainty and measured geometry. This pure fitter does not independently establish physical provenance.

`select_next` enumerates only learned contact/distance candidates and predicts one short car step. It scores progress, cross-track error, heading error and empirical uncertainty, with conservative inflated-rectangle coverage over a supplied union of road rectangles. It refuses wrong-sign turning responses and steps exceeding the measured translation/yaw range. A 90-degree objective yields a bounded intermediate proposal; after that push, observe and recompute contacts in the new vehicle frame. The sampled coverage model describes an interpolated rectangular car only. It does not qualify the tool, robot, hose, retraction/recontact path or the unknown actual physical sweep. This is a finite one-step receding-horizon selector, not a full hybrid MPC implementation.

An action proposal carries vehicle contact coordinates, pushing direction/distance and predicted vehicle pose. It carries no TCP command or motion authority. The later executor must use measured drawing-to-BASE and contact-to-TCP geometry, validate approach/recontact clearance, retain the installed receiver's guards, then independently check the robot endpoint and vehicle outcome. Selecting a new contact does not teleport the tool there.

Stable contact mechanics and feedback pushing motivate this design: [Lynch and Mason's stable-pushing study](https://publications.ri.cmu.edu/stable-pushing-mechanics-controllability-and-planning), [Hogan and Rodriguez's contact-mode feedback controller](https://arxiv.org/abs/1611.08268), and [Bauza, Hogan and Rodriguez's data-efficient learned pushing controller](https://proceedings.mlr.press/v87/bauza18a.html). The cited experiments do not validate this installation or prescribe a guaranteed number of trials. The current code is an original, smaller empirical proposal implementation, not a reproduction of those published controllers.

## Fixed start and expected overlap

The operator may establish one fixed Pizza car setup and a repeatable robot start even when the pusher overlaps the car in the camera view. `start_reference.py` freezes the current full-precision idle TCP/joints against fresh stationary Native samples and exact map/TCP/tool identity. `tools/capture_fixed_start.py` uses authenticated GET plus FC03 only; no vehicle detection, image warp, return command or camera restart is involved.

The initial car source remains `operator_fixed_setup`, not a successful detector result. This robot start record is not a measured car pose, contact model or full drawing-to-BASE registration. Later verification checks only the robot; returning the tool alone cannot prove the car was reset. Do not reuse the initial car location as a fresh post-push measurement.

During admitted motion, Native/receiver completion and the existing independent heartbeat govern robot state. Tool/marker visibility is not required on every frame. The optional `visual_probe.py` component/feature-flow diagnostics can report `unknown` without dropping the robot session or refitting the board. The first real small retreat exposed red-pad/printed-start-mask ambiguity; this is a diagnostic limitation, not a robot motion failure.

Vehicle observation is needed at the action/check boundaries where lateral drift, yaw, signal or arrival must be decided. Expected transient occlusion retains the fixed map/start/contact model and waits for an eligible new observation or a separately qualified observation retract. It does not justify inventing completion, replaying the push or blind continuation. MUSE reviews the unchanged imagery and expected outcome, while numerical car metrology retains its own source and uncertainty. The present physical API's trusted automated observation/MUSE bridge is still unconnected.

## Implementation boundary and next slice

Existing `translate` preserves literal TCP orientation and can support reviewed short planar pushes. Existing `rotate` requires a raised tool and reviewed joint edges. Keep those guards. The new empirical proposal selector, fixed-start capture and visual diagnostics have equipment-free tests; actual car response collection, contact approaches and physical executor integration remain pending. No contact turn is enabled merely by those modules.

Proposed observation fields are `x_mm`, `y_mm`, `yaw_deg`, `uncertainty`, `visible_fraction`, `frame_id`, `captured_at` and `installation_id`. A metric estimator must account for roof-height parallax and front/back ambiguity before its pose drives targets. MUSE receives the unchanged before/after images, expected action and bound source identities for progress/uncertainty review, and judges the paper signal only at the current verified stop. It does not generate authoritative BASE coordinates. The current physical API still rejects an unconfigured automated observation/review bridge.

The next admitted push needs both the verified robot endpoint/stationarity receipt and a fresh accepted vehicle outcome. A robot `DONE` alone cannot prove car completion. Keep the listener heartbeat independent of image processing and MUSE latency; unknown car outcomes inhibit the next push rather than restarting the camera or pendant.

The implementation order is: fresh TCP/tool/payload and stationary readback; reviewed installation/profile and persistent idle connection; drawing-to-BASE teaching/check; straight-push repeatability; car-pose/physical-review bridge; small drift corrections; contact turns; mission stop/signal integration. No historical POC slot target, profile or pending command enters this sequence.
