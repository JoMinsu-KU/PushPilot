<sub>[PushPilot](../README.md) / [Documentation](README.md) / Development</sub>

# Run the temporary-map workspace

**Build the operator interface, run one Python service, and verify each simulated decision.**

[Architecture](ARCHITECTURE.md) · [Services](SERVICE_COMPOSITION.md) · [Voice input](VOICE_INPUT.md) · [Roadmap](ROADMAP.md) · [Deployment](../deploy/README.md)

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

The launcher defaults to loopback and one worker. It has no reload loop, dependency installer, provider preflight, robot connection, camera ownership, service-manager integration, or GX10 transfer. Set an unused port explicitly when necessary:

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

`PUSHPILOT_LIVE_CAMERA_URL` is an explicit process-environment opt-in, also accepted through `--live-camera-url`. It names an existing numeric loopback HTTP preview service with a port; it is not a camera device selector or a startup command. Do not put private device identities or connection details in committed configuration. Live display locks and frames remain in memory and disappear on application restart.

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

| Area | Current boundary |
| :--- | :--- |
| Map | Replaceable temporary drawing graph and board-to-image test overlays. Production routes, robot/BASE transforms, qualified stop lines, and live signal ROIs remain unresolved. |
| Hardware | No robot transport, physical execution, profile replay, mailbox restoration or existing operating-service restart. The optional explicitly started standalone helper owns only its selected camera and `ffmpeg` child. |
| Live preview | Ephemeral native JPEG display, source/age labels and explicit fixed display lock. It does not mutate mission/evidence state, call MUSE or qualify robot observations. |
| Signals | Simulated source only in this slice. Full stop even on GREEN; RED, unknown, stale, and obscured observations must inhibit physical admission later. |
| Review | Scene-only inspection cannot advance actions. Bound recorded-pair MUSE results can review simulation alongside explicit demo inputs; live receipt-bound capture and physical checks remain future work. |
| Voice | Planned bounded backend Meta transcription, editable transcript confirmation, common goal interpretation, and explicit plan approval. Capture and normalization are not established by this slice. |
| Models | Validated goal interpretation; no generated robot scripts or authoritative coordinates. |
| Evidence | Source-labelled event history. A provider call is not evidence of physical execution. |
| Stops | UI HOLD and process exit do not imply immediate in-flight robot stopping. |

Push-to-talk will require trusted target-device HTTPS, secure-context and permission checks, bounded recordings normalized to Meta's supported mono 16-bit PCM WAV, cancellation, and late-result rejection. New goals remain restricted to non-executing preparation. Streaming and speech output remain later options.

## State and restart

Runtime state belongs in ignored `runtime/` locally or dedicated shared storage on GX10. SQLite contains mission state/events and command receipts; the private scene directory contains frames, hashes, map/reference bindings, and validated inspection records. Preserve both deliberately across updates, restrict access, and apply a reviewed media retention policy. A rollback must not overwrite newer history.

After restart, an active mission enters non-executing recovery. Pending work, admitted crossings, previous approval, and old GREEN observations do not automatically regain authority. Reconcile or terminate the prior simulation explicitly before starting another.

---

[Frontend](../frontend/README.md) · [Backend](../backend/README.md) · [Contracts](../contracts/README.md) · [Prompts](../prompts/README.md) · [Tests](../tests/README.md)
