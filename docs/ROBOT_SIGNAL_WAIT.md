# Robot signal-wait reference

The operator selected the actual stopped observation pose at sequence478 on
October 29, 2026 as `SOUTH_JUNCTION_NORTHBOUND_SIGNAL_WAIT`. It belongs to the
shared C/Villa and D/Hanok approach after the first turn and rear seating.
It is not automatically applicable to B/Office or another approach direction.

The private waypoint registry stores two distinct references:

- The actual last vehicle-contact endpoint, its motion receipt and Native
  endpoint evidence. This is the coordinate reference for later recontact.
- The actual withdrawn observation TCP pose and joint values, with a separate
  fresh stationary Native proof and the operator-selected original image.

The seventeen-stage rear-seating unit passed its original whole-unit MUSE
review. A separate current-original MUSE inspection found the whole car visible
and the right junction region unobstructed. It found no standing paper signal
face. This supports this observation reference, without establishing a measured
stop-line margin or actual red/green recognition.

The scenario policy for this stage is:

1. Complete and verify the vehicle stopping action, then release contact and
   move to the recorded observation pose.
2. RED, UNKNOWN, occlusion or stale evidence keeps the scenario waiting.
3. A fresh, correctly bound MUSE GREEN result plus the local stop/entry checks
   may admit a new coordinate recontact and bounded crossing.

Recontact targets the recorded last contact endpoint, not the beginning of the
old seating stroke. Every departure requires the actual current source, a new
profile binding and new command UUIDs. No interrupted request, old profile or
mailbox is restored.

This is a commissioning waypoint record. The actual paper-signal target and
physical signal-color entry integration are not qualified or activated by
recording it. A readable empty region or an observation pose never grants GREEN.
Further motion commissioning and an enabled traffic scenario are separate
operating modes. Raw operating coordinates and full evidence stay private on
GX10 and in local backups; the public scope is recorded in
[the wait-stage evidence](evidence/taught-signal-wait-stage-20261029.json).
