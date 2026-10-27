<div align="center">

# Build roadmap

**Complete the software loop before claiming the physical mission.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Mission](MISSION.md) · [Meta intelligence](META_INTELLIGENCE.md)

</div>

---

The roadmap separates work that can proceed now from work that depends on a final map, installed hardware and measured pushing behavior. Checkboxes describe repository status, not a competition submission or deployment commitment.

## 0 · Repository foundation

- [x] Establish a self-contained application workspace and component boundaries.
- [x] Provide equipment-free source checks and bootstrap tests.
- [x] Provide reviewed source-release packaging and integrity verification tools.
- [x] Document product direction, mission policy and evidence boundaries.
- [x] Create the truthful initial commit with the owner's configured Git identity.
- [x] Connect the chosen GitHub repository and review publication contents.

**Exit evidence:** reproducible bootstrap checks and a reviewed committed source tree. A valid release archive proves packaging integrity, not application functionality.

## 1 · Map-independent mission core

- [ ] Implement versioned mission, action, observation and event contracts.
- [ ] Implement the supervisor and abstract action simulator.
- [ ] Require approval, per-action review and mandatory stop-line stopping.
- [ ] Exercise red/unknown waiting and fresh-green admission.
- [ ] Implement uncertainty, reobservation, faults and restart into review.
- [ ] Record stable identifiers, source labels and transition causes from the first integration.

**Exit evidence:** meaningful automated scenarios cover the nominal loop and failure paths without a map, camera or robot. Simulated results remain labelled as simulated.

## 2 · Operator workspace

- [ ] Build the English navy/cyan tablet interface and scene placeholder.
- [ ] Connect goal interpretation, plan review and approval to actual backend state.
- [ ] Show expected/observed outcome, actual model decision and next pending check.
- [ ] Make red waiting, rejected review, uncertainty and faults visible.
- [ ] Add a source-aware replay timeline and expandable evidence.
- [ ] Verify keyboard access, readable contrast and tablet layouts.

**Exit evidence:** the interface follows backend events and visibly changes when an outcome is rejected or unclear. It does not rely on a scripted success animation.

## 3 · Genuine Meta interaction

- [ ] Verify the chosen provider model/API and lock the integration contract.
- [ ] Add versioned English goal/review prompts and validated structured responses.
- [ ] Send reviewed recorded/test images through actual provider calls.
- [ ] Persist request/result evidence, versions, latency and reported usage.
- [ ] Handle malformed output, stale imagery, timeout and disagreement without authorizing action.
- [ ] Show at least one actual model judgment changing continuation or reobservation.

**Exit evidence:** inspectable genuine provider requests and their resulting supervisor decisions. Recorded-image results are reported separately from physical execution.

## 4 · Evaluation and isolated delivery

- [ ] Freeze independently labelled held-out input bundles before prompt tuning.
- [ ] Evaluate matched actions with different outcomes and compare a recorded/shadow baseline.
- [ ] Publish a repeatable hardware-free review workflow in the repository.
- [ ] Inspect GX10 read-only and select explicit runtimes, dependency locks and service configuration.
- [ ] Deploy to a separate reviewed release directory and validate the nonphysical application.
- [ ] Prepare accurate contribution, asset-origin and demonstration records.

**Exit evidence:** reproducible software evaluation, a reviewed release manifest and a separate application health check. Existing POC services remain outside the new release boundary.

## 5 · Final installation and physical qualification

**Blocked by external prerequisites:** the final map must be available, installed and released for map-dependent work; the actual car and pushing tool must be available.

- [ ] Establish final road/signal semantics and installed observation regions.
- [ ] Measure and independently validate camera/board/robot registration.
- [ ] Qualify straight pushing, contact changes and both required turn senses.
- [ ] Implement the robot adapter with measured completion and ambiguous-result handling.
- [ ] Validate stop-line placement, actual stopping and green admission under the qualified policy.
- [ ] Test occlusion/reobservation and distinguish tool completion from vehicle completion.
- [ ] Record all physical attempts, outcomes and limitations before making demonstration claims.

**Exit evidence:** new measured physical runs on the final setup. Earlier POC success, current bootstrap tests and simulated city missions do not satisfy this gate.

## Optional expansion

Extra destinations, voice capture, supplementary segmentation, real glasses, additional models and custom policy training follow the complete core loop. Their value must justify the integration and evaluation cost.

The glasses companion remains a future concept until its actual capture/display capabilities are integrated and verified. Spatial AR remains dependent on the final map and registration.

## Status vocabulary

| Status | Meaning |
|---|---|
| `planned` | Intended scope; implementation absent |
| `design_only` | A documented interface or behavior, without runtime proof |
| `implemented_unverified` | Code exists but supporting checks are incomplete |
| `software_verified` | Defined software checks pass within their stated scope |
| `physically_demonstrated` | Physical execution is supported by identified measured evidence |

Use these distinctions in [contributions](../CONTRIBUTIONS.md), release notes and demonstration material. Update evidence and limitations with the feature, rather than leaving design claims to imply implementation.

---

[← Meta intelligence](META_INTELLIGENCE.md) · [Start developing →](DEVELOPMENT.md)
