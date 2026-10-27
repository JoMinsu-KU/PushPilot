<div align="center">

# Build roadmap

**Complete the software loop before claiming the physical mission.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Mission](MISSION.md) · [Meta intelligence](META_INTELLIGENCE.md)

</div>

---

Checkboxes describe implementation scope. Automated simulation tests, real provider calls, visual verification, deployment, and physical qualification are separate evidence categories.

## 0 · Repository foundation

- [x] Establish a self-contained application workspace and component boundaries.
- [x] Provide source checks, offline tests, source-release packaging and integrity verification.
- [x] Document product direction, mission policy and evidence boundaries.
- [x] Connect the chosen GitHub repository using the owner's configured Git identity.
- [x] Select and lock React/Vite and Python FastAPI/Uvicorn dependencies.

**Evidence:** reviewed repository history and repeatable source/tooling checks. A valid source archive proves packaging integrity, not deployment or application behavior.

## 1 · Map-independent mission core

- [x] Implement the workspace DTO and validated revisioned API requests.
- [x] Implement SQLite supervision, source-labelled events and graph-derived abstract action simulation.
- [x] Bind temporary plans to map/version/geometry hash and scope fresh GREEN/stop evidence to each junction.
- [x] Derive drawing-only route segments and illustrative stop lines from the selected map, binding simulated motion steps to display segments.
- [x] Require current-plan approval, per-action demo review and mandatory stopping.
- [x] Exercise RED/UNKNOWN waiting and fresh-GREEN automatic admission.
- [x] Implement uncertainty, new review bindings, faults and non-executing restart recovery.
- [x] Reject stale revisions and changed-payload request-ID reuse; retain original command receipts.
- [x] Reject goal replacement during active simulation, including signal/review waits.
- [x] Define temporary map/route and recorded-scene DTOs with validated API inputs.
- [x] Bind operator-selected recorded before/after images to a mission/action/review/map context.
- [x] Add native-frame planning/action/signal request and evidence contracts with durable idempotent operation reservations.
- [x] Bind original server-selected BEFORE/AFTER frames to simulated action/stop receipts and reject late or superseded results.
- [x] Implement one-action review orchestration and finite stopped-signal observation cycles without an infinite runner.
- [x] Define finite voice upload/candidate/workspace binding and explicit original-versus-confirmed goal text.
- [ ] Complete browser capture/transcript-editing contracts and independently qualified physical observations/receipts.

**Evidence:** offline tests cover nominal/failure transitions with isolated state and injected providers. Action/stop receipts remain simulated; manual colors/verdicts, original live/recorded images and actual model results retain distinct sources. Live-backed plans reject manual/recorded bypasses. Independent scene inspection cannot advance a mission. Actual calls and completed runs keep their exact input/version scope in [verification](VERIFICATION.md).

## 2 · Operator workspace

- [x] Implement the initial English React/TypeScript workspace; its navy/cyan appearance is retained in historical screenshots.
- [x] Complete visual verification of the industrial light-dashboard restyle in [Design system](DESIGN_SYSTEM.md).
- [x] Connect typed goal submission, plan review and explicit approval to backend state.
- [x] Present current simulation state, next pending check and source-labelled evidence.
- [x] Provide explicit simulated signal and demo-review controls.
- [x] Display temporary drawing routes and separate recorded-frame upload, marker-lock overlay and scene-inspection controls.
- [x] Distinguish completed/current/remaining route portions and junction stop/signal/review context from authoritative simulation state.
- [x] Read English names and destination choices from map metadata, retaining planned-only display for older plans without segment bindings.
- [x] Record desktop/tablet/mobile layout and SVG arrow checks in [verification](VERIFICATION.md).
- [ ] Complete the full keyboard and contrast accessibility review.
- [x] Provide the backend finite-upload transcription service and explicit confirmed-transcript goal binding.
- [ ] Connect browser push-to-talk/PCM encoding, editable transcript confirmation, cancellation and typed fallback on the actual tablet origin.
- [x] Implement recorded-image upload and explicit MUSE scene inspection without mission advancement.
- [x] Add operator-selected before/after recorded-image review tied to the pending simulated action.
- [x] Add an opt-in native live camera preview with separate Live/Recorded sources, RAM frames, age labels and fixed display-registration behavior.
- [x] Explicitly lock the installed live view and record fixed-transform observations and limits in [verification](VERIFICATION.md); this is display registration, not robot calibration.
- [ ] Complete dedicated live action/signal operation controls and readable selected-frame evidence throughout the tablet flow.
- [ ] Integrate live capture with receipt-bound fresh physical action evidence, independent of preview.

**Evidence:** the UI must reflect backend snapshots and events, including wait, rejection, uncertainty, and recovery. [Route display](ROUTE_DISPLAY.md) separates drawing geometry and simulated progress from measured car pose. No scripted success animation substitutes for a state transition. The wearable panel remains a concept. The temporary spatial map is drawing data and a locked camera overlay is test-only; unavailable capability labels stay explicit. Actual checks and limits belong in [verification](VERIFICATION.md).

## 3 · Genuine Meta interaction

- [x] Verify Meta authentication and a bounded `muse-spark-1.3` text completion.
- [x] Implement backend goal interpretation using a strict response schema and fixed Meta origin.
- [x] Verify a real application goal request producing PLAN_READY with approval still pending.
- [x] Test sanitized provider failures, timeout, malformed output and no demo fallback.
- [x] Implement original-native-image plus replaceable-graph MUSE route selection with exact directed-path and departure/turn/via/avoid validation.
- [x] Add versioned live route/action/signal prompts and strict local result validation with original-frame hash preservation.
- [ ] Extract/version the inline goal instruction and response schema in a traceable prompt catalog.
- [x] Implement the Meta Voice Transcribe adapter and bounded supported-WAV validation/canonicalization without resampling.
- [x] Bind transcript candidates to current workspace/map state, expire/supersede them and preserve original versus explicitly confirmed text in accepted goal evidence.
- [ ] Verify actual ASR account access and Korean/English recognition on recorded and microphone input.
- [ ] Complete browser transcript editing/revision UI and its device end-to-end acceptance checks.
- [x] Implement a strict-schema, frame/hash-bound recorded-scene MUSE adapter with late-result rejection.
- [x] Record the actual-provider shop/car/signal scene case independently of simulation.
- [x] Connect strict-schema MUSE recorded-action judgment to the supervisor with late/superseded-result rejection.
- [x] Implement server-bound live BEFORE/AFTER review after simulated action receipts, including reobservation without repeated action.
- [x] Implement new post-stop native-frame MUSE signal judgment, approach-target projection, deterministic acceptance and finite RED/UNKNOWN requery.
- [x] Retain deliberate native originals, request bindings, prompt/schema versions, validated results and elapsed timing in the private ledger/journal.
- [ ] Add a complete unified provider-envelope/export policy and retain usage fields where the provider reports them; missing usage remains unknown.
- [ ] Evaluate the new live action/signal services with actual provider responses and real-car/paper-signal images; software/mock results do not establish accuracy.
- [ ] Evaluate held-out real-car success, no-progress and occlusion cases with independent labels.

**Evidence:** [Meta API records](META_API_CHECK.md) record actual requests with their exact input, prompt version and outcome, including any clarification/withheld plan. [Live intelligence](LIVE_INTELLIGENCE.md) documents the new route/review/signal code; [Action reviews](ACTION_REVIEWS.md) retains the separate recorded-pair path. Preview polling does not trigger inference. Real-car action/signal accuracy, actual voice access, physical receipt qualification and robot execution remain separate gates. Completing a backend checkbox does not establish those outcomes.

## 4 · Evaluation and isolated GX10 delivery

- [x] Publish reproducible local build, startup and hardware-free simulation instructions.
- [x] Inspect GX10 read-only and select Python 3.12+ serving compiled frontend assets.
- [x] Provide an explicit launcher and generic isolated-service example.
- [x] Verify ARM64 dependency installation and compiled frontend/API startup in a dedicated GX10 release.
- [ ] Exercise the complete live-backed mission on GX10 with reviewed installed-map signal targets.
- [ ] Provision reviewed target-device HTTPS before claiming microphone support.
- [x] Transfer reviewed source and compiled frontend assets from the same commit.
- [x] Verify separate fresh shared state, health and deliberate application activation.
- [ ] Exercise rollback without history loss and startup after boot without login.
- [ ] Freeze independently labelled held-out image inputs before prompt tuning.
- [ ] Evaluate matched actions with different outcomes and compare a recorded/shadow baseline.
- [ ] Complete demonstration records with supported source and execution claims.

**Evidence:** GX10 inspection found ARM64 Ubuntu 24.04.4 and Python 3.12.3, with no Node/npm on the inspected PATH. The October 28 isolated application release installed the locked ARM64 dependencies and matching source/frontend assets, passed offline checks and started with fresh unapproved state. It connects directly to the independent native camera helper; an SSH forward provides local browser access. A bounded text-only MUSE connectivity smoke passed; no image, action or signal inference was part of deployment. The enabled user service requires a user session; boot without login, rollback and trusted tablet HTTPS remain unverified. See [deployment verification](VERIFICATION.md#gx10-application-deployment-october-28). Existing POC services remain outside the release boundary.

## 5 · Temporary map and recorded-image inputs

- [x] Build a replaceable sanitized Little Town drawing/graph adapter, excluding source artwork and historical robot assumptions.
- [x] Derive east-facing PIZZA routes to BAKERY, BOOKSTORE, and SCHOOL with independent stop/signal gates at every junction.
- [x] Select a reviewed map through `--map-path` or `PUSHPILOT_MAP_PATH`, with optional cardinal start heading and map-owned labels/aliases.
- [x] Supply MUSE goal interpretation with the selected map's allowed destination vocabulary; keep deterministic route construction separate.
- [x] Supply live planning with the selected symbolic directed graph and declared-start semantics; compile the selected route locally into existing AR geometry.
- [x] Validate a proposed map through a bounded read-only API/CLI, including reachability and optional approach-specific signal targets, without installing it.
- [x] Require matching map/version/hash for route display and new plan/registration after map replacement.
- [x] Accept bounded private JPEG/PNG frames with hashes, timestamps and map identity.
- [x] Detect print markers and require an explicit four-marker lock for a test-only board-to-image overlay.
- [x] Retain the fixed reference under partial occlusion; withhold changed or unverifiable views without automatic refitting.
- [x] Bind scene inspection to its immutable frame and reject superseded results.
- [ ] Evaluate real car visibility, separate paper-signal recognition, glare, occlusion, and uncertainty using held-out input.
- [x] Record the initial actual provider scene outcome without implying a live camera or robot run.
- [x] Implement native preview transport and an independent memory-only live display lock, without saving preview frames into recorded evidence.
- [x] Record installed static-view marker coverage, backend frame availability and reported receive ages in [verification](VERIFICATION.md).
- [ ] Measure browser presentation rate, exposure-to-display latency and moving/occluded scenes; the short backend sample is not an end-to-end motion benchmark.
- [x] Support deliberate departure, first-turn, ordered-via and avoid constraints on a model-selected alternative directed path.
- [ ] Configure reviewed active-paper signal targets on the installed map; the current temporary definition intentionally contains none.
- [ ] Evaluate route interpretation across held-out user phrasings and assess obstacle-aware rerouting if required by the final scenario.

## Next demonstration gate · Same action, different evidence

The next evaluation should show one expected action with independently labelled success, no progress and occlusion. Preserve the actual input, source, response and supervisor consequence for each case. Synthetic fixtures and injected responses are useful pipeline checks; publish them separately from real-car imagery. Measure the rate of incorrect continuation and reobservation, response latency and reported usage once a defined sample exists. Do not infer task accuracy from the software test count.

Follow [Temporary map](TEMPORARY_MAP.md), [Route display](ROUTE_DISPLAY.md) and [Test inputs](TEST_INPUTS.md). A recorded 1920×1080 frame supported four-marker fitting at 1.4333 px residual; this is fit error, not absolute millimeter accuracy. Temporary drawing routes, simulated progress and recorded/live display overlays are authorized test scope. Production geometry, robot/BASE registration, qualified stop lines, measured car pose and physical turning remain unresolved. Illustrative stop-line graphics do not satisfy those gates.

## 6 · Final installation and physical qualification

**External prerequisites:** a final installed map released for map-dependent work, the actual wheel-less car, and the pushing tool.

- [ ] Establish final road/signal semantics and installed observation regions.
- [ ] Measure and independently validate camera/board/robot registration.
- [ ] Qualify straight pushing, contact changes and required turns.
- [ ] Implement a robot adapter with measured completion and ambiguous-result handling.
- [ ] Validate stop-line placement, actual stopping and green admission under the qualified policy.
- [ ] Test occlusion/reobservation and distinguish tool completion from vehicle completion.
- [ ] Record physical attempts, outcomes and limitations before making demonstration claims.

**Evidence:** new measured physical runs on the final setup. Earlier POC success, software tests, and simulated city missions do not satisfy this gate.

## Later expansion

Extra destinations, streaming transcription, continuous listening, speech output, supplementary segmentation, real glasses, additional models and custom policy training follow the core loop. Bounded push-to-talk remains initial-demo scope: its finite-upload backend is implemented, while browser capture/confirmation and actual voice verification remain pending. See [Voice input](VOICE_INPUT.md) and [Voice backend](VOICE_BACKEND.md).

The glasses companion remains a concept until its actual capture/display path is integrated and verified. Registered spatial AR remains dependent on the installed map and calibration.

## Status vocabulary

| Status | Meaning |
|---|---|
| `planned` | Intended scope; implementation absent |
| `design_only` | A documented interface or behavior, without runtime proof |
| `implemented_unverified` | Code exists but supporting checks are incomplete |
| `software_verified` | Defined software checks pass within their stated scope |
| `physically_demonstrated` | Physical execution is supported by measured evidence |

Use these distinctions in [contributions](../CONTRIBUTIONS.md), release notes, and demonstration material. Update evidence and limitations with the feature.

---

[← Meta intelligence](META_INTELLIGENCE.md) · [Start developing →](DEVELOPMENT.md)
