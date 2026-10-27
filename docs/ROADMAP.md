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
- [x] Require current-plan approval, per-action demo review and mandatory stopping.
- [x] Exercise RED/UNKNOWN waiting and fresh-GREEN automatic admission.
- [x] Implement uncertainty, new review bindings, faults and non-executing restart recovery.
- [x] Reject stale revisions and changed-payload request-ID reuse; retain original command receipts.
- [x] Reject goal replacement during active simulation, including signal/review waits.
- [x] Define temporary map/route and recorded-scene DTOs with validated API inputs.
- [x] Bind operator-selected recorded before/after images to a mission/action/review/map context.
- [ ] Define complete voice capture/transcript and fresh physical observation contracts.

**Evidence:** offline tests cover nominal and failure transitions with isolated state and injected providers. Mission actions/signals remain simulated. Reviews distinguish operator-injected demo verdicts from actual MUSE recorded-pair results. Independent recorded-scene inspection cannot advance a mission. Completed runs and their sources belong in [verification](VERIFICATION.md).

## 2 · Operator workspace

- [x] Implement the initial English React/TypeScript workspace; its navy/cyan appearance is retained in historical screenshots.
- [x] Complete visual verification of the industrial light-dashboard restyle in [Design system](DESIGN_SYSTEM.md).
- [x] Connect typed goal submission, plan review and explicit approval to backend state.
- [x] Present current simulation state, next pending check and source-labelled evidence.
- [x] Provide explicit simulated signal and demo-review controls.
- [x] Display temporary drawing routes and separate recorded-frame upload, marker-lock overlay and scene-inspection controls.
- [x] Record desktop/tablet/mobile layout and SVG arrow checks in [verification](VERIFICATION.md).
- [ ] Complete the full keyboard and contrast accessibility review.
- [ ] Add bounded push-to-talk, backend batch transcription and editable transcript confirmation.
- [x] Implement recorded-image upload and explicit MUSE scene inspection without mission advancement.
- [x] Add operator-selected before/after recorded-image review tied to the pending simulated action.
- [x] Add an opt-in native live camera preview with separate Live/Recorded sources, RAM frames, age labels and fixed display-registration behavior.
- [x] Explicitly lock the installed live view and record fixed-transform observations and limits in [verification](VERIFICATION.md); this is display registration, not robot calibration.
- [ ] Integrate live capture with receipt-bound fresh physical action evidence, independent of preview.

**Evidence:** the UI must reflect backend snapshots and events, including wait, rejection, uncertainty, and recovery. No scripted success animation substitutes for a state transition. The wearable panel remains a concept. The temporary spatial map is drawing data and a locked recorded-image overlay is test-only; unavailable capability labels stay explicit.

## 3 · Genuine Meta interaction

- [x] Verify Meta authentication and a bounded `muse-spark-1.3` text completion.
- [x] Implement backend goal interpretation using a strict response schema and fixed Meta origin.
- [x] Verify a real application goal request producing PLAN_READY with approval still pending.
- [x] Test sanitized provider failures, timeout, malformed output and no demo fallback.
- [ ] Extract/version the inline goal instruction and response schema in a traceable prompt catalog.
- [ ] Integrate Meta Voice Transcribe with bounded backend audio normalization.
- [ ] Preserve original/edited transcript revisions and reject cancelled or stale results.
- [x] Implement a strict-schema, frame/hash-bound recorded-scene MUSE adapter with late-result rejection.
- [x] Record the actual-provider shop/car/signal scene case independently of simulation.
- [x] Connect strict-schema MUSE recorded-action judgment to the supervisor with late/superseded-result rejection.
- [ ] Persist complete provider receipts, including versions, exact inputs/results, timing and reported usage.
- [ ] Evaluate held-out real-car success, no-progress and occlusion cases with independent labels.

**Evidence:** [Meta API records](META_API_CHECK.md) establish the stated real text and scene calls. [Action reviews](ACTION_REVIEWS.md) describes the recorded-pair integration; [verification](VERIFICATION.md) identifies actual versus injected responses. [Live preview](LIVE_CAMERA.md) is a separate source and does not automatically supply model input. Real-car accuracy, voice, trusted action-bound live capture and physical execution remain separate gates.

## 4 · Evaluation and isolated GX10 delivery

- [x] Publish reproducible local build, startup and hardware-free simulation instructions.
- [x] Inspect GX10 read-only and select Python 3.12+ serving compiled frontend assets.
- [x] Provide an explicit launcher and generic isolated-service example.
- [ ] Verify dependency installation and full application behavior in a dedicated GX10 release.
- [ ] Provision reviewed target-device HTTPS before claiming microphone support.
- [ ] Transfer reviewed source and compiled frontend assets from the same commit.
- [ ] Verify separate shared state, health, deliberate activation, and rollback without history loss.
- [ ] Freeze independently labelled held-out image inputs before prompt tuning.
- [ ] Evaluate matched actions with different outcomes and compare a recorded/shadow baseline.
- [ ] Complete demonstration records with supported source and execution claims.

**Evidence:** GX10 inspection found ARM64 Ubuntu 24.04.4 and Python 3.12.3, with no Node/npm on the inspected PATH. A separately authorized native camera helper runs there with loopback SSH transport; the full application remains Windows-hosted and has not been installed or activated on GX10. Existing POC services remain outside the release boundary.

## 5 · Temporary map and recorded-image inputs

- [x] Build a replaceable sanitized Little Town drawing/graph adapter, excluding source artwork and historical robot assumptions.
- [x] Derive east-facing PIZZA routes to BAKERY, BOOKSTORE, and SCHOOL with independent stop/signal gates at every junction.
- [x] Accept bounded private JPEG/PNG frames with hashes, timestamps and map identity.
- [x] Detect print markers and require an explicit four-marker lock for a test-only board-to-image overlay.
- [x] Retain the fixed reference under partial occlusion; withhold changed or unverifiable views without automatic refitting.
- [x] Bind scene inspection to its immutable frame and reject superseded results.
- [ ] Evaluate real car visibility, separate paper-signal recognition, glare, occlusion, and uncertainty using held-out input.
- [x] Record the initial actual provider scene outcome without implying a live camera or robot run.
- [x] Implement native preview transport and an independent memory-only live display lock, without saving preview frames into recorded evidence.
- [x] Record installed static-view marker coverage, backend frame availability and reported receive ages in [verification](VERIFICATION.md).
- [ ] Measure browser presentation rate, exposure-to-display latency and moving/occluded scenes; the short backend sample is not an end-to-end motion benchmark.

## Next demonstration gate · Same action, different evidence

The next evaluation should show one expected action with independently labelled success, no progress and occlusion. Preserve the actual input, source, response and supervisor consequence for each case. Synthetic fixtures and injected responses are useful pipeline checks; publish them separately from real-car imagery. Measure the rate of incorrect continuation and reobservation, response latency and reported usage once a defined sample exists. Do not infer task accuracy from the software test count.

Follow [Temporary map](TEMPORARY_MAP.md) and [Test inputs](TEST_INPUTS.md). A recorded 1920×1080 frame supported four-marker fitting at 1.4333 px residual; this is fit error, not absolute millimeter accuracy. Temporary drawing routes and recorded overlays are authorized test scope. Production geometry, robot/BASE registration, qualified stop lines, and physical turning remain unresolved.

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

Extra destinations, streaming transcription, continuous listening, speech output, supplementary segmentation, real glasses, additional models, and custom policy training follow the complete core loop. Bounded push-to-talk remains planned initial-demo scope; see [Voice input](VOICE_INPUT.md).

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
