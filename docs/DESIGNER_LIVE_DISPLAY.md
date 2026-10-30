# Designer workspace and execution display

Implemented on October 30, 2026, from application baseline `7e1ce59` in an isolated UI worktree. This change does not activate or qualify a physical release.

## Presentation

The supplied designer layout now wraps the existing application controller: full-screen Camera/Spatial, rounded glass header and cards, From/To, a collapsible mission panel, complete route and history lists, and internally scrolling dialogs. Pretendard remains the application font. Page scrolling is disabled; long evidence stays within its own list. Stop remains accessible in the collapsed panel and open application dialogs.

Robot mode retains the existing physical status hook, explicit Start/Stop requests, request IDs, expected revisions, plan binding, uncertain-response handling and no automatic replay. Simulation remains explicit. Physical sequence, receipt totals, review, source labels, errors and history come from physical status; missing data is not filled from the symbolic simulator. A held mission without a current step scrolls to the next pending row without labelling it as moving.

The original camera JPEG URL, frame dimensions, homography, board focus and shared image/route navigation remain intact. No new camera correction, top view, image recompression, segmentation or MUSE call is introduced by presentation.

## Optional read-only display service

`GET /api/v1/physical/display` returns a cached `pushpilot.physical-display.v1` snapshot. An independent collector reads bounded portions of the existing append-only journal and verifies the configured packet hash, current mission/plan binding, journal chain, request identity and Native endpoint evidence. It imports no executor or robot port, obtains no journal-owner lock, performs no network request, and writes no operating data. The endpoint itself performs no collection or disk IO. Constructor, collector, endpoint and shutdown errors affect only this optional display.

Each service instance has a producer epoch and increasing sequence. Browser polling is single-flight and bounded; a different mission invalidates an old snapshot immediately. Repeated successful responses containing the same sequence do not refresh the 3.5-second collector-liveness budget. Reconnection never starts, retries or resumes a robot command.

The Spatial vehicle illustrates confirmed contact progress along direction-compressed legs of the selected map route. It uses contact receipts and semantic direction annotations, not robot BASE coordinates or measured car pose. A short 650 ms tween illustrates a newly confirmed contact receipt; an intent recorded before dispatch cannot start it. The first snapshot reconciles directly to its current estimate without replaying the earlier journey.

Approach, withdrawal, unloaded wrist, recontact, signal wait, MUSE review, HOLD, unavailable/stale feeds and empty home return do not animate vehicle travel. Confirmed delivery leaves the illustrated car at the destination while the empty robot returns. The view is labelled **Execution estimate / Display only**. It does not reproduce slip, exact position or yaw, and cannot establish arrival or authorize continuation.

Signal presentation consumes the existing physical gate lifecycle. A completed recontact remains `Signal passed` even after the policy clears its green sample counter. The UI creates no second signal watcher, no new admission and no countdown. The separately identified physical 120-second wait-policy change is outside this migration.

## Model and map identity

The new toy-city asset is fitted by `frontend/public/models/city-display.json`, separate from the physical map definition. The manifest binds the unchanged map geometry hash to the actual GLB SHA-256. Model bytes are verified before parsing, including plain LAN HTTP contexts without WebCrypto. Invalid/missing assets disable the optional viewer; physical commands and Camera remain separate.

The existing physical map JSON, coordinate packet, tool/TCP/Z, motion limits, B/C/D recipes, C26 arrival rule, signal policy, receiver and robot API are not changed. The separately authored robot-progress diagnostic candidates in the shared checkout are not included.

Rendering starts with DPR capped at 1.5 and 1024-pixel shadows. Rendering pauses when hidden and disposes its resources when unmounted. Actual sustained iPad Safari performance still requires the target device; a desktop viewport check is not hardware qualification.

## Verification and release boundary

- Syntax check passed without equipment access.
- Backend suite: 1,132 tests run, 5 skipped; 23 new display tests cover corrupt/partial/rotated journals, Native binding, phase freeze, signal presentation and lifecycle isolation.
- Frontend suite and production build passed, including existing map/camera projection checks and new real-data layout/display tests.
- An uninstalled, read-only projection executed from stdin on GX10 parsed its existing journal successfully. It reported the actual held mission at 18/31 receipts, 14/20 confirmed contact stages, NORTH route leg and signal passed with green counter zero. Physical status was identical before and after. No configuration or packet payload was exported by this verification.
- Local browser QA used a captured native JPEG and captured API data; explicitly synthetic wait/return/disconnection variants were served by a loopback-only fixture server with all POST requests rejected. These are UI tests, not fresh hardware missions.
- Landscape viewport checks cover 1376 × 1032 and 1194 × 834, including internal route/history scrolling, collapsed controls and modal Stop access. No page overflow was observed.

The installed GX10 application remains untouched while its existing HOLD mission is unresolved. No robot, camera or Rodi process was restarted, no mission was reset, and no loaded trial was issued. Activation requires an inactive, reconciled boundary. Build and transfer from this isolated commit; never collect the shared dirty checkout or implicitly activate its experimental robot changes.
