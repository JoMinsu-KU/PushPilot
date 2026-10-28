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

## Implementation boundary and next slice

Existing `translate` preserves literal TCP orientation and can support reviewed short planar pushes. Existing `rotate` requires a raised tool and reviewed joint edges. Keep those guards. Contact yaw correction and contact turning require new separately reviewed primitives; they are not enabled by this document.

Proposed observation fields are `x_mm`, `y_mm`, `yaw_deg`, `uncertainty`, `visible_fraction`, `frame_id`, `captured_at` and `installation_id`. A metric estimator must account for roof-height parallax and front/back ambiguity before its pose drives targets. MUSE receives the unchanged before/after images, expected action and bound source identities for progress/uncertainty review, and judges the paper signal only at the current verified stop. It does not generate authoritative BASE coordinates. The current physical API still rejects an unconfigured automated observation/review bridge.

The next admitted push needs both the verified robot endpoint/stationarity receipt and a fresh accepted vehicle outcome. A robot `DONE` alone cannot prove car completion. Keep the listener heartbeat independent of image processing and MUSE latency; unknown car outcomes inhibit the next push rather than restarting the camera or pendant.

The implementation order is: fresh TCP/tool/payload and stationary readback; reviewed installation/profile and persistent idle connection; drawing-to-BASE teaching/check; straight-push repeatability; car-pose/physical-review bridge; small drift corrections; contact turns; mission stop/signal integration. No historical POC slot target, profile or pending command enters this sequence.
