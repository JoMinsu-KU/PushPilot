<sub>[PushPilot](../README.md) / [Documentation](README.md) / Development</sub>

# Build the workspace, select the execution scope

**Build the operator interface, run one Python service, and keep execution sources explicit.**

[Architecture](ARCHITECTURE.md) · [Services](SERVICE_COMPOSITION.md) · [Voice input](VOICE_INPUT.md) · [Roadmap](ROADMAP.md) · [Deployment](../deploy/README.md)

## Current source scope · November 2, 2026

The public clone starts equipment-free simulation by default. The configured City deployment uses `seoul-city-a3` v`2026-10-28.4`, with Pizza-front departure and Office Building/Villa/Hanok destinations. Select the reviewed JSON explicitly through `PUSHPILOT_MAP_PATH`; Little Town remains the default compatibility example used below.

Physical site-trial code is implemented separately under `/api/v1/physical/*`. It requires explicit private `PUSHPILOT_PHYSICAL_CONFIG`, taught packet/review geometry, verified controller runtime, profiles, source-bound receiver state and installed camera/signal configuration. These are intentionally not published in a public clone. Read [Current status](CURRENT_STATUS.md), [Robot operations](ROBOT_OPERATIONS.md) and [deployment prerequisites](../deploy/ROBOT_CONTROL.md) before configuring equipment access. A successful source build alone cannot reproduce the installed Robot mode.

The initial November 2 publication recorded 1,177 backend tests run with five skipped, 126 frontend tests and a successful build. The later Native recovery source `bcac769` recorded 1,199 backend tests/five skipped, 143 frontend tests, zero failures and a passing build. These are separate software checkpoints in [Verification](VERIFICATION.md), not perception or physical-repeatability measurements. No provider or hardware call is required to check documentation or the default offline suite.

## Runtime and dependency setup

This is the independent application repository. It runs with the sanitized temporary map data in `backend/data/little-town-temporary.json`, without private planning material, handoff archives, original map artwork, raw camera photos, or historical robot profiles.

| Requirement | Purpose |
| :--- | :--- |
| Python 3.12+ | FastAPI/Uvicorn, SQLite, OpenCV marker detection and NumPy geometry. GX10 has Python 3.12.3; isolated ARM64 dependency installation and application startup were verified on October 28. |
| Node 24 and npm | Build or develop the React/TypeScript frontend locally. GX10 serves compiled assets without Node. |
| Git on `PATH` | Reviewed source identity, source packaging, and isolated release tests. |
| `requirements.lock` and `frontend/package-lock.json` | Exact Python and frontend dependency versions. |

Create an isolated Python environment from the repository root.

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
```

On Linux or macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Activate the environment using your shell's normal mechanism, or substitute its Python executable in subsequent commands. Installing from the lockfile requires package-registry access; normal offline tests do not call providers.

## Build and run one origin

```sh
cd frontend
npm ci
npm run build
cd ..
python tools/serve.py
```

Open `http://127.0.0.1:8080`. The same Python process serves `frontend/dist` and `/api`; no frontend development server is required. `GET /api/health` identifies simulation with robot/qualified hardware disconnected and separately reports `camera_preview_connected` when an opt-in preview is live.

With optional equipment configuration absent, the launcher defaults to loopback and one worker, with no robot connection or camera ownership. It has no reload loop, dependency installer, automatic provider preflight, service-manager activation or GX10 transfer. Explicit physical configuration enables driver readiness/status access; process startup still does not authorize or dispatch motion. Set an unused port explicitly when necessary:

```sh
python tools/serve.py --host 127.0.0.1 --port 8080
```

A missing frontend build fails early. Backend-only work can use `python tools/serve.py --api-only`. Keep `workers=1`: the SQLite supervisor in this first slice is a single-process application.

For frontend development, run the API with `--api-only` in one terminal and `npm run dev` in `frontend` in another. Vite binds to loopback on port 5173 and proxies `/api` to `http://127.0.0.1:8080`. If the backend port changes, update the explicit proxy configuration too. Use `npm run build` to type-check and produce the delivery assets before review.

## Optional live preview

Live preview is disabled by default. After deliberately starting the separate native camera helper and loopback SSH forward, opt in to the already-running service:

```sh
python tools/serve.py --port 8893 --live-camera-url http://127.0.0.1:8895
```

This launcher does not start a camera process. [`Live camera`](LIVE_CAMERA.md) documents the explicit Linux helper, numeric-loopback URL restriction, native JPEG transport, eight-frame RAM cache, age semantics and fixed display lock. This is the Windows development arrangement. The deployed GX10 frontend/API instead uses host loopback to the existing helper; see [deployment verification](VERIFICATION.md#gx10-application-deployment-october-28). Live/Recorded selection does not turn Image tools into live review: recorded tools use immutable uploaded frames, while explicit live-intelligence operations select their own native observations. Neither path establishes qualified physical action observations.

## Verify the first connected slice

The workspace connects a typed destination to a deterministic temporary-map route, explicit approval, simulated actions, per-junction mandatory stops and signal waits, action reviews and evidence. Supported destinations are BAKERY, BOOKSTORE and SCHOOL from east-facing PIZZA. Simulated signals and operator-injected demo verdicts remain labelled. Actual Meta requests support goals, independent scene inspection and recorded before/after action review. Only the action-bound path can satisfy a pending simulated review; none grants physical execution authority.

Use a separate test database when exploring restart and fault behavior:

```sh
python tools/serve.py --state-path ../pushpilot-test-state/workspace.sqlite3
```

The path is resolved relative to the calling directory. It is never part of a source release. No real credential is required to use the demo simulator.

1. Submit a Bakery goal in demo mode and inspect the resulting plan.
2. Approve the exact current plan, then advance one simulated action.
3. Observe the required review and explicitly supply a labelled demo verdict.
4. Complete the mandatory stop and its review. RED or UNKNOWN must retain the wait.
5. Supply fresh simulated GREEN. An accepted stopped review permits automatic crossing; no repeated approval is required.
6. Review the crossing, then repeat the approach/stop/review/signal cycle at the next junction. Earlier stop evidence and GREEN cannot authorize another junction. Review final verification and inspect the event history.
7. Restart during an active mission using the same test state. Recovery must require reconciliation and must not resume old work automatically.

These checks establish graph-based simulation only. Drawing lengths are not robot targets or measured vehicle travel. They do not qualify pushing, turning, physical signal perception, robot registration, or stopping.

## Inspect a temporary printed-map image

Use [Temporary map](TEMPORARY_MAP.md) and [Test inputs](TEST_INPUTS.md) for print/capture requirements. Upload JPEG/PNG through the recorded-frame control; the backend accepts at most 8 MiB and 12 megapixels, with at least 32 pixels per side. An optional capture timestamp must include its timezone and remains operator-provided; upload time does not establish live freshness.

A full four-marker detection produces a registration candidate. Explicitly lock that recorded view before displaying a projected route. Later partial visibility retains the reference without refitting; inconsistent/missing reference evidence withholds the overlay. This is drawing-board-to-image projection, never a robot/BASE transform.

With MUSE configured, explicitly submit an expectation for the current frame. Independent inspection can report USABLE/REOBSERVE/UNKNOWN, visible places, whether a separate 3D car is visible and whether a separate paper signal is identifiable. It does not complete a mission step or supply the signal gate.

For a pending simulated action, open **Visual action review** to pin BEFORE, upload AFTER, describe the expected visual outcome and explicitly choose **Review action with MUSE**. This separate action-bound endpoint can apply PASS/FAIL/REOBSERVE/UNKNOWN through the supervisor. Review its independent source labels and record; selected uploads are not trusted physical capture windows, and preview frames are not automatically selected as evidence. [Action reviews](ACTION_REVIEWS.md) documents the complete workflow and the optional synthetic provider-evaluation harness. Actual results belong in [verification](VERIFICATION.md).

## Checks and tests

```sh
python tools/dev.py check
python tools/dev.py test
cd frontend
npm run build
```

`check` parses Python and JSON source without loading credentials. `test` runs offline release-boundary, connection-tool, mission, temporary-map, recorded-scene, and API tests with isolated test state. Provider behavior is injected in tests; the suite must not read the operator's real `.env` or contact equipment. Frontend build validation checks TypeScript and bundle generation. Visual review at desktop and tablet widths remains necessary for spacing, arrows, and readable state labels.

The separate [Meta connection check](META_API_CHECK.md) makes a real provider request only when deliberately invoked. A successful connection check establishes endpoint access, not model judgment quality.

## Credentials and configuration

`.env.example` contains empty placeholders. The backend reads `META_API_KEY` from its process environment or repository-local ignored `.env` when the ASGI application starts. It does not make an automatic provider request at startup. Enter credentials directly into that local file or the host's restricted configuration through the existing direct-input workflow.

`PUSHPILOT_STATE_PATH` selects SQLite; the launcher also exposes `--state-path`. The default is ignored `runtime/workspace.sqlite3`. `PUSHPILOT_SCENE_DIR` optionally selects private frame/registration/inspection storage; by default it is `scene/` beside the SQLite file. `PUSHPILOT_MAP_PATH` selects a validated, explicitly temporary map JSON, defaulting to the bundled sanitized definition. Restart with deliberate state reconciliation after changing map configuration; incompatible plan/registration hashes cannot carry over. `PUSHPILOT_FRONTEND_DIST` is an optional process-environment asset-directory override. Credentials, private frames, configuration and runtime state must not enter browser build variables, Git, source packages, or public screenshots.

`PUSHPILOT_LIVE_CAMERA_URL` is an explicit process-environment opt-in, also accepted through `--live-camera-url`. It names an existing numeric loopback HTTP preview service with a port; it is not a camera device selector or a startup command. Do not put private device identities or connection details in committed configuration. Preview frames remain bounded RAM. A fixed display reference can have a private persisted receipt and explicit checked resume after application memory is lost; this restores neither physical coordinates nor old plan/signal authority. See [Live camera](LIVE_CAMERA.md).

`PUSHPILOT_PHYSICAL_CONFIG` is a separate process-environment path to a private site-trial configuration. Do not place route coordinates, hardware credentials, profiles or runtime archives in `.env.example` or public JSON. An enabled driver may access equipment readiness/status; startup does not run a mission. To develop without equipment, leave this setting absent and use isolated state. Robot mode has its own physical revision and source binding rather than changing the legacy simulation capability flags.

## Repository discipline

Source, identifiers, comments, logs, prompts, UI copy, accessibility text, errors, and development documentation are English. Original-language transcripts and goal text are user data. User discussion may remain Korean.

Commit source, contracts, versioned prompts, lockfiles, meaningful tests, and reviewed examples. Keep credentials, private images, generated dependencies, compiled assets, runtime logs, operating profiles, mailboxes, and raw archives outside Git and source releases.

Inspect current status and remotes before preparing a snapshot:

```sh
git status --short --branch
git remote -v
```

Use the user's actual Git identity and the real contribution date. Record reused work and exact changes in [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md). An import does not automatically acquire publication rights or become newly authored.

## Prepare a source release

Review and commit intended source first. The builder requires a clean committed HEAD, including no staged or nonignored untracked work. Create the output directory outside the repository:

```sh
python -c "from pathlib import Path; Path('../release-bundles').mkdir(parents=True, exist_ok=True)"
python tools/build_release.py --output ../release-bundles/pushpilot-source-v0.1.0.zip
python tools/build_release.py --verify ../release-bundles/pushpilot-source-v0.1.0.zip
```

The builder refuses an existing output path. The manifest binds committed source and hashes; verification checks integrity and path policy without extraction. Neither step transfers files, starts a service, authenticates a publisher, or establishes publication rights. Ignored `frontend/dist` is absent: each GX10 release needs compiled assets built from that same clean commit in addition to source. See [GX10 deployment](../deploy/README.md).

## Boundaries and next implementation work

The [review follow-up](REVIEW_FOLLOW_UP.md) records open Start/Stop concurrency, duplicate physical Stop side effects, synchronous symbolic Meta inference, general request deadlines/polling and full CI work. These are documented findings and proposed acceptance checks, not newly implemented or independently rerun results. This update changes Markdown only.

| Area | Current boundary |
| :--- | :--- |
| Map | Replaceable City/Little Town drawing graph and board-to-image display overlays; physical recipes remain private taught BASE data, separate from display geometry. General calibration qualification is open. |
| Hardware | Default startup is equipment-free. Explicit site-trial configuration enables separate driver/API/receiver access; never restore old profiles, mailboxes or unknown commands as part of development. |
| Live preview | Ephemeral native JPEG display, source/age labels and explicit fixed display lock. It does not mutate mission/evidence state, call MUSE or qualify robot observations. |
| Signals | Simulation has per-junction gates. Configured physical `single_departure` uses one accepted stopped GREEN, measured recontact and continuation without a second color wait; new missions need new admission. |
| Review | Scene-only inspection cannot advance actions. Simulation and physical Native/MUSE review keep separate receipts and authority; C-specific progress/arrival policies have narrow documented scope. |
| Voice | Finite supported PCM upload/transcription and bound candidates are implemented. Browser capture/PCM encoding/editor, trusted tablet HTTPS and actual ASR acceptance remain pending. |
| Models | Validated goal interpretation; no generated robot scripts or authoritative coordinates. |
| Evidence | Source-labelled event history. A provider call is not evidence of physical execution. |
| Stops | UI HOLD and process exit do not imply immediate in-flight robot stopping. |

Push-to-talk will require trusted target-device HTTPS, secure-context and permission checks, bounded recordings normalized to Meta's supported mono 16-bit PCM WAV, cancellation, and late-result rejection. New goals remain restricted to non-executing preparation. Streaming and speech output remain later options.

## State and restart

Runtime state belongs in ignored `runtime/` locally or dedicated shared storage on GX10. SQLite contains mission state/events and command receipts; the private scene directory contains frames, hashes, map/reference bindings, and validated inspection records. Preserve both deliberately across updates, restrict access, and apply a reviewed media retention policy. A rollback must not overwrite newer history.

After restart, active work remains non-executing. Pending commands, admitted crossings, previous approval and old GREEN observations do not automatically regain authority. Simulation reconciliation and physical reset/resume are separate operations. Never automatically replay an unknown motion; follow [Robot operations](ROBOT_OPERATIONS.md) for exact completed-boundary continuation and START preparation. The separate host's [legal-idle Native recovery](HOST_NATIVE_RECOVERY.md) is implemented/deployed, with one actual same-session timeout recovery recorded; it requires new stationary telemetry and does not repair every protocol phase or replay a target. An actual disconnect still requires explicit connection/source preparation. An HTTP HOLD is not a hardware emergency stop.

---

[Frontend](../frontend/README.md) · [Backend](../backend/README.md) · [Contracts](../contracts/README.md) · [Prompts](../prompts/README.md) · [Tests](../tests/README.md)
