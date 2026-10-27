<sub>[PushPilot](../README.md) / Mission / MUSE signal gate</sub>

# Stop, ask MUSE, then wait or proceed

**User-confirmed scenario, clarified on October 27, 2026. The native-frame backend is implemented against simulated stop receipts; actual robot stopping and real-provider recognition are not verified.**

[Mission](MISSION.md) · [Live intelligence](LIVE_INTELLIGENCE.md) · [Architecture](ARCHITECTURE.md) · [Current verification](VERIFICATION.md)

At each applicable intersection, the robot first stops before the stop line. After stopping is verified, the application captures a new image and asks MUSE to judge the relevant signal color. MUSE is the visual color judge. The executor waits or admits the crossing according to that result after validating its current execution context. A second local color classifier is not required by this scenario.

The robot wording above describes the physical target scenario. Today's application performs the same state sequence in **simulation**, with server-created simulated action/stop receipts and explicitly selected native camera images. It sends no robot commands and cannot verify a physical stop.

## Single-signal final-print concept, October 28

The current design intent starts every mission at PIZZA, initially travels east in the printed map frame and requires the route to pass through one designated signal-controlled approach. The user proposes one physical paper signal at the road edge beside the Office Building block's northwest corner, at the central junction's southeast corner. This is a proposed placement, not a measured installation or a replacement of the active temporary map.

Explicitly identify both the controlling junction and incoming approach. One visible signal must not silently control all four incoming roads. Initial eastbound departure alone does not determine whether the eventual central-junction approach is from the west or south; finalize the actual start position and approach path before assigning those map nodes or a stop line.

Proposed English presentation labels:

| Item | Display label | Binding |
|---|---|---|
| Central controlled intersection | `Main Junction` | Reviewed junction node in the final map |
| Single active paper signal | `Signal 01` | One configured `SignalTarget.id` |
| Mandatory entry from the PIZZA route | `Pizza approach` | Reviewed incoming road/node, not a compass direction inferred from the label |
| Required stopping point | `Stop before Main Junction` | The selected approach's STOP checkpoint before its crosswalk/entry |

These labels are proposed presentation names, not finalized graph IDs. They do not rename the current temporary junction `C`, register a paper target or enable a crossing. The existing target contract binds `id`, `junction_id`, `approach_from`, `bounds_mm` and `description`. It has no independent stop-line field: associate the signal with the current route's approach/STOP checkpoint and preserve that checkpoint in the bound plan. Any later schema extension must make a stop-line identity explicit rather than inventing an existing field.

The same junction/approach/signal relationship belongs in map metadata, the MUSE request context and the operator's decision display. A compact printed-map label may use the same names without covering the vehicle corridor. The initial plan includes the mandatory stop and conditional wait/continue behavior. Each stopped judgment uses a new original frame selected after the bound STOP context, never the signal color seen in the initial planning image. A raised paper signal's visible face must be checked in the installed camera view; its apparent region must not be assumed from the flat board footprint alone.

Example prompt instruction, to accompany the actual bound metadata:

```text
Judge only Signal 01 assigned to Main Junction for the configured Pizza approach.
Use the supplied junction_id, approach_from and signal_target.id bindings.
The current image must belong to the supplied post-stop observation.
Do not select a signal for another approach or use printed decorative lights.
If the specified controlling signal cannot be identified clearly, return UNKNOWN.
```

Example decision presentation: `Signal 01 · Main Junction`, `Approach: Pizza approach`, then `Checking signal…`, `RED · WAIT`, `GREEN · CONTINUE` or `UNKNOWN · REOBSERVE`. Show the actual MUSE summary and observation source/time with that bound result. These are design examples; the current frontend still requires the complete latest-decision presentation described in the UI audit.

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

The implemented request binds the mission, plan and map identities, STOP/wait context, junction, incoming road, configured signal target and immutable original frame identity/hash with capture provenance. MUSE receives the unchanged original JPEG and a server-projected signal-target polygon tied to that exact frame. The polygon is a location hint, not proof of visibility or recognition. No image crop, board rectification or re-encoding is used. A future supplemental crop would need explicit lineage and could not add missing source detail.

The local supervisor validates:

- A matching server-created **simulation** stop receipt and the current approved plan/step. A qualified physical adapter must later supply a real measured stop receipt.
- The current junction, approach direction, map and signal-target identity.
- Frame provenance and the configured capture/result age policy.
- Response schema and the exact active request/stop-context binding.
- Absence of cancellation, fault, replacement or another invalidating state change.

These checks do not independently classify RED or GREEN. A valid `GREEN` response supplies the visual signal judgment, while the checks establish whether this particular response can be used now. A later preview frame alone does not supersede a pending model request; a new query, changed stop context or explicit invalidation does. The simulated mission stays stopped during provider delay. The physical implementation must preserve actual stopping through its independently qualified controller.

After admission, the current bounded simulated crossing needs its own live action review before the next approach. The future physical crossing must be separately qualified. A later red change is not an immediate in-flight interruption request in this scenario. Each next intersection needs its own stop and MUSE observation cycle. A web HOLD or server shutdown is not a controller stop receipt.

## Current implementation boundary

`POST /api/v1/live-signals/reviews` now performs one server-bound native-frame MUSE judgment while the approved simulated mission is waiting after a mandatory STOP and accepted action review. It requires an approach-specific target in the selected map. It projects that target into the original frame, persists the deliberate selected observation and request binding, runs inference outside the workspace lock, then revalidates context and age before applying a result. `RED` and `UNKNOWN` keep waiting. An accepted current `GREEN` admits one simulated crossing and binds the signal image as that crossing's BEFORE frame.

`POST /api/v1/live-signals/wait` makes a finite sequence of one to three new judgments, with a 0.5–10 second interval; defaults are three attempts and two seconds. It stops on admission, exhausted attempts, failure or an invalidated context. There is no infinite background polling. The selected frame must follow the observation request under the conservative camera-host-receive/transport age bound; exposure time is still unknown. The default result acceptance window is 30 seconds in simulation, not a qualified physical tolerance.

`POST /api/v1/live-signals/watch` supports a longer bounded background RED/UNKNOWN wait: defaults are 30 new judgments, two seconds between attempts and a 300-second total budget; caps are 60 judgments, a 10-second interval and 900 seconds. A successful live STOP review through `/live-actions/run` starts this watch automatically only when its current view and approach-specific target are configured. Missing targets keep waiting. GREEN ends the watch with CROSS still requiring its action review; no next mission action runs automatically. Explicit `/watch/stop`, changed execution context, provider/view failure or an exhausted budget prevents further queries, and restart never resumes a prior watch. `GET /api/v1/live-signals/watch` exposes its status. This service controls observation requests, not physical robot stopping.

Live-backed plans reject manually injected colors and demo/recorded action verdicts. Separate explicit demo missions retain operator-injected `simulation` signals. Independent recorded-scene inspection may report a color but cannot supply a mission signal or advance a step. Preview polling itself remains an ephemeral display source; it does not invoke the signal provider or persist frames.

Signal requests use prompt `pushpilot.live-signal.prompt.v1` and result schema `pushpilot.live-signal.result.v1`. The strict result contains only `color`, `visible`, English `summary` and `limitations`. RED/GREEN requires `visible: true`; uncertainty is UNKNOWN with `visible: false`. Request-ID retries do not resend inference. Late, expired, cancelled, superseded or interrupted results cannot resume execution automatically.

Offline generated-image/mock-provider tests cover these software bindings and transitions. No actual request through the new live signal endpoint, recognition accuracy, physical signal-to-controller adapter, measured stopping or physical continuation is established by this implementation. Historical provider evidence keeps its original recorded/text source and scope.

## Map and print preparation

Identify the signal that controls each approach in replaceable map metadata. Decorative traffic-light artwork is not automatically an active signal. The operator-controlled red/green target must be distinguishable in the actual camera image. Its final size and location require testing on the printed installation, including occlusion, shadows and red/green/unknown cases. MUSE as the judge does not remove the need for sufficient visible image detail. No recognition accuracy is established by the supplied 3D rendering.

The current temporary map intentionally has no reviewed active-paper signal targets. Live signal requests therefore reject before dispatch until target identities, incoming approaches, board regions and descriptions are supplied in reviewed replacement-map metadata. This does not require recalibrating for a passing gripper or hose; camera registration remains fixed until an actual view/map change requires explicit relocking. See [map replacement](MAP_REPLACEMENT.md).
