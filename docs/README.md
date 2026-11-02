<div align="center">

# PushPilot documentation

**From sight to action. A shared plan. A checked outcome.**

[Repository](../README.md) · [Current status](CURRENT_STATUS.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Architecture](ARCHITECTURE.md) · [Robot operations](ROBOT_OPERATIONS.md)

</div>

---

The original loop still organizes the product: **Observe → Plan → Approve → Act → Verify**. Meta MUSE turns operator intent and original images into a route proposal, signal interpretation and outcome judgment. The supervisor validates those judgments; a configured Robot executor follows taught BASE coordinates and records Native receipts. Camera and Spatial make the plan and decision evidence visible.

Start with the [demo and recorded-decision guide](DEMO.md) for actual tablet footage and the equipment-free archived-review explorer, then the [current capability matrix](CURRENT_STATUS.md). The repository contains an equipment-free simulation path, an opt-in current-site physical trial, and dated implementation/commissioning history. Historical screenshots and trials are retained with their source and limits; they are not the current runtime specification.

## Operate and recover

| Need | Current guide |
|---|---|
| Know what is implemented, demonstrated or still unqualified | [Current status](CURRENT_STATUS.md) · [Known limitations](KNOWN_LIMITATIONS.md) |
| Prepare a mission, stop, return, reset or recover | [Robot operations](ROBOT_OPERATIONS.md) |
| Understand the B/Office, C/Villa and D/Hanok delivery scope | [Delivery-first site trial](DELIVERY_SITE_TRIAL.md) · [Autonomous policy and trial boundary](AUTONOMOUS_EXECUTOR.md) |
| Review the paper-signal admission | [Single signal departure](SINGLE_SIGNAL_DEPARTURE.md) · [Signal wait reference](ROBOT_SIGNAL_WAIT.md) · [Signal service scopes](MUSE_SIGNAL_GATE.md) |
| Review C's endpoint and visual policies | [C26 delivery endpoint](C26_DELIVERY_ENDPOINT.md) · [C intermediate review matrix](C_INTERMEDIATE_PROGRESS_REVIEW.md) |
| Continue a known completed action after review hold | [Explicit continuation](EXPLICIT_REVIEW_CONTINUATION.md) |
| Prepare the scoped C11 boundary or a fresh START session reference | [C11 boundary recovery](C11_BOUNDARY_RECOVERY.md) · [Stationary START reference](SESSION_START_REFERENCE.md) |

Reset retires an ended mission at an independently verified START; it does not move the robot. A lost movement outcome never permits automatic replay. [Legal-idle Native read recovery](HOST_NATIVE_RECOVERY.md) is implemented and has one recorded actual recovery; non-idle failures and broader reliability qualification remain separate from MUSE and signal waiting. See [known limitations](KNOWN_LIMITATIONS.md).

## Understand the product and Meta intelligence

| Need | Guide |
|---|---|
| Follow the original user scenario and next decision | [Mission](MISSION.md) |
| See how MUSE connects intent, route and visual evidence | [Meta intelligence](META_INTELLIGENCE.md) · [Prompt catalogue](../prompts/README.md) |
| Understand modules, processes and source ownership | [Architecture](ARCHITECTURE.md) · [Service composition](SERVICE_COMPOSITION.md) |
| Inspect APIs and data contracts | [Backend](../backend/README.md) · [Contracts](../contracts/README.md) |
| Understand native-image graph planning and simulation live-review services | [Live intelligence](LIVE_INTELLIGENCE.md) |
| Inspect recorded-pair review and actual dated provider requests | [Action reviews](ACTION_REVIEWS.md) · [Meta API records](META_API_CHECK.md) |
| Understand finite voice upload versus pending browser capture | [Voice input](VOICE_INPUT.md) · [Voice backend](VOICE_BACKEND.md) |

MUSE review is not TCP control. Native completion is not proof of vehicle arrival. Keep these separate sources visible when explaining a run.

## Display the scene and replace its inputs

| Need | Guide |
|---|---|
| Preserve the light glass workspace, Pretendard and viewport priorities | [Design system](DESIGN_SYSTEM.md) · [Frontend](../frontend/README.md) · [Designer display](DESIGNER_LIVE_DISPLAY.md) |
| Understand current City A3 drawing identities | [City A3](CITY_A3.md) |
| Follow the selected route in Camera and Spatial | [Route display](ROUTE_DISPLAY.md) |
| Install the current private model and distinguish older model packages | [Spatial 3D](SPATIAL_3D.md) · [Spatial signal display and preview](SPATIAL_SIGNAL_PREVIEW.md) |
| Connect the separately authorized preview and preserve original frames | [Live camera](LIVE_CAMERA.md) · [Camera preview recovery](CAMERA_PREVIEW_RECOVERY.md) |
| Replace a drawing without migrating obsolete plans/registrations | [Map replacement](MAP_REPLACEMENT.md) |
| Read the earlier compatibility map and source boundaries | [Little Town history](TEMPORARY_MAP.md) · [Test inputs](TEST_INPUTS.md) |
| Inspect current illustration versus old screenshots | [Artwork inventory](assets/README.md) |

The private model and nominal map fit are display inputs. The illustrated Spatial car is an execution estimate. Neither supplies measured car pose or authorizes physical motion.

## Build, verify and release

| Need | Guide |
|---|---|
| Set up equipment-free development or deliberate private configuration | [Development](DEVELOPMENT.md) |
| Build locally and serve compiled assets on GX10 | [Application deployment](../deploy/README.md) |
| Install the separate commissioning API and inherited receiver runtime | [Robot deployment](../deploy/ROBOT_CONTROL.md) · [Robot control](ROBOT_CONTROL.md) |
| Find offline, provider and equipment-contacting utilities | [Tools](../tools/README.md) |
| Inspect software checks and dated validation | [Tests](../tests/README.md) · [Verification](VERIFICATION.md) |
| Separate corrected documentation from unresolved review findings | [Repository review follow-up](REVIEW_FOLLOW_UP.md) |
| See remaining implementation and qualification work | [Roadmap](ROADMAP.md) |
| Contribute while preserving source/evidence boundaries | [Contributing](../CONTRIBUTING.md) · [Workspace instructions](../AGENTS.md) |
| Record authorship and imported material | [Contributions](../CONTRIBUTIONS.md) · [Third-party notices](../THIRD_PARTY_NOTICES.md) |

Publication, source packaging, GX10 activation and physical mission start are separate actions. Releases exclude credentials, raw camera media, private artwork/models, taught geometry, profiles, old mailboxes and operational archives.

## Inspect the history without mistaking it for current operation

| Historical or scope-specific material | Read with |
|---|---|
| [Measured route catalogue](MEASURED_ROUTE_CATALOGUE.md) | Original B/C/D arrival/return records, packet cutoffs and derived-path limitations |
| [Taught-course compatibility executor](TAUGHT_EXECUTOR.md) · [TCP coordinate control](TCP_COORDINATE_CONTROL.md) | The runner/version and dated commissioning cutoff stated in each section |
| [Contact pushing](PUSH_ALIGNMENT.md) · [Local contact trials](LOCAL_CONTACT_TRIALS.md) | Experimental response fitting versus the active delivery-only trial |
| [Robot calibration](ROBOT_CALIBRATION.md) | Rejected/global fit evidence versus independently taught BASE routes |
| [Fixed-face review](FIXED_FACE_CALIBRATION_REVIEW.md) · [Line datum](LINE_DATUM_COMMISSIONING.md) | Historical acquisition proposals and preserved failed checks |
| [POC receiver review](POC_RECEIVER_REVIEW.md) | Original missing-profile/HELLO defect, distinct from later Native idle timeouts |
| [Evidence index](evidence/README.md) | All original dated evidence records and their current successor guides |
| [Original diagram prompts](assets/GENERATION_PROMPTS.md) · [Original voice prompts](assets/VOICE_GENERATION_PROMPTS.md) | Exact historical generation records; new assets have a separate [current prompt record](assets/CURRENT_GENERATION_PROMPTS.md) |

The unmodified [Pretendard font record](../frontend/public/fonts/pretendard/README.md) retains its pinned upstream source and license. Older generated concepts, rejected design passes, synthetic provider examples and failed physical observations remain dated records.

---

[← Back to PushPilot](../README.md) · [Current status →](CURRENT_STATUS.md)
