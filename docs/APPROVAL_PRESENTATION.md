# Approve once; display actual execution separately

The operator-requested Robot frontend uses **Awaiting approval** with **Approve plan**, followed by **Approving…** or **Confirming…** while the existing start request is unresolved. Only an enabled, connected, accepted physical mission matching the current workspace session, plan ID and revision displays **Approved once** and a disabled green **Approved** button. The original start API and its guards remain unchanged; there is no extra approval endpoint or second click.

The reviewed copy is: “Review and explicitly approve this plan revision.” After acceptance it reads: “After this, PushPilot resumes on its own when the signal and execution conditions allow.” This describes normal mission progression, not automatic fault recovery. The Robot status link retains the actual current state. HOLD, errors, disconnected evidence and completed runs retain their operational messages rather than a green running/approval claim. A replacement plan cannot inherit an earlier approval.

At the operator's explicit request, **Stop robot mission** controls are removed from the workspace and all six dialogs. Backend Stop/HOLD APIs, physical control policy, motion geometry, command bindings, signal admission and recovery remain unchanged. Existing completion/reset behavior is retained.

Reported complete rows use an orange filled marker with the existing white check icon, in both the sidebar Route sequence and View all route lists. This CSS-only treatment preserves the original complete-status predicate, ordering, marker size and typography. Current, pending, held and error rows do not acquire completion styling.

Spatial additionally shows the upper red face illuminated for a valid source-bound RED at the stopped signal wait. Accepted GREEN illuminates the lower green face and preserves the existing single-departure grant through recontact/passage. UNKNOWN, invalid bindings and stale display feeds leave both printed colors unlit. These materials are read-only displays and do not classify camera pixels or authorize robot movement.

This source is prepared independently for the coordinated server release. Offline checks and UI fixtures do not resume the held physical mission or qualify loaded movement. Runtime activation belongs to the robot-operations release owner.
