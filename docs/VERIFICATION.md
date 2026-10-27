# First workspace verification

Verified on **2026-10-27, Asia/Seoul**. This record covers the first map-independent software slice; it is not a physical mission report.

| Check | Result | Boundary |
|---|---|---|
| `python tools/dev.py check` | Passed | Python and JSON source syntax; no credentials loaded |
| `python tools/dev.py test` | 49 passed | Release integrity, connection checker, mission core and API/provider tests |
| `npm test` in `frontend` | 3 passed | Valid command UUIDs on native, LAN HTTP and minimal browser paths |
| `npm run build` in `frontend` | Passed | TypeScript checking and Vite production bundle |
| Real Meta application-goal request | HTTP 200, `PLAN_READY` | One strict-schema text request; [details](META_API_CHECK.md) |
| Combined Python service | Passed | Built UI and API served from one loopback origin |
| Browser mission flow | Passed | Demo goal → approval → push review → mandatory stop review → RED wait → GREEN auto-admission → crossing review → destination review → completion |
| Browser evidence replay | Passed | Source-labelled events and read-only event detail; no execution controls in replay |
| Responsive browser checks | Passed | 1440×1000, 1280×800, 1024×768 and 390×844; no horizontal overflow of visible buttons, inputs, selects or SVGs |
| Browser console | No errors observed | Verified software session; not a full browser/device matrix |
| GX10 compatibility preparation | Dependency wheels resolved | CPython 3.12 Linux ARM64 packages downloaded locally; no GX10 installation or application execution claimed |

The local verification host used Windows CPython 3.14 and Node 24.19. The GX10 was inspected read-only: Ubuntu 24.04.4, ARM64, Python 3.12.3 and no Node/npm on its command path. The deployment design builds frontend assets locally and serves them from Python on GX10.

## Meaningful failure-path coverage

Offline tests cover stale revisions, request identity reuse, exact approval identity, blocked goal replacement during an active mission, required per-action review, GREEN without verified stopping, RED/UNKNOWN/stale signal inhibition, uncertain reobservation, explicit failure, restart recovery and provider rejection without a demo fallback. Test providers and databases are isolated; the ordinary suite never reads the operator's real key or contacts a model.

Visual review also found and corrected a LAN HTTP fallback that initially produced non-UUID command IDs and mobile footer wrapping. The final fallback tests enforce the API UUID contract.

## Limits and next validation

- Robot, camera, pose registration, spatial AR, image review and voice capabilities are unavailable in this version. Demo verdicts and paper-signal stand-ins remain explicitly simulated.
- The supplied [temporary print candidate](TEST_INPUTS.md) was inspected as a document. No camera image of that print has been reviewed and no vehicle motion has been measured.
- The MUSE goal adapter currently serializes the store during an upstream request. HTTPX limits individual network operations, not total elapsed request duration. Move remote work outside the store lock and revalidate revisions before integrating live observation/control.
- Events retain transition causes and source labels. Complete immutable media/provider receipts, usage, latency, prompt versions and held-out image evaluation remain future work.
- The test client emits an upstream Starlette/HTTPX deprecation warning; all current tests pass. This does not affect the production HTTP server path.
- GX10 activation, trusted tablet HTTPS/microphone testing and physical qualification have not occurred.

The actual workspace screenshot is [`assets/workspace-simulation.jpg`](assets/workspace-simulation.jpg). It shows an original illustration, a symbolic plan and simulation controls, not a live camera or successful physical run.
