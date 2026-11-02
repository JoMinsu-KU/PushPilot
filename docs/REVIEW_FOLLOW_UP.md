# Repository review follow-up

**November 2, 2026 · documentation-only reconciliation**

[Current status](CURRENT_STATUS.md) · [Verification](VERIFICATION.md) · [Known limitations](KNOWN_LIMITATIONS.md) · [Demo](DEMO.md)

The supplied repository review assessed source [`7d33b32`](https://github.com/JoMinsu-KU/PushPilot/tree/7d33b328afdf21bef72f65e531a92697515a73fe). The operator explicitly limited this response to **Markdown files**. Application code, tests, workflow files, dependencies, image bytes, original evidence JSON and deployed services are unchanged by this documentation update. The issues below are not described as repaired or deployed.

## Documentation reconciled

| Review finding | Documentation response |
| --- | --- |
| Current guides still called Native idle repair unimplemented | Architecture, roadmap, backend, development, services, tests, tools and deployment guides now point to [implemented legal-idle recovery](HOST_NATIVE_RECOVERY.md) and its exact limits. |
| Recovery observation and later START readiness were disconnected | Current summaries distinguish the original no-outage interval, one real idle timeout recovery and the later [stationary START binding](evidence/start-reference-ready-20261102.json). A dated readiness record is not a claim about the robot's present state. |
| New public evidence was hard to find | The [evidence index](evidence/README.md) includes the existing Native-recovery and START-readiness records without changing their contents. |
| Current representative footage was confused with the older return clip | The [55-second action/review clip](assets/PHYSICAL_MEDIA.md#representative-physical-action-and-fresh-review) and the earlier post-arrival/empty-return footage are named separately. |
| C26 version and selected-media count lagged implementation | The current review matrix identifies physical prompt v4; historical v3 results remain dated. Notices account for four selected stills. |
| Engineering contribution and model failure analysis were difficult to discover | [Contributions](../CONTRIBUTIONS.md) separates inherited transport from new orchestration/recovery/packaging. [Meta intelligence](META_INTELLIGENCE.md#evidence-and-evaluation) links existing actual-image failure analysis and the 11-stage Native-complete/MUSE-FAIL example. |

The original **From sight to action** and **Observe → Plan → Approve → Act → Verify** concept remains unchanged. Controller completion, model judgment and permission for another action remain distinct.

## Code findings remain open

These are the supplied review's findings, checked against the stated source paths. The regression scenarios describe acceptance criteria for future implementation; they are not newly committed tests or evidence of a fix.

| Open item | Current behavior / affected source | Required acceptance scenario |
| --- | --- | --- |
| Start/Stop request contention | [`App.tsx`](../frontend/src/App.tsx) shares `physicalBusy` between physical requests. A pending Start response can disable Stop even when polling shows an active mission. | Hold Start's response, publish an active status, then verify a real Stop click sends its POST. Limit duplicate Stop independently. Never automatically replay an uncertain movement. |
| Blocking symbolic Meta interpretation | [`app.py`](../backend/app.py), [`core.py`](../backend/core.py) and [`meta.py`](../backend/meta.py) retain a symbolic branch that calls synchronous dispatch/provider inference while holding the workspace lock. Live/recorded service behavior must not be generalized to this branch. | Reserve under a short lock, perform inference outside it, and revalidate identity/revision/session/cancellation before commit. Concurrent status/cancel/Stop must remain responsive; stale results must not overwrite newer state. Moving the whole locked operation to a thread alone is insufficient. |
| Historical Stop replay side effect | [`PhysicalMissionService.stop()`](../backend/physical_mission.py) changes cancellation state before checking the stored request identity. A duplicate or conflicting old ID can affect a later mission. | Replay an old Stop after reset/new start with no change to the new mission, worker, cancellation generation or driver calls. Reject conflicting payloads before side effects while preserving prompt admission of a genuinely new Stop during preparation. |
| General request lifetime and overlap | General workspace/review requests in [`App.tsx`](../frontend/src/App.tsx) and scene operations in [`MapScene.tsx`](../frontend/src/MapScene.tsx) lack the same complete request/body deadline and sequential-poll protections used by dedicated transports. | A response or JSON body that never completes must time out; cleanup aborts pending reads, and polling remains single-flight and recovers. A timed-out mutating POST is an **unknown result**, followed by status reconciliation rather than automatic resubmission. |
| Select keyboard announcement | [`WorkspaceUI.tsx`](../frontend/src/WorkspaceUI.tsx) changes visual active selection without consistently exposing that candidate through focus or `aria-activedescendant`. | Direction keys update the candidate announced to assistive technology; Enter, Escape and focus restoration retain their expected behavior. |

The software Stop is a request to hold further execution; it is not a hardware emergency stop. Existing protocol, completion and unknown-outcome boundaries still apply. See [robot operations](ROBOT_OPERATIONS.md) and [API contracts](../contracts/README.md).

## CI proposal, not an installed workflow

The current [Pages workflow](../.github/workflows/review-pages.yml) checks and deploys only the recorded-review artifact. It does not constitute full application CI. A future general workflow should run pinned Python dependencies, `python tools/dev.py check`, `python tools/dev.py test`, and Node 24 `npm ci`, `npm test`, `npm run build`, plus the recorded-review integrity checks. Use equipment-free jobs without private runtime, API keys or hardware access, and retain explicit private-runtime skips.

No workflow YAML was added or modified in this documentation-only response. A successful future CI run should be linked by commit and run URL before being presented as a result.

## Reported verification checkpoints

| Source | Result and attribution |
| --- | --- |
| Project's published Native-recovery record, source `bcac769` | [Original JSON](evidence/native-read-recovery-20261102.json): 1,199 backend tests run, five skipped, no failures; 143 frontend tests and production build passed. Its dated deployment/device observations retain their own scope. |
| Supplied independent review, source `7d33b32` | Reviewer reports Linux x86_64, Python 3.12.14 and Node 24.22.1: 1,206 backend tests, 1,203 passed/three private-runtime skips; 143 frontend tests and build passed; 168 Python/45 JSON checks. These are **reviewer-reported results**, not a new project-run log or a hardware qualification. |

Different source revisions, platforms and skip conditions can produce different totals. The earlier public JSON is not rewritten to match the review. No general accuracy or route-success percentage follows from either software checkpoint.

## Evidence linkage and operator benefit still to establish

The representative video visibly connects a physical push, clear-view review, new PASS and next action. Its [manifest](assets/physical-media.json) records the selected interval and sampled visible states. The three synthetic cases in the [public explorer](https://jominsu-ku.github.io/PushPilot/) are a different execution and must not be substituted for that physical run's provider evidence.

The proposed stronger link remains to be assembled in a publishable, source-verified form: the same execution's command/Native receipt, selected observation hashes, exact model/prompt/verdict and next-step admission. Where a public mapping is unavailable, mark it unavailable. Do not infer it from nearby timestamps, borrow another run's PASS or publish raw coordinates/private input images to fill the gap.

Existing [actual-image evaluation summaries](C_INTERMEDIATE_PROGRESS_REVIEW.md#archived-evaluation-2026-10-30) retain their original call/pair/sample units, rejected prompt variants, false negatives, occlusions and timeouts. They are not a held-out accuracy benchmark; separate experiments must not be pooled into one success rate. This update adds no offline model-comparison files or private raw evaluation material.

Operator impact is still an evaluation proposal. With consented target users and archived cases, a future study can measure time to explain a hold, locate the supporting image/judgment/action, and distinguish preparation, in-mission intervention and cleanup. Use a stated task, comparator, participant count and error definition. No time-saving percentage, reduced intervention rate or customer-validation result has yet been established here.

Keeping these follow-ups explicit lets the documentation show completed engineering accurately without representing proposed repairs, future studies or recorded examples as production guarantees.
