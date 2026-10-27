# Contribution record

Prepared on 2026-10-27, Asia/Seoul. Status: internal development record, not a submitted competition disclosure.

PushPilot has existing POC robot transport, earlier tabletop experiments, a city-map scaffold, design references and planning documents outside this repository. Creating this workspace does not make those earlier components new work. The user selected the Startup track; detailed organizer requirements and source copies remain in the separate planning workspace.

## Initial repository boundary

| Component | Origin and present status | Supported claim |
|---|---|---|
| Workspace instructions, metadata and development/deployment documentation | Prepared for this application workspace on the actual current date | Repository preparation only |
| Public README system and documentation artwork | New English documentation and original SVG vectors in `docs/assets/`; no reference screenshots copied | Product design and documentation only |
| Generated process diagrams | AI-generated conceptual PNGs, with exact prompts in `docs/assets/GENERATION_PROMPTS.md` and `docs/assets/VOICE_GENERATION_PROMPTS.md`; reviewed against the documented architecture | Documentation illustration only; no runtime or physical result |
| Local validation and release-packaging tools | New workspace bootstrap; inspect their tests and commit history | Packaging/development support only |
| Meta API connection checker | New opt-in standard-library tool, four offline tests and one recorded real text completion; see `docs/META_API_CHECK.md` | Authentication and text inference only; no image review or physical claim |
| Voice input and service composition | New first-demo design for browser push-to-talk, backend Meta transcription, editable text and explicit plan approval | Design only; no microphone capture, voice API call or deployed service verified |
| Frontend, backend, MUSE reviewer and mission supervisor | Planned; directory readmes define intended ownership | No working application claim |
| Robot bridge, new-map pushing/turning and signal operation | Not included or demonstrated | No physical mission claim |
| Earlier POC code, map, images and run evidence | Preserved outside this repository; not copied by this scaffold | Historical context only |

The first Git commit, when created, is a truthful snapshot after this work. Do not backdate commits or present it as a reconstructed start-of-event snapshot.

## Record each implemented feature

- Feature and affected paths; contributor(s); actual work interval with timezone.
- Baseline/import source and version/hash; exact change or commit evidence.
- Third-party rights, inherited dependencies and asset origin.
- Status: `planned`, `design_only`, `implemented_unverified`, `software_verified` or `physically_demonstrated`.
- Tests and limitations; model/prompt/schema versions; real provider request evidence when applicable.
- Supported demo claim and corresponding run IDs/timestamps.

Keep mock, recorded, live-provider and physical-run evidence separate. A real Meta call on a recorded frame proves provider interaction, not a physical mission. A wrapper around inherited code is a new wrapper, not a newly built driver.

## Current public disclosure

> PushPilot builds on our earlier tabletop-control experiments and existing robot transport. This standalone repository currently contains new development and source-release tools, bootstrap tests, application design documentation and original documentation artwork. The mission application, Meta integration and robot connection are planned. Existing foundations, imported material and external dependencies are identified in the contribution record and third-party notices. Demonstration claims must distinguish simulation, recorded inputs, real Meta-model calls and physical execution. The wearable companion is a future concept.

Update this statement from completed work and its evidence as implementation progresses. This document records provenance; it does not authorize publication or submission.
