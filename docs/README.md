<div align="center">

# PushPilot documentation

**Understand the mission. Inspect the decisions. Build within clear boundaries.**

[Repository](../README.md) · [Architecture](ARCHITECTURE.md) · [Mission](MISSION.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Roadmap](ROADMAP.md)

</div>

---

PushPilot is being developed as a tablet workspace for an image-grounded tabletop robot mission. An operator states a goal, reviews the proposed task, and follows the evidence behind each decision to proceed, wait or observe again. A future glasses companion extends the interaction concept.

**The repository currently contains the application bootstrap and design documentation.** The mission runtime, frontend, Meta integration and physical robot connection are planned. Final map geometry and installation are unresolved, so implementation begins with symbolic locations and explicitly simulated actions.

## Choose a reading path

| Your goal | Start here | Continue with |
|---|---|---|
| Understand the product | [Mission](MISSION.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Understand the system | [Architecture](ARCHITECTURE.md) | [Component boundaries](#component-boundaries) |
| Test Meta authentication and text inference | [API connection check](META_API_CHECK.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Work on the repository | [Development workflow](DEVELOPMENT.md) | [Roadmap](ROADMAP.md) |
| Review a demonstration claim | [Evidence model](ARCHITECTURE.md#evidence-that-explains-a-decision) | [Contribution record](../CONTRIBUTIONS.md) |
| Prepare a release | [Development workflow](DEVELOPMENT.md) | [GX10 delivery plan](../deploy/README.md) |

## The interaction in one line

> **Observe → Plan → Approve → Act → Verify**
>
> Fresh observations and accepted checks determine the next action. Uncertainty stays visible and changes the workflow.

The current mission begins at symbolic **PIZZA** and pushes a wheel-less car toward a selected destination. At every configured intersection, the car stops before the stop line, even when the signal is already green. Red, unclear or stale signal observations mean wait. Fresh green and accepted checks permit entry. Each bounded action is followed by image-grounded review.

## Component boundaries

| Directory | Intended ownership | Present state |
|---|---|---|
| [`frontend/`](../frontend/README.md) | English tablet workspace, operator review and replay | Boundary documentation |
| [`backend/`](../backend/README.md) | Mission supervisor, observations, Meta adapter and evidence | Boundary documentation |
| [`contracts/`](../contracts/README.md) | Versioned requests, results and source-labelled events | Boundary documentation |
| [`prompts/`](../prompts/README.md) | Versioned English model prompts and review expectations | Boundary documentation |
| [`tools/`](../tools/) | Equipment-free source checks and release packaging | Implemented bootstrap tools |
| [`tests/`](../tests/) | Bootstrap checks; later application behavior tests | Bootstrap tests |
| [`deploy/`](../deploy/README.md) | Separate GX10 releases and shared runtime state | Proposal and examples |

Frameworks, application startup commands and executable API contracts will be documented when their implementations are added. The repository is self-contained; parent planning files, old maps and historical operating archives are not build dependencies.

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
- Use MUSE to interpret and review evidence; deterministic checks retain action admission authority.
- Keep the tablet interface English, with dark navy and electric cyan. Label future wearable interaction as a concept.
- Defer map coordinates, routes, registration, stop lines, signal regions and spatial AR until the final installation is available.

For implementation priorities and the conditions that open later work, read the [roadmap](ROADMAP.md). For inherited work, rights and supported claims, read [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).

---

[← Back to PushPilot](../README.md) · [Next: architecture →](ARCHITECTURE.md)
