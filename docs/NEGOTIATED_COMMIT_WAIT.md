<sub>[PushPilot](../README.md) / Robot / Connection resilience</sub>

# Wait for fresh evidence before committing once.

The November 2 profile-transition interruption exposed a remaining protected
handshake: the pendant had sent `profile_ready`, but three Native acquisitions
timed out before the host sent `profile_commit`. The old host closed after
about six seconds. No new profile commit or subsequent C18 motion was sent in
that incident. Preserve the original HOLD and unresolved command record.

This update adds an explicitly negotiated pendant variant; it does not change
the taught routes, TCP, height, speed, payload, workspace or motion primitives.

| Clock or policy | Behavior |
| --- | --- |
| Connection / BEGIN / top-level packet wait | Original 3-second connection and 10-second packet waits. |
| PROFILE_READY → PROFILE_COMMIT and READY → GO | The separately supplied full script advertises `bounded-commit-wait-30s-v1` and waits 30 seconds at these two calls only. |
| Protected Native verification | With that exact capability, at most 20 seconds measured from the earlier PREPARE send. Each acquisition stays bounded to two seconds; transient read failures discard the current pair. Two new eligible stationary samples are required. |
| Original pendant | No capability means the original bounded stationary guard. The host must not assume a 30-second wait for the old script. |
| Command lifetime | The original absolute 30-second wire expiry remains. Recovery never extends it. Check it again at PREPARE, IK_QUERY, GO and PROFILE_COMMIT transmission, as well as inherited validation. |
| Profile/inspection receipt wait | Outer API completion 60 seconds; caller poll 70 seconds. These acknowledgment windows do not extend command execution authority. Admission remains 10 seconds. |
| Motion DONE / wrist completion | Original operation-specific completion windows. No motion replay or changed controller movement argument. |

No IDLE packet is inserted inside a protected handshake. The existing one-owner
legal-idle recovery remains responsible for ordinary waiting and post-DONE,
post-IK_RESULT and post-PROFILE_APPLIED evidence. A scoped adapter binds the
exact accepted preflight request to the final wire send. It restores the private
module callback even when an exchange exits exceptionally; inherited runtime
files and the original source manifest remain unchanged.

A persistent outage still blocks execution. Safe closure is required when the
bounded handshake cannot obtain fresh evidence; neither a cached measurement
nor an automatic GO/COMMIT retry is a substitute. This update improves tolerance
of transient delay, not the robot controller's underlying response latency.

## Diagnose the correct boundary

An exact bound `command_not_committed` event can expose
`PROFILE_NOT_COMMITTED_NATIVE_TIMEOUT` or `MOTION_NOT_COMMITTED_NATIVE_TIMEOUT`.
The durable job still stays `outcome_unknown`, disarmed and unavailable for
automatic replay. Any matching GO/COMMIT intent or transmission prevents this
specific diagnosis. Missing acknowledgments after a possible commit remain
unknown and require independent reconciliation.

Mission exceptions invalidate the prior displayed connected/stationary/START
facts without making an extra hardware request or claiming that HOLD physically
stopped the robot. Historical receipts, progress and original errors remain.

## Install and verify separately

The full pendant candidate and its source hash are handed to the operator
privately. [Artifact identity](data/robot-pendant-timeout-variant.json) records
the original and candidate hashes without publishing private inherited source.
Keep the old file for rollback. Install the full file while stopped, start it
from the beginning, and confirm the new HELLO capability before relying on the
extended policy. A syntax check on a desktop is not a Rodi interpreter test.

Offline faults cover old/new negotiation, repeated timeouts and recovery,
deadline exhaustion, expired/mismatched requests, malformed actual state,
lost committed acknowledgments, exactly-once dispatch and callback restoration.
Run the hash-verified inherited exchange with synthetic sockets/telemetry too.
Actual manual installation, no-motion handshake and later physical mission
evidence must be reported separately from those tests and server activation.

[Earlier idle recovery](HOST_NATIVE_RECOVERY.md) · [Operations](ROBOT_OPERATIONS.md)
