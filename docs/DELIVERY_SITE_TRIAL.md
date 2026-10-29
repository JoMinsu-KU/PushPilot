# Delivery first · current-site trial

The October 29 operator workflow prioritizes arrival at Office Building, Villa
or Hanok, followed by an empty-tool return to START. Parallel parking and
automatic numeric alignment corrections are deferred. The fixed start is the
Pizza box, with the car facing the original departure direction.

The physical workspace displays real executor receipts, MUSE observations and
signal frames. Missing observations remain unavailable. A Native endpoint
confirms the robot pose; it does not prove that the car moved. Vehicle arrival
and robot return are separate states. The AR line remains the planned route,
not a fabricated live vehicle trace.

## Execution

1. Bind the exact live MUSE plan, destination, map and current fixed camera.
2. Verify the original START from fresh Native state and a fresh car image.
3. Prepare each reviewed coordinate unit from its actual source. Preserve
   working Z, speed 5 mm/s, acceleration 10 mm/s² and the 20 mm command limit.
4. Approach, push and withdraw using coordinates. Review the completed contact
   unit with MUSE before advancing. Unloaded intermediate repositioning needs
   its actual completion receipt, without pretending that the car moved.
5. At the selected northbound signal stop, wait at the far-right observation
   pose. Two distinct fresh exclusive-GREEN images permit measured recontact,
   followed by a fresh entry check. RED, both visible, neither visible and mask
   transitions wait. The black disc/cable tie is described in the observation
   target; it is never an implicit GREEN command.
6. A visible, road-contained car at the correct destination with an original
   MUSE PASS completes delivery. Parallel alignment is not required. Return
   the empty tool along the explicitly reviewed clear path, preserving current
   Z and directed unloaded wrist checks. A new mission requires a car reset.

## Release boundary

`pushpilot.site-trial-driver.v1` is a separate opt-in current-site trial mode.
It does **not** turn historical successes into repeatability qualification.
The private packet retains original receipt references and explicitly labels
derived connections, fixed-height posture binding and numerical shared-vertex
normalization. Every translation keeps literal runtime Z/Euler; wrist targets
retain directed joint winding, endpoint IK and the existing 19-sample receiver
FK guard. The existing qualified-release driver remains separate.

The private review allowlists exact geometry, source/tool/car/surface identities,
site bounds and wrist intents. Each unit creates a new narrow installation and
profile, independently confirmed before dispatch. Interrupted preparation,
ambiguous dispatch, external profile changes and unknown endpoints hold without
replay. Application deployment never restarts the camera, robot API or Rodi.

Wrist commands honor the installed, hash-bound rotation runtime's completion
timeout. The current reviewed runtime allows 120 seconds; the generic 60-second
translation wait cannot shorten it. The outer receipt poll uses the same
effective timeout plus 15 seconds for admission and receipt delivery. An
unresolved outcome still holds without replay or automatic continuation.

The source includes no private coordinates, profiles, camera images or secrets.
The packet/compiler and offline tests establish software consistency only.
Actual end-to-end repetition, signal readability from the right-hand wait and
vehicle response under changed friction remain physical test results to record.

## Explicit mission retirement after an interrupted trial

`POST /api/v1/physical/reset` is a same-origin, revision-bound **no-motion** operation. Its body contains `request_id`, `expected_revision`, the exact ended `mission_id`, and a `reason`. It is available only after the mission worker has exited and the robot has independently returned to measured START.

The original unresolved request must already be `complete` or explicitly `reconciled` in the robot ledger. The reset validates the preserved dispatch identity, held/disarmed/idle state, absence of pending commands, current site/tool/payload/height, fixed camera registration and fresh independent host Native START evidence. It neither returns the robot nor reconciles, resends, or marks the failed motion successful. A profile installed by an independently reviewed empty return is repinned only after these checks.

Reset preserves requests, failed mission events, original journal records and dispatch markers, appending a `MISSION_RETIRED_AT_START` proof. The previous live plan is permanently retired for physical execution. Reset the workspace with `/api/v1/reset` and create a new live MUSE plan before the next explicit tablet Start. Vehicle placement is not inferred from the empty-tool START proof; the next mission still performs its original fixed-start visual check.

After a web-only restart, explicitly resuming the unchanged saved display reference may create a new registration ID. Retirement alone can accept that ID in `site_binding.calibration_id`, `ports.registration_id`, and all existing signal-target registration fields. Every other configuration value must remain identical, including camera epoch, map, pixels, physical review and control limits. The operator/deployer must independently verify the unchanged saved homography and reference frame. The terminal request, current camera and fresh Native START checks still run; normal automatic configuration reload cannot bypass an unresolved checkpoint.
