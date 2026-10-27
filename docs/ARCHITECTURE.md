<div align="center">

# Architecture

**A visible reasoning loop with explicit execution gates.**

[Documentation](README.md) · [Mission](MISSION.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Roadmap](ROADMAP.md)

[Service composition](SERVICE_COMPOSITION.md) · [Live camera preview](LIVE_CAMERA.md) · [Voice input](VOICE_INPUT.md)

</div>

---

**Status: temporary-map simulation, recorded-image review and an opt-in live camera preview are implemented.** React/TypeScript and one FastAPI/Uvicorn backend combine a replaceable map graph, SQLite mission state, demo verdicts, Meta goal interpretation and action-bound recorded-image review. Independent scene inspection remains a separate path without mission authority. The live preview has a separate memory-only frame cache and explicitly locked display registration; it cannot mutate a mission or supply MUSE/action evidence. Recorded action reviews can affect simulation through the supervisor; they establish neither fresh physical action evidence nor robot capability. Voice, robot/BASE registration and physical control remain unavailable. Only a separately authorized camera helper runs on GX10; the application is not deployed there.

## System shape

[![Proposed voice-enabled architecture: the operator workspace exchanges bounded audio and draft transcripts with a backend voice adapter; the operator reviews text and approves a MUSE-interpreted plan; the mission supervisor retains deterministic admission authority, actions use a simulator first and observations feed evidence and replay.](assets/architecture-overview-voice.png)](assets/architecture-overview-voice.png)

*Design illustration created before the first runtime slice. Its voice/image flows and footer describe that earlier design stage; current implementation status is stated above and in the component text below. Select the image for the full-size view.*

The **tablet workspace** presents the goal, current state and approval. The **mission supervisor** combines source-labelled observations with goal interpretation and fresh-image MUSE review, then applies deterministic admission checks. Accepted bounded actions go to the abstract simulator first; a qualified robot adapter is a later integration. Action results feed new observations, while the evidence store connects the inputs, reviews and transitions back to the operator's timeline.

The planned **voice adapter** belongs inside the same backend. Its planned first implementation will accept a finite push-to-talk recording and call Meta's file transcription endpoint. It returns an editable draft transcript to the workspace. Only after the operator submits the text does it join the shared typed-goal interpretation path; the resulting plan still requires explicit tablet approval. The API key stays on the backend. [Voice input](VOICE_INPUT.md) defines cancellation, language and revision handling; [service composition](SERVICE_COMPOSITION.md) defines module and deployment ownership.

There are two complementary decisions: the model explains what the scene supports, including the intended at-stop signal-color judgment; the supervisor validates whether the current response and required execution conditions permit a state transition. An image answer cannot manufacture frame freshness, verified stopping or a hardware receipt. A second local color classifier is not required by the user-confirmed scenario.

## Responsibilities

| Component | Owns | Does not establish by itself |
|---|---|---|
| **Tablet workspace** | Goal entry, review, approval, scene evidence and replay | Permission to bypass backend gates |
| **Mission supervisor** | State transitions, action sequencing, waits, faults and admission | Physical motion capability without a qualified adapter |
| **Meta provider adapter** | Actual request/result handling, versions, timeouts and structured output validation | Authoritative robot coordinates or immediate stopping |
| **Voice adapter** | Bounded audio intake, server-side transcription, editable draft text and capture/session binding | Mission approval, raw robot commands or physical stopping |
| **Observation adapters** | Timestamped images, signal-target identity and capture provenance for MUSE review | Metric accuracy without calibration and evaluation |
| **Live preview adapter** | Ephemeral native JPEG frames, source/age metadata and an explicitly locked display transform | Persisted evidence, model review, local signal verification or mission authority |
| **Action adapter** | One bounded action and its corresponding result | Successful vehicle displacement merely because a tool reached its target |
| **Evidence store** | Immutable inputs/results and their causal connection to decisions | A physical claim unsupported by the recorded sources |

The action adapter is a hardware-free simulator using PUSH, STOP, CROSS, and VERIFY. `backend/maps.py` derives an east-facing route from the sanitized temporary drawing graph; `backend/core.py` expands it into per-junction actions, serializes transitions and records SQLite events. `backend/app.py` validates requests, `backend/meta.py` interprets goals, and `backend/scene.py` handles private uploaded frames, marker detection, locked board-to-image overlays and independent MUSE scene inspection. The [action-review adapter](ACTION_REVIEWS.md) adds immutable before/after frame binding, strict provider output and supervisor application. `backend/live_camera.py` polls an explicitly configured loopback preview service without opening a device or touching those recorded stores. [`workspace.ts`](../contracts/workspace.ts), [`scene.ts`](../contracts/scene.ts) and [`live-camera.ts`](../contracts/live-camera.ts) describe frontend DTOs. These source interfaces are not a complete standalone JSON Schema catalog.

### Live preview is a separate display path

The authorized development arrangement is a standalone `tools/camera_preview.py` helper on GX10, bound to `127.0.0.1:8084`, an SSH forward to client loopback port `8895`, and the Windows application on port `8893` started with `--live-camera-url http://127.0.0.1:8895`. These are development ports, not a GX10 application deployment. The helper requests native 1920 × 1080 MJPEG at 30 fps and copies JPEG bytes without re-encoding; requested capture rate is not measured preview throughput. Default application startup does not start a camera, create a tunnel or restart any prior service.

The application retains at most eight preview frames in RAM. It records camera identity, epoch, sequence, frame ID, dimensions, SHA-256 and host-receive timestamps in the transient snapshot; it does not write raw preview frames to the scene store or SQLite evidence. Unique image responses permit a short private browser cache. Host receive/dequeue time is not sensor exposure time. Preview age includes reported upstream age, request time and elapsed client time; a repeated sequence does not refresh age, and a frame becomes stale after 1,500 ms.

A live display lock requires all four consistent print markers in a fresh selected frame and the current frame. Camera identity/epoch, resolution or map identity changes withhold the transform and require an explicit new lock. Temporary marker occlusion retains the fixed homography as `locked_occluded`, with current alignment unverified; it does not refit the board. A spatially distributed, coherent shift observed in at least two markers over three newly accepted frames latches `view_changed` and withholds the overlay until manual registration. These are display checks, not a physical calibration result or a measured accuracy claim.

`camera_preview_connected` reports the dedicated preview connection separately from workspace `camera` and `robot` capabilities, which remain false for qualified control observations. The preview never feeds scene-only MUSE inspection, recorded-pair action review, traffic-signal admission or robot state. See [Live camera preview](LIVE_CAMERA.md) for the opt-in interface and limits.

Voice is planned initial-demo scope. Start with browser capture and one modular backend containing the voice adapter, MUSE adapter, mission supervisor, simulator and evidence modules. A separate speech server is not required by this design. Realtime transcription and speech playback are later options. No voice provider request or microphone path has been verified. Actual Muse Spark text and image requests are recorded separately in [Meta API evidence](META_API_CHECK.md).

## Execution gates

The simulator requires current-plan approval, exact review binding and its simulated stop/signal gates. The operator may inject a labelled demo verdict or submit a recorded before/after pair to MUSE for the pending action. A validated actual result passes through the same supervisor state rules and cannot replace its signal or action receipt. The full future physical supervisor must check the applicable conditions together:

1. The operator has approved the current mission interpretation.
2. The preceding bounded action has a valid completion result and accepted review.
3. Required observations belong to the current action/session and meet freshness requirements.
4. MUSE supplies the visual judgment; local checks validate stop receipts, provenance, freshness, response schema and current request/action bindings.
5. At an intersection, stopping is verified and a valid current MUSE GREEN judgment for the applicable approach permits admission.
6. The requested action belongs to the capabilities qualified for the selected action adapter.

Exact tolerances, freshness windows and physical action sizes are configuration and qualification work. They are not established by illustrative simulation settings.

### MUSE judges the signal while the robot is stopped

The confirmed scenario is mandatory stop, verified stopping, a new image sent to MUSE, then wait or proceed according to MUSE's signal-color judgment. RED keeps the robot stopped and starts another observation cycle. GREEN can admit the current crossing after local binding and freshness checks. UNKNOWN, an obscured target, timeout, malformed output or a superseded request keeps the robot stopped. MUSE is the visual color judge; local supervision does not require another color opinion.

The request identifies the current junction, approach direction and intended signal region, with the original frame and capture provenance. The supervisor checks the stop receipt and current plan/step/request before accepting the result. It holds the robot while MUSE is pending. This dedicated stopped-live signal-review path is planned, not supplied by the existing independent recorded-scene endpoint or live preview. See [MUSE signal gate](MUSE_SIGNAL_GATE.md).

Every configured approach requires a stop even on green. Once the qualified crossing has been admitted, it completes under its defined policy before the next approach. **Interrupting a moving robot when the paper changes color is outside the current scenario.** A web `HOLD` or server shutdown must never be presented as a physical emergency stop.

## Evidence that explains a decision

[![Proposed evidence chain: an accepted goal defines an expected bounded action; its result and fresh observations support local checks and MUSE review; the supervisor records a decision and continues, waits, reobserves or faults.](assets/evidence-loop.png)](assets/evidence-loop.png)

*Planned evidence flow. Every decision must retain its input sources and transition cause.*

The intended sequence is:

1. Record the operator goal and accepted interpretation.
2. Define the expected bounded action and its expected outcome.
3. Collect the action result and a fresh observation bundle.
4. Run local checks and retain the actual MUSE response and uncertainty.
5. Record the supervisor decision with its transition cause.
6. Continue with the next action, wait, request another observation or enter a fault state.

The current SQLite store retains workspace/plan/step/review identities, map/version/geometry-hash route binding, junction-scoped signals, ordered source-labelled events, request digests, and original idempotent command receipts. Reusing a request ID with different content or submitting a stale revision is rejected. Reset retains event history. The Meta goal result is represented by its interpreted summary and source; the current store does not preserve a full raw provider receipt with usage, timing, or a prompt version.

The recorded-scene store separately persists original frame bytes, SHA-256, source, received time, optional operator-provided capture time, map identity, registration reference and validated inspection records. A late inspection cannot attach to a newer frame/revision. The action-review path binds its selected immutable pair to the pending mission/action/review and map, validates the result, and rechecks the binding before application. [Action reviews](ACTION_REVIEWS.md) lists the implemented receipt fields. Raw media remains private runtime data. The live preview cache is outside this evidence chain. Live action-receipt-bound capture, qualified local vehicle measurements, crop lineage and a complete unified provider receipt/export policy remain later work.

Robot state, image, vehicle pose, signal and model response retain **independent source labels**. Unknown values remain unknown. Unavailable provider cost is not reported as zero. Credentials must never appear in evidence, prompts, logs or release archives.

Raw payloads and provenance belong in expandable evidence views. The main workspace shows the information needed to understand the decision: expected versus observed outcome, concise grounded explanation and the next pending check.

## Failures and restart

| Condition | Intended behavior |
|---|---|
| Red, stale or unclear signal at an approach | Remain stopped; observe again |
| Obscured vehicle or insufficient image evidence | Request another observation; do not assume completion |
| Model timeout, malformed response or missing result | Preserve evidence and wait/reobserve according to bounded policy |
| Model and local check disagree | Block continuation and expose the disagreement |
| Action result is missing or ambiguous | Enter review/fault; do not automatically resend the action |
| Application restarts | Reconstruct history in a non-executing review state |

Old pending actions, old green observations and earlier crossing admission must not regain execution authority after restart. A code rollback changes the release, not the evidence history or pending command state.

## Map and physical integration boundary

The user authorized a replaceable temporary Little Town adapter. Sanitized drawing/graph/marker facts are bundled in `backend/data/little-town-temporary.json`; original artwork, historical robot transforms, and grasp assumptions are excluded. The temporary simulator supports BAKERY, BOOKSTORE, and SCHOOL from east-facing PIZZA. Each traversed junction gets its own mandatory stop, demo review, and fresh simulated GREEN. Drawing distances are not robot travel measurements.

Recorded-image registration is board-to-image only. Four consistent markers are required for an explicit lock. Later partial visibility retains the reference without refitting; disagreement, changed view, or no visible reference markers withholds the recorded overlay. The separate live display path retains its fixed reference through temporary occlusion with an explicit unverified-alignment status, as described above. A recorded 1920×1080 frame supported four-marker fitting with 1.4333 px residual; this is historical recorded-image fit error, not live registration success or independent absolute accuracy in millimeters. See [Temporary map](TEMPORARY_MAP.md), [Test inputs](TEST_INPUTS.md), and [verification](VERIFICATION.md).

Production integration must establish the final road graph, installed camera/board/robot registration, stop and exit lines, signal regions, vehicle/tool geometry, pushing behavior and contact turning. Replacing the configured temporary map invalidates mismatched plans and scene references; it does not recalibrate the robot. A fixed gripped-car transform is not a model of surface pushing. Reusing a successful robot endpoint does not prove where an ungripped vehicle ended up.

## Delivery boundary

Development and testing take place in this repository. A clean committed source tree can be packaged with a commit/hash manifest using the release tools. That ZIP excludes ignored compiled frontend assets. The selected GX10 delivery uses a local frontend build and one Python runtime serving the bundle, with isolated release directories and shared SQLite state. Read-only inspection found ARM64 Ubuntu and Python 3.12.3, with no Node/npm on the inspected PATH; application installation and activation have not occurred. The independently started camera helper is a separate preview process and does not change that deployment status.

See [development](DEVELOPMENT.md) for actual commands and [deployment](../deploy/README.md) for the proposed host separation. Packaging does not transfer files, start services or connect a robot.

---

[← Documentation](README.md) · [Next: mission behavior →](MISSION.md)
