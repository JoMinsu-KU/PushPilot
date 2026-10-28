<sub>[PushPilot](../README.md) / Engineering / Persistent receiver review</sub>

# Preserve the proven receiver. Establish the current installation.

This review records the October 28, 2026 KST investigation of the pendant connection error and the inherited POC control path. It distinguishes the verified transport design from the still unqualified city-print installation. No motion, profile activation, calibration or receiver-script change is established by this review.

[Commissioning service](ROBOT_CONTROL.md) · [Deployment](../deploy/ROBOT_CONTROL.md) · [Source manifest](data/robot-runtime-source.json) · [Contact pushing](PUSH_ALIGNMENT.md)

## Separate the application API from the POC receiver

| Boundary | Role | What a successful connection establishes |
|---|---|---|
| New GX10 commissioning HTTP API, loopback port `8897` | Authenticated requests, durable command records, installation checks, disarming and reconciliation | The API is available; this alone does not connect the pendant |
| GX10 pendant TCP listener, port `19507` | Owns the Rodi socket and exchanges the persistent receiver protocol | A listening socket is available; a validated handshake and continuing replies are still required |
| Controller Native Modbus FC03, port `502` | Independent read-only program state, flags, TCP, joints and joint-speed checks | Current controller telemetry within its register resolution; it does not verify active TCP configuration, contact clearance or vehicle pose |

The POC receiver used the pendant TCP listener and independent Native checks; the new commissioning HTTP API is a separate application layer. The controller initiates the TCP connection to the host. The HTTP API does not replace that listener and does not open a second robot-command socket. Its inherited adapter publishes one expiring, bound mailbox request for the host to consume. Camera and MUSE processing are independent of the host's idle heartbeat.

The inherited source was imported without historical operating profiles, pending mailboxes, coordinates or run state. Source verification occurs before runtime imports. The original POC operating policy is to preserve the receiver and use its profile-update exchange for ordinary target, direction and setting changes. A healthy connection does not need another PLAY for each target.

## Exact inherited source identity

The handoff's `current/deployed/robot/hcr1-pose-receiver/` sources were compared with the application's provenance manifest. These SHA-256 values identify source bytes, not a new readback of the pendant's current editor contents.

| File | SHA-256 |
|---|---|
| `hcr1_pose_receiver.stable-v1-online.script` | `889b79b44e3c1729597b767c506d7cb4ce993fe37e7855bea1b49453dbec6938` |
| `server.py` | `b84980fe2c04b471f645899ef4f8b259c557f78c14210b27cfa4b223539dc87f` |
| `transport.py` | `02d539703ce5b72cd29d7923d730295b4c7321b2d9c1a05fce09ce78c87fdb00` |
| `policy.py` | `2828db82d487ec924d2855abd1432847d0944cc3628130129b8476b6aa77bbfe` |

The build is `poc-persistent-v1`; the wire schema is `pushpilot.hcr1-pose.experimental-v1`; the revision is `pose-receiver-experimental-v1`. In the private installed application runtime, `hcr1_pose_receiver.script` is an alias of the online source above. The handoff also preserves a distinct canonical default-motion-false source with SHA-256 `60cedfa00c25584384c2e4fabd342745a9395c7c2c0b31504b75666557727faa`. Those two files must not be confused merely because their names are similar.

The handoff runtime contract records historical installed validation of handshake, idle, current FK, profile update and raised wrist rotation. Its archived success does not establish a current session or qualify the new print, car or pushing geometry.

## How the persistent exchange works

1. **HELLO:** the script reads the current TCP/joints/speeds and reports its schema, revision, build, capabilities and local motion flag.
2. **BEGIN:** the host validates the peer, profile, current Native state and HELLO. It sends a new session ID, profile digest, exact observed origin and execution mode.
3. **SESSION_READY:** the receiver independently checks the initial profile, pose, joints and bounds, then acknowledges the session.
4. **IDLE / IDLE_OK:** the host sends a heartbeat and checks its bound reply and fresh Native stationarity. This continues without a target while the session is healthy.
5. **Optional profile update:** `profile_prepare → profile_ready → profile_commit → profile_applied` binds old/new profile identities and the stationary pose. This changes reviewed settings without performing a move.
6. **Admitted physical command:** `prepare → ready → go → entering → done` binds the session, sequence, profile, operation, target, runtime and command digest. Only the matched GO reaches the guarded movement call. DONE is followed by independent Native endpoint/stationarity checks.

The sequence is not an unguarded stream of XY positions. Each command has a bounded lifetime and a specific expected source state. Unknown outcomes are reconciled rather than replayed. The installed blocking movement calls have no qualified in-flight cancel wire operation; server exit or a web HOLD is not an emergency stop.

The original host checked eligible stopped/pre-PLAY program states before accepting the connection. In the dedicated application host, the pendant has already started its script by `accept()`. Its post-accept Native guard therefore correctly requires running program state `2`; copying the original pre-PLAY `(1, 6)` check into that location would reject a legitimate running receiver. The earlier stationary baseline in program state `6` does not change that ordering.

## What the October 28 fault evidence establishes

The user's photograph shows controller `CODE 45102`, `number is not normal`, highlighting `ppNumber(x)`. The photographed TCP configuration is `test_robot2`, offset `[0, 0, 200]` mm, orientation `[0, 0, 0]` degrees and payload `0.1 kg`. These settings are operator-provided configuration evidence. The screenshot alone does not prove the TCP is incorrectly configured, independently verify the active controller selection, or identify the numeric argument that triggered the exception.

Private host diagnostics from approximately **14:33–14:34 KST** received valid HELLO packets identifying `poc-persistent-v1` with the local motion flag true. The corresponding journal records `profile_wait_closed_without_begin`; no BEGIN transmission occurred in those connections. This proves those attempts reached the host and emitted finite validated HELLO telemetry. It does not prove a completed session or that every field in a later runtime path is valid.

The `ppNumber` implementation is already present in the verified POC source. Its presence in the photograph is not evidence that a new numerical validator was introduced. The exact cause of `45102` remains **unconfirmed**: a valid HELLO plus a later closed socket does not identify which subsequent argument or interpreter path produced the fault. Host timing and the pendant exception need to be correlated before assigning that cause.

The user requested consultation of the historical POC task on October 28. Its retained records identify distinct **45100** cases: a shortened `rotation_runtime` object missing `primitive` (`r7-runtime-shape-repair.json`), `ppUpdate` reading absent `old_profile_id` (`diagnostics/r4.1-dispatch-review.md`), and interpreter helper/loop variable failures (`rodi-runtime-error.json` and helper-scope evaluations). The archived control handoff preserves those cases privately. They do not establish the current 45102 caller. The consultation's completed response confirmed that neither a matching full generated-program export nor the current 45102 call stack was preserved. The 55-line difference between source line 16 and photographed line 71 fits a generated prefix, but does not prove its contents. Source-body hashes are not a substitute for the complete currently installed program. The smallest remaining diagnostic is to compare the original failure's full error details/program and last received/transmitted packet from that same execution; a later HELLO from a separate attempt cannot identify its numeric caller.

### The identifiable host defect

The initial `--wait-for-profile` implementation bound the pendant port while the named reviewed profile was absent, accepted HELLO, and deliberately closed without BEGIN. It safely avoided inventing a profile or consuming a command, but presented an available connection endpoint that could never complete the installed receiver's startup. The pendant then exited its one-session script rather than remaining in persistent idle.

That early-close behavior explains why a live listening port was insufficient. It may expose the receiver's disconnect/rejection path, but it does not by itself prove the exact `45102` arithmetic failure. The appropriate host correction is to report the missing-profile state before admitting an execution connection; the corrected behavior and its actual deployment must be recorded separately from this source review. It must not be described as successful persistent idle.

## Why an unqualified idle profile cannot repair the current script

The online source sets `ppAllowMotion=true`. Its BEGIN check requires `execute_motion` to equal that local flag, and its profile policy requires `allow_motion=true` and `site_verified=true` when the local flag is true. Consequently, `BEGIN.execute_motion=false` with an honest unqualified profile cannot enter idle using the unchanged online script.

The original POC documentation deliberately retained `allow_motion=false` and `site_verified=false` for a receive-only profile. Its narrow bounds were labelled parser/communication-test geometry, not physically reviewed clearance. A promise by the new host to send no GO cannot turn those limits into measured site qualification.

The operator's paper placement, current stationary readback, photographed TCP offset and confirmed approximately ±2 mm local XY clearance are not a reviewed installation, inflated keepout model, contact geometry or swept tool/arm envelope. A proposed true-flag bootstrap profile was rejected because those measurements were missing. **It was not executed, and no true-flag profile or motion command was created for that proposal.** No altered receiver candidate is implemented or installed by this review.

## Recovery paths and their proof requirements

| Path | Preparation | Required evidence | Status |
|---|---|---|---|
| **Preserve the installed receiver; qualify the current installation** | Record the actual selected TCP/payload, fresh TCP/joints, measured operating bounds, contact Z/clearance, keepouts and intended bounded primitive. Create a new private reviewed profile with genuine flags. Do not reuse POC poses or profiles. | Source identity, current Native/HELLO agreement, matched BEGIN/SESSION_READY and sustained IDLE replies; no target during initial connection verification. Later commands require separate qualification/admission. | Preferred path; current measurements are incomplete |
| **Explicit read-only receiver compatibility change** | Deliberately design a distinct read-only session that permits false/false qualification flags while preserving every physical motion guard. Add an immutable host outbound allowlist and separate status; consume no mailbox. | Offline protocol and negative-path tests, exact installed script readback, one real handshake and sustained stationary replies. VM success is not installed-Rodi proof. | Optional design only; needs one deliberate receiver change and real validation |

Simply retaining an unstarted socket after HELLO cannot provide durable idle: the inherited receiver waits approximately ten seconds for a packet. Repeated invalid packets, fabricated qualification flags, automatic PLAY, cached poses or restoration of an old mailbox are not recovery mechanisms.

Neither path qualifies vehicle steering, 90-degree contact turns, map-to-BASE registration, signal-stop geometry or post-push MUSE judgments. Those remain explicit commissioning work after the communication session is established. Existing camera, web and independent API processes need not be restarted to prepare the measurements or inspect the protocol.
