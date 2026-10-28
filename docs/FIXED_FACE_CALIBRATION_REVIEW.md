<sub>[PushPilot](../README.md) / Engineering / Fixed-face calibration review</sub>

# Relative image agreement does not yet locate the physical pushing face.

**October 28, 2026 result: physical calibration incomplete. No accepted transform or qualified operating region was produced.**

**Later operator correction:** the tablet acquisition and gripper-image tracking approach below were stopped. Preserve this review as historical diagnostics, not the active procedure. Current control uses TCP coordinates, a fixed planar frame and endpoint/basis interpolation; vision verifies vehicle/signal outcomes. See [TCP coordinate control](TCP_COORDINATE_CONTROL.md). Three new fixed-pose TCP moves completed to receiver sequence 29 without qualifying a whole-map transform or a destination.

The latest request keeps the current literal Z, orientation, low-speed Linear limits and safety configuration. It excludes rotation, Z changes, vehicle contact and safety-setting changes. The earlier [opposite-normal line procedure](LINE_DATUM_COMMISSIONING.md) cannot be completed within this fixed-orientation scope and is not the current execution procedure.

This review used the existing actual image/coordinate ledger, a fresh stationary Native FC03 series of three samples and three new original camera frames. No motion command, arming, profile change, camera restart, receiver restart or pending-command replay occurred during this review. The receiver remained connected and idle at sequence 26. Source images and private operating coordinates remain outside Git.

## A. Relative feature-to-command diagnostics

The existing physical samples span a local 20 by 60 mm BASE patch. The most defensible previously traversed car-clear paths are the P2-P3, P3-D and D-E segments, plus the recent E-P3-F sequence. This is path evidence, not a whole-sheet boundary survey or certification of the complete gripper footprint. Do not infer a new reachable region from a rejected transformation.

The lower red contour was compared at seven distinct positions. These were provisional manual annotations of an extended lower segment; consistent identity of its actual physical endpoints has not been established. P0/P1/P2 were used for fitting, and P3/D/E/F were withheld. No sample was discarded or moved into the fit after its check result was seen.

Predeclared targets remain maximum fit error 2 mm, maximum independent total physical error 3 mm, unexplained scale deviation 2% and repeat alignment spread 1.5 mm. The latter cannot be certified by an unverified image reference.

| Diagnostic | Fit errors, mm | Held-out residuals P3 / D / E / F, mm |
|---|---|---|
| Unit-scale apparent-paper rigid fit | 0.784 / 1.432 / 2.199 | 2.563 / 3.640 / 2.457 / 1.973 |
| Unrestricted image-feature similarity | 0.654 / 0.714 / 0.302 | 0.496 / 2.235 / 1.258 / 0.210 |

These residuals compare actual robot displacement with a model of image features after the display homography. They are **not independently measured physical contact-face errors**. The unit-scale model exceeds both fit and check targets. The similarity uses scale 0.934842, an unexplained deviation of 6.516%; its smaller residuals cannot justify rescaling the paper or issuing robot targets. Possible causes include height parallax, changing contour identity, lens/display geometry, print geometry and plane orientation. This review does not establish one cause as the explanation.

## B. Physical face-to-map location

The supplied TCP offset and nominal gripper drawing do not identify the actual installed unloaded/loaded face offset. The approximately 3 mm operator-reported tip gap is not a measured plane or height bound. No applicable camera intrinsic/distortion calibration or surveyed paper BASE plane was found.

With the currently accepted fixed-pose image/XY correspondences alone, the actual face-origin translation and the elevated feature's projection offset remain confounded. Additional identical translations do not supply the missing absolute reference. A fixed-pose face-reference command transform could absorb a constant tool offset, but only after that face reference is actually located on the paper. It must not masquerade as a separately surveyed paper-origin/TCP transformation or support later wrist rotations.

### Bounded alternative investigated: rigid axial edges

The silver actuator's longitudinal grooves are more credible axial-line candidates than the inclined flexible fingers. A joint candidate camera fit used nine segments from preselected P0/P3/F images, the paper homography's metric constraints and a square-pixel, zero-skew camera hypothesis. D and E were withheld without refitting:

| Original image endpoint residual | RMS, px | Maximum, px |
|---|---:|---:|
| Fit P0/P3/F | 0.3943 | 0.6778 |
| Held-out D | 0.3887 | 0.4305 |
| Held-out E | 0.4447 | 0.7112 |

This is promising image agreement, not a calibrated camera result. The candidate assumes that the selected installed grooves are parallel to BASE Z and that the paper is parallel to BASE XY. The nominal drawing does not independently establish those relationships. The narrow motion patch cannot tightly verify plane parallelism: fitting the two elevated features gives different horizon estimates, highly sensitive to one-pixel perturbations.

Even while holding those hypotheses and the paper homography fixed, bounded one-pixel endpoint perturbations permit a roughly 18.9 mm range in the inferred camera normal-foot position. Its effect on the provisional lower-feature correction is about 0.64 mm, excluding distortion, homography uncertainty, actual groove direction, plane tilt, segment identity and scale-estimation uncertainty. Therefore it is not a total physical error bound, and the 3 mm acceptance requirement remains unproven. No inferred camera matrix, normal foot or corrected transform was installed.

This candidate follows the projective principles in [Criminisi, Reid and Zisserman, *Single View Metrology*](https://www.robots.ox.ac.uk/~vgg/publications/1999/Criminisi99/criminisi99.pdf) and [Liebowitz, *Camera Calibration and Reconstruction of Geometry from Images*](https://www.robots.ox.ac.uk/~vgg/publications/2001/Liebowitz01/). These sources support the geometry; they do not verify this installation's physical line identities or accuracy.

## Selected next acquisition: fixed-optics tablet checkerboard

The operator has no projection guide and supplied an overhead photograph instead. It shows both distal red jaw ends, but the wrist hides proximal material and the correspondence between the phone's upper rubber rim and the installed camera's lowest face edge is unproved. The feature is far from the photograph's optical centre, and no applicable phone intrinsics or capture-time pose binding are available. Three visible markers can register the paper plane; they cannot make an elevated rubber contour a paper-normal projection. The photograph remains useful for feature identity, not an accepted absolute anchor.

More translations through the same uncalibrated camera would repeat the unresolved projection ambiguity. A casual second overhead photograph would retain unbounded viewing-ray parallax. The selected route is therefore **one bounded intrinsic/distortion calibration of the installed camera using the existing tablet**, followed by reconstruction of the same material face reference. This avoids a new probe, a ruler at each position, robot rotation or a Z change. It is a candidate route, not a guaranteed completion.

Read-only V4L2 inspection found continuous autofocus enabled, absolute focus 20 and zoom 131. No setting was changed. Before acquisition, obtain explicit approval to disable continuous autofocus while preserving the verified current focus, zoom, pan, tilt and native 1920 by 1080 resolution. Re-read those values at execution; if focus is no longer 20, do not silently substitute a new setting. The autofocus helper upload was rejected by automatic approval review because the earlier authorization covered read-only inspection only. Do not upload or execute that helper, an equivalent command or an indirect workaround without new user authorization.

The isolated [tablet target](../tools/camera_calibration_target.html), [camera-only collector](../tools/capture_camera_intrinsics.py) and [offline estimator](../backend/robot_control/camera_intrinsics.py) are prepared. They do not install a camera model, issue robot commands or update the product's display registration. After approval, keep the camera mounted and robot held/disarmed, show the complete target in landscape, then move the tablet through the image centre and corners with varied tilt around both axes. Use **16 accepted stationary views within 240 seconds**: capture indices declare 12 fit views and four held-out views before fitting. Unit square dimensions suffice for intrinsics; the displayed squares must remain planar and square. Reflections, rolling display artefacts, poor coverage or inadequate tilt may invalidate this attempt.

For the large 13-inch tablet, the utility target now starts at 65% display size, with 50/65/80/100% choices that preserve square aspect. Only the complete checkerboard and its white border need to fit in the camera image; the tablet bezel may extend outside it. Start approximately parallel to the map in the clear right-hand area, without touching the installation. Do not move the robot home merely to fit the target. A timed-out target webpage or read-only optics monitor must be restored explicitly before acquisition; do not accept stale monitoring records.

The operator subsequently approved the autofocus-only change. Execution verified continuous autofocus 1 to 0, focus 20, zoom 131 and pan/tilt 0 unchanged, with no camera restart or robot motion. The former automatic-review rejection is no longer a missing authorization for that exact change; it is not permission for other optics changes. Two same-pose static native frames before/after the lock support image-geometry compatibility: 967 quality-passing printed-feature tracks have raw displacement RMS 0.117 px, P95 0.229 px and maximum 0.496 px over a 1514 by 637 px field. All 181 quality-failing tracks were retained in the private report. Independent detector corners differed by up to 1.635 px and one marker was not detected afterward. These observations neither qualify the actual face nor prove identical intrinsics for every historical autofocus-on frame. No accepted intrinsic or physical transform has yet been produced.

The estimator retains all accepted views and uses training images only for the camera matrix and five Brown distortion coefficients. It rejects inadequate viewpoint diversity. Predeclared image limits are 0.5 px training RMS, 0.8 px per-view RMS and 0.7 px held-out check-corner RMS. In each held-out image only even-index corners estimate the target pose; odd-index corners test it with the camera model frozen. No outlier pruning or threshold relaxation is allowed. Any changed optics/identity/resolution, missing fresh frame, robot baseline change, exhausted budget or failed image criterion terminates this attempt without an accepted physical transform.

### How this supplies the missing geometry

Intrinsics alone do not locate the face. First undistort printed references and face observations; do not decompose the existing distorted display homography as though it were a metric camera model. For a consistently matched material feature, known TCP XY translations at fixed orientation and Z define a metric feature plane: `X_camera(C) = r1 * Cx + r2 * Cy + t_feature`. The unknown constant feature-to-TCP offset is absorbed in `t_feature`. The calibrated paper pose gives origin `O`, orthonormal in-plane axes `p1`, `p2` and normal `n`. The feature's paper-normal location is then `d(C) = [p1 p2]^T * (X_camera(C) - O) = A*C + b`; invert `A` to obtain a **face-reference drawing-to-TCP command relation**.

This does not separately identify the true BASE location of the paper origin and the tool's physical offset. It is valid only for that material reference, current fixed orientation/Z and unchanged tool shape. If the paper is tilted relative to BASE XY, the clearance `n^T * (X_camera(C) - O)` varies with XY and must be bounded over the proposed path. A changing silhouette endpoint, deformed rubber edge or ambiguous face identity cannot be substituted for a matched material feature.

Reuse the existing original images, robot coordinates and held-out split only after proving optical compatibility with the newly fixed camera. Earlier frames were captured with autofocus enabled and have no per-frame focus record; a matching resolution or epoch alone is insufficient. Preserve them as historical diagnostics if compatibility cannot be demonstrated. Native FC03 readings before and after new acquisition independently check stationary robot coordinates; receiver API state alone is not that independent check.

Finally, reconstruct several new withheld positions on already verified complete-tool paths, check independent printed references and repeat alignment, and propagate camera, paper-pose, feature-localisation and print-scale uncertainty. The original maximum 2 mm fit, 3 mm total physical error, 2% unexplained scale and 1.5 mm repeat-spread limits remain unchanged. Where a separate absolute anchor is used, its proposed budget remains at most 1 mm, leaving at most 2 mm for other error by conservative addition. The former D similarity residual of 2.235 mm is not relabelled as a pass. Nominal A3/100% artwork dimensions are not independently surveyed print dimensions. Stop if the actual material reference or total error cannot be bounded; neither low checkerboard pixel error nor a visually aligned overlay completes robot calibration.

Once a valid reference is obtained, first qualify only the actually measured fixed-pose region and verified complete-tool swept paths. The needed future mission coverage is the road area of PIZZA-S, S-Office Building, S-C, C-Hanok and C-Villa, including road widths, turn envelopes, actual stop/signal observation and arrival areas. It is not a request to survey every building. This plan does not enlarge the active physical workspace or qualify those roads.

## Separate future car observation and recovery

This noncontact review establishes no vehicle pose or correction ability. A later contact phase must predeclare position/yaw uncertainty and freshness limits; confirm front/back heading or explicitly retain 180-degree ambiguity; and reject insufficiently visible, inconsistent or superseded measurements. A tool-line detection or predicted car pose is not an observed vehicle pose. Current source has no verified physical performance for these acceptance limits.

For a future obscured vehicle, first withhold contact commands, then permit at most three new stationary observations within a declared ten-second budget. This is a proposed recovery budget, not a measured result. If a new pose is accepted, recompute contact geometry and check a separately verified reapproach path, complete vehicle/pad swept area, actual front-boundary stop-line clearance and signal visibility before proceeding. Unknown results, failed budgets or missing path qualification remain held. Do not generate an untested unocclusion move, rotation or recontact automatically. None of these future contact/recovery actions is enabled by this review.

## Completion status

| Required result | Status |
|---|---|
| Physical map-to-command transform for the selected contact face | **Not accepted** |
| Multiple withheld physical-location errors | **Not measured**; relative image residuals reported above |
| Predeclared total error bound satisfied | **Not established** |
| Qualified area / height / orientation / face | **No qualified area**; current fixed-pose local evidence only |
| Hardware/session preservation | Fresh stationary evidence; no new motion or configuration change |

The minimum missing input is an independently bounded paper-normal location of the actual lower face segment, or equivalently verified camera/plane/feature geometry that supplies it. The current data does not justify filling that gap with an inferred success.
