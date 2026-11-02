# Action names in the route sequence

The November 2, 2026 presentation update replaces numbered B/C/D row titles with English action names in both the mission sidebar and **View all**. Titles describe the intended action: leaving Pizza shop, approaching a junction, turning the car, repositioning or orienting the empty gripper, recontacting after signal approval, destination delivery and empty-tool return.

`frontend/src/executionLabels.ts` matches the reviewed site-trial primitive IDs. It does not infer an action from a step number, pose or image. Unknown or replacement primitives keep the server-provided title. A repeated known primitive retains its title while its distinct command receipt remains separate. The complete telemetry list, ordering, current-row selection, receipt count, status, details and original IDs are retained. The detailed route still exposes the original numbered label and primitive ID.

The signal stop row describes its actual approach and withdrawal. Signal waiting remains the real signal card/state; no synthetic wait, verification or completion row is inserted. An unloaded wrist action is labelled as gripper orientation, not a vehicle turn. Arrival titles are action intentions, not evidence of success. Parallel parking and final alignment remain deferred.

`Pizza shop` is a frontend display alias for the existing `PIZZA` node when its original label is `Pizza`. A replacement map's custom name is preserved. Goal requests, original operator queries, node IDs, map bytes/hash, coordinates and planning inputs are unchanged.

The change adds no API request, polling, command, executor decision or physical operation. Robot recipes, motion order, speeds, Z/TCP/posture, profiles, signal admission, MUSE reviews, return behavior and backend code remain unchanged. Automated checks cover immutable telemetry, preserved rendered rows/status/order and stable command/map identities. UI verification uses an isolated display fixture without an equipment connection; it does not qualify physical performance.
