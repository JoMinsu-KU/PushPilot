<sub>[PushPilot](../README.md) / Engineering / Line datum commissioning</sub>

# Use a repeatable face constraint before fitting the map.

**Status: proposed physical acquisition procedure; not executed or qualified.**

The active installation still permits free-XY teaching at one literal Z and orientation. Eleven translations have endpoint evidence, including the latest +X 10 mm, -Y 20 mm and -X 10 mm sequence. These measurements establish robot displacement, not a paper origin, car displacement or a contact-turn response. The camera, persistent receiver and current TCP definition remain unchanged. This document neither applies a profile nor authorizes a new motion.

The selected alternative is **line-to-line registration using the same existing physical right rubber face**, with different actual face orientations later. No tool change, pointer, guessed corner, pad centroid or invented face midpoint is involved. The physical face keeps its tool-local identity when hidden. The method is conditional on finding a repeatable unloaded straight segment at the working height; the supplied flexible-gripper drawing alone does not establish that condition.

## Next experiment: repeat one line alignment

This experiment answers one question: can the existing face reproduce a physical line alignment well enough to serve as a datum? It does not attempt a map fit or push the car.

| Item | Predeclared procedure |
|---|---|
| Datum | One continuous straight segment of the existing right rubber face, at one fixed height, aligned with one specified **edge** of a printed straight bar. Do not alternate between the two edges or the middle of a thick bar. |
| Preparation | Establish a car-clear pose with the face parallel to the chosen line, unchanged TCP, fixed Z/roll/pitch, finger opening and pneumatic state. The present fixed-orientation profile does not establish that a suitable parallel pose has been reached. Any changed wrist orientation requires separate pose commissioning; no rotation is admitted by this procedure or the current profile. |
| Physical alignment evidence | The operator confirms the vertical projection of the actual face segment against the selected line edge. Both ends of that segment must agree without bending or pressing the rubber. An oblique camera image of an elevated edge overlapping ink is insufficient. If a near-normal physical view cannot establish alignment, record UNKNOWN. |
| Motion constraint | Once prepositioned, all trial approaches use one fixed BASE XY direction with a nonzero component normal to the line. The command coordinate perpendicular to this BASE approach vector stays unchanged; this does not assume a measured map tangent. Use only freshly bound local commands within the actual reviewed envelope, retaining literal Z and orientation. |
| Acquisition | Three independent alignments, each separated by a deliberate unloaded retreat of at most 2 mm. At most two adjustments of at most 2 mm per alignment. No continuous visual servo, automatic search or extra acquisition to discard an inconvenient result. |
| Record | Fresh full-precision receiver TCP/joints, stationary Native confirmation, actual line-edge ID, same-face/height/pneumatic confirmation, physical alignment verdict and original diagnostic frame. Preserve unknowns and failures. |
| Repeatability check | Maximum pairwise **XY TCP distance** across the three aligned captures must be at most **1.5 mm**. Since approach direction and commanded tangent are fixed, this bounds the normal spread conservatively without assuming a calibrated BASE normal. It is a repeatability test, not an accuracy certificate. |
| Pass | Three accepted physical alignments; all confirmations unchanged; pairwise spread within the predeclared limit; no unknown robot outcome. |
| Stop/fail | Any unclear vertical projection, changing/deforming face, unexpected contact, changed tool/board/camera identity, out-of-envelope request or unknown motion outcome. Stop after the third capture or the first failed/unknown condition; do not expand the search or relax the threshold. |

Required human input is the physical **line-alignment verdict**, not ruler coordinates for an arbitrary TCP point. This has not yet been acquired. Camera occlusion alone does not invalidate the robot connection or refit the fixed board transform; inability to establish this particular datum makes the metrology capture unknown.

## Full registration after the datum passes

Use drawing coordinates `q = (drawing_x, -drawing_y)` so that a proper planar rotation is meaningful. The desired relationship is `base = R q + t`, with unit scale. Printing at nominal A3 size is an assumption to check, not a reason to apply a fitted scale.

1. **Measure map direction.** Align the face at two separated locations on the same printed straight edge, with the identical wrist orientation, opening and height. The difference between their actual TCP positions gives the line tangent independently of the unknown TCP-to-face offset. Record which drawing tangent direction was followed; an unoriented line alone has a 180-degree ambiguity. Use the longest valid baseline within the real straight segment and reviewed reach. A short baseline may have inadequate angular precision even if the first experiment passes.
2. **Measure a parallel-line distance.** At the same wrist orientation, align the same face with a different parallel edge of known drawing separation. The unknown face offset cancels from their normal TCP separation. Keep this capture out of the origin/offset solve and compare measured distance with nominal distance. Reject a discrepancy greater than 2%; do not hide it by scaling the map. This checks scale in one normal direction only, not second-axis scale, shear or full-sheet print geometry.
3. **Solve origin and face-normal offset.** Acquire three aligned captures with the same physical face's actual normal in map directions +X, -X and +Y. The -X case requires physically reversing that face orientation, rather than using the other finger, another same-yaw parallel line or a sign change in an equation. These captures solve two translation components and one constant unloaded face-normal offset.
4. **Check two normal directions independently.** Reserve newly captured vertical and horizontal line alignments for verification; do not refit after seeing them. The parallel-distance capture can supply one direction, and a fourth physical normal (-Y) supplies the other. Prefer distinct unused printed lines and far-separated working locations where real reach permits. If a check shares a geometric line with the fit, disclose that correlation; it is weaker than validation against an unused line. Each held-out normal-distance error must be at most 3 mm. One line checks only one scalar component, not a complete 2D point.
5. **Check actual route coverage.** Additional independent observations near the destination frontages and turn area must satisfy the same limits before claiming those regions. Central-junction-only observations do not qualify the whole A3 sheet. Declare the tested domain and reject extrapolation claims.

The first repeatability experiment has three captures. A compact subsequent acquisition can reuse its accepted datum captures and needs five additional stationary captures: a second tangent location, a parallel-distance check, the actual opposite-normal pose, an orthogonal-normal pose and the second held-out normal direction. Thus **eight captures are a minimum staged example, not eight automatically runnable motions or a promise of full-map accuracy**. Longer direction baselines and additional route checks may be necessary. Each physical acquisition can require multiple bounded positioning commands. Stop on a failed check rather than collecting indefinitely.

### Candidate drawing edges

The final-map adapter records four central yellow-bar components in native raster coordinates. Their intersection-facing edges are nominal candidates. They are drawing geometry only, not taught TCPs or mechanically contacted walls:

| Edge | Native raster boundary | Nominal useful segment |
|---|---|---|
| West | x = 2716 | y = 1950 to 3012 |
| East | x = 4300 | y = 1950 to 3012 |
| North | y = 1688 | x = 2976 to 4040 |
| South | y = 3272 | x = 2976 to 4040 |

Use the adapter's declared X/Y page scale and unchanged source hash. Boundaries have approximately two source pixels of raster-reading uncertainty, separate from actual print distortion and human alignment error. The roughly 64 mm segments may be too short for the required direction accuracy once the finite face length is considered. Do not assert that the active local envelope, present wrist orientation or robot reach covers these candidates. No new paper marks or mechanical stops are assumed.

### Why actual opposite face directions are necessary

For a signed map line `n_i dot q = d_i`, let `N_i = R n_i` equal the **actual oriented face normal** in BASE. At an aligned pose with actual TCP position `p_i`, the constant unloaded normal offset `h` gives:

```text
N_i dot p_i + h = d_i + N_i dot t
[N_ix, N_iy, -1] [t_x, t_y, h]^T = N_i dot p_i - d_i
```

After rotating into map-aligned coordinates, physical +X, -X and +Y normals give rows `[1,0,-1]`, `[-1,0,-1]` and `[0,1,-1]`, which have rank three. Repeated identical normals do not. Negating a line equation while leaving the tool physically unchanged also negates the corresponding offset term; it cannot create a new independent observation.

This solves map origin and one unloaded face-normal offset under the stated assumptions. It does **not** identify the finite face's tangential center, ends, usable contact interval, deformed shape, force or loaded car-contact point. Those remain a separate tool/contact characterization task. A tilted paper plane or changing effective face height invalidates this planar model.

The three independent scalar origin/offset constraints are a minimal solve with no residual degrees of freedom. An exact fit to them is therefore not an accuracy result. Retain all repeated observations, the separate direction/scale checks and the held-out normal checks. For an overdetermined fit, preserve the previously declared maximum 2 mm fit residual as an additional requirement; a small residual never replaces independent verification.

The constraint approach is informed by [Ikits and Hollerbach, *Kinematic Calibration Using a Plane Constraint*](https://www.sci.utah.edu/~ikits/publications/Ikits_ICRA_97.pdf). Their experiment uses an actual probe/plane constraint and addresses kinematic identification. Our proposed manual, unloaded face/printed-line acquisition is an engineering adaptation; the paper does not validate its accuracy with this flexible gripper.

## Separate car-response commissioning

Only after actual registration, usable-face geometry and relevant workspace checks pass should the isolated contact scope be considered. Begin with one short straight push, then an independently observed one-sided yaw response. Robot endpoint completion is checked by receiver/Native coordinates. Car translation/yaw needs separate actual outcome evidence; encoder displacement cannot prove it when the car can slip or rotate. Preserve predicted versus observed pose, uncertainty and fresh MUSE review as separate records. Do not advance the mission from a free-XY receipt or restore a historical contact pose.

The current contact software remains offline and unactivated. See [experimental contact trials](LOCAL_CONTACT_TRIALS.md), [robot calibration](ROBOT_CALIBRATION.md) and [contact pushing](PUSH_ALIGNMENT.md).
