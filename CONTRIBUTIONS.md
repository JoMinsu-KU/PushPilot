# Contribution record

Prepared on 2026-10-27, Asia/Seoul. Status: internal development record, not a submitted competition disclosure.

PushPilot has existing POC robot transport, earlier tabletop experiments, a city-map scaffold, design references and planning documents outside this repository. Creating this workspace does not make those earlier components new work. The user selected the Startup track; detailed organizer requirements and source copies remain in the separate planning workspace.

## Initial repository boundary

### October 28, 2026 KST — isolated robot commissioning

New `backend/robot_control/`, authenticated commissioning CLI/API, private durable command journal, bounded admission/review/reconciliation, equipment-free failure tests and GX10 deployment preparation were implemented under the user's explicit robot-control request. These are new wrappers around the existing `poc-persistent-v1` protocol, not a newly authored robot driver. The unchanged inherited host/policy/transport/kinematics and installed pendant script are imported privately by exact hashes in [the runtime provenance manifest](docs/data/robot-runtime-source.json); no historical profile, coordinate, mailbox or run is restored or publicly bundled. The offline helper derives a fresh profile only from explicitly reviewed measured installation/current-state inputs. Status: software verified; no new-map physical motion, car-turn, measured stop, production calibration or physical MUSE loop demonstrated. See [commissioning boundaries](docs/ROBOT_CONTROL.md).

| Component | Origin and present status | Supported claim |
|---|---|---|
| Workspace instructions, metadata and development/deployment documentation | Prepared for this application workspace on the actual current date | Repository preparation only |
| Public README system and documentation artwork | New English documentation and original SVG vectors in `docs/assets/`; no reference screenshots copied | Product design and documentation only |
| Generated process diagrams | AI-generated conceptual PNGs, with exact prompts in `docs/assets/GENERATION_PROMPTS.md` and `docs/assets/VOICE_GENERATION_PROMPTS.md`; reviewed against the documented architecture | Documentation illustration only; no runtime or physical result |
| Local validation and release-packaging tools | New workspace bootstrap; inspect their tests and commit history | Packaging/development support only |
| Meta API connection checker | New opt-in standard-library tool, four offline tests and one recorded real text completion; see `docs/META_API_CHECK.md` | Authentication and text inference only; no image review or physical claim |
| Voice input and service composition | New first-demo design for browser push-to-talk, backend Meta transcription, editable text and explicit plan approval | Design only; no microphone capture, voice API call or deployed service verified |
| Mission supervisor, abstract simulator and API | New Python implementation in `backend/`, versioned workspace DTO and isolated offline tests, 2026-10-27 KST | Software simulation only: approval, bounded actions, mandatory stop, signal admission, review and restart recovery |
| Operator frontend and replay | New React/TypeScript implementation and original code-native SVG scene, 2026-10-27 KST | Connected software workspace; illustration is not camera imagery or registered AR |
| Visible goal and microphone entry | New glass intent bar, original-query inspection, goal-dialog tabs and disconnected voice guidance, 2026-10-27 KST | UI only; accepted request remains separate from editor draft and model interpretation. No microphone capture, transcription or voice-provider claim |
| Native-image MUSE backend | New graph-grounded route provider, server-bound live action/signal services, finite run/wait helpers and private original-frame SQLite ledger, 2026-10-27 KST | Real left/right route-preview checks are documented separately; action and stop receipts remain simulated, with no physical motion authority |
| Replaceable-map planning contracts | New exact selected-route compiler, constraints, approach-specific signal targets, validation API/CLI and optional spatial-only registration flag, 2026-10-27 KST | Map data can change independently of UI; no installed print, signal region, robot geometry or 3D asset is inferred |
| Finite voice backend | New bounded PCM WAV intake, official Meta ASR adapter, editable transcript receipts, revision/map binding and offline tests, 2026-10-27 KST | Backend prepared; actual ASR access, microphone capture and recognition quality remain unverified |
| Meta goal adapter | New strict-schema server-side adapter; one real structured goal request on 2026-10-27 at 14:07 KST; see `docs/META_API_CHECK.md` | Live text interpretation only; no image/voice inference or physical result |
| Action-bound MUSE outcome reviewer | New `backend/action_review.py`, shared DTO and UI for operator-selected recorded pairs, 2026-10-27 KST | Strict actual-provider result can change the simulated mission through local gates; no fresh physical evidence or robot authority |
| Recorded-review evaluation harness | New original synthetic schematic fixtures and opt-in three-case provider harness, 2026-10-27 KST; actual run results belong in `docs/META_API_CHECK.md` | Pipeline/state evidence on explicitly synthetic input, not real-car accuracy or physical motion |
| First light-dashboard pass and judge-facing README | New user-directed interface styling, historical application screenshot and evidence-first repository narrative, 2026-10-27 KST; the user rejected the first layout as insufficiently close to the supplied references | Historical software design/documentation; not a user approval |
| Fixed spatial stage and translucent overlays | New viewport composition, rounded glass mission/status surfaces, bounded goal/plan/replay/review dialogs, tabs and pagination, 2026-10-27 KST | Software presentation only; actual layout checks and limits belong in `docs/VERIFICATION.md`, not a physical or design-approval claim |
| Pretendard typography integration | User-selected Pretendard Variable v1.3.9, authored upstream by Kil Hyung-jin, vendored unmodified with its SIL Open Font License 1.1; new application font loading, 2026-10-27 KST | Application integration only, not newly authored font design; official sources, byte size and SHA-256 are recorded in `frontend/public/fonts/pretendard/README.md` |
| Private city clean-road variant | User-supplied 3D artwork retained privately; new native GLB material exporter and Spatial integration, 2026-10-27 KST. Only the cracked road texture binding is replaced with matte charcoal; binary geometry, road markings and other materials are preserved | A derived display asset and software integration, not newly authored city geometry, a physical map change or robot calibration |
| Camera board focus | New neutral-background display mask over the existing explicitly locked test mapping, 2026-10-27 KST; original camera perspective and overlay geometry are preserved, with complete Full frame available | Display mask only; original frames remain MUSE/evidence inputs. No additional image detail, occlusion recovery, metric/BASE registration or physical accuracy claim |
| Native live camera preview | New standalone `tools/camera_preview.py`, opt-in `backend/live_camera.py`, DTO and source-selectable UI, 2026-10-27 KST; helper on GX10, loopback SSH transport to the Windows application | Ephemeral native JPEG preview and explicit fixed display-registration path only; actual connection/lock observations belong in `docs/VERIFICATION.md`. No persisted live mission evidence, automatic MUSE input, qualified signal observation, physical calibration or robot authority |
| Temporary map adapter and route supervision | New adapter over explicitly inherited v11 geometry, with source hash in `backend/data/little-town-temporary.json`; 2026-10-27 KST | Three temporary graph routes and independent junction gates in simulation; no new physical motion claim |
| Execution-aware route display and map replacement | New map-derived PUSH/CROSS display segments, illustrative junction stop lines, action bindings and current/completed/remaining AR presentation; map metadata, startup map selection and selected-map MUSE destination vocabulary, 2026-10-27 KST | Software drawing/simulation integration; actual checks belong in `docs/VERIFICATION.md`. No measured car pose, physical stopping/turning, alternative/via routing or automatic live-image MUSE capture |
| Recorded-scene inspection and test overlay | New OpenCV/NumPy processing, private frame storage, explicit projection locking and strict-schema Muse Spark image adapter; 2026-10-27 KST | Recorded-image scene evidence and UI overlay only; no live camera, robot registration or action approval |
| Robot bridge, new-map pushing/turning and signal operation | Not included or demonstrated | No physical mission claim |
| Earlier POC code, map, images and run evidence | Preserved outside this repository; not copied by this scaffold | Historical context only |

The first Git commit, when created, is a truthful snapshot after this work. Do not backdate commits or present it as a reconstructed start-of-event snapshot.

## Record each implemented feature

The signal scenario was clarified by the user on 2026-10-27: MUSE judges signal color from a new image after verified stopping. Documentation now distinguishes that intended color judgment from local stop/provenance/freshness/request validation, without requiring a second local color classifier. This is a design correction only; it does not implement live signal capture, a MUSE signal endpoint or physical stop/continuation. See [the planned boundary](docs/MUSE_SIGNAL_GATE.md).

- Feature and affected paths; contributor(s); actual work interval with timezone.
- Baseline/import source and version/hash; exact change or commit evidence.
- Third-party rights, inherited dependencies and asset origin.
- Status: `planned`, `design_only`, `implemented_unverified`, `software_verified` or `physically_demonstrated`.
- Tests and limitations; model/prompt/schema versions; real provider request evidence when applicable.
- Supported demo claim and corresponding run IDs/timestamps.

Keep mock, recorded, live-provider and physical-run evidence separate. A real Meta call on a recorded frame proves provider interaction, not a physical mission. A wrapper around inherited code is a new wrapper, not a newly built driver.

## Current public disclosure

> PushPilot builds on our earlier tabletop-control experiments, existing robot transport and an inherited Little Town drawing. This repository adds a tablet workspace with a fixed spatial stage and translucent information overlays, a replaceable-map simulation supervisor and execution-aware route display, optional native live preview, recorded-image test overlays and Camera board-focus display masking, evidence replay, Meta goal/scene/action-review adapters, verification and release tools, and original UI artwork. Route progress is simulated and its stop-line geometry is illustrative; the display does not track a physical car. Live preview remains ephemeral and separate from model/evidence inputs. Original recorded frames remain unchanged for model requests and evidence. Action review uses operator-selected recorded pairs and can affect simulation through deterministic gates. Voice, trusted action-bound physical observation and robot connection remain future integration work. Existing foundations, adapted material and external dependencies are identified in the contribution record and third-party notices. Demonstration claims distinguish simulation, synthetic fixtures, recorded real inputs, live preview, actual Meta-model calls and physical execution. The wearable companion is a future concept.

Update this statement from completed work and its evidence as implementation progresses. This document records provenance; it does not authorize publication or submission.
