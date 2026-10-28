<div align="center">

# PushPilot documentation

**Understand the mission. Inspect the decisions. Build within clear boundaries.**

[Repository](../README.md) · [Design system](DESIGN_SYSTEM.md) · [Architecture](ARCHITECTURE.md) · [Live intelligence](LIVE_INTELLIGENCE.md) · [Live camera](LIVE_CAMERA.md) · [Voice backend](VOICE_BACKEND.md) · [Mission](MISSION.md) · [Roadmap](ROADMAP.md)

</div>

---

PushPilot is being developed as a tablet workspace for an image-grounded tabletop robot mission. An operator states or types a goal, confirms the chosen text, reviews and approves the proposed task, and follows the evidence behind each decision to proceed, wait or observe again. A future glasses companion extends the interaction concept.

The current [visual direction](DESIGN_SYSTEM.md) follows the user's industrial references through a continuous scene, rounded translucent overlays, Pretendard typography and restrained orange accents. Earlier flat-light and navy/cyan screenshots document their original design stage and do not define the current interface composition.

**The application now implements explicit native-frame MUSE planning, action review and stopped-signal services alongside simulation and recorded-image review.** React/TypeScript and FastAPI/Uvicorn provide replaceable graph routes, SQLite supervision and source-labelled evidence. Preview polling remains ephemeral; deliberate live-intelligence requests separately select unchanged originals for inference and private evidence. The voice backend accepts bounded PCM WAV uploads and returns workspace-bound transcript candidates. Browser microphone capture is disconnected. Offline checks and [actual provider records](META_API_CHECK.md) retain separate scopes; real-car action/signal recognition, ASR access, robot registration, measured stopping and physical control remain unverified or unavailable.

## Choose a reading path

| Your goal | Start here | Continue with |
|---|---|---|
| Understand the product | [Mission](MISSION.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Confirm the intersection scenario | [MUSE signal gate](MUSE_SIGNAL_GATE.md) | Implemented native-frame judgments after simulated stop receipts; physical stopping remains unqualified |
| Follow MUSE route selection and native-frame reviews | [Live intelligence](LIVE_INTELLIGENCE.md) | [Live contracts](../contracts/live-intelligence.ts) and [backend](../backend/README.md) |
| Design the operator workspace | [Design system](DESIGN_SYSTEM.md) | [Frontend](../frontend/README.md) |
| Follow route progress or replace the drawing | [Route display](ROUTE_DISPLAY.md) | [Map validation and replacement](MAP_REPLACEMENT.md) |
| Use the placed City A3 print | [City A3](CITY_A3.md) | New places and shared Camera/Spatial drawing correspondence; physical geometry remains unqualified |
| Understand the system | [Architecture](ARCHITECTURE.md) | [Service composition](SERVICE_COMPOSITION.md) |
| Prepare isolated robot tests | [Robot commissioning](ROBOT_CONTROL.md) | [Dedicated GX10 delivery](../deploy/ROBOT_CONTROL.md); startup disarmed, no motion replay |
| Review voice goal entry | [Voice input](VOICE_INPUT.md) | [Finite-upload backend](VOICE_BACKEND.md); browser capture remains disconnected |
| Test Meta authentication and goal interpretation | [API connection check](META_API_CHECK.md) | [Meta intelligence](META_INTELLIGENCE.md) |
| Connect image judgment to a simulated action | [Live intelligence](LIVE_INTELLIGENCE.md) | [Explicit recorded-pair alternative](ACTION_REVIEWS.md) and [verification](VERIFICATION.md) |
| Test the temporary printed map | [Temporary map](TEMPORARY_MAP.md) | [Test inputs](TEST_INPUTS.md) and [verification](VERIFICATION.md) |
| Connect a preview-only live camera | [Live camera](LIVE_CAMERA.md) | [Development](DEVELOPMENT.md) and [verification](VERIFICATION.md) |
| Work on the repository | [Development workflow](DEVELOPMENT.md) | [Roadmap](ROADMAP.md) |
| Review a demonstration claim | [Evidence model](ARCHITECTURE.md#evidence-that-explains-a-decision) | [Contribution record](../CONTRIBUTIONS.md) |
| Inspect completed software checks | [Verification](VERIFICATION.md) | [Current workspace screenshot](assets/scene-workspace.jpg) |
| Prepare a release | [Development workflow](DEVELOPMENT.md) | [GX10 delivery plan](../deploy/README.md) |

## The interaction in one line

> **Observe → Plan → Approve → Act → Verify**
>
> Fresh observations and accepted checks determine the next action. Uncertainty stays visible and changes the workflow.

The mission begins at symbolic **PIZZA** and pushes a wheel-less car toward a selected destination. Every configured intersection requires a stop, even when its signal is already green. Red, unclear or stale signal observations mean wait. A live-backed plan uses server-bound native-image MUSE reviews and a current approach-specific MUSE GREEN after a matching simulated stop; separate demo missions retain explicit demo/recorded review and injected simulation signals. Independent scene inspection cannot advance either path. Native images do not establish physical robot completion, measured vehicle position or actual stopping.

## Component boundaries

| Directory | Intended ownership | Present state |
|---|---|---|
| [`frontend/`](../frontend/README.md) | English tablet workspace, camera/recorded sources, route progress, model evidence, approval and replay | React/TypeScript implementation; full live-operation controls and browser voice capture still need integration |
| [`backend/`](../backend/README.md) | Live frame/graph planning, native/recorded review, MUSE signal judgments, simulation supervision, finite voice uploads and evidence | FastAPI/Uvicorn, SQLite, OpenCV and NumPy; offline service/provider tests |
| [`contracts/`](../contracts/README.md) | Workspace/map/scene/preview/live-intelligence DTOs, capabilities and source-labelled events | TypeScript interfaces plus backend request validation; voice multipart contract documented separately |
| [`prompts/`](../prompts/README.md) | Model instructions and review expectations | Goal/scene instructions plus the action-review contract; complete template catalog remains later work |
| [`tools/`](../tools/) | Source checks, packaging, local application startup and an explicitly started standalone native camera helper | Implemented; preview helper is separate from application deployment |
| [`tests/`](../tests/) | Release, provider-boundary, mission and API behavior | Offline automated suite |
| [`deploy/`](../deploy/README.md) | Separate GX10 releases and shared runtime state | Isolated frontend/API release and independent camera helper verified on October 28; see deployment evidence |

Run `python tools/serve.py` after installing `requirements.lock` and building `frontend/dist`; see [Development](DEVELOPMENT.md). Python 3.12+ serves both API and compiled frontend. Node 24 is required only for frontend development/build. The repository is self-contained; parent planning files, old maps and historical operating archives are not build dependencies.

## Keep these distinctions visible

| Label | What it can establish |
|---|---|
| **Simulation** | Software behavior under generated actions and observations |
| **Recorded input** | Behavior on a previously captured image or event |
| **Live preview** | A current source-labelled camera display within its stated age limit; not a qualified action observation |
| **Selected native evidence** | An original live frame bound to a deliberate inference request; it does not prove a physical action or stop |
| **Real provider call** | An actual model request and response on the stated input |
| **Physical execution** | Hardware activity supported by corresponding measured evidence |

These describe separate parts of a run. For example, a real provider may review a recorded image while the robot remains simulated. One label must never silently upgrade the others.

## Decisions currently fixed

- Push the car on the surface; do not pick up or carry it.
- Stop before every configured intersection and evaluate its operator-switched paper signal.
- Include bounded push-to-talk goal entry through backend Meta transcription, editable text confirmation and typed fallback in the first demo. Explicit tablet mission approval remains separate.
- Use MUSE to interpret and review evidence; deterministic checks retain action admission authority.
- Keep the tablet interface English and follow the industrial light-dashboard [design system](DESIGN_SYSTEM.md). Label future wearable interaction as a concept.
- Use the replaceable map adapter for simulation and explicitly labelled image overlays. Validate proposed definitions without installing them; configure reviewed paper-signal regions per approach before live signal testing. Defer robot coordinates, final production geometry/registration and qualified stop lines until the physical installation is available.
- Keep location labels, destination vocabulary and route geometry in the selected map definition. Replacing it requires a new plan and reviewed display registration; simulated AR progress never supplies measured car pose.

For implementation priorities and the conditions that open later work, read the [roadmap](ROADMAP.md). For inherited work, rights and supported claims, read [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).

---

[← Back to PushPilot](../README.md) · [Next: architecture →](ARCHITECTURE.md)
