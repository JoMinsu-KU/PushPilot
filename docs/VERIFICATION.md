# Workspace verification

Initial software verification on **2026-10-27, Asia/Seoul**; the GX10 deployment follow-up on **2026-10-28** is recorded below. This record covers replaceable-map live-image planning, bound native-image action/signal services, finite voice uploads, execution-aware route display, recorded reviews and native preview. Execution remains simulated; this is not a physical mission report.

| Check | Result | Boundary |
|---|---|---|
| `python tools/dev.py check` | Passed | Python and JSON source syntax; no credentials loaded |
| `python tools/dev.py test` | 324 tests passed | Includes native-frame/graph planning, evidence, voice, signal watching, fixed-reference ROI recovery, expected robot occlusion, and independent city-model import/material tests. |
| `npm test` in `frontend` | 53 passed | Includes route display and immediate marker-quality withdrawal without mixing image/corner frames; color alone never advances a route |
| `npm run build` in `frontend` | Passed | TypeScript checking and Vite production bundle |
| Real Meta application-goal requests | Accepted, `PLAN_READY` | Bakery and Bookstore interpretations; [details](META_API_CHECK.md) |
| Real Meta image inspection | Accepted, `USABLE` | Four shops, no separate physical car, signal UNKNOWN; recorded frame only |
| Actual MUSE action-review requests | Three designed conditions matched | Synthetic success → READY, no progress → FAULT, occlusion → REOBSERVE; one request per condition, no physical accuracy claim |
| Browser MUSE action-review workflow | Passed | Pin BEFORE, upload AFTER, explicit actual-provider request, PASS, one simulated step accepted, persisted comparison and read-only replay |
| Actual recorded-image test registration | Passed | Four markers in the selected native 1080p frame; 1.4333 px image-fit RMS, no metric accuracy claim |
| Actual native live preview | Connected and explicitly locked | Native 1080p JPEGs, fixed display mapping and original-perspective Board focus; details below |
| Execution-aware route display | Passed in isolated simulation | Reviewed/current/upcoming paths, mandatory stops, RED/UNKNOWN wait, admitted crossing, final review; no vehicle motion measured |
| Replacement-map MUSE plan | Accepted, `PLAN_READY` | Synthetic Harbor map, gallery → MUSEUM, five drawing segments; no artwork, camera registration or physical execution |
| Combined Python service | Passed | Built UI and API served from one loopback origin |
| Browser mission flow | Passed | Bakery eight-action simulation: C RED wait, C GREEN admission, S mandatory stop with UNKNOWN after C's signal was cleared, S fresh GREEN, final review/completion |
| Browser evidence replay | Passed | Source-labelled events and read-only event detail; no execution controls in replay |
| Responsive browser checks | Passed | 1440×1000, 1280×800, 1024×768 and 390×844; no horizontal overflow of visible buttons, inputs, selects or SVGs |
| Browser console | No errors observed | Verified software session; not a full browser/device matrix |
| GX10 compatibility preparation | Dependency wheels resolved | CPython 3.12 Linux ARM64 packages downloaded locally; no GX10 installation or application execution claimed |

The local verification host used Windows CPython 3.14 and Node 24.19. The GX10 was inspected read-only: Ubuntu 24.04.4, ARM64, Python 3.12.3 and no Node/npm on its command path. The deployment design builds frontend assets locally and serves them from Python on GX10.

## GX10 application deployment, October 28

Source commit `e5637f3` was installed as a separate GX10 release on **2026-10-28, Asia/Seoul**. This follow-up supersedes the earlier helper-only deployment status; the October 27 software and provider checks above retain their original scope.

| Deployment check | Observed result | Boundary |
|---|---|---|
| Release payload | All 190 reviewed payload-file hashes matched the transferred release | Matching source and compiled assets; unrelated robot-control work excluded |
| ARM64 runtime | All 20 locked wheels installed offline; dependency consistency and runtime imports passed | Isolated Python 3.12 environment; no system dependency replacement |
| Host software checks | `python tools/dev.py check` and `python tools/dev.py test` exited successfully | Offline software tests; no provider or physical mission claim |
| Frontend/API service | User systemd service active on loopback port 8080 | One Python process; browser access through an SSH forward |
| Initial mission | `IDLE`, revision 0, `approved: false`, no plan | Fresh shared state; previous mission, approval, signal and pending operations were not restored |
| Existing camera | Fresh native 1920 × 1080 preview, same helper epoch and process | Helper was not restarted; no measured motion or exposure-to-display latency |
| Fixed display mapping | Only the latest authentic saved reference receipt was imported; explicit resume passed current marker validation with the exact original homography | Display registration only; no refit, robot coordinates or approval migration |
| Spatial and font assets | Clean-road private GLB hash matched; Pretendard WOFF2 and Draco WASM returned successfully | Asset delivery verified; no new geometry or browser performance claim |
| Provider configuration | MUSE configuration present on the backend | Credentials remained server-side and private |
| Actual MUSE connectivity | Model discovery returned HTTP 200; one `muse-spark-1.3` text completion returned HTTP 200 and the exact requested `PUSHPILOT_API_OK` text; 65 tokens reported | Bounded text-only connectivity smoke; no image/action/signal inference, mission change or robot operation |
| GX10 browser workspace | Camera and Spatial loaded at 1194 × 834 CSS pixels; Pretendard applied; no console warning/error or vertical scrolling observed | Actual deployed UI check at one viewport; not a full tablet/browser or motion benchmark |

The application user service is enabled for user-session startup. Lingering is disabled (`Linger=no`), so startup after boot without login has not been established. Trusted tablet HTTPS/microphone capture, full live-backed mission operation, final-map signal targets, rollback, physical control and wearable integration remain separate checks. Private deployment receipts, account details, addresses, media, state and credentials remain outside public source.

## Live backend integration

The software now includes graph-grounded native-image planning, exact selected-route compilation, server-captured BEFORE/new AFTER comparison, post-stop MUSE signal review, finite action/reobserve and signal-wait helpers, background signal watching, immutable selected-frame SQLite evidence and map-validation API/CLI. A configured accepted live STOP can start watching without another approval: default 30 judgments over at most 300 seconds, ending on GREEN, failure, cancellation or budget exhaustion. Finite mono PCM WAV ingestion and the official Meta transcription adapter return editable, revision/map-bound transcript receipts. Browser microphone capture remains disconnected.

Offline tests exercise west departure without shortest-path replacement, one-way roads, constraints and map replacement; provider refusal/malformed output/timeouts; byte/hash persistence beyond preview eviction; post-request host-receive ordering; idempotency, supersession, cancellation and restart interruption; manual-signal bypass rejection; accepted simulated stopping before fresh RED/GREEN judgment; missing signal targets; voice format bounds and transcript binding. Mocked results establish software behavior, not recognition accuracy.

Four actual live-image planning checks are recorded in [Meta evidence](META_API_CHECK.md#native-image-graph-planning-october-27). Prompt v1 accepted a left route and held a scene-uncertain right request. Prompt v2 accepted both natural-language sides: the eastern loop and western route. Neither was approved or executed. No actual live action, physical signal or ASR request was part of this backend verification.

The QA browser displayed the actual western route over the live camera. Replay opened its selected original JPEG at **1920 × 1080**, with no display mask or resampling in the provider/evidence path. At **1194 × 834** and **1024 × 768**, inspected workspace and native-evidence dialogs fit the viewport without vertical overflow; image and complete-record tabs remained accessible. Long records use explicit pages. Camera SVG filtering remained `none`.

Current Little Town has no reviewed signal-target regions, so its live signal requests fail closed until configured. A robot adapter, physical stop receipts, car/tool contact and turning, BASE/Z calibration, installed-map qualification, actual voice access remain outside verified software behavior. The GX10 installation and startup scope is recorded in the October 28 deployment follow-up above.

## Fixed spatial workspace

The current October 27 revision follows the user's industrial references and the [design system](DESIGN_SYSTEM.md): one continuous camera/map backdrop beneath the rail, header and rounded translucent mission/status overlays. The scene has no reserved right-hand column: real image detail sits behind the glass. Long routes, replay history, image tools and comparison details use bounded dialogs, tabs and explicit pages. Horizontal summary paging is allowed; vertical page/panel scrolling is not the content strategy. The first flat light-dashboard pass was rejected and remains historical.

Static checks, **136 Python tests, 46 frontend tests**, and the TypeScript/Vite build passed for the earlier route-display integration. Board-focus tests cover map ID/version/hash binding, locked versus changed/candidate mapping, marker-inclusive bounds, full projective division, unchanged source geometry, viewport bounds and malformed/degenerate/off-image fallback. Board focus masks the surrounding workbench in original camera coordinates. Full frame remains available; no perspective rectification or generated image content is used.

Browser verification used a separate loopback preview and a copied private state. Landscape checks covered **1194×834, 1366×1024 and 1024×768 CSS pixels**. Workspace dimensions fit the viewport; route pages, Replay, image-tool tabs and the recorded comparison were checked for lost vertical content. Review-required and RED-wait states retained the primary action, termination control and source label. The isolated simulation exercised approval, push review, mandatory stop, RED waiting, fresh GREEN crossing admission, cancellation, reset and a new unapproved plan. BEFORE selection survived the image-tools round trip. No new model request, camera capture or robot access was used for these presentation checks.

The actual compiled glass surface was checked through computed style: `backdrop-filter: blur(12px) saturate(1.05)`, with a white gradient at 59%–45% opacity. The rail uses 38% white. Explicit rounded clips prevent backdrop effects from leaking beyond their panels in the inspected browser. The camera SVG's computed filter is `none`; its original image URL, pixels and viewBox remain intact. For the inspected frame, the board-focus viewBox is 1772.6 source pixels wide and its 1194×834 layout is 1210 CSS pixels wide. Display dimensions are capped at the source viewBox dimensions; no sharpening, perspective warp, recompression or image blur is applied. Glass softens only the portions behind a panel.

A prefixed-declaration ordering issue that removed the standard backdrop property during CSS minification was corrected. Review API errors now appear inside the native review dialog, and action verdicts take precedence over independent scene-inspection results.

Pretendard Variable **v1.3.9** is bundled unchanged and served from the same application origin, with its SIL OFL notice. The full WOFF2 is 2,057,688 bytes and supports the variable weight range declared by upstream. No external font CDN or runtime Node.js is required on GX10. Font loading and tablet wrapping were checked in the local browser; real-device performance and a full accessibility/contrast audit remain unverified.

The active README image is [`assets/scene-workspace.jpg`](assets/scene-workspace.jpg), showing the self-authored architectural illustration. Supplied print artwork and raw recorded-camera screenshots stay outside Git. [`assets/light-industrial-workspace.jpg`](assets/light-industrial-workspace.jpg) records the rejected first pass. None is a physical-run or final user-design-approval claim.

## Visible goal and voice entry

The later goal-entry revision added a visible microphone and the accepted original query in a compact glass bar above camera controls. Browser checks covered opening voice guidance, its disabled capture control, typed fallback and original-query inspection. Editing an unsent draft left the accepted query unchanged; the draft was restored without submitting a new goal. The page remained tied to the existing unapproved plan and live display lock. No microphone permission, audio capture, provider request, camera restart or robot action occurred for this UI change.

Goal-entry and typed-dialog layouts were inspected at **1194×834, 1366×1024 and 1024×768 CSS pixels**. Voice guidance was additionally checked at 1194×834 and 1024×768. Document sizes matched the viewports; visible inputs/actions stayed within their dialog or viewport bounds. The goal bar and camera controls retained a separate gap. A rounded clip was added to the route legend to contain its backdrop blur. The existing **136 Python tests, 46 frontend tests** and production build passed; no new speech capability is established. See [Voice input](VOICE_INPUT.md#visible-goal-and-voice-entry).

## Execution-aware route display and map replacement

An isolated copy of private workspace state was used for a complete Bakery simulation through the browser. The current approach was emphasized; after an abstract action receipt it remained review-pending, and only accepted review changed it to reviewed. At C, the reviewed approach was green while the RED-wait crossing was amber and remaining segments were dashed. Fresh GREEN admitted the crossing. A subsequent RED did not roll back that already admitted crossing or label it a new stop. The next approach moved the signal scope to S and cleared the prior signal; S required a new mandatory stop and fresh GREEN. Final VERIFY review produced completion. These were explicit simulation actions and injected demo verdicts, not live MUSE action reviews or physical movement.

Browser goal changes produced distinct School and Bookstore paths with the same renderer. School's final leg turned left; Bookstore used a straight crossing and three motion segments instead of five. The path, stop line and junction-label anchors share the selected camera source's fixed display projection. A missing legacy visualization draws only the planned route. Tests cover malformed node/step bindings, short adjacent junctions and cancelling a never-approved plan without inventing progress.

The self-authored [Harbor replacement fixture](../tests/fixtures/harbor-map.json) changed the board to **600×300 mm**, used a north-facing DOCK start, different node/marker identifiers, four destinations and display aliases. The browser showed its map title, location labels and a second destination page containing Clinic. Its spatial view bounds adapted to the new dimensions. At **19:39 KST**, an actual browser MUSE request interpreted “gallery” as `MUSEUM`; the resulting unapproved plan followed `DOCK → J_WEST → J_EAST → MUSEUM` and displayed five planned segments. An initial request in a network-restricted test process failed visibly without creating a plan; the successful browser check used the network-enabled test process. No image was sent.

RED-wait layouts were checked at **1194×834, 1366×1024 and 1024×768 CSS pixels**, with document dimensions equal to each viewport and no visible button/input/select outside the bottom or right edge. The replacement-map view was also checked at 1194×834. Long junction labels are bounded inside the projected board, truncated visually and preserved in SVG titles; this is not a full accessibility audit.

The current application was then updated independently of its camera helper and SSH forward. At **19:42 KST**, an actual MUSE Bakery goal created a new unapproved `PLAN_READY` plan with five drawing segments over the native live image. Camera epoch and the existing Little Town geometry hash were unchanged. The live display was explicitly relocked after the application restart. Robot services were not started or moved. Live car tracking, physical stop lines, via-point/alternative-route requests and automatic live-image MUSE reviews remain unimplemented.

## Native live camera preview

The operator authenticated directly in the camera terminal. Only the standalone camera helper was started on GX10; the application remained Windows-hosted behind a dedicated loopback SSH forward. No robot, receiver, historical web service or existing POC camera service was started or restarted. Application-only changes did not restart the native camera process.

The actual installed camera supplied **1920 × 1080 native JPEGs**. Its four printed markers supported an explicit **Lock live view**, after which the browser showed Board focus and the planned route over the live original-perspective image. Twelve successive half-second observations all reported `live` and `locked`, with twelve distinct source sequences, one unchanged registration ID and one unchanged homography. Reported frame age ranged from **91.8 to 230.1 ms**. A fetched image's SHA-256 exactly matched its frame metadata. The mission stayed `PLAN_READY`, unapproved, at revision 46; no MUSE request or robot action occurred.

A separate **4.981-second backend sample** observed 36 distinct preview frames, approximately **7.03 new frames/s**, with reported ages of **73.6–303.9 ms**. Every sample remained `live` and `locked` with the same homography. This measures backend availability on this installed static scene, not browser presentation rate, sensor-exposure latency, a motion benchmark or a guaranteed sustained rate. The source requests 30 fps and application polling targets 125 ms; neither configuration value is an achieved end-to-end rate. Receive time is host dequeue time, not exposure time.

The small foreshortened upper markers needed a live-only, bounded decoder fallback. Seven sampled native frames all passed the existing complete four-marker geometry guard, with image-fit RMS **1.254–1.6851 px** and local offline detector times of **29–55 ms**. Those same development images informed the decoder settings; they are not a held-out accuracy evaluation. The fallback uses the dictionary's supported one-bit correction and small rejected-quad crops with original-pixel offsets. It neither enlarges the displayed image nor changes the locked transform. Fit residual does not establish board-to-BASE or millimeter accuracy.

The live workspace was inspected at **1194×834, 1366×1024 and 1024×768 CSS pixels**. Document dimensions equalled each viewport, with no visible button/input/select extending past its bottom or right edge. The image URL changed as frames arrived while its board-focus SVG viewBox stayed fixed. The camera SVG filter remained `none`; the mission surface retained `blur(12px) saturate(1.05)` backdrop glass. No browser errors or warnings were observed. Robot/car occlusion and physical motion were not exercised; live objects are displayed as captured, with no object removal or generated fill.

The final offline suite covers native JPEG parsing, ownership and cleanup, fixed versus changed registration, partial/total marker occlusion, stale/repeated sequences, cache expiry, unchanged recorded scene/mission, bounded decoder recovery and UI freshness/reset races. Raw live images, device identity, connection details and screenshots remain in the private workspace outside Git. Live preview still does not supply action-bound images to MUSE or authorize motion; see [the source boundary](LIVE_CAMERA.md).

The final browser build was also kept open across an application-only restart while the camera epoch continued unchanged. The UI withdrew the old AR and board mask, showed an unregistered live frame, and required a new explicit lock. A successful pre-restart lock was not silently restored. The native camera and SSH forward remained running throughout.

## Recorded-pair action review

The integrated source passed **96 Python tests and 12 frontend tests**, followed by the TypeScript/Vite build. Provider work releases both stores, has a 50-second total limit, reserves request/review identity durably and revalidates mission, action, review, map and immutable frames before accepting a result. Tests cover duplicate dispatch, original receipt replay, interruption, cancellation, superseded frames/reviews/maps, malformed/truncated/refused output, missing configuration, provider errors and STOP/signal admission. Provider failure leaves the pending review unchanged; no demo verdict is substituted.

Three actual Muse Spark image comparisons at **17:04 KST** used the same expected outcome on explicitly labelled original synthetic schematics. Progress returned PASS and READY; unchanged position returned FAIL and FAULT; an occluder returned REOBSERVE and REOBSERVE. Each is one designed pipeline case, not a held-out real-image evaluation. See the [actual API conditions and timings](META_API_CHECK.md) and [public structured results](evidence/synthetic-action-reviews-20261027.json).

An additional actual browser request at **17:09 KST** exercised selecting BEFORE, uploading AFTER, entering the expectation and submitting the recorded pair. PASS advanced only that simulated PUSH review. The UI retained both images and source/hash/capture-time labels, displayed the actual model result and exposed full provenance. During the pending request, image mutation and duplicate submission were disabled while **End simulation** remained available. Replay displayed the selected MUSE event's pair; selecting an unrelated event removed that pair and exposed no execution/review controls.

Before the current fixed-stage revision, the integrated view was checked at **1440×1000, 1280×800, 1024×768, 768×1024 and 390×844**. Those checks covered pair image proportions, expanded Plan and read-only Replay in the preceding layout. They do not establish current phone-layout acceptance, a full accessibility audit or a real-device matrix. The current layout checks are recorded above.

## Meaningful failure-path coverage

Offline tests cover stale revisions, request identity reuse, exact approval identity, blocked goal replacement during an active mission, required per-action review, GREEN without verified stopping, RED/UNKNOWN/stale signal inhibition, uncertain reobservation, explicit failure, restart recovery and provider rejection without a demo fallback. Test providers and databases are isolated; the ordinary suite never reads the operator's real key or contacts a model.

Visual review also found and corrected a LAN HTTP fallback that initially produced non-UUID command IDs and mobile footer wrapping. The final fallback tests enforce the API UUID contract.

## Limits and next validation

- Native live preview is connected and its temporary display mapping was explicitly locked. Robot control, measured vehicle pose, production metric AR, fresh physical action-bound image review and voice remain unavailable. Actual MUSE recorded-pair reviews can affect simulated state; demo verdicts remain explicitly labelled and signals/action receipts remain simulated.
- The supplied [temporary print](TEST_INPUTS.md) was photographed separately and the selected recorded frame was inspected by MUSE. No vehicle motion was measured.
- The MUSE goal adapter currently serializes the store during an upstream request. HTTPX limits individual network operations, not total elapsed request duration. Move remote work outside the store lock and revalidate revisions before integrating live observation/control.
- Events retain transition causes and source labels; private immutable frames and scene-inspection records bind their image/map/model/expectation identities. Recorded-action events additionally retain the pair, action binding, prompt/schema versions, parsed result, elapsed time and reported token usage. Equivalent complete receipts for older goal/scene paths and held-out real-image evaluation remain future work.
- The test client emits an upstream Starlette/HTTPX deprecation warning; all current tests pass. This does not affect the production HTTP server path.
- Full GX10 application activation, trusted tablet HTTPS/microphone testing and physical qualification have not occurred. Only the independent native camera helper runs on GX10.

Earlier public screenshots remain in [`assets/temporary-map-workspace.jpg`](assets/temporary-map-workspace.jpg), showing the self-authored schematic and actual model-result text, and [`assets/workspace-simulation.jpg`](assets/workspace-simulation.jpg), showing the original first slice. Both predate the light-dashboard restyle. Private recorded-camera screenshots remain outside Git. None of these views is a physical-run claim.

## Fixed-reference recovery and expected marker covers

The native ROI recovery path was checked against 50 privately held, unchanged JPEGs from a stationary temporary-board view. The previous path decoded all four markers in 49 images; adding guarded fixed-reference ROI decoding recovered the remaining image. Only one additional failure case was recovered. This is a limited regression corpus, not a general recognition rate, robot-occlusion trial or metric calibration result. Raw media and observation metadata remain outside the repository.

Generated-image and real `LiveCamera` integration tests cover missing/covered markers, exact fixed-transform continuity, camera/map binding, wrong or duplicate IDs, native-pixel preservation, bounded decoding, immediate frontend verification withdrawal and confirmed-view-change latching. MUSE providers are mocked for these admission tests. Zero/one visible marker does not block planning, model-supported action PASS or valid stopped GREEN; vehicle REOBSERVE and signal UNKNOWN retain their own holds. Contradictory distributed evidence and a confirmed view change still reject admission. One isolated doubtful marker does not override two distributed matching observations.

No moving robot, pushed vehicle, real paper-signal recognition or physical stopping was tested by this change. The fixed-reference policy assumes the camera and board remain mechanically fixed while markers are covered.
