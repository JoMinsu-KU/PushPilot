# From sight to action · current status

**Source-backed status, November 2, 2026 · Native recovery source `bcac769`, with dated recovery and subsequent stationary START-preparation evidence.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Robot operations](ROBOT_OPERATIONS.md) · [Known limitations](KNOWN_LIMITATIONS.md)

PushPilot's original promise is unchanged: **see the scene, express a goal, inspect a shared plan, approve the mission and review the outcome**. Meta MUSE is the intelligence layer connecting the operator's intent and visual evidence to the next decision. A deterministic supervisor applies execution gates; the Robot executor follows reviewed BASE coordinates.

## Capability and evidence matrix

For a first visit, [Demo and recorded decisions](DEMO.md) leads with the approved **55-second physical action → fresh MUSE review → next step** recording: C Step 1 pushes the car, the tool withdraws, a new PASS appears at 06:42:17, and C Step 2 begins. The older Camera clip is supporting post-arrival/empty-return footage; the Spatial clip shows the rendered application estimate. The public [recorded-decision explorer](https://jominsu-ku.github.io/PushPilot/) presents three existing synthetic-input Meta API records. Watching/selecting these archives invokes no new inference or equipment control. [Exact media scope](assets/PHYSICAL_MEDIA.md)

| Capability | Current implementation | Evidence boundary |
|---|---|---|
| Goal understanding and route selection | MUSE receives the selected graph, operator goal and deliberately selected native image; local checks validate its exact directed path and constraints. | Actual provider records are dated and map-specific. A route preview is not physical reachability or motion permission. |
| Operator workspace | Camera/Spatial, From/To, glass mission/status overlays, Pretendard, typed goals, approval and source-labelled review/history. | Page scrolling is disabled. Internal route/history scrolling exists and needs explicit acceptance against the earlier broader no-scroll requirement. |
| Camera | Original-perspective native JPEG display, fixed-reference Board focus, shared image/AR navigation and bounded recovery after stalled requests. | Occlusion may retain an unverified fixed mapping; stale frames or contradictory visible evidence still inhibit the relevant display/admission. |
| Spatial | Manifest-verified private city model and shared selected drawing route; optional contact-receipt-driven car estimate. | **Execution estimate / Display only**. It does not measure vehicle position, slip or yaw. |
| Default simulation | Graph-derived actions, source-labelled observations, stop/signal gates, review and replay without equipment. | Receipts belong to simulation; the separate physical service has its own status and Native records. |
| Configured Robot trial | Private taught B/C/D primitives, per-unit coordinate approach/contact/withdrawal, Native receipts, MUSE review, configured signal admission and empty START return. | Current-site experimental release. Historical deliveries and software checks do not qualify repeatable unattended performance for every derived path. |
| Physical signal | Two printed colors with one manually covered; selected far-RIGHT observation, stopped MUSE judgment, accepted GREEN, measured recontact and single-departure continuation. | A new mission requires a new admission. Unknown/transitioning evidence waits. Do not infer a verified physical wait duration from the wrist or simulation timers. |
| Vehicle alignment | Generic measured-response/correction and parking policy modules exist. The active site trial is **delivery_only**. | Numeric drift correction, final straightening and parallel parking are deferred; they are not active acceptance guarantees. |
| Voice | Backend accepts bounded supported WAV, targets the Meta transcription adapter and returns revision-bound candidate text. | Browser capture/encoding/confirmation, actual ASR access and recognition quality remain pending or unverified. Typed goals remain available. |
| Goal editing | Robot UI disables edits during a physical mission; simulation validates its workspace state. | Workspace/voice APIs do not yet share a server-side active-mission lock with the separate physical service. |
| Recovery | Explicit completed-review continuation, scoped C19 omission, C11 boundary preparation and session-bound START reference; ended-mission retirement at verified START. | No automatic unknown-command replay. Reset does not itself move the robot. Some reconnects require local PLAY. |
| Receiver resilience | Deployed same-owner legal-idle heartbeats contain transient Native read failures; `native_wait` blocks dispatch until two new stationary Native samples are available. [Recovery](HOST_NATIVE_RECOVERY.md) | One actual idle read timeout recovered in the unchanged session at 13:42:35–13:42:37 KST. No reconnect, motion or profile dispatch occurred. Non-idle protocol phases and loaded-route repeatability remain unqualified; no automatic motion replay. |
| Glasses companion | Retained product concept for seeing, stating and reviewing the shared plan. | No wearable integration is claimed. |

## One start. Three destinations.

All current taught recipes share the accepted Pizza-front START. B is **Office Building**, C is **Villa**, and D is **Hanok**. C/D share the first northbound approach and later branch west/east. The car slides on the surface; it is not grasped or lifted.

The C endpoint is **C-step-26**. Final review asks whether the car visibly occupies the selected Villa frontage destination, not whether it is parked parallel. The empty tool has a separate START-return recipe. [Current delivery scope](DELIVERY_SITE_TRIAL.md) and [C26 endpoint](C26_DELIVERY_ENDPOINT.md) describe the exact boundaries.

The current C review matrix includes C4/C6 details, C14's clear signal-wait reference spanning recontact, qualitative C17 progress, optional explicitly configured C19 Native-only continuation and destination-only C26 arrival. [Review matrix](C_INTERMEDIATE_PROGRESS_REVIEW.md)

## Map, model and motion identities

| Identity | Current role |
|---|---|
| `seoul-city-a3`, version `2026-10-28.4` | Explicitly selected current drawing adapter: City places and nominal A3 road/marker facts from the final PDF's embedded JPEG. |
| Final A3 PDF / `7016 × 4961` embedded source image | Nominal artwork provenance; the original bytes stay private. It is not a survey of the installed paper. |
| `little-town-temporary` | Source-default compatibility fixture and historical provider/simulation example. Selecting City does not erase this history. |
| `frontend/public/models/city-display.json` | Current private toy-city model hash and display-only fitting metadata. The old ZIP/clean-road variant is a different asset workflow. |
| Private taught-BASE packet and profile review | Robot motion authority for the explicitly configured site trial. Do not derive it from image pixels, the Spatial model or a nominal drawing transform. |
| Fixed camera reference | Image/AR display and selected observation identity. A display relock is not robot-coordinate recalibration. |

The public map's `temporary: true` and `physical_execution_enabled: false` remain valid drawing-adapter flags. They do not negate the separate configured physical trial. Do not modify the map identity merely to reconcile model documentation. [City](CITY_A3.md) · [Replacement](MAP_REPLACEMENT.md) · [Spatial](SPATIAL_3D.md)

## Build and deployment snapshot

The latest recorded software checkpoint for Native recovery source `bcac769` ran **1,199 backend tests with five skips and zero failures**, **143 frontend tests with zero failures**, and the TypeScript/Vite build successfully. The GX10 related suite ran 80 tests with zero failures. These are software checks; they do not measure model accuracy or loaded-route repeatability. [Dated source and validation record](evidence/native-read-recovery-20261102.json)

That source was activated as the server-only host release `20261102-native-recovery-bcac769`. The initial 13:35:44–13:41:52 KST idle observation had no read failure. Observation continued through 13:45:54; a real Native timeout at 13:42:35 retained the same pendant session/sequence/profile and reacquired two new valid samples by 13:42:37, restoring the original fresh host-journal proof. No connection close, reconnect, movement or profile dispatch was observed. This establishes **one real idle read-failure recovery**, with the installed Rodi script and other service identities retained. [Activation and limits](HOST_NATIVE_RECOVERY.md#validation-and-activation-boundary)

At that recovery cutoff, the new session still needed a stationary START binding. The subsequent explicitly requested preparation completed one no-motion profile/reference handoff; its **13:58:44 KST** post-handoff proof confirmed available, connected, stationary, held/disarmed at START, with no blockers, active command or mission. Original teaching files, workspace bounds, tool/payload and motion limits stayed unchanged. This was point-in-time readiness for operator tablet Start, not a mission or new vehicle-placement check. [Separate START-readiness record](evidence/start-reference-ready-20261102.json)

The **initial November 2 publication checkpoint** was runtime code `7aa7753`: 1,177 backend tests with five skips, 126 frontend tests, source checks and the frontend production build. Its five recovery/START code files matched the inspected GX10 source release `20261031-c11-activation-fix` before publication; that earlier comparison was not a new activation or mission-readiness test. The documentation/image refresh reran those earlier totals. They remain explicitly historical in [verification](VERIFICATION.md#initial-publication-and-documentation-checkpoint--november-2-2026).

The earlier November 2 frontend-only Spatial signal overlay has its own [source and activation record](SPATIAL_SIGNAL_PREVIEW.md#operational-activation--november-2-2026), including its separate 136-test frontend checkpoint. That display update is distinct from the later Native recovery activation and the initial source-publication checks above.

Public source contains wrappers, UI, maps' drawing facts, schemas and tests. Private inherited receiver code, taught coordinates/profiles, credentials, model/artwork bytes and operational evidence are installed separately. The web process, camera helper, commissioning API and receiver host have separate owners/lifecycles. [Deployment](../deploy/README.md) · [Robot deployment](../deploy/ROBOT_CONTROL.md)

## Read the current operation before the history

1. [Robot operations](ROBOT_OPERATIONS.md): new mission, Stop/HOLD, empty return, reset and explicit continuation.
2. [Known limitations](KNOWN_LIMITATIONS.md): Native idle timeouts, different clocks, visibility and qualification limits.
3. [Single signal departure](SINGLE_SIGNAL_DEPARTURE.md), [C26](C26_DELIVERY_ENDPOINT.md) and [C review matrix](C_INTERMEDIATE_PROGRESS_REVIEW.md).
4. [START reference](SESSION_START_REFERENCE.md), [C11 boundary](C11_BOUNDARY_RECOVERY.md) and [review continuation](EXPLICIT_REVIEW_CONTINUATION.md).
5. [Evidence index](evidence/README.md): immutable dated trials and their successor guides.

Historical FAIL/UNKNOWN, incomplete checkpoints and failed calibration remain historical facts. A later taught-route arrival does not retroactively make a rejected registration pass.
