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
- [x] Implement SQLite supervision, source-labelled events and abstract action simulation.
- [x] Require current-plan approval, per-action demo review and mandatory stopping.
- [x] Exercise RED/UNKNOWN waiting and fresh-GREEN automatic admission.
- [x] Implement uncertainty, new review bindings, faults and non-executing restart recovery.
- [x] Reject stale revisions and changed-payload request-ID reuse; retain original command receipts.
- [x] Reject goal replacement during active simulation, including signal/review waits.
- [ ] Define and validate full voice capture/transcript and image observation bundle contracts.

**Evidence:** offline tests cover nominal and failure transitions with isolated state and injected providers. Every action, signal, and review in this first slice is simulated or manually demo-sourced.

## 2 · Operator workspace

- [x] Implement an English navy/cyan React/TypeScript workspace.
- [x] Connect typed goal submission, plan review and explicit approval to backend state.
- [x] Present current simulation state, next pending check and source-labelled evidence.
- [x] Provide explicit simulated signal and demo-review controls.
- [x] Record desktop/tablet/mobile layout and SVG arrow checks in [verification](VERIFICATION.md).
- [ ] Complete the full keyboard and contrast accessibility review.
- [ ] Add bounded push-to-talk, backend batch transcription and editable transcript confirmation.
- [ ] Add actual camera/image evidence and actual MUSE expected-versus-observed judgment.

**Evidence:** the UI must reflect backend snapshots and events, including wait, rejection, uncertainty, and recovery. No scripted success animation substitutes for a state transition. The wearable panel and scene illustration remain concepts, and unavailable capability labels remain explicit.

## 3 · Genuine Meta interaction

- [x] Verify Meta authentication and a bounded `muse-spark-1.3` text completion.
- [x] Implement backend goal interpretation using a strict response schema and fixed Meta origin.
- [x] Verify a real application goal request producing PLAN_READY with approval still pending.
- [x] Test sanitized provider failures, timeout, malformed output and no demo fallback.
- [ ] Extract/version the inline goal instruction and response schema in a traceable prompt catalog.
- [ ] Integrate Meta Voice Transcribe with bounded backend audio normalization.
- [ ] Preserve original/edited transcript revisions and reject cancelled or stale results.
- [ ] Send explicitly sourced recorded/test images to actual MUSE review calls.
- [ ] Persist complete provider receipts, including versions, exact inputs/results, timing and reported usage.
- [ ] Evaluate actual image review changing continuation, reobservation, or rejection.

**Evidence:** [Meta connection and goal records](META_API_CHECK.md) establish the stated text paths. Voice, image review, scene judgment quality, and physical execution remain unverified.

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

**Evidence:** GX10 inspection found ARM64 Ubuntu 24.04.4 and Python 3.12.3, with no Node/npm on the inspected PATH. The application has not been installed or activated there. Existing POC services remain outside the release boundary.

## 5 · Temporary vision inputs

- [ ] Capture user-provided temporary printed-map scenes with explicit map/input identifiers.
- [ ] Test vehicle visibility, paper-signal recognition, glare, occlusion and uncertainty.
- [ ] Record the exact image source and model outcome without implying a live robot run.

Follow [Test inputs](TEST_INPUTS.md). Temporary prints permit input and model experiments while final geometry remains open. They do not release road-route, coordinate, signal-ROI, or AR-registration work.

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
