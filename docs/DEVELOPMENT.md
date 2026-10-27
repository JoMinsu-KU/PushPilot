<sub>[PushPilot](../README.md) / [Documentation](README.md) / Development</sub>

# Run the map-independent workspace

**Build the operator interface, run one Python service, and verify each simulated decision.**

[Architecture](ARCHITECTURE.md) · [Services](SERVICE_COMPOSITION.md) · [Voice input](VOICE_INPUT.md) · [Roadmap](ROADMAP.md) · [Deployment](../deploy/README.md)

## Runtime and dependency setup

This is the independent application repository. It must run without private planning material, handoff archives, historical previews, map assets, or operating evidence.

| Requirement | Purpose |
| :--- | :--- |
| Python 3.12+ | FastAPI/Uvicorn API, SQLite mission state, tooling, and offline tests. GX10 has Python 3.12.3. |
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

Open `http://127.0.0.1:8080`. The same Python process serves `frontend/dist` and `/api`; no frontend development server is required. `GET /api/health` identifies the service as simulation with hardware disconnected.

The launcher defaults to loopback and one worker. It has no reload loop, dependency installer, provider preflight, robot connection, camera ownership, service-manager integration, or GX10 transfer. Set an unused port explicitly when necessary:

```sh
python tools/serve.py --host 127.0.0.1 --port 8080
```

A missing frontend build fails early. Backend-only work can use `python tools/serve.py --api-only`. Keep `workers=1`: the SQLite supervisor in this first slice is a single-process application.

For frontend development, run the API with `--api-only` in one terminal and `npm run dev` in `frontend` in another. Vite binds to loopback on port 5173 and proxies `/api` to `http://127.0.0.1:8080`. If the backend port changes, update the explicit proxy configuration too. Use `npm run build` to type-check and produce the delivery assets before review.

## Verify the first connected slice

The initial workspace connects a typed goal, symbolic plan, explicit approval, simulated bounded actions, mandatory stop, signal waiting, review decisions, and immutable evidence. Simulated signals and manually injected demo reviews are labelled as such. A backend Meta goal request is a distinct opt-in provider operation, with server-held credentials; it does not establish image review or physical execution.

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
6. Review the crossing and final verification. Inspect the evidence history for the source and cause of each decision.
7. Restart during an active mission using the same test state. Recovery must require reconciliation and must not resume old work automatically.

These checks establish the software simulation flow. They do not qualify pushing, turning, signal perception, map registration, or actual robot stopping. The UI and capability response must keep those unavailable capabilities explicit.

## Checks and tests

```sh
python tools/dev.py check
python tools/dev.py test
cd frontend
npm run build
```

`check` parses Python and JSON source without loading credentials. `test` runs offline release-boundary, connection-tool, mission, and API tests with isolated test state. Provider behavior is injected in tests; the suite must not read the operator's real `.env` or contact equipment. Frontend build validation checks TypeScript and bundle generation. Visual review at desktop and tablet widths remains necessary for spacing, arrows, and readable state labels.

The separate [Meta connection check](META_API_CHECK.md) makes a real provider request only when deliberately invoked. A successful connection check establishes endpoint access, not model judgment quality.

## Credentials and configuration

`.env.example` contains empty placeholders. The backend reads `META_API_KEY` from its process environment or repository-local ignored `.env` when the ASGI application starts. It does not make an automatic provider request at startup. Enter credentials directly into that local file or the host's restricted configuration through the existing direct-input workflow.

`PUSHPILOT_STATE_PATH` selects the SQLite file; the launcher also exposes `--state-path`. The default is ignored `runtime/workspace.sqlite3`. Credentials, configuration files, and state must not enter browser build variables, Git, source packages, or screenshots.

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

The builder refuses an existing output path. The manifest binds committed source and hashes; verification checks integrity and path policy without extraction. Neither step transfers files, starts a service, authenticates a publisher, or establishes publication rights. Ignored `frontend/dist` is absent: a future GX10 release needs compiled assets built from that same clean commit in addition to source. See [GX10 deployment](../deploy/README.md).

## Boundaries and next implementation work

| Area | Current boundary |
| :--- | :--- |
| Map | Symbolic locations and abstract actions. Final routes, metric coordinates, registration, stop lines, and signal ROIs remain deferred. User-provided images may be labelled temporary vision fixtures. |
| Hardware | No robot transport, physical execution, profile replay, mailbox restoration, camera ownership, or operating-service restart. |
| Signals | Simulated source only in this slice. Full stop even on GREEN; RED, unknown, stale, and obscured observations must inhibit physical admission later. |
| Review | Demo verdicts are manually injected. Live-image MUSE review and independent local perception need separate implementation and validation. |
| Voice | Planned bounded backend Meta transcription, editable transcript confirmation, common goal interpretation, and explicit plan approval. Capture and normalization are not established by this slice. |
| Models | Validated goal interpretation; no generated robot scripts or authoritative coordinates. |
| Evidence | Source-labelled event history. A provider call is not evidence of physical execution. |
| Stops | UI HOLD and process exit do not imply immediate in-flight robot stopping. |

Push-to-talk will require trusted target-device HTTPS, secure-context and permission checks, bounded recordings normalized to Meta's supported mono 16-bit PCM WAV, cancellation, and late-result rejection. New goals remain restricted to non-executing preparation. Streaming and speech output remain later options.

## State and restart

Runtime state belongs in ignored `runtime/` locally or dedicated shared storage on GX10. The SQLite database contains mission state and append-only evidence events. Preserve it across a code update, restrict access, and back it up deliberately. A rollback must not overwrite newer history.

After restart, an active mission enters non-executing recovery. Pending work, admitted crossings, previous approval, and old GREEN observations do not automatically regain authority. Reconcile or terminate the prior simulation explicitly before starting another.

---

[Frontend](../frontend/README.md) · [Backend](../backend/README.md) · [Contracts](../contracts/README.md) · [Prompts](../prompts/README.md) · [Tests](../tests/README.md)
