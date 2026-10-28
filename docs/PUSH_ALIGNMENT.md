<sub>[PushPilot](../README.md) / Engineering / Contact pushing</sub>

# Keep the contact height. Measure the car outcome.

The operator placed the wheel-less car and pusher on the city print on October 28, 2026 and requested retaining the current contact Z while preparing XY control and drift correction. Current Native FC03 TCP/joint snapshots are stored privately. An unchanged controller Z value is a recorded starting condition, not a measured pad-to-paper clearance or a qualified working height. No physical push or correction is established by this design.

## Coordinate and tool contract

| Frame or setting | Collection and use |
|---|---|
| Drawing | Current versioned city graph, nominal road centerlines and destination fronts |
| Camera | Existing fixed drawing homography and native unchanged images; expected marker covers do not refit it |
| Command reference | Physical registration is pending; the flexible underside is an extended line, so the proposed lower-corner point alignment was withdrawn |
| Pusher | Record the selected TCP definition/offset, tool identity and payload; measure the offset from that TCP to the actual pushing-face center |
| Car | Measure footprint length/width, contact face, height and front direction; record the actual center/yaw independently of the nominal Pizza start |

With independently verified print scale and a horizontal work plane, fit a constrained planar rigid fixed-pose reference-to-command transform and inspect residuals on the independent point. If scale, tilt or residuals do not support that model, measure the installation before creating motion targets. Do not hide disagreement with an unconstrained affine fit. The AR image homography is not a robot command calibration.

Known printed geometry and independent checks remain the registration objective, without teaching every complete route. The proposed three-plus-one lower-corner alignment was withdrawn after the user showed that the current flexible underside supplies a line rather than a repeatable sharp point. Do not manufacture that point or use pad overlap as proof of alignment. A future valid physical-reference method must retain its original measurements, declared tolerances and independent checks. An already touching start pose is one TCP observation; it is not a measured full-board transformation or car-center-to-TCP offset. [Horn's absolute-orientation formulation](https://people.csail.mit.edu/bkph/papers/Absolute_Orientation_Scanned.pdf) supplies point-registration mathematics, not evidence that this gripper provides point correspondences.

Changing a target TCP pose is different from changing the controller's TCP definition. Changing the definition or rotating an offset tool can change the physical pad height even if the numeric TCP Z remains fixed. Preserve the current definition and literal orientation for the first straight-push trials. Any later orientation change needs its own tool geometry and swept-clearance checks.

## Calibrate references, then execute from coordinates

The user's current direction is a coordinate/formula-based executor, with vision used for auxiliary calibration diagnostics and meaningful outcome checks. It does not require uninterrupted tool/car tracking or a continuous visual-servo loop while the robot moves. Register the fixed camera/print relationship once, separately establish and independently validate the reference-to-command relationship, then bind both to the current map, print, camera, tool and TCP identities. Expected occlusion by the robot or hose retains those exact references; a confirmed physical view or installation change requires explicit review.

Robot-guided XY samples can compare actual BASE displacement with the motion of one identifiable rigid tool feature. Keep their fixed Z/orientation and independent held-out samples. An elevated pad feature projected through the paper homography remains an apparent paper-plane feature: it may support axis/scale diagnostics, but is not an absolute TCP ground measurement. A local feature-plane fit or a rough ruler reading cannot silently become a qualified full-board transform. Preserve its declared support region and uncertainty until physical reference checks justify extension.

Keep two different outcomes in the executor state. Receiver/Native endpoint and stationarity evidence establish the robot's actual TCP movement. The vehicle state is separately `car_xy` and `car_yaw`, with a measured or predicted source. A successful robot movement does not prove the expected vehicle displacement, retained contact or arrival. The fixed Pizza setup may supply an operator-established initial condition while the tool overlaps the car; it cannot be reused as a fresh vehicle observation after motion.

## Compute contact geometry in the vehicle and tool frames

Use a declared right-handed map-plane convention for the following geometry; explicitly convert the drawing's downward Y before applying planar rotations. Let `r_car` be the selected contact point relative to the car centre in the vehicle frame. The intended map-plane contact point is:

```text
p_contact = car_xy + R(car_yaw) * r_car
tcp_xy = T_map_to_base(p_contact) - [R_base_tool * r_tcp_to_contact]_xy
```

`T_map_to_base` is the independently measured map-to-BASE transform. `R_base_tool` is the rotation of the current physical tool/TCP frame into BASE. `r_tcp_to_contact` is the measured vector from that TCP origin to the selected point on the actual pushing face, expressed in the tool frame. The second equation subtracts the rotated TCP-to-contact offset to place the physical contact point at its intended BASE location. Contact height and paper clearance remain separate measured requirements; the XY equation does not justify lowering the tool or rotating an offset pad at an unverified height.

The same physical pushing face can point in a different world direction when tool yaw changes. Its rotated offset and face normal must therefore be recomputed; a constant BASE offset or an unconditional addition to the displayed RZ is insufficient. Measure the usable contact offset for each physical face and tool-pose configuration, or validate a rigid geometric model across those configurations. Retain the actual tool convention and controller rotation semantics. Do not infer face geometry from the pad's image centroid or from its nominal overall width alone.

The operator selected the physical rubber face currently visible on the screen-right side as the primary pushing face. Give that face a persistent tool-local identity, rather than renaming whichever surface happens to appear on screen-right later. Retain the existing tool; do not add a pointer or replacement pad. The lower-corner point proposal is withdrawn. Measure the actual extended contacting region/TCP relationship and its compliance before extending to contact turns. Geometric contact candidates in the code are not proof that the broad pad can realize those contacts.

The face does not need to be visible during operation. Once its rigid offset `r_tcp_to_face` and normal `n_face` are measured, calculate `face_base = tcp_base + R_base_tool * r_tcp_to_face` and `normal_base = R_base_tool * n_face` from controller pose feedback. A fixed-orientation reference-to-command calibration may absorb the unknown offset for that orientation; it cannot provide an unmeasured yaw-dependent offset or full face geometry. An occluded face preserves its tool-local identity and qualified model, without image-driven reidentification, mapping refit or command replay. Separately, actual car slip remains an observation/contact-model question; controller pose alone cannot measure it.

A car that becomes diagonal still uses its current vehicle-frame rear/contact geometry in these equations. Recompute the selected contact point and intended force direction from the accepted current `car_yaw`, rather than retaining the initial eastbound heading or using camera screen-left/right. A changed image silhouette does not change the identity of the physical pushing face. An unreadable heading remains unknown, rather than a reason to invent a new face or assume the car stayed aligned.

A centred rear contact primarily proposes forward translation. An off-centre contact proposes a yaw moment whose direction depends on both contact position and applied force. Their actual effects must come from measured responses on this car and surface. A wrist yaw change reorients the pusher; it does not establish a car yaw change. Reaching a new contact requires an admitted approach/recontact path rather than rotating while pressed against the car or teleporting the TCP to a different side. [Stable-pushing mechanics](https://publications.ri.cmu.edu/stable-pushing-mechanics-controllability-and-planning) and [contact-mode feedback pushing](https://arxiv.org/abs/1611.08268) motivate this distinction; neither supplies this installation's contact offsets or guaranteed steering response.

## Straight travel before steering

Use a broad, flat pushing face centered behind the car, where the actual rear shape permits two separated contacts or stable line contact. Avoid assuming that an arbitrary curved rear surface will align itself. Record whether the current red pad contacts the intended face, whether its lower edge clears the paper, and whether it pushes rather than squeezes, lifts or tilts the car.

The pad is reported as approximately 20 mm wide and the car body as 18 mm wide. If both actually presented flat, parallel faces of those widths, their nominal width surplus would leave only about 1 mm per side for full-width overlap when centred. This is a geometric inference, not measured usable contact clearance: the current triangular pad has a non-uniform section, so its effective width at the actual contact Z must be measured. Lateral error or a diagonal rear face can concentrate contact near an edge/corner and introduce unwanted yaw. Passive alignment by the broad face is an empirical hypothesis to test, not a guaranteed recovery mechanism.

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

For a large observed heading error, inhibit the next forward push and use a qualified retract/recontact followed by a short measured contact-turn response. Do not expect a longer straight push or an arbitrary corner hit to restore alignment. The current local teaching profile preserves literal working Z and tool orientation; these recovery and face-reorientation proposals do not enable or claim a new physical wrist rotation.

## Core controller: choose the contact, direction and distance

The user's later clarification makes drift recovery and physical car rotation the core algorithm, rather than replaying destination TCPs. `backend/robot_control/pushing.py` implements a pure empirical one-step proposal selector. It requires measured vehicle length/width and an explicit rectangular footprint approximation; actual rounded bumpers, the pusher's finite face width and reachable contact approaches still need physical qualification.

Define the vehicle frame as right-handed: +X is forward, +Y is the vehicle's left and positive yaw is counterclockwise. A drawing whose Y grows down must be converted explicitly before using this controller. Rear left/right are vehicle-relative, not the camera's screen-left/right.

| Contact candidate | Proposed effect to measure | Main use |
|---|---|---|
| Rear centre, forward push | Translation with small yaw, where stable line contact is attainable | Straight progress |
| Rear left, forward push | Nominal clockwise torque | Correct positive heading error or begin a right turn |
| Rear right, forward push | Nominal counterclockwise torque | Correct negative heading error or begin a left turn |
| Left/right side centre, inward push | Nominal lateral translation | Reduce cross-track offset after a qualified recontact |
| Front-left side, inward toward vehicle right | Nominal clockwise torque plus lateral motion | Correct a leftward nose deviation |
| Front-right side, inward toward vehicle left | Nominal counterclockwise torque plus lateral motion | Correct a rightward nose deviation |
| Rear-left / rear-right side, inward push | Opposite torque sign from the corresponding front-side contact | Alternative yaw correction or a separately measured compensating contact |

The torque signs follow `tau = rx * Fy - ry * Fx`; they are proposals under the stated frame convention, not a claim about this car's friction centre or actual angular response. Offset contacts lie partway along the rear face, not automatically on its sharpest corner. A wide pad may contact both sides at once and erase the intended moment. If the current tool cannot isolate a candidate contact, exclude that candidate rather than pretending a point force exists.

For the reported 45 x 18 mm rectangular approximation, the side-offset candidates are at body X = +/-13.5 mm and Y = +/-9 mm. These are geometric candidates partway along the sides, not surveyed contact points on the actual rounded body. The current catalogue includes `front_left_side`, `front_right_side`, `rear_left_side` and `rear_right_side`; adding their geometry supplies no response gain, approach path or permission to use them physically.

Separate heading error from cross-track error before selecting a correction. A car whose nose points left of the desired heading may admit a short front-left inward push to propose clockwise correction. A car parallel to the road but displaced left instead calls for a measured lateral-centre response. When both errors exist, compare the supported responses against both objectives and the inflated road footprint; a steering action can also translate the car. In particular, front-left and rear-right inward pushes have the same nominal clockwise moment but opposite lateral force directions. Alternating them is a candidate for reducing net lateral displacement while turning. Each contact still needs its own measured model, clear recontact path and outcome check; the current one-step selector does not execute or guarantee a blind two-push couple.

The practical learning loop is `measure vehicle pose -> propose a supported contact/distance -> compile and admit a coordinate action -> verify robot endpoint -> review vehicle outcome -> update response/state`. Use the actual before/after vehicle yaw, body-frame translation, pusher travel and measurement uncertainty to learn corrections. No universal command such as "push the front side 2 mm to rotate 5 degrees" is assumed. The data-efficient pushing work cited below supports learning a local dynamics model for constrained feedback control, not a guaranteed trial count for this car. Completely eliminating vehicle observations would require separately qualified contact/force feedback or physical constraints; [force-feedback pushing research](https://arxiv.org/abs/2305.11048) uses a contact force sensor and does not establish that this robot currently supplies that measurement.

`fit_response` needs at least three distinct measured small-push trials per contact. It fits local body-frame forward/lateral/yaw response per millimetre of pusher travel and records empirical residuals plus the actually tested distance interval. Unmeasured contacts, mixed installation/tool/TCP/car/surface identities, excessive residuals and unsupported distances are rejected. A `measured` source label is a structured assertion; a future trusted trial recorder must validate the unique command receipt, before/after observations, uncertainty and measured geometry. This pure fitter does not independently establish physical provenance.

`select_next` enumerates only learned contact/distance candidates and predicts one short car step. It scores progress, cross-track error, heading error and empirical uncertainty, with conservative inflated-rectangle coverage over a supplied union of road rectangles. It refuses wrong-sign turning responses and steps exceeding the measured translation/yaw range. A 90-degree objective yields a bounded intermediate proposal; after that push, observe and recompute contacts in the new vehicle frame. The sampled coverage model describes an interpolated rectangular car only. It does not qualify the tool, robot, hose, retraction/recontact path or the unknown actual physical sweep. This is a finite one-step receding-horizon selector, not a full hybrid MPC implementation.

An action proposal carries vehicle contact coordinates, pushing direction/distance and predicted vehicle pose. It carries no TCP command or motion authority. The later executor must use measured drawing-to-BASE and contact-to-TCP geometry, validate approach/recontact clearance, retain the installed receiver's guards, then independently check the robot endpoint and vehicle outcome. Selecting a new contact does not teleport the tool there.

Stable contact mechanics and feedback pushing motivate this design: [Lynch and Mason's stable-pushing study](https://publications.ri.cmu.edu/stable-pushing-mechanics-controllability-and-planning), [Hogan and Rodriguez's contact-mode feedback controller](https://arxiv.org/abs/1611.08268), and [Bauza, Hogan and Rodriguez's data-efficient learned pushing controller](https://proceedings.mlr.press/v87/bauza18a.html). The cited experiments do not validate this installation or prescribe a guaranteed number of trials. The current code is an original, smaller empirical proposal implementation, not a reproduction of those published controllers.

## Fixed start and expected overlap

The operator may establish one fixed Pizza car setup and a repeatable robot start even when the pusher overlaps the car in the camera view. `start_reference.py` freezes the current full-precision idle TCP/joints against fresh stationary Native samples and exact map/TCP/tool identity. `tools/capture_fixed_start.py` uses authenticated GET plus FC03 only; no vehicle detection, image warp, return command or camera restart is involved.

The initial car source remains `operator_fixed_setup`, not a successful detector result. This robot start record is not a measured car pose, contact model or full drawing-to-BASE registration. Later verification checks only the robot; returning the tool alone cannot prove the car was reset. Do not reuse the initial car location as a fresh post-push measurement.

During admitted motion, Native/receiver completion and the existing independent heartbeat govern robot state. Tool/marker visibility is not required on every frame. The optional `visual_probe.py` component/feature-flow diagnostics can report `unknown` without dropping the robot session or refitting the board. The first real small retreat exposed red-pad/printed-start-mask ambiguity; this is a diagnostic limitation, not a robot motion failure.

Vehicle observation is needed at the action/check boundaries where lateral drift, yaw, signal or arrival must be decided. Expected transient occlusion retains the fixed map/start/contact model and waits for an eligible new observation or a separately qualified observation retract. It does not justify inventing completion, replaying the push or blind continuation. MUSE reviews the unchanged imagery and expected outcome, while numerical car metrology retains its own source and uncertainty. The present physical API's trusted automated observation/MUSE bridge is still unconnected.

Between observations, a future estimator may propagate a predicted vehicle state from the measured contact-response model and the robot's verified actual displacement. Propagate its covariance or a conservative error bound as well, accounting for contact uncertainty and the model's tested range. Predicted state must remain labelled `predicted`; it must not be supplied as a fresh `MeasuredPose` or silently assigned zero uncertainty. A new accepted observation corrects that prediction, while a disagreement outside the validated correction region inhibits the next push.

During one admitted bounded segment, expected occlusion does not force image-by-image stopping or a new transform fit. At the segment endpoint, preserve the verified robot result and wait for a fresh eligible vehicle/MUSE outcome when the car is unreadable or the review is UNKNOWN. Do not blindly launch the next segment, repeat the last command or turn a predicted arrival into an observed success. A separately qualified retract may expose the vehicle; its own movement and clearance remain explicit executor actions. The numerical vehicle estimate, MUSE review, robot receipt and signal judgment retain independent provenance.

## Implementation boundary and next slice

Existing `translate` preserves literal TCP orientation and can support reviewed short planar pushes. Existing `rotate` requires a raised tool and reviewed joint edges. Keep those guards. The new empirical proposal selector, fixed-start capture and visual diagnostics have equipment-free tests; actual car response collection, contact approaches and physical executor integration remain pending. No contact turn is enabled merely by those modules.

Proposed observation fields are `x_mm`, `y_mm`, `yaw_deg`, `uncertainty`, `visible_fraction`, `frame_id`, `captured_at` and `installation_id`. A metric estimator must account for roof-height parallax and front/back ambiguity before its pose drives targets. MUSE receives the unchanged before/after images, expected action and bound source identities for progress/uncertainty review, and judges the paper signal only at the current verified stop. It does not generate authoritative BASE coordinates. The current physical API still rejects an unconfigured automated observation/review bridge.

The next admitted push needs both the verified robot endpoint/stationarity receipt and a fresh accepted vehicle outcome. A robot `DONE` alone cannot prove car completion. Keep the listener heartbeat independent of image processing and MUSE latency; unknown car outcomes inhibit the next push rather than restarting the camera or pendant.

The implementation order is: fresh TCP/tool/payload and stationary readback; reviewed installation/profile and persistent idle connection; drawing-to-BASE teaching/check; straight-push repeatability; car-pose/physical-review bridge; small drift corrections; contact turns; mission stop/signal integration. No historical POC slot target, profile or pending command enters this sequence.
