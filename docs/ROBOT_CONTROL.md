<sub>[PushPilot](../README.md) / Engineering / Robot commissioning</sub>

# One command. One receipt. No automatic replay.

**October 29 straight-stroke cadence:** use one explicitly reviewed 10 mm contact stroke initially, then consider up to 20 mm when the observed car response supports continuation. The operator corrected the earlier 50 mm suggestion to 10–20 mm. Review a fresh original before/after image pair with MUSE once after each completed stroke; do not call it after internal interpolation points. The contact schema permits at most 20 mm, defaults to 1 mm, and retains the smaller configured installation/profile limit. Existing 5 mm reviews still permit only 5 mm. Preserve speed, acceleration, literal Z/orientation, independent endpoint checks and held outcome review. Turns and destination approaches require separately established shorter increments. The first actual 1.982 mm contact translation has a verified robot endpoint and an UNCERTAIN MUSE displacement judgment; it is not a qualified car destination or turn.

**Latest operator direction:** [TCP coordinate control](TCP_COORDINATE_CONTROL.md) separates robot execution from vehicle/signal review. Use taught endpoint geometry and Native TCP readback; do not gate ordinary fixed-frame motion on visual gripper-tip detection. Three further noncontact fixed-pose segments completed to sequence 29. This does not qualify a whole road, car transport or contact turning.

**A separate GX10 commissioning service prepares bounded robot tests without converting the tablet's simulated mission into physical execution.** Implemented October 28, 2026 KST under explicit user authorization. A later current-site local profile established the persistent connection, five read-only IK queries and one real 0.5 mm tool retreat. Car pushing, turning and destination completion remain unqualified. See [current scoped evidence](evidence/robot-calibration-20261028.json).

[Source provenance](data/robot-runtime-source.json) · [Control API](../backend/robot_control/api.py) · [Offline tests](../tests/test_robot_control_service.py) · [GX10 delivery](../deploy/ROBOT_CONTROL.md)

The [POC receiver review](POC_RECEIVER_REVIEW.md) records the actual persistent protocol and current startup issue. The host now waits for a genuine reviewed profile **before opening the pendant port**. Missing configuration reports `waiting_reviewed_profile`, `listening: false`; it must not trigger manual PLAY. The earlier HELLO-then-close behavior below is historical. Successful HELLO capture did not establish persistent idle, and the photographed `45102` numeric error has not yet been tied to a particular argument. [Correction verification](evidence/rodi-startup-correction-20261028.json).

The operator's current-Z pushing request and drift/coordinate collection plan are recorded in [Contact pushing](PUSH_ALIGNMENT.md). A private read-only stationary baseline is available; TCP identity/payload, measured drawing-to-BASE correspondences, contact clearance and physical pushing remain pending. The target pose may change without changing the TCP definition; preserving its numeric Z alone does not preserve an offset tool's physical height through rotation or a TCP-definition change.

> **Historical profile-wait startup, October 28, 2026:** the separate host from `98b2a19` opened the configured pendant port in `waiting_reviewed_profile` with no BEGIN, consumed mailbox or motion. The API remained at source `6cfe6d2`, disarmed with no installation. Web/API processes, camera epoch and exact display transform were retained. GX10 passed all 474 equipment-free tests. Persistent pendant idle was not established. [Historical scoped result](evidence/rodi-profile-wait-20261028.json).

> **Earlier API deployment, October 28, 2026, 01:17 KST:** source `6cfe6d2` started on loopback 8897; the pendant listener was stopped at that time. The original 414 local / 64 GX10 subset results retain their historical scope in the [earlier evidence](evidence/robot-control-20261028.json).

## Service boundaries

| Process | Responsibility | Failure behavior |
|---|---|---|
| `serve_robot_control.py`, loopback HTTP | Authenticated commissioning, durable SQLite commands, installation/observation admission and reconciliation | Remains available after individual request/worker errors; starts disarmed after restart |
| `serve_rodi_host.py`, explicitly started pendant listener | Unchanged persistent protocol, independent idle heartbeat, Native FC03 state/endpoint checks | Failed session closes; listener waits for a new manual pendant connection; never republishes an old mailbox |
| Existing camera and MUSE application | Original images, fixed display mapping and currently simulated mission judgments | Separate processes; no camera or Rodi restart to update this API |

The API uses the inherited mailbox interface through a hash-verified private runtime. It does not implement another robot driver. The manifest identifies each exact imported source; installer excludes old profiles, mailboxes, observations and run state. Original Rodi functions for translation, raised wrist repositioning, profile update and persistent idle are preserved.

The host has an explicit `--wait-for-profile` startup mode for preparing a new installation. While its named reviewed profile is absent or invalid, it waits before binding or accepting the pendant and reports `waiting_reviewed_profile`, `listening: false`, `ready: false`. It sends no BEGIN and consumes no command. A genuine reviewed profile precedes a fresh manual PLAY. The installed online script cannot accept a fabricated unqualified idle profile. See [deployment](../deploy/ROBOT_CONTROL.md#keep-preparation-alive-while-current-measurements-are-being-prepared).

The user's later commissioning instruction explicitly includes agent-driven coordinate collection and eventual pushes/contact turns to all three destinations. Read-only coordinate acquisition and measured XY registration are now separate from receiver startup: see [Robot calibration](ROBOT_CALIBRATION.md). That request does not turn old contact heights, an image homography or a stationary TCP reading into current installation qualification. No physical destination completion is established by the calibration code.

## What is implemented

- Strict finite BASE TCP targets, current session/sequence/profile binding, measured workspace/Z/speed/step limits and single-command ownership.
- Durable UUID idempotency: retry the **same ID and identical payload** to retrieve its receipt. A new ID cannot bypass an unresolved command.
- Separate `inspect_current`, `inspect_ik`, `profile_update`, `translate` and reviewed raised-tool `rotate` operations.
- Short push admission followed by mandatory fresh post-action vehicle review. Robot endpoint verification alone does not prove the car moved correctly.
- Per-request exceptions, independent heartbeat, startup disarm, no automatic motion replay and explicit unknown-outcome reconciliation.
- Equipment-free mock mode, integration/failure tests and an offline measured-installation profile generator.

This service does not yet connect the web supervisor's MUSE action/signal loop to physical execution. Self-labelled automated observations and MUSE reviews are rejected unless a trusted physical bridge validator is explicitly supplied. Operator observations/reviews support commissioning and remain labelled `operator`. Camera hashes and operator poses are submitted assertions in this mode, not independently verified sensor measurements.

## Occlusion and completion

| Situation | Decision | Connection |
|---|---|---|
| Some or all board markers covered; fixed installation identity retained | Keep exact mapping, label `marker_occluded`; do not refit | Idle heartbeat continues |
| Car unreadable before a push | `waiting_observation`, within original admission deadline | API and receiver stay available |
| Car unreadable after a verified robot endpoint | `awaiting_review`; fresh observation/review required before another push | Idle heartbeat continues |
| Confirmed view/map/calibration/epoch mismatch | Reject stale geometry; installation review required | No automatic refit or motion |
| Lost DONE, transport failure or ambiguous publication | `outcome_unknown`, disarm and block new commands | Host waits for a fresh manual connection if the link dropped |
| API restart while queued | `interrupted_before_dispatch`; never replay | Startup disarmed |
| Restart during dispatch/commit/run | `outcome_unknown`; inspect/reconcile | Never automatically resubmit |

Admission is checked again just before a durable `committed` record. **That record is the command admission boundary.** After it, a later HOLD/cancel may arrive before mailbox publication but cannot revoke the admitted command. HOLD inhibits uncommitted commands; cancellation during dispatch/run records intent and inhibits subsequent commands. Neither sends a robot stop. The installed blocking MoveL/MoveJ protocol has no emergency-stop/cancel wire command. Use the actual controller's stop facilities when required.

`done` is followed by independent Native endpoint/stationarity verification in the inherited host. A push then needs a different, fresh post-action frame bound to the installation and a visible measured car pose plus an accepted review. PASS records review acceptance and its source; it does not relabel operator assertions as independent physical evidence. UNKNOWN/REOBSERVE remain pending. FAIL disarms. No request automatically moves the tool aside to reveal the car: such a retract must be an explicitly qualified motion sequence.

## Commissioning order

1. Fix the actual print and camera mechanically. Record print/hash, installation and calibration identities. The temporary web overlay is not board-to-BASE calibration.
2. Measure current TCP/tool identity, payload, workspace limits, work Z and raised Z. Capture actual TCP and six joint angles at the reviewed stationary starting pose. Never reuse POC slot coordinates.
3. Create private measured Installation and robot-state JSON files. Run the offline profile helper with explicit site review, then validate the resulting profile using the inherited policy. No motion or network is used by this helper.
4. Deliberately start the separate host with that profile, then PLAY the existing `poc-persistent-v1` script once. Confirm fresh idle, exact build/profile, actual pose/joints and motion mode. Start/load the API installation, inspect current/IK while disarmed, then explicitly arm.
5. Begin with raised, short bounded translations; measure results. Qualify straight contact pushes, retract/observation pose, stop-line approaches and left/right contact turns separately. Record each outcome and fresh evidence.

Car dimensions, friction, contact point and 90-degree pushing mechanics remain pending. The `rotate` endpoint rotates a **raised tool at fixed XYZ** through reviewed directed joint edges; it is not a qualified 90-degree car turn. Teaching every route combination is unnecessary: qualify reusable straight/approach/turn primitives in the installed geometry, then compile graph routes only from qualified edges. No graph-to-BASE adapter or car-turn qualification is inferred by this API.

## Local mock usage

```sh
python tools/serve_robot_control.py --backend mock --port 8897
python tools/robotctl.py status
python tools/robotctl.py events
```

Only `/health` is unauthenticated. Other endpoints require the private control token, read directly by `robotctl.py`; never paste it into chat. Browser-origin control requests are refused. Run the real mailbox backend on GX10 so monotonic state freshness is evaluated on the same host.

| Client action | JSON input |
|---|---|
| `installation --data <private.json>` | Measured `Installation` |
| `arm --data <private.json>` | Installation ID, exact receiver binding and review reason |
| `hold --data <private.json>` | Reason; inhibits uncommitted commands only |
| `observe --data <private.json>` | Installation/frame identity, hash/time, fixed-view status and car pose |
| `command --data <private.json>` | UUID, kind/purpose, binding, target/profile, time budgets and expected visual outcome |
| `get --id <UUID>` / `cancel --id <UUID>` | Existing request ID |
| `review --id <UUID> --data <private.json>` | Fresh post-action observation ID, source, verdict and summary |
| `reconcile --id <UUID> --data <private.json>` | Measured outcome, exact fresh idle binding and operator reason |

Inspect the strict schemas in [models.py](../backend/robot_control/models.py) before preparing private JSON. TCP uses BASE `[x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg]`; `car_pose` uses measured board `[x_mm, y_mm, yaw_deg]`. Workspace limits are BASE, never image pixels. Observation time is UTC Unix seconds; GX10 and camera time provenance must be qualified before an automated bridge is admitted.

## Honest availability limits

Software errors and brief visual occlusion are isolated from idle heartbeat. This is not a guarantee against power, process, network or pendant failure. The unchanged pendant script has no reconnect loop: a real TCP break can require another manual PLAY. The host continues listening; reconciliation and explicit rearming precede further commands. No historical command/profile is restored to make reconnection appear seamless.

All commissioning state, tokens, geometry, profiles and imported runtime files live under ignored `runtime/robot-control/` or a separate private GX10 shared directory. The public repository contains new wrapper code, schemas, provenance and offline tests only.
