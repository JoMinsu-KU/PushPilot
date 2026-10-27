# Workspace verification

Verified on **2026-10-27, Asia/Seoul**. This record includes the temporary-map extension to the initial software slice; it is not a physical mission report.

| Check | Result | Boundary |
|---|---|---|
| `python tools/dev.py check` | Passed | Python and JSON source syntax; no credentials loaded |
| `python tools/dev.py test` | 81 passed | Release integrity, connection checker, graph routes, mission/API, recorded scene and provider tests |
| `npm test` in `frontend` | 7 passed | Projection direction/division, singular rejection, corner arrow direction and command UUIDs |
| `npm run build` in `frontend` | Passed | TypeScript checking and Vite production bundle |
| Real Meta application-goal requests | Accepted, `PLAN_READY` | Bakery and Bookstore interpretations; [details](META_API_CHECK.md) |
| Real Meta image inspection | Accepted, `USABLE` | Four shops, no separate physical car, signal UNKNOWN; recorded frame only |
| Actual recorded-image test registration | Passed | Four markers in the selected native 1080p frame; 1.4333 px image-fit RMS, no metric accuracy claim |
| Combined Python service | Passed | Built UI and API served from one loopback origin |
| Browser mission flow | Passed | Bakery eight-action simulation: C RED wait, C GREEN admission, S mandatory stop with UNKNOWN after C's signal was cleared, S fresh GREEN, final review/completion |
| Browser evidence replay | Passed | Source-labelled events and read-only event detail; no execution controls in replay |
| Responsive browser checks | Passed | 1440×1000, 1280×800, 1024×768 and 390×844; no horizontal overflow of visible buttons, inputs, selects or SVGs |
| Browser console | No errors observed | Verified software session; not a full browser/device matrix |
| GX10 compatibility preparation | Dependency wheels resolved | CPython 3.12 Linux ARM64 packages downloaded locally; no GX10 installation or application execution claimed |

The local verification host used Windows CPython 3.14 and Node 24.19. The GX10 was inspected read-only: Ubuntu 24.04.4, ARM64, Python 3.12.3 and no Node/npm on its command path. The deployment design builds frontend assets locally and serves them from Python on GX10.

## Light industrial restyle

The subsequent October 27 visual update follows the user's industrial dashboard references and the [design system](DESIGN_SYSTEM.md): off-white canvas, white panels, a slim icon rail, charcoal typography, restrained orange controls, a dominant scene and a right mission panel. Scope is frontend presentation and design documentation; existing source labels, projective image coordinates and mission admission boundaries remain requirements.

The design-only snapshot was checked independently of the concurrent recorded-action feature. Static checks, all 81 Python tests, all 7 existing frontend tests, and the TypeScript/Vite build passed. Fresh browser checks covered 1440×1000, 1280×800, 1024×768, 768×1024 and 390×844: visible controls/SVGs had no horizontal overflow and the full 1920×1080 photograph retained its 16:9 aspect ratio with the same projected route. Camera and spatial views, eight-step expanded Plan, read-only Replay, image tools and expandable inspection evidence were inspected. A copied private simulation state exercised approval, push review, mandatory stop at C, RED waiting, fresh GREEN automatic crossing admission, cancellation, reset and a new unapproved plan. No new provider request or hardware access was used for this design verification. The primary action renders as a stable element across periodic state refreshes instead of remounting a nested component.

The active README image is [`assets/light-industrial-workspace.jpg`](assets/light-industrial-workspace.jpg), captured from this independently running design snapshot. It shows the original spatial schematic and a previously recorded MUSE scene result; no supplied print artwork or raw camera photograph is visible. Separate action-bound MUSE integration and its tests belong to their own verification record. This is not a full keyboard/contrast audit, device performance benchmark or GX10 deployment result.

## Meaningful failure-path coverage

Offline tests cover stale revisions, request identity reuse, exact approval identity, blocked goal replacement during an active mission, required per-action review, GREEN without verified stopping, RED/UNKNOWN/stale signal inhibition, uncertain reobservation, explicit failure, restart recovery and provider rejection without a demo fallback. Test providers and databases are isolated; the ordinary suite never reads the operator's real key or contacts a model.

Visual review also found and corrected a LAN HTTP fallback that initially produced non-UUID command IDs and mobile footer wrapping. The final fallback tests enforce the API UUID contract.

## Limits and next validation

- Robot, live camera, measured vehicle pose, production metric AR, action-bound image review and voice remain unavailable. Temporary recorded-image overlays and MUSE scene inspection are implemented separately. Action verdicts and signal stand-ins remain explicitly simulated.
- The supplied [temporary print](TEST_INPUTS.md) was photographed separately and the selected recorded frame was inspected by MUSE. No vehicle motion was measured.
- The MUSE goal adapter currently serializes the store during an upstream request. HTTPX limits individual network operations, not total elapsed request duration. Move remote work outside the store lock and revalidate revisions before integrating live observation/control.
- Events retain transition causes and source labels; private immutable frames and scene-inspection records bind their image/map/model/expectation identities. Complete provider usage/latency receipts, prompt catalogs and held-out image evaluation remain future work.
- The test client emits an upstream Starlette/HTTPX deprecation warning; all current tests pass. This does not affect the production HTTP server path.
- GX10 activation, trusted tablet HTTPS/microphone testing and physical qualification have not occurred.

Earlier public screenshots remain in [`assets/temporary-map-workspace.jpg`](assets/temporary-map-workspace.jpg), showing the self-authored schematic and actual model-result text, and [`assets/workspace-simulation.jpg`](assets/workspace-simulation.jpg), showing the original first slice. Both predate the light-dashboard restyle. Private recorded-camera screenshots remain outside Git. None of these views is a physical-run claim.
