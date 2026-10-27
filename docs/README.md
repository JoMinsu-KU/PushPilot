<div align="center">

# PushPilot documentation

**Understand the mission. Inspect the decisions. Build within clear boundaries.**

[Repository](../README.md) · [Design system](DESIGN_SYSTEM.md) · [Architecture](ARCHITECTURE.md) · [Services](SERVICE_COMPOSITION.md) · [Voice input](VOICE_INPUT.md) · [Mission](MISSION.md) · [Roadmap](ROADMAP.md)

</div>

---

PushPilot is being developed as a tablet workspace for an image-grounded tabletop robot mission. An operator states or types a goal, confirms the chosen text, reviews and approves the proposed task, and follows the evidence behind each decision to proceed, wait or observe again. A future glasses companion extends the interaction concept.

The current [visual direction](DESIGN_SYSTEM.md) follows the user's industrial light-dashboard references: off-white surfaces, white panels, charcoal typography, a slim icon rail and restrained orange accents. Earlier navy/cyan screenshots and generated diagrams document their original design stage and do not define the current interface palette.

**The temporary Little Town application connects simulation and recorded-image review.** React/TypeScript and a FastAPI/Uvicorn backend provide graph-based plans, SQLite supervision, simulated actions/signals, explicit demo verdicts and actual Meta goal interpretation. Uploaded frames support marker detection, a locked test overlay and independent MUSE scene inspection. A separate action-bound before/after review can change the simulated mission through the supervisor. Neither path establishes physical freshness or robot capability. Voice, live camera capture, robot registration and physical control remain unavailable.

## Choose a reading path

| Your goal | Start here | Continue with |
|---|---|---|
| Understand the product | [Mission](MISSION.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Design the operator workspace | [Design system](DESIGN_SYSTEM.md) | [Frontend](../frontend/README.md) |
| Understand the system | [Architecture](ARCHITECTURE.md) | [Service composition](SERVICE_COMPOSITION.md) |
| Review voice goal entry | [Voice input](VOICE_INPUT.md) | [Frontend](../frontend/README.md) and [contracts](../contracts/README.md) |
| Test Meta authentication and goal interpretation | [API connection check](META_API_CHECK.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Connect image judgment to a simulated action | [Action reviews](ACTION_REVIEWS.md) | [Contracts](../contracts/README.md) and [verification](VERIFICATION.md) |
| Test the temporary printed map | [Temporary map](TEMPORARY_MAP.md) | [Test inputs](TEST_INPUTS.md) and [verification](VERIFICATION.md) |
| Work on the repository | [Development workflow](DEVELOPMENT.md) | [Roadmap](ROADMAP.md) |
| Review a demonstration claim | [Evidence model](ARCHITECTURE.md#evidence-that-explains-a-decision) | [Contribution record](../CONTRIBUTIONS.md) |
| Inspect completed software checks | [Verification](VERIFICATION.md) | [Current workspace screenshot](assets/light-industrial-workspace.jpg) |
| Prepare a release | [Development workflow](DEVELOPMENT.md) | [GX10 delivery plan](../deploy/README.md) |

## The interaction in one line

> **Observe → Plan → Approve → Act → Verify**
>
> Fresh observations and accepted checks determine the next action. Uncertainty stays visible and changes the workflow.

The mission begins at symbolic **PIZZA** and pushes a wheel-less car toward a selected destination. Every configured intersection requires a stop, even when its signal is already green. Red, unclear or stale signal observations mean wait. In the simulator, explicit demo verdicts or bound recorded-image MUSE results can review an action; fresh simulated GREEN and accepted stop checks still gate entry. Independent scene inspection cannot supply either review or signal authority. Fresh post-action physical imagery remains future integration work.

## Component boundaries

| Directory | Intended ownership | Present state |
|---|---|---|
| [`frontend/`](../frontend/README.md) | English tablet workspace, graph routes, recorded frames, inspection, action-review input, approval and replay | React/TypeScript implementation; voice remains planned |
| [`backend/`](../backend/README.md) | API, temporary map graph, simulation, recorded-scene/action review, Meta adapters and evidence | FastAPI/Uvicorn, SQLite, OpenCV and NumPy |
| [`contracts/`](../contracts/README.md) | Workspace/map/scene snapshots, capabilities and source-labelled events | TypeScript DTOs; Pydantic request validation in backend |
| [`prompts/`](../prompts/README.md) | Model instructions and review expectations | Goal/scene instructions plus the action-review contract; complete template catalog remains later work |
| [`tools/`](../tools/) | Source checks, source packaging and local application startup | Implemented |
| [`tests/`](../tests/) | Release, provider-boundary, mission and API behavior | Offline automated suite |
| [`deploy/`](../deploy/README.md) | Separate GX10 releases and shared runtime state | Host inspected read-only; application not deployed |

Run `python tools/serve.py` after installing `requirements.lock` and building `frontend/dist`; see [Development](DEVELOPMENT.md). Python 3.12+ serves both API and compiled frontend. Node 24 is required only for frontend development/build. The repository is self-contained; parent planning files, old maps and historical operating archives are not build dependencies.

## Keep these distinctions visible

| Label | What it can establish |
|---|---|
| **Simulation** | Software behavior under generated actions and observations |
| **Recorded input** | Behavior on a previously captured image or event |
| **Real provider call** | An actual model request and response on the stated input |
| **Physical execution** | Hardware activity supported by corresponding measured evidence |

These describe separate parts of a run. For example, a real provider may review a recorded image while the robot remains simulated. One label must never silently upgrade the others.

## Decisions currently fixed

- Push the car on the surface; do not pick up or carry it.
- Stop before every configured intersection and evaluate its operator-switched paper signal.
- Include bounded push-to-talk goal entry through backend Meta transcription, editable text confirmation and typed fallback in the first demo. Explicit tablet mission approval remains separate.
- Use MUSE to interpret and review evidence; deterministic checks retain action admission authority.
- Keep the tablet interface English and follow the industrial light-dashboard [design system](DESIGN_SYSTEM.md). Label future wearable interaction as a concept.
- Use the replaceable temporary print adapter for simulation and explicitly labelled recorded-image overlays. Defer robot coordinates, production routes/registration, qualified stop lines, and live signal regions until the final installation is available.

For implementation priorities and the conditions that open later work, read the [roadmap](ROADMAP.md). For inherited work, rights and supported claims, read [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).

---

[← Back to PushPilot](../README.md) · [Next: architecture →](ARCHITECTURE.md)
