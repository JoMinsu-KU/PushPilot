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

The source includes no private coordinates, profiles, camera images or secrets.
The packet/compiler and offline tests establish software consistency only.
Actual end-to-end repetition, signal readability from the right-hand wait and
vehicle response under changed friction remain physical test results to record.
