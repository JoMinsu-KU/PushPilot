<p align="center">
  <img src="docs/assets/hero.svg" width="1280" alt="PushPilot — From sight to action. A shared plan. A checked outcome. Concept illustration of a robot, scene evidence and an operator review.">
</p>

<p align="center">
  <strong>An operator workspace for reviewable, visually grounded robot tasks.</strong><br>
  Understand the goal. Inspect the outcome. Know why the next step happens.
</p>

<p align="center">
  <a href="#why-pushpilot">Why PushPilot</a> &nbsp;·&nbsp;
  <a href="#the-interaction-loop">The workflow</a> &nbsp;·&nbsp;
  <a href="#build-status">Build status</a> &nbsp;·&nbsp;
  <a href="#quick-start">Quick start</a> &nbsp;·&nbsp;
  <a href="docs/README.md">Documentation</a>
</p>

<p align="center">
  <code>Stage: repository foundation</code> &nbsp;
  <code>Tooling: Python 3.11+</code> &nbsp;
  <code>Deployment target: GX10</code>
</p>

---

## Why PushPilot

A robot reaching a commanded point does not tell an operator whether the object reached its goal. PushPilot is being built around that missing connection: **the intended task, the scene evidence and the decision to continue belong together.**

The proposed experience connects an operator's goal to a shared plan, bounded actions and fresh visual reviews through the planned Meta-model integration, MUSE. The operator can inspect what was expected, what was observed and why the application continues, waits or asks for another observation.

| Understand the task | Check the outcome | Explain the next step |
|---|---|---|
| Ground the goal in the supplied scene and task context. | Compare the intended action with new evidence after it stops. | Keep the model result, local checks and resulting state change connected. |

The first use case is a controlled tabletop mission: push a wheel-less car from a named starting station to a destination, stop at controlled intersections, wait on red and enter on qualified green. It is a compact testbed for an inspectable operator workflow. A future AR-glasses companion extends the product idea beyond the tablet.

**The current repository contains the development and release foundation.** The mission application and model/device integrations are planned; the illustrations describe the intended experience.

## The interaction loop

<p align="center">
  <img src="docs/assets/workflow.svg" width="1280" alt="Proposed interaction loop: Observe, Plan, Approve, Act, Verify. Fresh observations and reviewed evidence determine the next bounded action.">
</p>

1. **Observe** — obtain a source-labelled scene and the operator's goal.
2. **Plan** — interpret the task and prepare an explanation the operator can review.
3. **Approve** — bind the reviewed task to the current context.
4. **Act** — perform one bounded, qualified action through the execution boundary.
5. **Verify** — compare fresh observations with the expected outcome, then continue, wait or reobserve.

MUSE provides semantic interpretation and outcome review in the proposed integration. The supervisor enforces deterministic state, freshness, traffic and qualification checks. A model result does not directly issue robot scripts or authoritative coordinates.

### A mission with visible decisions

| Moment | Operator experience | Decision rule |
|---|---|---|
| State a goal | `Push the car to the bakery.` | Ground the request in supplied task context. |
| Review the plan | A shared task and its expected outcomes. | Approval applies to the current task/context. |
| Finish an action | `Expected / Observed` with a new image and model result. | Accept the reviewed outcome and required local checks before continuing. |
| Reach a controlled approach | `Stopped at stop line` | Always stop first, including on green arrival. |
| Observe red or an unclear signal | `Waiting for green` or `Signal unclear · Waiting` | Remain stopped; card exchange or occlusion cannot imply green. |
| Confirm green | `Crossing intersection` | Fresh green and accepted entry checks permit automatic entry. |
| Reach the destination | A final outcome and its evidence. | Measured completion and the required review establish success. |

The signal source is operator-switched red/green paper. Each bounded contact action requires a fresh-image MUSE review in the planned integration. Ordinary waiting and execution faults are separate states. Read the [mission specification](docs/MISSION.md).

## What makes the model useful

The product is designed to show five concise pieces of information together:

> **Goal understood** → **Scene evidence** → **Expected / Observed** → **MUSE decision** → **Next check**

A useful review can identify no progress, an unexpected outcome or insufficient visibility and change what happens next. Evidence is retained so that the operator can inspect the decision. A successful-looking caption over predetermined motion is not the intended integration.

The planned evidence model records source identity independently for the robot, image, object pose, signal and model result. An actual Meta response over a recorded image is a real provider test; it does not turn simulated motion into physical execution. Read [Meta intelligence and evidence](docs/META_INTELLIGENCE.md).

## Build status

| Area | Status | What is available now |
|---|---|---|
| Repository structure and component ownership | **Ready** | Standalone workspace with component guides and development rules. |
| Equipment-free checks | **Ready** | Python source/example-JSON checks and 13 release-boundary tests. |
| Source-release tooling | **Ready** | Clean-commit packaging, file hashes and archive verification. |
| Mission backend and abstract simulator | **Planned** | Responsibilities and interaction boundaries are documented. |
| Operator frontend and evidence replay | **Planned** | English product flow and visual direction are specified. |
| Live MUSE/provider integration | **Planned** | Goal/outcome roles and review requirements are documented. |
| Final map, metric AR and robot integration | **Deferred** | Awaiting the final installed map and physical qualification. |
| AR-glasses companion | **Concept** | Future experience; no wearable integration is claimed. |

**Current verification: 13 passing bootstrap tests.** These exercise Git/source-release boundaries; they are not mission, model-accuracy or physical-robot results. There is no application server startup command yet.

Final road geometry and physical placement are unresolved. Current development uses symbolic locations, abstract actions and explicitly labelled test inputs. Map-specific routes, calibration, stop lines, signal regions and spatial AR remain deferred. Existing map examples are not embedded as a production dependency.

## Quick start

### Prerequisites

- **Python 3.11 or newer**.
- **Git** available on your command path. Release tests create isolated local Git fixtures.
- No third-party packages, model credentials or robot connection are required for the current tooling.

From the repository root:

```bash
python tools/dev.py check
python tools/dev.py test
```

These commands work from PowerShell or a shell with the prerequisites available. They validate repository tooling without starting an application, contacting a model or operating equipment.

For the full workflow and future runtime setup, read [Development](docs/DEVELOPMENT.md).

### Create a source release

After committing the reviewed source, keep the working tree clean and choose a new output path outside the repository:

```bash
python -c "from pathlib import Path; Path('../release-bundles').mkdir(exist_ok=True)"
python tools/build_release.py --output ../release-bundles/pushpilot-source.zip
python tools/build_release.py --verify ../release-bundles/pushpilot-source.zip
```

The builder uses committed, allowlisted source and writes a Git-bound SHA-256 manifest. It rejects dirty source, private paths and unsupported file types. Verification does not extract files or authenticate a publisher. Use a new filename for each release; existing output is not overwritten.

This creates a **source bundle**, not a deployed service. Read [Release tooling](tools/README.md) and [GX10 deployment](deploy/README.md) for the exact boundaries.

## Repository structure

```text
.
├── frontend/             Operator workspace and presentation boundary
├── backend/              Mission, model/provider and evidence boundary
├── contracts/            Versioned cross-component interfaces
├── prompts/              Versioned English model instructions
├── tests/                Bootstrap and future application verification
├── tools/                Equipment-free checks and source-release tools
├── deploy/               Isolated GX10 release plan and example config
├── docs/
│   ├── README.md         Documentation hub
│   ├── ARCHITECTURE.md   Components, authority and source boundaries
│   ├── MISSION.md        Behavior and signal-entry rules
│   ├── META_INTELLIGENCE.md
│   ├── DEVELOPMENT.md    Local workflow and release preparation
│   ├── ROADMAP.md        Milestones and acceptance gates
│   └── assets/           Original repository illustrations
├── CONTRIBUTING.md       Development and review guide
├── CONTRIBUTIONS.md      Origin, status and new-work disclosure
├── THIRD_PARTY_NOTICES.md
├── AGENTS.md             Development instructions
└── pyproject.toml        Current tooling requirements
```

Component directories define ownership before their application implementations are added. Future internal layouts are documented as planned, not presented as existing modules.

| Start here if you want to… | Read |
|---|---|
| Understand the system and authority boundaries | [Architecture](docs/ARCHITECTURE.md) |
| Inspect pushing, waiting and verification behavior | [Mission](docs/MISSION.md) |
| Understand MUSE's role and evidence requirements | [Meta intelligence](docs/META_INTELLIGENCE.md) |
| Work on the operator interface | [Frontend](frontend/README.md) |
| Work on task and provider services | [Backend](backend/README.md) |
| Review schemas or model instructions | [Contracts](contracts/README.md) · [Prompts](prompts/README.md) |
| Run checks or prepare a source bundle | [Tests](tests/README.md) · [Tools](tools/README.md) |
| Understand the delivery sequence | [Roadmap](docs/ROADMAP.md) · [Deployment](deploy/README.md) |

## Local development → GitHub → GX10

The local repository is the development source. GitHub records reviewed source and history. GX10 is the deployment target for a specific verified release.

The proposed target separates immutable `releases/` from runtime configuration, credentials, evidence and logs in `shared/`, with a `current` pointer to the active version. The scaffold does not transfer files, create remote directories or start services. Existing camera and robot environments retain their ownership.

Deployment requires an actual runtime, a verified target environment and a release activation procedure. Read [Deployment](deploy/README.md); example configuration is a proposal, not a record of a configured host.

## Roadmap and contribution history

The next milestone is a complete **map-independent software loop**: abstract mission events, genuine Meta interaction, visible decisions and source-labelled replay. Final map and robot acceptance follow the physical setup gate. Optional voice input, extra destinations, segmentation and wearable hardware follow the core evidence loop.

PushPilot builds on earlier tabletop experiments and an existing robot-transport foundation. Those materials have not been copied into this standalone application scaffold. The workspace, tools and documentation are recorded separately; later imports and implemented features must identify their origin, changes and evidence.

Read the [Roadmap](docs/ROADMAP.md), [Contributing guide](CONTRIBUTING.md), [Contribution record](CONTRIBUTIONS.md) and [Third-party notices](THIRD_PARTY_NOTICES.md). The header and workflow are original repository vectors, not camera captures or working-product screenshots.

**License:** a repository license has not yet been selected. Consult [Third-party notices](THIRD_PARTY_NOTICES.md) before reuse or importing material.

---

<p align="center">
  <strong>PushPilot · From sight to action</strong><br>
  <sub>A shared plan. A checked outcome. An understandable next step.</sub>
</p>
