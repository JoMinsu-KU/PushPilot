# Continue a completed action after a visual-review hold

An explicit `POST /api/v1/physical/resume` can reconcile the old C-course
`MEASURED_CORRECTION_PRECONDITIONS_REQUIRED` observation-budget hold. It accepts
the same revision-bound identity fields as reset: `request_id`,
`expected_revision`, `mission_id`, and `reason`. Same-origin checks apply.
Status polling, browser reload and service startup never initiate continuation.

This narrow operation supports a completed intermediate contact action after
the already-admitted crossing. It does not recover a controller fault, an
ambiguous command, an interrupted primitive, C14's missing volatile reference,
an uncompleted signal crossing, or a terminal arrival failure.

Before any new motion, the service verifies the original accepted mission,
completed receipt, held state, issued-command lineage and unchanged live plan.
The driver verifies its hash-chained private journal, terminal robot request,
actual Native session/sequence/profile/pose/joints, fixed height and tool/site
identity. The exact completed geometry and next primitive's source must match.
The camera epoch, original reference photograph and homography must also match;
only an explicitly renewed registration ID may differ after a web restart.

The only allowed policy migration is the deployed C intermediate-progress
review. Route geometry, source/target contexts, physical review, signal policy,
return path and limits must remain unchanged. Original failures and raw model
responses are retained.

Two new visual checks are required: comparison of the held endpoint against a
fresh image must positively establish unchanged car position/orientation and
board view, then the original pre-action image and a new current image must pass
the deployed qualitative progress policy. Uncertainty, a changed scene or an
explicit problem preserves HOLD. These checks are visual evidence, not metric
vehicle-pose qualification.

Only then does the normal mission worker continue from the completed action's
observation cursor. The completed action is never dispatched again. All issued
command IDs, completed receipts and the already-consumed signal admission stay
in the same mission. The next primitive still receives fresh source checks and
the original guarded profile preparation. Stop requests during reconciliation
prevent continuation. A failed reconciliation is recorded and is never retried
automatically. One additional explicit request may repeat all no-motion checks
after a provider transport/parse failure. A negative or uncertain scene verdict
cannot be retried through a new request ID for the same hold.

This feature does not establish route repeatability or guarantee correction of
vehicle drift. Existing C26 destination verification and empty-tool return
remain mandatory.
# Explicit C19 review omission

The October 30 operator request permits omitting MUSE at C19 and continuing to C20. This is a separate, explicit `POST /api/v1/physical/continue-c19` operation with the same request ID, revision, mission and reason fields. It is accepted only for the exact ended `CAR_NO_VISIBLE_PROGRESS` hold at `C-step-19` / `C-upper-WEST-corner`, with its completed Native receipt and unchanged source, geometry, session, tool and camera reference. No completed contact is repeated. Original failure evidence remains unchanged; the journal records `MISSION_CONTINUED_WITH_C19_REVIEW_OMITTED`, not a MUSE PASS.

Private `observations.c19_native_endpoint_only: true` also omits C19 review on subsequent missions after a verified motion receipt. The policy constructor rejects this mode on any other primitive, final arrival or signal step. C20 onward remains under its existing observation policy. This mode does not establish car progress, car pose or scene continuity; no synthetic car observation is created. It does not recover unknown motion outcomes or alter signal admission, velocity, Z, collision limits or coordinates.
