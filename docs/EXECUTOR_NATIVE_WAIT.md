# Executor waiting for fresh Native recovery

**November 2, 2026 · source implemented and deployed to the configured GX10 trial.**

The host can retain a connection during a Native read interruption while publishing `native_wait` instead of idle. Previously, the executor treated that temporary non-idle status as `PHYSICAL_STATUS_REQUIRED` and ended the mission even when the host recovered. The executor now waits for the explicitly identified recovery and obtains fresh stationary evidence before continuing.

The API and web processes were restarted at an ended C4 HOLD; the running RODI host, receiver session/sequence/profile, literal pose, installation, completed receipts and held mission were retained. This activation issued no robot motion or profile request. A new loaded route test is not claimed. The earlier host-only deployment and idle-recovery evidence remain documented in [Host Native recovery](HOST_NATIVE_RECOVERY.md).

## Exact waiting conditions

`backend/robot_control/status_wait.py` permits waiting only when all of these conditions hold:

- The service is physical, held and disarmed, with no active command. The receiver remains connected and physically executing its packet loop.
- The receiver explicitly publishes `stage=native_wait`, `native_telemetry_available=false` and `reason=RECEIVER_NATIVE_WAIT`.
- Sanitized telemetry identifies `NATIVE_TELEMETRY_UNAVAILABLE` or `NATIVE_STATIONARITY_PENDING` in a recognized recovery phase. Stationarity-pending applies only to the stationary phase.
- The original host publication is fresh: its monotonic source age remains within five seconds. Polling never refreshes an old measurement.
- Session, sequence, profile identity, full profile, installation and literal TCP pose remain bound to the original baseline. Existing joint quantization checks remain intact; their allowance does not accumulate across polls.

`RealTaughtPorts` additionally retains its complete profile, tool, site and limit validation on every poll. Reviewed profile preparation uses the same waiting helper while preserving its separate handoff checks.

Closed or stale connections, unknown outcomes, operator holds, active commands, ordinary busy states, changed bindings and invalid physical evidence are errors, not recoverable waiting states.

## Execution policy and Stop

The standalone default wait is 120 seconds. An explicitly configured mission can instead keep waiting while every condition above remains valid:

```json
{
  "ports": {
    "status_wait_timeout_s": null
  }
}
```

This `null` is an explicit indefinite **status observation** policy. It does not extend command lifetime, admission deadlines, protected READY/GO or profile-commit budgets. A finite configured wait ends with `PHYSICAL_STATUS_WAIT_TIMEOUT`.

Waiting issues status GETs only, normally every 0.2 seconds. It does not arm, submit a motion or profile, retry a command, replay a completed step, clear an unknown-outcome latch, reset a mission or resume an already ended HOLD. Stop is checked before and after each status poll and interrupts the active wait. Start/Stop coordination sets the shared Stop latch before waiting for the serialized start operation to finish.

Readiness monitoring uses a single nonblocking status read. A valid recovery reports `NATIVE_STATUS_PENDING` and readiness remains unavailable; the monitor does not occupy the execution wait for 120 seconds or indefinitely.

## Fresh evidence after recovery

An observed wait invalidates cached Native evidence. If recovery begins during host-journal capture, a restart is eligible only when coherent fresh original host files agree with the exact validated API recovery and binding. A generic invalid Native proof is never reclassified as a transport delay.

After recovery, the executor acquires a new completed host-journal proof under the original stationary, source-age and ordering requirements. A status becoming idle alone is insufficient. Failed snapshot guards also discard the candidate cache. The executor never synthesizes stationary evidence or accepts pre-wait samples as newly observed.

The private journal records wait start, periodic progress, completion or failure, elapsed time and binding, with zero commands issued. Synthetic tests cover delayed recovery beyond 120 seconds under the explicit indefinite policy, Stop cancellation, finite timeout, binding changes, stale/closed/unknown states and fresh-proof restart without motion replay. These tests do not establish physical route repeatability.

## Completed C4 continuation

The observed interruption followed a known completed C4 receipt, before the next coordinate dispatch. A separate explicit continuation path accepts only this pre-signal `C-step-4` / Villa `PHYSICAL_STATUS_REQUIRED` case. It keeps the original interruption and completed receipt, verifies the terminal robot job and current Native endpoint, and rejects any later dispatch or unknown outcome.

For this older journal, the BEFORE image was not directly attached to the command event. Recovery therefore requires exactly one original camera-metadata/JPEG pair between the original service dispatch (and preceding completed primitive) and the hash-verified C4 primitive intent. It verifies the original JPEG hash, camera reference and source timestamp; it does not select by file modification time. Missing or ambiguous captures reject continuation. New current imagery must pass the existing C4 progress review and make the normal policy select C5; no car verdict or completed motion is fabricated.

A no-motion preparation may check these conditions while retaining HOLD and no worker. A later explicit resume request repeats fresh endpoint and MUSE checks; it never reuses an expired observation, replays C4 or consumes a signal admission. This is a narrow completed-action recovery, not arbitrary transport/robot-error continuation.

## Validation and activation

- Backend: **1,284 tests run, six skipped, zero failures**. This includes the completed-C4 continuation and threaded Stop/shutdown regressions.
- GX10: two new same-owner host-journal Native snapshots passed after activation, with the same receiver identity/profile/pose and held, disarmed, no-command state. No extra Native socket was opened.
- The private mission configuration explicitly uses `status_wait_timeout_s: null`. The camera reference was resumed with the same epoch, matrix and original reference lineage; no optical change or new fit occurred.
- The live connection was not deliberately faulted. Beyond-120-second delay and cancellation were verified with synthetic time/source fixtures; these are separate from live Native-read validation and loaded-route qualification.
- A separate no-motion C4 preparation recovered the unique original BEFORE image, confirmed the actual endpoint and received a fresh MUSE `PROGRESS_OBSERVED`. The normal policy selected `C-step-5`. The original mission remained HOLD with 4/30 completed and no worker; a later explicit resume repeats fresh checks before motion.
