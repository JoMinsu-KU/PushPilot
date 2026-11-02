<sub>[PushPilot](../README.md) / Operations / Robot</sub>

# Prepare once. Execute coordinates. Preserve the evidence.

**Documentation cutoff: November 2, 2026.** The public source baseline is `7aa7753`; the last read-only deployment audit identified GX10 application release `20261031-c11-activation-fix`. Publishing source does not activate it, reconnect a pendant or establish current readiness. Check the actual live status before operating.

PushPilot retains **Observe → Plan → Approve → Act → Verify**. In the configured Robot trial, a selected MUSE plan binds a private destination recipe; the executor supplies taught BASE coordinates, the receiver and Native telemetry verify robot endpoints, and fresh original camera images support MUSE outcome review after withdrawal. The default equipment-free simulation has its own receipts and grants no physical authority.

[Current scope](DELIVERY_SITE_TRIAL.md) · [Known limitations](KNOWN_LIMITATIONS.md) · [Source and deployment](../deploy/README.md) · [Evidence index](evidence/README.md)

## Choose the operation by the actual state

| Situation | Operation and effect | Movement and required evidence |
| --- | --- | --- |
| New mission at the original common START | Create a new workspace session/plan; explicitly select Robot and Start. The service checks the current recipe and exact plan/map/site binding. | Start can execute the released course. The robot must already be at START; the car needs separate start-box placement and a fresh visual check. |
| Mission ended after Stop/failure; robot already returned | `POST /api/v1/physical/reset` retires the exact ended mission. Then `/api/v1/reset` clears the workspace plan for a new session. | Both resets are no-motion. Physical reset requires held/disarmed/idle, no unresolved robot command, fresh independent Native START evidence, unchanged site and camera. |
| Empty tool needs to return after an interrupted mission | A separately reviewed, current-source-bound empty return is required before retirement. | Reset is not a return command. Returning the robot does not return the car. Keep completed and unknown outcomes separate. |
| Completed C intermediate action held only by visual review | Explicit `/api/v1/physical/resume` may reconcile the narrow supported review hold. | Preparation checks exact completed receipt, current Native/session/profile/endpoint, camera/scene continuity and a new accepted qualitative progress review. It never repeats the completed action. |
| Exact ended C19 no-progress review hold | Explicit `/api/v1/physical/continue-c19`, if that exact omission is configured/authorized. | No C19 contact replay. Preserve the original verdict; record an omission, never a new MUSE PASS. Later reviews and signal/control guards stay active. |
| Interrupted C12 approach, independently restored C11 boundary | `/api/v1/physical/prepare-boundary` performs no-motion checks and can report `BOUNDARY_READY`; a separate explicit `/resume` starts C12. | The earlier reverse movement and any original unsent-request reconciliation need their own evidence. This is not generic arbitrary-step recovery. |
| Receiver reconnect differs only in START readback precision | An explicit session-scoped `session_start_reference` may bind a fresh stationary START. | No motion; at most 0.005 mm/degree component difference from the original START. Original packet and other taught endpoints remain immutable. A larger difference is not precision rebinding. |
| Rodi session disconnected | Inspect the ended session and actual controller state; prepare the matching reviewed current-source profile before local PLAY. | PLAY opens the existing protocol; it does not itself submit a route. Reconnection never restores an old mailbox or automatically resumes a mission. |
| Movement may have been transmitted but completion is unknown | Keep HOLD and reconcile against independent controller/Native evidence and the durable command ledger. | Never submit the same physical action under a new ID to bypass an unknown outcome. No reset/resume shortcut can turn uncertainty into completion. |

Physical controls are same-origin requests. Start/reset/resume enforce the expected revision; Stop remains accepted when the status revision advances. Start supplies the workspace/plan/destination/map identities; reset/resume/preparation supplies the exact mission ID and reason. The private robot token stays server-side. These routes are operator controls, not instructions to invoke them during documentation or deployment work.

## Meta MUSE at the decision boundaries

MUSE reviews vehicle progress after coordinate withdrawal, the paper signal while stopped at far RIGHT, and visible arrival at the selected building frontage. Each result carries its actual images, capture identities, provider receipt and explanation into the supervisor gate. This is the visual feedback that connects **Act** to **Verify**; the coordinate executor then carries out the next admitted unit. During an ordinary released mission, these decisions run inside the product pipeline without a conversational agent choosing each step.

## Normal delivery sequence

1. Keep the fixed print, camera, TCP/tool definition and installation identities consistent. Confirm the original common START and car placement separately.
2. Bind the live MUSE plan to B / Office Building, C / Villa or D / Hanok. Office is the direct frontage route; C/D share the first turn and northbound approach before their later branch.
3. Execute each released coordinate unit: approach/contact, Native-confirmed endpoints, normal release, then coordinate withdrawal. Expected contact occlusion does not require detecting a gripper tip.
4. Review the car using original camera frames after withdrawal. C's configured intermediate policy asks for qualitative visible progress rather than a precise heading; explicit problems and invalid source evidence still hold.
5. At the configured northbound signal gate, stay at the selected far-RIGHT wait pose until one accepted stopped GREEN decision covers two distinct fresh frames. Recontact the exact last contact endpoint, then continue the admitted crossing without a second color wait. A new mission needs a new admission.
6. Confirm destination delivery. C ends at C26; final straightening and parallel parking are deferred. After accepted delivery, execute the reviewed empty return and verify START separately. Resetting the car for another run is a separate physical setup action.

The alternative `fresh_entry` signal policy remains for compatibility configurations. It performs an entry recheck after recontact; it is not the selected `single_departure` site-trial behavior. Neither policy authorizes motion from an old mission's GREEN result.

## Distinguish the clocks

| Budget | Meaning at this source cutoff | What it does not establish |
| --- | --- | --- |
| Physical paper-signal wait | The operator requested 120 seconds. The public physical policy does not by itself publish a verified deployed 120-second timer; verify the exact private configuration and running release before making that guarantee. | The wrist timeout below is not this timer. |
| Simulation signal watcher | Default 300 seconds; request schema allows 1–900 seconds. | No physical wait or robot connectivity guarantee. |
| Signal image age | Default 15 seconds, explicitly configurable up to 30 seconds in the physical policy. Original capture time remains authoritative. | Slow provider completion does not make an old image fresh. |
| MUSE request/reobservation | Bounded by the selected adapter/request configuration and observation budget. Preserve provider failures and the pending checkpoint. | A provider retry is not permission to replay a push. |
| Translation/wrist completion | Translation uses its configured completion budget. The reviewed inherited wrist runtime described by the October 29 release allows 120 seconds; the outer receipt poll adds 15 seconds. | A longer completion budget cannot fix a dead idle connection. |
| Native stationary acquisition | Diagnosed idle failures exhausted three approximately two-second reads, closing the session after about six seconds. These are inherited-runtime observations, not a new public resilience setting. | It is not the traffic-signal timer. |
| Receiver/wire and publication freshness | Inherited pendant receive and host wire bounds are separate (10 and 12 seconds in the reviewed runtime); the public wrapper rejects a host snapshot older than five seconds. Exact imported bytes are bound by the runtime manifest. | A fresh web status response does not prove a fresh Native or pendant state. |

The host calls the Native guard synchronously inside the persistent exchange. MUSE and camera run in other processes, but the Native guard can block the same exchange that maintains pendant liveness. **Idle-timeout hardening is not implemented at this cutoff.** A future fix must separate connection liveness from unavailable telemetry while inhibiting dispatch, with explicit recovery for ambiguous motion; raising every timeout would not solve that lifecycle problem.

## What to retain after a failure

Keep the original mission/command IDs, receiver session/sequence/profile, sent/unsent/unknown distinction, endpoint/Native evidence, original camera hashes, MUSE response and error. Report robot delivery, visual car arrival, empty return and readiness as separate facts. A browser refresh, service restart or source push must not manufacture a successful receipt or clear an unresolved movement.

Use the actual controller stop facilities for an in-flight physical stop. Tablet Stop/HOLD prevents subsequent dispatch; it is not an emergency stop and cannot revoke a command already admitted by the blocking installed motion protocol.

For the exact checks and restrictions, see [explicit review continuation](EXPLICIT_REVIEW_CONTINUATION.md), [C11 recovery](C11_BOUNDARY_RECOVERY.md), [START precision binding](SESSION_START_REFERENCE.md), [C review policy](C_INTERMEDIATE_PROGRESS_REVIEW.md) and [deployment](../deploy/ROBOT_CONTROL.md).
