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
| PROFILE_READY → PROFILE_COMMIT and READY → GO | The corrected full script advertises `bounded-commit-wait-30s-v2`. Each native read uses 10,000ms; only an empty result permits another read, with three reads maximum. |
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

The supplied full candidate also includes the exact earlier `ppNear` expansion:
six explicit comparisons replace its local-index loop, preserving both vector
checks, literal Euler values and the original tolerance. This avoids shipping
the call site photographed with `i is not defined` again. The separate historic
patch and its equivalence tests are retained privately; it does not establish
the internal cause of that interpreter behavior or claim current installation.

Offline faults cover old/new negotiation, repeated timeouts and recovery,
deadline exhaustion, expired/mismatched requests, malformed actual state,
lost committed acknowledgments, exactly-once dispatch and callback restoration.
Run the hash-verified inherited exchange with synthetic sockets/telemetry too.
Actual manual installation, no-motion handshake and later physical mission
evidence must be reported separately from those tests and server activation.

[Earlier idle recovery](HOST_NATIVE_RECOVERY.md) · [Operations](ROBOT_OPERATIONS.md)

## Activation checkpoint

Server code `a6e4b57` and the separate final frontend source `361a81c` were
activated as GX10 release `20261102-commit-wait-a6e4b57`. The actual HTTP index
and four chunks matched the frontend manifest. Backend verification ran 1,237
tests with six skips; the frontend ran 152 tests. The actual startup-profile
file also passed all nine hash-verified inherited-exchange fault scenarios
using virtual telemetry and zero hardware sockets, plus 131 GX10 tests with
one skip. [Dated record](evidence/negotiated-commit-wait-20261102.json)

The first deployment verification deliberately rolled back when the web
restart changed the display registration identity. The subsequent activation
verified the persisted `resumed_from` lineage, identical homography, same camera
epoch and current agreeing markers. No camera optical setting, refit, map,
signal pixel region, robot command or old unresolved outcome was changed by
that display-reference restoration. New identity binding during later explicit
START preparation is a separate operation.

At this checkpoint the old mission remained HOLD at 18/31, its original unknown
request was preserved and deployment submitted no movement. The full pendant
file had been delivered for manual installation; actual installation and the
separately requested empty START return were still pending.

## Pendant argument-range correction

The first installed v1 candidate failed with `wrong argument: timeout(30000)`
during a no-motion profile handshake. The local official **Rodi Script
Programming Guide_KR.pdf**, section 11.1.14, PDF page 178, specifies a 1–15,000ms
argument range and an empty string when no line is available. The desktop mocks
had not enforced that native range; their success did not establish interpreter
compatibility. No motion command was submitted during this failed check.

Do not install v1. The corrected v2 uses up to three explicit 10,000ms reads,
continuing only after an empty string. Nonempty, oversized and malformed data
are never retried or combined. The server recognizes only the v2 capability
for the extended protected budget; the old v1 advertisement gets the original
bounded policy. No new IDLE, resend, reconnect or movement argument is added.
The v1 artifact and failed handshake evidence are preserved. Actual v2
installation, no-motion verification and START return remain separate checks.

## Reacquire stationary evidence without accepting nonzero speed

The v2 no-motion exchange succeeded, followed by eleven completed empty-tool
XY return commands. After the last confirmed endpoint, one later Native row
reported a single `0.1` speed register; the prior guard closed the connection.
The motion receipt remains complete and the completed movement is not replayed.

During a legal top-level IDLE only, a valid posture with nonzero speed up to
`0.1` now starts one bounded eight-second reacquisition window. Such a row is
never accepted as stationary. The host maintains IDLE liveness and requires
two new exact-zero samples before publishing readiness. Repeated noise does
not extend the deadline; larger speed, invalid pose/program/flags or failure to
obtain the original zero proof still blocks. READY→GO remains strict.

Explicit retirement can also validate a new stationary START reference through
the existing 0.005 component precision bound, unchanged original teaching/review
hashes and a fresh exact Native session/START match. This resolves connection
readback representation without moving Z or loosening profile admission. A
failed preparation still requires its separate documented reconciliation.

## Actual final START preparation

The operator installed v2 and its HELLO capability was received. Actual
no-motion profile exchanges succeeded. The eleven empty XY return movements
were preserved as completed; after the separate speed-evidence fix, only the
remaining reviewed wrist return was executed. The original common START was
independently confirmed, the ended HOLD was retired through the official reset
API and the workspace goal/plan were cleared. The applied stationary profile
and startup file match, with an explicit fresh-session START reference.

Final status was available, connected, stationary and at START, with no active
mission, no queued command and progress 0/0. The same saved camera epoch and
homography were resumed without a refit. No vehicle mission was automatically
started and this check does not claim fresh loaded B/C/D route qualification.
Forced second/third-read delay branches were verified with strict offline
mocks, separately from the actual immediate installed exchanges.
