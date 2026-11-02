<sub>[PushPilot](../README.md) / Engineering / Robot control</sub>

# One command. One receipt. No automatic replay.

**Current baseline: November 2, 2026, source `7aa7753`.** The configured Robot trial connects the tablet's live MUSE plan to coordinate action units, real robot receipts, original-frame MUSE review and a separate empty START return. The equipment-free simulator remains the default without private physical configuration. This is an opt-in current-site trial; it does not establish unattended repeatability.

[Operations and recovery](ROBOT_OPERATIONS.md) · [Delivery trial](DELIVERY_SITE_TRIAL.md) · [Known limitations](KNOWN_LIMITATIONS.md) · [Measured catalogue](MEASURED_ROUTE_CATALOGUE.md) · [GX10 deployment](../deploy/ROBOT_CONTROL.md)

## The implemented path

Observe → Plan → Approve → Act → Verify remains the product contract. MUSE interprets a destination and reviews visible outcomes; it does not emit TCP coordinates. The physical service binds the exact approved destination/path/map to a private recipe. Coordinate approach, contact, release and withdrawal execute from taught BASE geometry with current session/profile/Native checks. A fresh car review follows withdrawal, when the selected observation pose makes it readable.

| Layer | Responsibility | Boundary |
| --- | --- | --- |
| Tablet and main web service | Plan/approval, explicit Robot Start/Stop, actual progress/signal/review display | Simulation receipts never authorize hardware. UI Stop inhibits subsequent dispatch; it is not an emergency stop. |
| `physical_mission.py` + `physical_api.py` | One durable mission, source-bound driver, observations, restart HOLD and explicit recovery | Unknown movement never automatically replays; browser reload does not resume. |
| `site_trial_driver.py` + `coordinate_units.py` | Private B/Office, C/Villa and D/Hanok recipes; current-source installations/profiles; empty return | Active delivery-only scope defers numeric correction and parallel parking. |
| Commissioning HTTP API, loopback 8897 | Authenticated ledger, installation/admission/IK/endpoint/reconciliation interfaces | Token and geometry stay server-side. Starts disarmed. |
| `serve_rodi_host.py`, pendant listener 19507 | One persistent Rodi exchange, imported protocol/profile checks, bound state publication | No automatic PLAY, mailbox restoration or movement replay. Listener survives session failure; actual disconnect can require local PLAY. |
| Native FC03, controller port 502 | Independent read-only TCP/joint/program/speed and endpoint/stationarity evidence | Does not prove car motion, active TCP definition or contact clearance. Synchronous acquisition can block host liveness. |
| Camera helper and MUSE observer | Original-image provenance, fixed display references, visible progress/arrival/signal review | Display mapping is not board-to-BASE calibration; no hidden car pose becomes a TCP target. |

The inherited transport, policy and kinematic modules are imported privately through a byte/hash-verified [runtime manifest](data/robot-runtime-source.json). This wrapper does not ship a second driver or controller source. `taught_executor.py` remains a separate compatibility runner with historical per-action reviews; the current site-trial path reviews a bound approach/contact/withdrawal unit. See [TCP control](TCP_COORDINATE_CONTROL.md) and [taught runner](TAUGHT_EXECUTOR.md).

## Meta MUSE closes the visual loop

Meta MUSE provides the mission's visual judgment at three concrete boundaries: whether a released push produced visible vehicle progress, whether the stopped paper signal supports GREEN admission, and whether the car has arrived in the named destination road zone. The observer submits original images with exact frame/mission context and retains the explanation and provider receipt. The supervisor combines that result with known robot completion and source checks to advance, wait or hold. The tablet exposes the actual outstanding MUSE activity and resulting evidence; a coordinate receipt alone cannot answer those visual questions.

## Delivery, signal and return

- **B / Office:** direct Pizza frontage route. **C / Villa** and **D / Hanok:** shared first turn and northbound signal approach before their later destination branch.
- The signal unit completes contact, normal release and far-RIGHT parking. One accepted stopped GREEN judgment covering two distinct fresh frames admits exact measured recontact and the following crossing. Selected `single_departure` does not recheck color after recontact; each new mission requires new admission.
- C ends at **C26**, with visible car arrival in the selected Villa road zone. Diagonal orientation alone is not a failed delivery. C27/C28 and final parallel parking are deferred.
- Accepted arrival is followed by the reviewed empty return to the original common START and departure orientation. Robot return, car arrival and human car reset are separate states.

The reviewed site-trial release preserves fixed work height, literal translation posture, 5 mm/s speed, 10 mm/s² acceleration and 20 mm stage limit. Directed unloaded wrist operations retain installed runtime, IK and nineteen-sample FK guards. These are site-specific constraints, not permission to reuse or enlarge profiles elsewhere.

## Failure and visibility

| Situation | Behavior |
| --- | --- |
| Expected marker occlusion with the exact fixed reference retained | Keep mapping; do not refit or use marker count as gripper control. Fresh car/signal and scene-identity checks remain separate. |
| Car hidden after known robot completion | Reviewed observation/reobservation; no hidden pose, synthetic PASS or repeated push. |
| Confirmed camera/map/site/profile/session mismatch | Hold; display relocking does not rewrite taught BASE coordinates. |
| Lost DONE, ambiguous publication or interrupted movement | Preserve the unresolved command and disarm; independent reconciliation precedes new motion. |
| API/web restart | Preserve journals; HOLD/recovery, no automatic worker or command replay. |
| Native idle read budget exhausted | Current synchronous host closes the session. A listening port is not a connected pendant. |
| Eligible completed visual-review hold | Explicit source/scene/Native checks can admit the next unit; the completed unit never repeats. |

HTTP/MUSE/camera processing is separate from the host process. **Host heartbeat is not fully isolated from synchronous Native acquisition.** Idle-timeout hardening is unimplemented at this cutoff. A longer signal timer and START precision binding do not repair it; see [timeout distinctions](ROBOT_OPERATIONS.md#distinguish-the-clocks).

Admission is rechecked before durable command commit. A later HOLD/cancel cannot revoke an already admitted blocking MoveL/MoveJ operation. The installed protocol has no emergency-stop wire command. Use actual controller stop facilities when needed.

## Current-source preparation

The original common START, TCP/tool, payload, work height, print/camera identities and private workspace/profile coverage must agree. A flexible rubber face is not a point probe. Rejected global board fits and stopped gripper-tracking experiments remain historical; taught BASE recipes do not retroactively validate them.

Use [operations](ROBOT_OPERATIONS.md) for reset, return, reconnect and resume. `physical/reset` is no-motion retirement after an independently verified return. Session START precision binding is explicit, at most 0.005 mm/degree per component and valid for one receiver session; it does not move or redefine START. C11 recovery is narrowly bound to its original known/unsent command history.

No documentation update, source release, mock run or ordinary application deployment opens hardware sockets, activates a profile or replays a historical course.

## Local mock and client

```sh
python tools/serve_robot_control.py --backend mock --port 8897
python tools/robotctl.py status
python tools/robotctl.py events
```

The mock server is equipment-free. `robotctl.py` contacts the selected API; verify its target. Only `/health` is unauthenticated. Other endpoints use the private token file; never paste it into chat, build assets or Git. Real mailbox freshness is evaluated on the same GX10 host as the receiver.

| Client action | Private input / effect |
| --- | --- |
| `installation` / `arm` | Measured installation and exact receiver binding; arming is explicit. |
| `hold` | Inhibit uncommitted commands, not a physical stop receipt. |
| `observe` / `review` | Bound source-labelled frame/car/result evidence; operator assertions do not become independent measurements. |
| `command` | One UUID, purpose, source/profile, bounded target and expectation; can issue physical motion on the legacy backend. |
| `get` / `cancel` | Retrieve a request or inhibit eligible future dispatch. |
| `reconcile` | Explicit measured outcome and fresh idle binding; never invent missing DONE. |

See [strict schemas](../backend/robot_control/models.py). TCP is BASE `[x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg]`; measured car pose is a separate board quantity. Preview pixels are not BASE commands.

## Evidence chronology

October 28 records cover API deployment, profile-wait correction, local probes and the failed global calibration attempt. October 29 records include B/C/D actual arrivals and the selected RIGHT wait. The expanded catalogue corrects earlier incomplete archive selection. Later C26/review/recovery source is documented separately because the 31 original public JSON records end October 29. Preserve every failure and cutoff-specific claim.

[Evidence index](evidence/README.md) · [B arrival](evidence/taught-B-course-20261029.json) · [C accepted arrival](evidence/taught-C-operator-arrival-20261029.json) · [D arrival](evidence/taught-D-central-recovery-20261029.json) · [C26 endpoint](C26_DELIVERY_ENDPOINT.md)
