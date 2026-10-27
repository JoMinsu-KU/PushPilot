<sub>[PushPilot](../README.md) / Application / Frontend</sub>

# The operator workspace

**Look. Ask. Review. A shared plan, with its evidence in view.**

[Mission](../docs/MISSION.md) · [Architecture](../docs/ARCHITECTURE.md) · [Voice input](../docs/VOICE_INPUT.md) · [Development](../docs/DEVELOPMENT.md)

The first runnable workspace uses React, TypeScript and Vite. Its dark navy and electric cyan interface connects to the Python mission backend through the versioned [workspace contract](../contracts/workspace.ts). Production builds are static files served by that backend; GX10 does not need Node.js to run the built application.

## The experience

| Area | Implemented behavior |
| :--- | :--- |
| Goal | Editable typed input during preparation; explicit demo/MUSE interpreter selection. Provider availability comes from the backend. |
| Workspace | Original illustrative robot and wheel-less car scene, with separate image, pose, signal and robot source labels. |
| Plan | Symbolic PIZZA to BAKERY mission, bounded surface push, mandatory stop, signal admission and arrival review. |
| Approval | Explicit approval of the displayed plan identifier and revision. |
| Review | Expected and observed results, verdict, source and next required check. Demo verdict injection is visibly labelled. |
| Signal | RED, GREEN and UNKNOWN simulation inputs. The backend owns freshness, waiting and automatic crossing admission. |
| Replay | Inspectable event timeline and decision details. Replay cannot issue mission commands. |
| Companion | Clearly labelled future AR-glasses concept. |

This build has **no connected robot, camera, registered AR view or voice capture**. The scene is an original SVG illustration, not camera evidence. The symbolic plan contains no road coordinates. Demo review buttons do not call MUSE or claim image understanding. A configured Meta goal interpreter is a separate provider capability.

## Run locally

Use Node.js 24 or later to develop or build the frontend. Dependency versions and transitive packages are locked in `package-lock.json`.

```sh
cd frontend
npm ci
npm run dev
```

Vite listens on loopback port 5173 and proxies `/api` to the Python backend at `http://127.0.0.1:8080`. Start the backend separately as described in [Development](../docs/DEVELOPMENT.md).

```sh
npm run build
```

The build type-checks the source, then writes `frontend/dist`. Serve that bundle and the API from the same Python origin in production. There are no third-party fonts, image downloads or frontend provider credentials.

`npm test` verifies the request-identifier contract, including browsers on LAN HTTP where native `crypto.randomUUID` is unavailable. Distributed React, React DOM and Scheduler license texts are preserved in [`public/third-party-licenses.txt`](public/third-party-licenses.txt), which Vite copies into the production bundle.

## State and interaction boundaries

- Poll `/api/v1/state` for the authoritative snapshot. Ignore older revisions from the same session.
- Send a unique request identifier and the expected revision with every command. A stale-state response triggers a refresh and an explicit retry message.
- Accept goals during preparation only. Keep goal edits disabled throughout action, review and signal waits.
- Approve an exact plan before advancing its bounded simulation actions. Do not simulate successful reviews with timers.
- Show every independent source honestly. A successful model interpretation does not imply physical motion or a live observation.
- Keep microphone controls disabled until capture, normalization, transcription and target-device HTTPS are implemented and verified.

## Visual system

CSS Grid controls the workspace, scene, plan panel and companion cards. SVG view boxes control icons and arrows; text glyphs are not used to draw action arrows. The layout adapts from a tablet/desktop composition to stacked mobile panels without horizontal scrolling. Focus indicators, explicit button names, reduced-motion preferences and non-color status text support keyboard and assistive use.

Map artwork is intentionally absent from the production bundle. Temporary printed-map images may be introduced through a later source-labelled observation adapter, with an explicit map version and capture timestamp. They do not establish calibrated route geometry.
