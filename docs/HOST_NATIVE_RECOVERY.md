# Retain the connection. Reacquire the measurement.

The subsequent [negotiated commit-wait update](NEGOTIATED_COMMIT_WAIT.md) supports
a separately installed pendant variant at the two protected commit waits. The
unchanged-script behavior and dated validation below remain their original scope.

**November 2, 2026 · server-only recovery for the unchanged installed Rodi script.**

The passive diagnosis captured FC03 replies arriving after the original two-second Native deadline, including a 5.049-second reply after the controller had acknowledged the request. Three acquisition failures previously escaped from the synchronous guard and closed the separate Rodi session. This change contains that read failure at legal idle boundaries. It does not claim to repair the controller's internal response latency.

## Runtime behavior

`tools/serve_rodi_host.py` wraps the hash-verified inherited exchange with `backend/robot_control/host_resilience.py`. The inherited runtime, installed pendant script, reviewed coordinates, TCP definition, speed, acceleration, profile bounds and source-age checks remain unchanged.

One exchange thread owns all pendant I/O. Each Native snapshot retains the two-second ceiling. A known read timeout, incomplete connection, reset or selected network error invalidates dispatch and publishes `native_wait`; an IDLE/IDLE_OK exchange then keeps the pendant's existing packet loop alive before another read-only acquisition. The loop also refreshes legal idle liveness before a slow sequence of otherwise successful acquisitions can exhaust the pendant's wait.

Two new full stationary Native snapshots are required after the latest timeout/heartbeat boundary. Earlier or unavailable measurements never become fresh because a status file was republished. The original `host-journal-native-proof.v1` ordering is retained: last matching IDLE_OK, two original eligible Native rows and a later idle publication. `native_wait` cannot satisfy that proof or an idle admission gate.

| Phase or error | Server action |
| --- | --- |
| Established top-level idle; Native read unavailable | Retain exact session/sequence/profile, publish non-idle `native_wait`, exchange IDLE, reacquire two new stationary samples. No move or profile request is issued. |
| Validated DONE; Native endpoint observation unavailable | Use the pendant's **next** sequence for legal IDLE; require a new continuous two-second exact-zero interval before the inherited endpoint verifier can acknowledge completion. No GO is repeated. |
| Validated IK_RESULT / PROFILE_APPLIED | Legal idle uses the next sequence and, for an applied profile, the new profile identity. The inherited result/commit checks still decide completion. |
| HELLO awaiting BEGIN, READY awaiting GO, PROFILE_READY awaiting commit | Retain the original bounded guard and failure behavior. The unchanged script does not accept an inserted IDLE in these phases. |
| Invalid pose/program/servo/stop/manual flags, unexpected speed, malformed protocol or identity | Fail explicitly; no automatic read-failure recovery. |
| Journal/disk/ownership error, wire loss or invalid heartbeat | Fail explicitly. Session cleanup closes the journal even when archive writing fails; the listener remains subject to its outer error boundary. |
| Command already published but outcome uncertain | Preserve the command ledger and uncertainty latch. A recovered connection never resends or automatically clears an unknown physical operation. |

The valid-measurement settling window remains eight seconds with a two-second continuous-zero requirement. A read outage discards that interval and starts a new full observation window; unavailable time cannot prove stationarity. Persistent measured motion still fails. API completion budgets and command expiry are not extended by connection liveness, so a sufficiently long observation outage can still require explicit reconciliation.

The redundant outer pre-HELLO acquisition was removed: the inherited exchange still checks HELLO, reviewed origin, running program state and actual joints before BEGIN. This avoids spending two separate startup acquisition budgets inside the unchanged pendant's single ten-second BEGIN wait.

An extended outage after request preflight but before its final PREPARE can still exhaust that request's lifetime. The inherited post-READY expiry check prevents GO and can close that session. This uncommon boundary remains explicit; retaining idle connectivity does not renew an expired request or grant a retry.

## Validation and activation boundary

Equipment-free fault tests cover sustained outages, reset samples, legal and illegal wire phases, next sequence/profile identity, GO disconnect without replay, fatal measured/disk faults, settling and the existing host-journal proof. Synthetic checks are not loaded-route repeatability evidence. A separate private offline integration check runs the actual hash-verified inherited exchange against fake sockets/Native rows with network creation forbidden.

Source `bcac769` was deployed to GX10 host release `20261102-native-recovery-bcac769`. Only the disconnected host service restarted; the inherited runtime/script, startup profile, delivery configuration, camera identities, existing web/API processes and static frontend overlay matched before and after activation. After the operator's fresh PLAY, one unchanged idle session was observed from 13:35:44 to 13:41:52 KST. A file-only validator accepted the original fresh host-journal Native proof, with no movement/profile dispatch. No read outage occurred in that interval, so actual outage recovery is not claimed from this live observation. The new session's START reference still requires a separate stationary binding before tablet mission admission. [Dated evidence](evidence/native-read-recovery-20261102.json)

The observation was subsequently extended through 13:45:54 KST. At 13:42:35, a real Native read timeout published `native_wait` and retained the same pendant session/sequence/profile. New valid Native samples were acquired by 13:42:37; the session returned to idle. The file-only validator then confirmed actual outage recovery and the original fresh host-journal proof, with no close, reconnect, movement or profile dispatch. This verifies one real idle read-failure recovery, not every non-idle phase or loaded-route performance. The earlier six-minute no-outage observation remains preserved as the preceding checkpoint.

After a separate explicit preparation request, the new session's stationary START reference was verified and applied without motion. At 13:58:44 KST, the post-handoff Native proof and real tablet readiness passed; the robot remained held/disarmed at START with no mission. Exact workspace bounds and original teaching files remained unchanged. [Preparation evidence](evidence/start-reference-ready-20261102.json)

Deploy to a separate host release and switch only `pushpilot-robot-control/host-current` after confirming no active mission, pending command or connected pendant session. Preserve original source/profile/camera hashes and web/API process identities. The host restart prepares the listener; it neither presses PLAY nor starts a mission. A fresh local PLAY is needed to exercise a real idle session after activation.

Physical network loss, pendant faults and unavailable measurements inside the protocol's non-idle handshakes remain explicit limitations. This repair contains known read transport failures; it is not an uninterrupted-operation guarantee.
