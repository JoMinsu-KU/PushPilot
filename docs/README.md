<div align="center">

# PushPilot documentation

**Understand the mission. Inspect the decisions. Build within clear boundaries.**

[Repository](../README.md) · [Architecture](ARCHITECTURE.md) · [Services](SERVICE_COMPOSITION.md) · [Voice input](VOICE_INPUT.md) · [Mission](MISSION.md) · [Roadmap](ROADMAP.md)

</div>

---

PushPilot is being developed as a tablet workspace for an image-grounded tabletop robot mission. An operator states or types a goal, confirms the chosen text, reviews and approves the proposed task, and follows the evidence behind each decision to proceed, wait or observe again. A future glasses companion extends the interaction concept.

**The first map-independent application slice is implemented.** It contains a React/TypeScript workspace, a FastAPI/Uvicorn backend, a SQLite mission supervisor, explicitly simulated actions/signals/reviews, evidence history, and a backend Meta goal interpreter. Typed goals can prepare a symbolic BAKERY plan; explicit approval remains separate. Voice, image review, camera input, registered AR, and physical robot control are not implemented. Final map geometry and installation remain unresolved.

## Choose a reading path

| Your goal | Start here | Continue with |
|---|---|---|
| Understand the product | [Mission](MISSION.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Understand the system | [Architecture](ARCHITECTURE.md) | [Service composition](SERVICE_COMPOSITION.md) |
| Review voice goal entry | [Voice input](VOICE_INPUT.md) | [Frontend](../frontend/README.md) and [contracts](../contracts/README.md) |
| Test Meta authentication and goal interpretation | [API connection check](META_API_CHECK.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Prepare a temporary printed vision input | [Test inputs](TEST_INPUTS.md) | [Map boundary](ARCHITECTURE.md#map-and-physical-integration-boundary) |
| Work on the repository | [Development workflow](DEVELOPMENT.md) | [Roadmap](ROADMAP.md) |
| Review a demonstration claim | [Evidence model](ARCHITECTURE.md#evidence-that-explains-a-decision) | [Contribution record](../CONTRIBUTIONS.md) |
| Inspect completed software checks | [Verification](VERIFICATION.md) | [Actual workspace screenshot](assets/workspace-simulation.jpg) |
| Prepare a release | [Development workflow](DEVELOPMENT.md) | [GX10 delivery plan](../deploy/README.md) |

## The interaction in one line

> **Observe → Plan → Approve → Act → Verify**
>
> Fresh observations and accepted checks determine the next action. Uncertainty stays visible and changes the workflow.

The current mission begins at symbolic **PIZZA** and pushes a wheel-less car toward a selected destination. At every configured intersection, the car stops before the stop line, even when the signal is already green. Red, unclear or stale signal observations mean wait. Fresh green and accepted checks permit entry. Each bounded action is followed by image-grounded review.

## Component boundaries

| Directory | Intended ownership | Present state |
|---|---|---|
| [`frontend/`](../frontend/README.md) | English tablet workspace, typed goals, approval, simulation state and replay | React/TypeScript implementation; voice remains planned |
| [`backend/`](../backend/README.md) | API, supervisor, symbolic simulation, Meta goal interpretation and evidence | FastAPI/Uvicorn and SQLite implementation |
| [`contracts/`](../contracts/README.md) | Requests, snapshots, capabilities and source-labelled events | TypeScript DTOs; Pydantic request validation in backend |
| [`prompts/`](../prompts/README.md) | Model instructions and review expectations | Goal prompt inline in backend; versioned review templates planned |
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
- Keep the tablet interface English, with dark navy and electric cyan. Label future wearable interaction as a concept.
- Defer map coordinates, routes, registration, stop lines, signal regions and spatial AR until the final installation is available.

For implementation priorities and the conditions that open later work, read the [roadmap](ROADMAP.md). For inherited work, rights and supported claims, read [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).

---

[← Back to PushPilot](../README.md) · [Next: architecture →](ARCHITECTURE.md)
