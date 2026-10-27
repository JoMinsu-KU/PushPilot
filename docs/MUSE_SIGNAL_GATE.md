<sub>[PushPilot](../README.md) / Mission / MUSE signal gate</sub>

# Stop, ask MUSE, then wait or proceed

**User-confirmed scenario, clarified on October 27, 2026. Dedicated live integration is planned, not implemented.**

[Mission](MISSION.md) · [Architecture](ARCHITECTURE.md) · [Model boundaries](META_INTELLIGENCE.md) · [Current verification](VERIFICATION.md)

At each applicable intersection, the robot first stops before the stop line. After stopping is verified, the application captures a new image and asks MUSE to judge the relevant signal color. MUSE is the visual color judge. The executor waits or admits the crossing according to that result after validating its current execution context. A second local color classifier is not required by this scenario.

## Intended observation cycle

| Condition | Executor behavior |
|---|---|
| Approaching an intersection, including one that appears green | Complete the required stop before asking for crossing admission. |
| MUSE request pending after verified stopping | Remain stopped. |
| Valid current MUSE `RED` | Remain stopped; take another new image and ask again. |
| Valid current MUSE `GREEN` with accepted context checks | Admit the one current crossing without another operator approval. |
| `UNKNOWN`, obscured/ambiguous signal, invalid response, timeout or provider failure | Remain stopped; reobserve or expose the failure. |
| Result belongs to a cancelled, replaced or expired request/stop context | Discard it; it cannot admit the crossing. |

The observation cycle uses bounded, deliberate requests while waiting, with at most one active signal judgment per stop context. It does not send every video frame to MUSE. Each new query uses a new observation; re-querying the same old image cannot establish a changed signal. Request cadence, timeout and result-acceptance windows need measurement with the actual provider and installation. Preview's 1500 ms display age limit is not an established physical signal tolerance.

## MUSE judgment and local validation

The planned request binds the mission, plan and map identities, STOP/wait context, junction, approach direction, configured signal target and immutable original frame identity/hash with capture provenance. MUSE receives the image and an explicit instruction identifying the signal that controls this approach. A raw-resolution region of interest may supplement the original image if its crop lineage is preserved; it cannot add missing source detail.

The local supervisor validates:

- An actual matching stop receipt and the current approved plan/step.
- The current junction, approach direction, map and signal-target identity.
- Frame provenance and the configured capture/result age policy.
- Response schema and the exact active request/stop-context binding.
- Absence of cancellation, fault, replacement or another invalidating state change.

These checks do not independently classify RED or GREEN. A valid `GREEN` response supplies the intended visual signal judgment, while the checks establish whether this particular response can be used now. A later preview frame alone does not supersede a pending model request; a new query, changed stop context or explicit invalidation does. The robot remains stopped during provider delay.

After admission, the current qualified crossing completes before the next approach. A later red change is not an immediate in-flight interruption request in this scenario. Each next intersection needs its own stop and MUSE observation cycle. A web HOLD or server shutdown is not a controller stop receipt.

## Current implementation boundary

Current signal inputs are operator-injected `simulation` observations. The supervisor implements mandatory stopping and scoped fresh-GREEN admission in that simulation. Independent recorded-scene inspection can report a model-observed color but cannot supply a mission signal or advance a step. Recorded-action PASS satisfies only its bound simulated action-review gate. Live preview remains a separate ephemeral display source.

No dedicated live MUSE signal endpoint, trusted post-stop capture path, physical signal-to-executor adapter or robot stopping/continuation qualification is implemented by this clarification. Existing code and historical provider evidence retain their original sources and authority. This document corrects the intended architecture without upgrading a recorded image or manual signal into physical evidence.

## Map and print preparation

Identify the signal that controls each approach in replaceable map metadata. Decorative traffic-light artwork is not automatically an active signal. The operator-controlled red/green target must be distinguishable in the actual camera image. Its final size and location require testing on the printed installation, including occlusion, shadows and red/green/unknown cases. MUSE as the judge does not remove the need for sufficient visible image detail. No recognition accuracy is established by the supplied 3D rendering.
