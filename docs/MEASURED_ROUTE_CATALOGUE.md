# Measured route catalogue

The importer preserves the original B/Office, C/Villa and D/Hanok deliveries as historical trajectories. Recorded delivery, known robot geometry, and qualification for autonomous repetition are separate fields. A failed visual review remains failed even when its robot endpoints were verified.

```powershell
.venv/Scripts/python.exe -m tools.build_measured_mission_catalog `
  --audit-dir <private-audit-directory> `
  --output <private-audit-directory>/measured-mission-catalogue.private.json `
  --template-dir <private-audit-directory>/route-templates
```

The three generated `.disabled.private.json` templates contain concrete original stage references, geometry hashes, source/target contexts, destination names, and unresolved release slots. They preserve every selected stage in chronological order. They cannot become runnable merely by changing `enabled`: the mission plan, current installation/profile coverage, car preconditions, signal target, numeric measurement and primitive releases remain unset. Keep templates and all coordinates outside Git.

| Destination | Original delivery evidence | Empty return evidence |
|---|---|---|
| Office / B | 12 completed contact motions; separate original MUSE arrival | 11 completed translations, exact literal START pose |
| Villa / C | 212 completed motions plus one separately confirmed interrupted move; operator-accepted car arrival | 18 completed translations and two directed unloaded wrist edges; START XY and EAST face restored |
| Hanok / D | 158 completed motions after the clean START reset; original MUSE arrival | Derived 17-stage corridor candidate; one reverse free-row transition has not been executed |

C's original `RETURN-REAR-1` lost DONE when the receiver failed. Its unknown result is retained alongside the later `confirmed_completed` reconciliation and fresh Native proof. That proof differs from the requested endpoint by approximately 0.002 mm at most per XYZ component. The importer records the new baseline explicitly and creates no replacement motion receipt or coordinate adjustment. The final C return retains the corresponding tiny Z/Euler differences rather than silently rewriting the original START pose.

The old C trajectory includes observations, operator decisions and a receiver recovery. It demonstrates that the car reached Villa and the robot returned; it does not demonstrate unattended repetition. The newer selected RIGHT signal park is separately evidenced in D and needs a qualified connection into the selected C mission. Historical stages without original phase boundaries remain unclassified candidates, never automatic contact actions.

The importer verifies archive/member checksums, unique motion identities, original command/receipt bindings, exact literal joins and journal hash chains. It does not restore historical profiles, sessions, UUIDs or mailboxes. Runtime commands must be newly generated and bound to the current source. Clearance suffix selection accepts only actual directed contiguous stages; reverse paths are not inferred.
