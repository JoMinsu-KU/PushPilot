<sub>[PushPilot](../README.md) / Engineering / Fixed-face calibration review</sub>

# Relative image agreement does not yet locate the physical pushing face.

**October 28, 2026 result: physical calibration incomplete. No accepted transform or qualified operating region was produced.**

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

## Selected next acquisition: one independent whole-segment datum

The operator has no right-angle projection guide. Use an independent near-normal image of the **entire same lower physical face segment**, together with known printed references, while the robot and original camera remain unchanged. A phone/tablet image is an acquisition option rather than an assumed calibrated instrument. Keep the selected segment near the image centre, retain the original image and capture stationary robot coordinates with it. Do not substitute a guessed sharp corner or repeat ruler measurements at every pose.

Before admitting the datum, bound height/viewing-ray parallax, registration and segment-localisation errors. In particular, `height_bound * tan(ray_angle_bound)` contributes to the anchor error. A casual top-looking photograph does not prove a paper-normal projection. If the actual segment is hidden or the error cannot be bounded, retain UNKNOWN rather than using the photo as ground truth.

The proposed anchor budget is at most 1 mm. It is an unachieved acquisition target. With a 3 mm total physical error limit, retain at most 2 mm for the remaining held-out error under conservative addition; do not quote the image residual alone. The provisional D similarity residual 2.235 mm would fail that budget even if an anchor were available. Improve the actual reference/model and use genuinely new withheld samples; do not relabel that failure as a pass.

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
