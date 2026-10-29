<sub>[PushPilot](../README.md) / Engineering / TCP coordinate control</sub>

# Teach a fixed frame once. Compute the road between endpoints.

## Execute by coordinates. Review after withdrawal.

The latest October 29 operator instruction defines one finite action unit:
stored BASE/TCP approach and recontact, a bounded contact action, independently
verified robot completion, stored-coordinate disengagement and observation
withdrawal, then MUSE vehicle review. Do not require a visible car or a MUSE
verdict between the internal approach movements. Expected gripper cover is
not a robot-position failure. Original frames can still be retained as evidence.

Every internal movement retains its exact source/session/profile binding,
working height, reviewed posture, speed and step limits, sole dispatch attempt
and Native endpoint checks. A control/coordinate failure stops the unit. After
withdrawal, missing or contradictory vehicle evidence inhibits the next loaded
unit and route advancement; it does not justify replaying the preceding push.
MUSE judges the visible outcome of the whole unit. A covered contact frame
cannot prove the isolated push displacement or unchanged car pose during
withdrawal. Keep those narrower results uncertain when they cannot be observed.

`backend/robot_control/coordinate_units.py` now implements this finite phase
contract as a reusable `CoordinateUnitExecutor`. One instance executes a
continuous reviewed approach, exactly one <=20 mm contact trial and a required
coordinate withdrawal. Every internal command has its own durable UUID and
independent Native confirmation. There is no intermediate image capture or
MUSE admission dependency. One original before image and one fresh image after
the full withdrawal feed `RealTaughtPorts.review_coordinate_unit()`; the
provider receives all actual internal action/receipt references and explicit
whole-unit limitations. Provider/camera failure after withdrawal permits only
read-only reobservation. A control/Native ambiguity or restart requires
reconciliation, with no automatic replay. Verified arrival requires empty-tool
return before asking the operator to reset the car.

The unit review separately requires `car_footprint=WITHIN_ROAD` and
`heading_matches_expected=true`; a generic progress/PASS statement cannot
override island overlap, an unreadable boundary or contradictory heading.
Keep raw provider contradictions. Flat on the paper is not the same as fully
inside the road. These are visible vehicle-outcome checks after withdrawal,
never gripper/TCP detection or approach admission.

`CoordinateBinding` records current-site map/tool/car/surface identities without
inventing a qualified road. The existing physical API still enforces the
installation/profile, original low-speed limits, fixed posture and Native
guards. This component does not grant physical authority, qualify a path or
activate the web mission. The older `TaughtExecutor` per-action review flow is
retained for compatibility; it is not the new coordinate-unit dispatch path.

`tools/run_coordinate_unit.py --unit-file <private-bundle.json>` validates a
single `pushpilot.experimental-coordinate-unit.v1` bundle offline. Physical IO
requires `--execute`, private port configuration and a new journal outside the
source tree. The bundle's original SHA-256 site-review reference must bind every
stage, exact unit geometry, current installation/profile and map/tool identities
to the operator's experimental contact authorization. Validation does not grant
route qualification. The runner performs one unit and stops; it does not switch
services, resume a journal or treat simulation approval as physical authority.

Current commissioning helpers have physically completed northbound units,
contact turning and westbound delivery to Villa. On October 29 the operator
accepted the current **car position** as the final C destination, superseding
the remaining old raw TCP target. Preserve this as operator acceptance: the
three westbound unit reviews supported progress, road containment and heading,
but were not MUSE final-arrival judgments. The fourth prepared unit completed
only recontact; its contact push was never dispatched and must not be resumed.
D delivery and the reusable city-route/web hardware adapter remain incomplete.
The private measured registry preserves actual commands, interruptions and
acceptance sources separately. See the
[C delivery evidence](evidence/taught-C-operator-arrival-20261029.json).
See the
[coordinate-unit evidence](evidence/coordinate-unit-north-progress-20261029.json).

## Current mode: directly taught destinations

### Shared C/D course and joint observation

The Pizza departure, first NORTH turn and central-junction approach share the
same route geometry. C branches WEST and D EAST at the later junction. Reuse
the measured common geometry with a fresh current-session review, rather than
replaying C commands, profiles or journals. At the D checkpoint, four bounded
front-side turn units and a rear seating unit had Native-confirmed endpoints
and post-withdrawal MUSE progress/road/heading support. D arrival remained
incomplete. [Common-turn evidence](evidence/taught-D-common-turn-20261029.json).

Observation withdrawal must expose the vehicle and the configured right-side
paper signal together. `CoordinateUnit.required_signal_observation` optionally
binds the exact incoming edge, original private placement evidence, native
image bounds, camera epoch and registration. The private bundle must include
the matching hashed `signal_target_evidence` record. A changed view rejects
the binding, and a visible car with a covered signal stays `WAIT_REVIEW`.
Read-only reobservation does not repeat contact or automatically resume.
This visibility check follows coordinate withdrawal; it does not admit each
approach step or grant RED/GREEN crossing permission.

The actual far-right D observation showed the car and the nominal future
signal region unobstructed. No standing paper signal face was present, so
that observation does not validate actual signal readability. The optional
joint-target feature has offline coverage; the physical checkpoint used the
previous runner and a separate current-original visibility diagnostic.
Final vehicle arrival and its provider receipt are now persisted together
in the coordinate-unit checkpoint, only after all outcome and Native checks.
Operator arrival acceptance remains a distinct evidence source.

Unit interruptions retain a bounded guard code in the private event journal
and CLI output. A secondary failure while requesting HOLD does not replace
the original error; neither error authorizes a retry. An explicit reconciliation
may finish only never-issued withdrawal stages after proving all existing
intents have original Native-confirmed endpoints, a matching current source
and fresh stationary evidence. It must preserve the original interruption and
review the original whole-unit image pair after withdrawal; never repeat a
completed contact to recover an observation.

`confirm_joint_publication` is an explicit host-journal-only observation option,
disabled by default. A one-register joint publication crossing is retained as
a failed snapshot, with its original before/after states and Native hash. It
can trigger exactly two new read-only captures only when session, sequence,
profile, installation and literal TCP are unchanged, and the discarded proof
still satisfies the original Native agreement/freshness limits. Both new
captures must pass every original guard, have exactly matching current joints
and different completed-cycle evidence hashes. Continued instability, a larger
joint change, changed identity/TCP, stale evidence or Native disagreement stops
without further acquisition or command retry. This changes observation
acquisition, not physical limits, motion authority, replay policy or receiver
scripts. It is not a recovery path for an unknown command outcome.

On October 29 the operator selected the actual manually taught BASE positions B, C and D as the destination references. This mode uses those controller coordinates directly and does not require a drawing-to-BASE transform. The earlier nominal-map calibration remains rejected: the A/B/C unit-scale fit has a maximum 11.42 mm residual, and its reserved D/E numerical discrepancies are 2.87/6.47 mm. Reusing the records as operator-selected BASE goals does not make the map calibration pass or establish vehicle arrival.

`backend/robot_control/taught_roads.py` constructs route proposals from the taught lower A–B and upper C–D frontage lines. E locates a proposed perpendicular connecting road. This perpendicularity is an explicit layout assumption; proposed junctions and complete tool/arm/hose sweeps need actual review. B uses the lower frontage. C/D use the connector and their respective upper frontage. The algorithm uses no image coordinates, map artwork or printer scale. Every proposal preserves the observation hashes, fixed taught Z/orientation and missing physical qualifications.

Run `python tools/preview_taught_roads.py <private-input.json>` for geometry and optional route previews. Actual operating poses and source evidence stay outside Git. Input contains five `points`, each with `id`, `pose_base_mm_deg` and `observation_sha256`; an optional fresh `start` has the same fields. Without a fresh start, the tool does not substitute historical calibration point A as the car start. The utility never contacts a service or dispatches a move.

The operator then placed the car and selected its actual rear-contact START as the fixed reference. Three identical manual-mode Native reads captured that pose, and an unchanged original live frame documented the car/tool setup. Manual-control flags remain explicitly labelled; a stationary coordinate record is not controller execution readiness. START and the five taught coordinates are stored privately. Recheck the current actual pose before motion; selecting a fixed start never authorizes replay of interrupted commands or automatic recovery to it.

`next_fixed_pose_target` proposes one bounded point from the latest actual TCP toward a fixed-pose endpoint. It does not queue or replay an entire road. The execution service still requires a current installation/profile, low-speed limits, exact receiver binding and measured endpoint receipts. One actual car course subsequently reached B with separate robot and MUSE arrival evidence; repeatability, drift recovery and the two turns needed for C/D remain physical tests. The first C approach and corner experiment did not establish a visible car turn. Geometric direction changes are not gripper rotation commands: changed yaw needs measured contact geometry, reviewed rotation/recontact paths and observed car response. [B course](evidence/taught-B-course-20261029.json) · [First C trial](evidence/taught-C-first-turn-trial-20261029.json).

The taught endpoints currently describe the TCP at one tool orientation. Keep robot-reference completion and vehicle task completion separate. A lost/occluded car result waits for a new outcome observation; it must neither terminate the independent receiver heartbeat nor advance a destination as successful.

The October 28 operator correction supersedes gripper-image tracking as the execution basis. The map is a flat surface; its oblique camera appearance does not make a road curved. The executor uses controller TCP coordinates and a fixed map-to-BASE relation. It must not locate the rubber tip in each image to decide where the robot is.

| Responsibility | Source |
|---|---|
| Robot position and completed motion | Persistent receiver receipt plus independent Native TCP readback |
| Road target and intermediate TCP points | Fixed map frame and taught endpoint coordinates |
| Vehicle position, drift, turn progress and arrival | Separate fresh vehicle observations / MUSE review |
| Stopped signal colour | Fresh MUSE judgement with the configured approach and stop gates |

## A small set of references replaces dense teaching

Establish one known map origin and two non-collinear map directions in TCP/BASE coordinates. For an axis-aligned teaching layout, the origin and one known-distance point on each map axis supply the two basis vectors. Other road endpoints and midpoints are calculated from those references; do not teach every possible route or every short step separately. Reserve a few independent checks for errors and retain failed checks.

The planar relation is `TCP_XY = origin_BASE + u * basis_u + v * basis_v`. A road leg from taught TCP endpoint A to B uses `P(t) = A + t * (B - A)`. If a road runs along a map axis, its other map coordinate is constant. Both BASE X and Y may nevertheless change when the map axes are rotated relative to BASE; this is independent of the camera's perspective.

The current TCP definition can serve as the virtual reference for noncontact road teaching. A separate visually detected gripper centre is unnecessary for that motion. A nominal midpoint from the gripper drawing can initialize a tool reference but is not a measurement of the installed compliant contact surface. Keep an assumed origin/offset labelled nominal until the actual map correspondence is checked. Known BASE displacements alone do not establish the map's absolute origin.

## Short straight segments use coordinates

`backend/robot_control/tcp_path.py` supplies a pure fixed-pose segment splitter. It takes endpoint TCP poses and a maximum step length, preserves literal Z and orientation, and calculates every target directly from A and B. It has no image, segmentation, MUSE, service or motion-dispatch dependency. It neither qualifies endpoints nor enlarges an installation/profile.

The existing receiver remains responsible for bounded low-speed Linear moves. Verify each issued operation by its exact request/session/profile binding, endpoint receipt and Native coordinates. Do not infer robot completion from the camera or silently replay an interrupted command. Shorter segments make vehicle outcome checks and correction opportunities more frequent; they do not mechanically guarantee that a freely sliding car remains straight.

## Vision verifies the task outcome

Expected gripper occlusion must not break the persistent robot session, trigger map refitting or replace TCP coordinates with pixel estimates. Finish an already admitted bounded operation according to controller semantics. If vehicle outcome or signal evidence is unavailable afterward, withhold the next dependent action and obtain a bounded new observation. Unknown evidence is not success, and a software HOLD is not an immediate physical stop.

Vehicle yaw/cross-track error can inform the next qualified contact correction, remaining turn or route decision. The selected pushing face, approach/repositioning envelope, actual slip/rotation response and stopping geometry still need separate contact tests. No contact or rotation is authorized by this noncontact teaching result.

## Current physical evidence

The October 29 records separate one completed B car course, three actual
withdrawn-tool wrist repositioning trials and an incomplete first C corner
trial. The wrist journal retains 114 actual controller FK samples; the first
C trial retains its REOBSERVE/no-visible-yaw outcome. These records establish
their scoped robot movements and qualitative car observations; they do not
accept the rejected map fit or qualify a 90-degree vehicle turn. See
[the actual executor evidence](TAUGHT_EXECUTOR.md#actual-commissioning-evidence).

The following noncontact results are earlier checkpoints, retained with their
original scope.

After stopping the tablet-checkerboard approach, three new noncontact movements completed: BASE X +10 mm, then Y +10 mm and Y +10 mm. Each stayed on previously traversed segments with unchanged literal Z/orientation, profile and low-speed limits. Native readback and `motion_endpoint_verified` receipts confirmed the endpoints; the receiver advanced from sequence 26 to 29 and finished held/disarmed/idle. Original frames, full poses and receipts remain private.

This establishes those TCP movements and a new intermediate coordinate sample. It does not establish an accepted whole-map transform, a physically verified road destination, vehicle transport or a 90-degree contact turn. Dense additional sampling and gripper-image tracking were stopped at the operator's correction. The original physical accuracy targets remain unchanged.

The operator then removed the vehicle and requested a return to the earlier start. Five 20 mm steps retraced actual receiver-log-proven segments D-P3-P2-P1 midpoint-P1-P0, advancing sequence 29 to 34. Every endpoint had an independent Native check; final state was held/disarmed/idle with an empty mailbox. The same installation, profile, literal Z/orientation and speed limits remained active. This completed the requested start return, not road/intersection teaching. P0 lies at the right/lower edge of the existing local envelope. Neither repeating known BASE positions nor assigning a CAD midpoint supplies the missing map origin and axis direction; a known origin/direction or two independent map-point/TCP pairs is still required before compiling a physical whole-road route.
