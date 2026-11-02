# Inspect. Execute one unit. Keep the evidence.

The commissioning workbench is a separate tablet GUI on **port 8192**. Product
missions remain on 8080; the existing authenticated robot API remains on 8897,
RODI on 19507, and the existing host retains Native ownership. Starting or
opening the GUI performs no motion, profile preparation, camera registration,
production reset or automatic route execution.

## Ownership before movement

The GUI initially reads effective B/C/D geometry and GET-only live status.
Loading geometry uses the existing hash-checked `SiteTrialMissionDriver` loader,
including session precision references and the current fixed Z/posture. It
does not call production readiness or create a second robot connection.

`Acquire control` asks the product's small commissioning broker for an explicit
reservation. An active worker or an unresolved HOLD rejects it before driver
handoff. An eligible completed/ready product performs a fresh held, disarmed,
idle Native/camera proof, then releases its journal owner. The workbench must
acquire the **same production `runner.owner.lock`** and retain it for its entire
session. A different GUI port or journal directory alone is not exclusion.

During reservation the product cannot Start, resume, reset or reclaim its
driver through readiness polling. The workbench writes its own private journal
and SQLite history. It never overwrites the taught packet, production review,
configuration, completed receipts or original failed observations. Reservation
persists across a product restart. A workbench restart with an unfinished owner
or operation requires reconciliation; it never adopts and continues a run.

This fences the cooperating product/workbench. It is not a new lease protocol
for arbitrary clients holding the robot API credential. Do not run independent
commissioning scripts against the same API while the GUI owns the session.

## One logical unit at a time

1. Select B / Office, C / Villa or D / Hanok and a stored logical unit.
2. Inspect the original camera or the separate **BASE XY** coordinate view.
   The XY plot is not camera registration, a new map calibration or a car pose.
3. Execute the selected unit once. Its approach, contact and withdrawal retain
   the existing per-command speed, acceleration, <=20 mm stage limits, profile
   preparation, IK, exact source/session and fresh Native endpoint checks.
4. After withdrawal, inspect original BEFORE/AFTER JPEGs and actual MUSE results.
   The next unit never starts automatically, including after a MUSE PASS.
5. Acknowledge the completed result and explicitly select the next trial.
   Acknowledgment preserves a FAIL/UNCERTAIN verdict; it does not manufacture a
   PASS, car alignment, a qualified route or an unknown command completion.

One logical unit can contain several internal robot stages. The GUI is not a
continuous joystick or arbitrary TCP command terminal. A MUSE/provider failure
after known completion permits reobservation without repeating movement.
Uncertain preparation/dispatch/endpoint outcomes block further execution,
acknowledgment and release. Stop cannot clear that block.

Signal helpers are visible as explicit recontact/release rows. A signal stop
requires two new stopped GREEN observations through the original paper-mask
MUSE rules. Selecting a later step or acknowledging a review cannot bypass
GREEN and the exact recontact. Accepted single-departure permission is consumed
once by the matching crossing; later signal appearance does not add a wait.
Expired permission can be reobserved without replaying the stopped push.

## Reviewed XY candidates

Editing creates an immutable private candidate. It preserves the original
first source, last observation endpoint, stage identities/phases, literal Z and
Euler values, existing workspace bounds, per-command length and contact total.
Contiguous starts are shown explicitly. Loaded candidates must retain a normal
10 mm contact release before tangential withdrawal. Wrist and signal-helper
geometry cannot be edited here.

An approval must name the exact geometry hash and explicitly confirm fixed
pose, tool/car/hose clearance, contact release, continuity and the bounded XY
region. That creates a labelled **current-site experiment** review derivative
with unchanged limits; it never forges a historical receipt or repeatability
qualification. Fresh profile/IK preparation still runs before dispatch.

The private export contains routes, candidate revisions, reviews and operation
history. It is a proposed experiment record, **not an automatic production
deployment**. Raw JPEGs and full MUSE response bodies/hashes remain in the private
session journal. No production geometry is silently replaced.

## Stop, uncertainty and handback

Stop signals cancellation before acquiring the GUI state lock and inhibits
subsequent arm/dispatch. It does not claim an immediate physical emergency stop
of an already committed movement. An old duplicate Stop request cannot cancel
a later unit. Motion POSTs and broker POSTs have no automatic retry.

Returning product control requires a fresh exact original common START and no
pending/unknown operation. The GUI exposes the existing empty-tool return rows;
it does not invent a direct return from an arbitrary intermediate source. It
releases its OS owner, then the product independently checks START under its
own owner before removing the reservation. Existing product mission history
is retained; no new delivery starts as a side effect.

If the GUI process or a broker reply is lost, inspect the recorded owner ID,
request ID, command UUID and independent endpoint evidence. There is no force
unlock, clear-error-to-continue, or generic replay button.

## Run and access

Use `tools/serve_commissioning_console.py --help` and the dedicated
[user-service example](../deploy/pushpilot-commissioning-console.service.example).
Run one worker. Supply an explicit numeric loopback robot/camera deployment,
private state root, separate private console token and explicit host:port
allowlist. The browser receives an HttpOnly SameSite session after login; the
robot and MUSE credentials remain server-side. Requests require the exact
same Origin, bounded strict JSON and a revision plus unique request UUID.

The GUI uses the existing self-hosted Pretendard font, light glass panels and
orange controls. Its viewport has no page vertical scroll; stage/history
panels scroll internally. Original camera bytes are displayed without image
filters, rectification, resampling or AR-coordinate changes.

Software tests and no-motion handoff checks are separate from a real D course
qualification. A successful commissioning framework test does not establish
that D16/D17 reproduce the old car contact state or that D will complete.

## November 2 activation and verification

- Workbench code commit: `52d33e4`. GX10 runs the verified complete source
  bundle on 8192. Product 8080 received only the three broker/driver source
  files after C completed and returned to START.
- The local full backend run completed **1,329 tests, six skipped, no failures**.
  The final focused commissioning suite completed **48 tests without failure**.
  The existing frontend completed **152 tests**, TypeScript checking and the
  Vite production build. The workbench JS syntax check also passed.
- GX10 completed **108 equipment-free related tests** and loaded effective
  B/C/D geometry. A real **no-motion acquire → reserved product → release**
  check passed. Product state/history remained COMPLETE; the receiver stayed
  in the same session at sequence 551 with the same exact TCP, joints, profile
  and installation, held/disarmed with no active commands.
- The first candidate deployment omitted the inherited runtime's public
  source manifest. Its acquire failed before runtime loading, profile
  preparation or command intent. That failed setup state is retained
  privately. The final deployment uses the complete verified source bundle;
  CLI startup now verifies exact runtime sources before exposing the GUI.
- Restoring the saved camera reference after the idle web restart generated a
  new display-reference identity. Its stored lineage, camera epoch and exact
  homography were verified; only the three matching display identity fields
  in private configuration were rebound. No new fit, coordinate, height,
  orientation, signal pixels or taught geometry was introduced. Camera and
  RODI processes were not restarted for this deployment.
- No loaded unit, new MUSE inference or D trial was executed. The GUI is left
  in READ_ONLY without a reservation. Browser authentication uses the separate
  console token; private access material is excluded from source releases.
