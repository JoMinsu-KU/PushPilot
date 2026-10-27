# Workspace verification

Verified on **2026-10-27, Asia/Seoul**. This record covers the temporary map, light industrial workspace and recorded-pair action-review integration; it is not a physical mission report.

| Check | Result | Boundary |
|---|---|---|
| `python tools/dev.py check` | Passed | Python and JSON source syntax; no credentials loaded |
| `python tools/dev.py test` | 96 passed | The previous 81 checks plus 15 recorded-action API/provider, binding, concurrency and failure-path checks |
| `npm test` in `frontend` | 21 passed | Projection/arrows, UUIDs, recorded-pair readiness and nine board-focus identity/geometry/fallback checks |
| `npm run build` in `frontend` | Passed | TypeScript checking and Vite production bundle |
| Real Meta application-goal requests | Accepted, `PLAN_READY` | Bakery and Bookstore interpretations; [details](META_API_CHECK.md) |
| Real Meta image inspection | Accepted, `USABLE` | Four shops, no separate physical car, signal UNKNOWN; recorded frame only |
| Actual MUSE action-review requests | Three designed conditions matched | Synthetic success → READY, no progress → FAULT, occlusion → REOBSERVE; one request per condition, no physical accuracy claim |
| Browser MUSE action-review workflow | Passed | Pin BEFORE, upload AFTER, explicit actual-provider request, PASS, one simulated step accepted, persisted comparison and read-only replay |
| Actual recorded-image test registration | Passed | Four markers in the selected native 1080p frame; 1.4333 px image-fit RMS, no metric accuracy claim |
| Combined Python service | Passed | Built UI and API served from one loopback origin |
| Browser mission flow | Passed | Bakery eight-action simulation: C RED wait, C GREEN admission, S mandatory stop with UNKNOWN after C's signal was cleared, S fresh GREEN, final review/completion |
| Browser evidence replay | Passed | Source-labelled events and read-only event detail; no execution controls in replay |
| Responsive browser checks | Passed | 1440×1000, 1280×800, 1024×768 and 390×844; no horizontal overflow of visible buttons, inputs, selects or SVGs |
| Browser console | No errors observed | Verified software session; not a full browser/device matrix |
| GX10 compatibility preparation | Dependency wheels resolved | CPython 3.12 Linux ARM64 packages downloaded locally; no GX10 installation or application execution claimed |

The local verification host used Windows CPython 3.14 and Node 24.19. The GX10 was inspected read-only: Ubuntu 24.04.4, ARM64, Python 3.12.3 and no Node/npm on its command path. The deployment design builds frontend assets locally and serves them from Python on GX10.

## Fixed spatial workspace

The current October 27 revision follows the user's industrial references and the [design system](DESIGN_SYSTEM.md): one continuous camera/map backdrop beneath the rail, header and rounded translucent mission/status overlays. The scene has no reserved right-hand column: real image detail sits behind the glass. Long routes, replay history, image tools and comparison details use bounded dialogs, tabs and explicit pages. Horizontal summary paging is allowed; vertical page/panel scrolling is not the content strategy. The first flat light-dashboard pass was rejected and remains historical.

Static checks, **96 Python tests, 21 frontend tests**, and the TypeScript/Vite build passed. The new board-focus tests cover map ID/version/hash binding, locked versus changed/candidate mapping, marker-inclusive bounds, full projective division, unchanged source geometry, viewport bounds and malformed/degenerate/off-image fallback. Board focus masks the surrounding workbench in original camera coordinates. Full frame remains available; no perspective rectification or generated image content is used.

Browser verification used a separate loopback preview and a copied private state. Landscape checks covered **1194×834, 1366×1024 and 1024×768 CSS pixels**. Workspace dimensions fit the viewport; route pages, Replay, image-tool tabs and the recorded comparison were checked for lost vertical content. Review-required and RED-wait states retained the primary action, termination control and source label. The isolated simulation exercised approval, push review, mandatory stop, RED waiting, fresh GREEN crossing admission, cancellation, reset and a new unapproved plan. BEFORE selection survived the image-tools round trip. No new model request, camera capture or robot access was used for these presentation checks.

The actual compiled glass surface was checked through computed style: `backdrop-filter: blur(12px) saturate(1.05)`, with a white gradient at 59%–45% opacity. The rail uses 38% white. Explicit rounded clips prevent backdrop effects from leaking beyond their panels in the inspected browser. The camera SVG's computed filter is `none`; its original image URL, pixels and viewBox remain intact. For the inspected frame, the board-focus viewBox is 1772.6 source pixels wide and its 1194×834 layout is 1210 CSS pixels wide. Display dimensions are capped at the source viewBox dimensions; no sharpening, perspective warp, recompression or image blur is applied. Glass softens only the portions behind a panel.

A prefixed-declaration ordering issue that removed the standard backdrop property during CSS minification was corrected. Review API errors now appear inside the native review dialog, and action verdicts take precedence over independent scene-inspection results.

Pretendard Variable **v1.3.9** is bundled unchanged and served from the same application origin, with its SIL OFL notice. The full WOFF2 is 2,057,688 bytes and supports the variable weight range declared by upstream. No external font CDN or runtime Node.js is required on GX10. Font loading and tablet wrapping were checked in the local browser; real-device performance and a full accessibility/contrast audit remain unverified.

The active README image is [`assets/scene-workspace.jpg`](assets/scene-workspace.jpg), showing the self-authored architectural illustration. Supplied print artwork and raw recorded-camera screenshots stay outside Git. [`assets/light-industrial-workspace.jpg`](assets/light-industrial-workspace.jpg) records the rejected first pass. None is a physical-run or final user-design-approval claim.

## Recorded-pair action review

The integrated source passed **96 Python tests and 12 frontend tests**, followed by the TypeScript/Vite build. Provider work releases both stores, has a 50-second total limit, reserves request/review identity durably and revalidates mission, action, review, map and immutable frames before accepting a result. Tests cover duplicate dispatch, original receipt replay, interruption, cancellation, superseded frames/reviews/maps, malformed/truncated/refused output, missing configuration, provider errors and STOP/signal admission. Provider failure leaves the pending review unchanged; no demo verdict is substituted.

Three actual Muse Spark image comparisons at **17:04 KST** used the same expected outcome on explicitly labelled original synthetic schematics. Progress returned PASS and READY; unchanged position returned FAIL and FAULT; an occluder returned REOBSERVE and REOBSERVE. Each is one designed pipeline case, not a held-out real-image evaluation. See the [actual API conditions and timings](META_API_CHECK.md) and [public structured results](evidence/synthetic-action-reviews-20261027.json).

An additional actual browser request at **17:09 KST** exercised selecting BEFORE, uploading AFTER, entering the expectation and submitting the recorded pair. PASS advanced only that simulated PUSH review. The UI retained both images and source/hash/capture-time labels, displayed the actual model result and exposed full provenance. During the pending request, image mutation and duplicate submission were disabled while **End simulation** remained available. Replay displayed the selected MUSE event's pair; selecting an unrelated event removed that pair and exposed no execution/review controls.

Before the current fixed-stage revision, the integrated view was checked at **1440×1000, 1280×800, 1024×768, 768×1024 and 390×844**. Those checks covered pair image proportions, expanded Plan and read-only Replay in the preceding layout. They do not establish current phone-layout acceptance, a full accessibility audit or a real-device matrix. The current layout checks are recorded above.

## Meaningful failure-path coverage

Offline tests cover stale revisions, request identity reuse, exact approval identity, blocked goal replacement during an active mission, required per-action review, GREEN without verified stopping, RED/UNKNOWN/stale signal inhibition, uncertain reobservation, explicit failure, restart recovery and provider rejection without a demo fallback. Test providers and databases are isolated; the ordinary suite never reads the operator's real key or contacts a model.

Visual review also found and corrected a LAN HTTP fallback that initially produced non-UUID command IDs and mobile footer wrapping. The final fallback tests enforce the API UUID contract.

## Limits and next validation

- Robot, live camera, measured vehicle pose, production metric AR, fresh physical action-bound image review and voice remain unavailable. Actual MUSE recorded-pair reviews can affect simulated state; demo verdicts remain explicitly labelled and signals/action receipts remain simulated.
- The supplied [temporary print](TEST_INPUTS.md) was photographed separately and the selected recorded frame was inspected by MUSE. No vehicle motion was measured.
- The MUSE goal adapter currently serializes the store during an upstream request. HTTPX limits individual network operations, not total elapsed request duration. Move remote work outside the store lock and revalidate revisions before integrating live observation/control.
- Events retain transition causes and source labels; private immutable frames and scene-inspection records bind their image/map/model/expectation identities. Recorded-action events additionally retain the pair, action binding, prompt/schema versions, parsed result, elapsed time and reported token usage. Equivalent complete receipts for older goal/scene paths and held-out real-image evaluation remain future work.
- The test client emits an upstream Starlette/HTTPX deprecation warning; all current tests pass. This does not affect the production HTTP server path.
- GX10 activation, trusted tablet HTTPS/microphone testing and physical qualification have not occurred.

Earlier public screenshots remain in [`assets/temporary-map-workspace.jpg`](assets/temporary-map-workspace.jpg), showing the self-authored schematic and actual model-result text, and [`assets/workspace-simulation.jpg`](assets/workspace-simulation.jpg), showing the original first slice. Both predate the light-dashboard restyle. Private recorded-camera screenshots remain outside Git. None of these views is a physical-run claim.
