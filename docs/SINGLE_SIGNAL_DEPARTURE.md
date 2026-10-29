# One signal wait per departure

The operator's October 30 paper-signal scenario checks the signal once at the
selected right-side stop. One accepted MUSE result covering two distinct fresh
GREEN-only frames admits coordinate recontact and the immediately following
push/withdrawal. Subsequent paper colors, mask transitions and signal visibility
do not reopen this gate. This is a departure admission, not continuous traffic
monitoring or a claim that the signal remains green during motion.

`SignalGate.entry_policy = single_departure` selects this behavior explicitly.
Existing configurations without this field retain `fresh_entry` behavior. A new
mission obtains a new admission; restart, ambiguous motion completion, session
change and control faults never resume an old admission. Exact Native receipt,
source pose, command identity and a prompt stationary handoff remain required.
The next loaded unit still ends with withdrawal and fresh MUSE vehicle review.

The October 30 failed C trial had one configured gate, but the old entry policy
observed the signal again after recontact. Both printed colors were visible, so
it withdrew to wait again. A subsequent vehicle-change verdict held the mission.
Stored images show an orientation change; the failure must not be relabelled as
marker loss or automatically cleared. A later operator Stop hid the original
error; Stop now preserves a pre-existing HOLD error while still delivering Stop.

The recontact builder formerly reused the next archived unit's approach. That
path ended laterally at the car, unlike the stop unit's initial normal backoff.
New candidates reverse the exact withdrawal, including that final normal return.
Source hashes and superseded approach stages are preserved. Reversing geometry
does not establish physical clearance or repeatability: the changed path remains
a current-site trial and needs an actual fresh run. Fixed Z, posture, speed,
acceleration, stage bounds and guarded wrist behavior are unchanged.

No held mission is resumed or vehicle trial started by this software update.

## Current-site coordinate screening

The deployed October 30 update checks continuity and unchanged workspace bounds
for 122 primitives / 740 internal stages, including candidate empty returns.
Contact-relative screening found terminal lateral approaches and immediate
lateral withdrawals. Seven distinct primitives received normal approach or
withdrawal candidates; the signal recontact additionally reverses its exact
withdrawal. Loaded contact coordinates, working height, posture and external
primitive endpoints are preserved. No new physical motion was executed.

The explicit local proxy uses the reported 45 x 18 x 15 mm car, a 15 mm rubber
face, 10 mm normal backoff and 25 mm lateral clearance. It is not a full collision
simulation: actual car yaw/slip, rubber deformation, complete gripper/arm/hose
swept volumes and offsets after rotation remain unverified. The shared C/D
step 9 candidate leaves the existing workspace; that candidate was rejected and
the original approach retained as an unresolved physical-review item. Bounds
were not enlarged and the finding was not converted into PASS.

## Straight-run batching review only

Keeping existing contact points and merging only adjacent same-posture,
same-direction, coincident-endpoint strokes gives these hypothetical counts:

| Destination | Current route units | Straight-only groups |
| --- | ---: | ---: |
| B / Office | 6 | 1 |
| C / Villa | 28 | 19 |
| D / Hanok | 23 | 14 |

Counts exclude signal waiting and empty START return. They are not an executable
release: current bounded-contact limits and after-action reviews still apply.
Grouping labels alone saves no physical execution time. A ten-step C/D target
also needs a new evidenced turning/recontact strategy. No long-stroke commands,
contact-limit changes or reduced observation cadence were applied.
