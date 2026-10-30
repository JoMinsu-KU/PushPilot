# Villa delivery at C-step-26

The operator selected the vehicle location reached by C-step-26 as the Villa delivery endpoint on October 30. C-step-27 and C-step-28 are omitted from new C missions. B and D retain their existing routes. No final straightening or parallel parking is requested.

The terminal unit still completes its original contact and withdrawal stages. A fresh original-camera MUSE review then checks that the car is visible, inside the named Villa frontage road zone and wholly on the road. A diagonal parked orientation or no additional displacement from an already-arrived reference is not a terminal failure by itself. `expected_progress` and `heading_matches_expected` remain truthful diagnostic facts. A hidden car, wrong location, uncertain boundary or negative arrival review cannot be converted to success. Native robot completion alone never proves car arrival.

After confirmed delivery, the existing empty return restores START position and departure orientation. Long empty returns are partitioned at existing stage vertices so that a unit spans at most 150 mm per BASE axis, retaining margin within the original 200 mm local profile limit. Stage coordinates, fixed Z, 5 mm/s speed, 10 mm/s² acceleration, 20 mm command cap and guarded unloaded wrist checks are preserved.

`tools/revise_delivery_endpoint.py` creates an offline revised packet and retains the original route, primitives and reviews. Activation remains a separate current-site deployment. The revised packet is not a repeatability qualification.

## Observed failure and its limits

The original C-step-26 completed its Native-confirmed motion, but was an intermediate step (`goal_arrival_check=false`). Its expected outcome demanded visible WEST progress and WEST alignment. Three original MUSE reviews returned FAIL, with inconsistent progress/heading judgments, followed by `OBSERVATION_BUDGET_EXHAUSTED:MEASURED_CORRECTION_PRECONDITIONS_REQUIRED`. The deployed `muse_outcome` adapter has no qualified metric heading/lateral measurements or automatic correction templates, so repeating this observation cannot supply those prerequisites.

An offline diagnostic on the exact original before/after frames found approximately 12 pixels of leftward car-centroid displacement with little apparent orientation change. This is a pixel observation, not calibrated car travel or proof of friction/contact cause. The original FAIL reviews remain unchanged. The operator subsequently accepted that location and requested an empty return. Future runs use the separately declared final delivery criteria; they do not inherit a fabricated PASS from this run.

The first explicit return preparation was rejected before motion because its near-200 mm X span plus clearance margin exceeded the existing local profile bound. Splitting the unchanged return resolves that preparation limit without widening it. A separate diagnostic file-label error after the first five completed stages was reconciled at the actual endpoint; completed motions were excluded from the continuation.

An unconfirmed final delivery now reports `GOAL_ARRIVAL_UNCONFIRMED` and uses the finite reobservation budget. It never requests unavailable alignment measurements just because the final car is skewed or made no additional progress. Intermediate route checks remain unchanged.

## Verification on October 30

- Actual MUSE Spark 1.3, prompt v3: the original C26 reference/current pair returned PASS, arrived=true, within_road=true, and C-checkpoint-26. This is a separately recorded retrospective evaluation under the new endpoint criteria; original failures are preserved.
- A fresh current frame showed the car back in the Pizza start box. The same arrival evaluator returned FAIL, arrived=false and no Villa zone, correctly rejecting this negative example. It is not a second arrival-positive sample.
- Additional provider checks encountered two connection-stage failures; the instrumented failure was `ConnectTimeout` at approximately five seconds. The next completed call returned HTTP 200 and again judged the recorded C26 image PASS/arrived=true. There are two successful positive arrival evaluations, one correctly rejected start image, and two unsuccessful API calls; these are not a statistical accuracy benchmark.
- The coordinator regression test injects two consecutive observation timeouts after delivery, then a successful skewed-arrival review. It completes with exactly one delivery command and one return command, without replaying the push. Three consecutive provider failures still hold the mission; network availability is not guaranteed by these tests.
- Offline policy replay uses all three actual deployment plans with synthetic Native receipts and intermediate observations. B/C/D reach COMPLETE and START; C contains 26 route units, one signal recontact and four return units. RED and UNKNOWN wait, two distinct GREEN samples admit one recontact, and no second signal wait follows.
- Wrong zone, hidden car, missing arrival, uncertain provider output and off-road outcomes do not return or complete. An unknown motion receipt requires reconciliation and is never replayed.
- Empty START position and departure orientation were physically restored and independently read from Native. The failed mission was explicitly retired without rewriting it as an automatic success.

These checks cover software transitions and specific real images. They do not simulate contact mechanics, certify collision clearance for a changed scene, measure recognition accuracy, or establish repeatable full-route physical success. The next loaded run must still pass current start, signal, observation and Native checks.
