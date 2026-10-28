<sub>[PushPilot](../README.md) / [Documentation](README.md) / Live camera preview</sub>

# A live view, with a separate evidence boundary

**Native camera pixels in the workspace. No implied robot observation or automatic MUSE request.**

[Frontend](../frontend/README.md) · [Backend](../backend/README.md) · [Development](DEVELOPMENT.md) · [Recorded action reviews](ACTION_REVIEWS.md) · [Verification](VERIFICATION.md)

PushPilot now has an opt-in live camera preview alongside recorded images and the spatial illustration. A standalone helper reads one explicitly selected Linux camera; an existing loopback connection supplies its original JPEGs to the application. The live preview is independent of recorded `SceneStore` media, MUSE requests, action-review evidence and mission state. Connecting it does not enable robot control, physical signal admission or fresh post-action verification.

Since October 28, the GX10 deployment runs the application beside the independent camera helper and connects over host loopback. A Windows development instance can instead use the SSH-forward workflow below. Actual connection observations and registration outcomes belong in [verification](VERIFICATION.md); implementation of a lock does not establish that the current physical view has been successfully registered.

## Data path and startup

| Stage | Responsibility |
| :--- | :--- |
| `tools/camera_preview.py` | Explicitly own one V4L2 device, read native 1920 × 1080 MJPEG through an `ffmpeg` child with video copy, and expose the latest JPEG on loopback. |
| Optional SSH local forward | For Windows development, carry the helper's loopback HTTP service to another loopback port on the application host. The GX10 application connects directly over host loopback. No public camera listener is required. |
| `backend/live_camera.py` | Poll the configured service, validate source/frame identity, keep eight immutable JPEG frames in RAM, detect markers and expose a preview-only API. |
| Camera UI | Select Live or Recorded, decode a new image before displaying it, show age/source/registration status and preserve native perspective and overlay coordinates. |

Live preview is **disabled by default**. Starting the application does not open a camera, start the helper, change device permissions or restart an existing camera/robot/POC service. The helper requires Linux, Python and `ffmpeg`; it uses the standard library and does not require the application's Python environment. Resolve the actual device and reviewed camera identity privately before starting it. If authentication is needed, use the existing direct-input terminal workflow.

The following commands are an explicit operator workflow, not an automatic deployment script. Ports are examples; check availability and ownership first.

On the camera host, deliberately start the helper from the reviewed source:

```sh
python3 tools/camera_preview.py --device /dev/video0 \
  --camera-id '<reviewed-camera-identity>' --port 8084
```

For a Windows development application, establish the existing SSH connection's local forward:

```sh
ssh -N -L 127.0.0.1:8895:127.0.0.1:8084 gx10
```

Then start the Windows development application against that already-running forwarded service:

```sh
python tools/serve.py --port 8893 \
  --live-camera-url http://127.0.0.1:8895
```

On GX10, the deployed application instead connects directly to the already-running helper:

```sh
python tools/serve.py --port 8080 --live-camera-url http://127.0.0.1:8084
```

A development computer can reach that loopback-only application through a separate forward:

```sh
ssh -N -L 127.0.0.1:8897:127.0.0.1:8080 gx10
```

Open `http://127.0.0.1:8897` on that computer. These examples do not start or restart the camera helper.

PowerShell users can put each command on one line rather than using the POSIX continuation characters. `PUSHPILOT_LIVE_CAMERA_URL` is the equivalent explicit process-environment configuration. The URL must be numeric loopback HTTP with an explicit port, without credentials, paths, query strings or fragments. DNS names, remote addresses and redirects are rejected. No provider key is needed for preview.

The helper binds `127.0.0.1`, has an advisory device lock, and refuses an existing owner when `fuser` is available. It never terminates another owner. It does not resize, decode, re-encode or save images. Closing its terminal or stopping it cleans up its own `ffmpeg` child; it does not restart itself or other services. Changing the frontend is not a reason to restart the camera helper.

## Source, time and freshness

Each accepted frame has a camera identity, camera-process epoch, increasing sequence, application frame identifier, native dimensions, SHA-256, host-receive time and age. A new helper process has a new epoch. The receive timestamp is when the camera host dequeued the JPEG, **not the sensor exposure time**. Sequence and host age do not establish a robot-action capture window.

The application freshness limit is **1500 ms**, including reported upstream age, HTTP transport time and elapsed local monotonic time. Receiving the same sequence again does not refresh its age. A stale/disconnected image is labelled stale rather than presented as current. The helper has its own 2000 ms stale threshold; the application applies the stricter preview threshold. These are software display limits, not qualified physical-control timing tolerances.

The helper requests native 1920 × 1080 MJPEG at 30 frames per second. The application and UI target status/frame polling around 125 ms. Requested capture rate and polling interval are configuration values, **not measured delivered frame rate or end-to-end latency**. Do not report an achieved frame rate without a corresponding measurement.

The installed static-view check and short backend delivery sample are recorded in [verification](VERIFICATION.md). They do not establish browser presentation rate or exposure-to-display latency. Browser request, response and image-decode time count conservatively toward preview age; a delayed response cannot renew freshness.

The helper retains only its latest JPEG; the backend retains eight immutable frames in memory. They are not written to `SceneStore`, SQLite or server image files. Expired backend frame IDs return 404. Unique preview-image responses may be privately cached by the browser for 30 seconds to support decode-before-swap; this is not persistent mission evidence. Do not publish raw live images, hardware identities or private connection details in source or documentation assets.

## Fixed display registration

Live display registration is separate from a recorded-image lock. **Lock live view** requires a fresh selected frame and the current frame to contain all four consistent printed markers. The explicit lock binds camera identity, epoch, resolution and map ID/version/hash. The active transform is held in RAM; the application separately keeps its original server-held lock receipt in private SQLite for deliberate continuity after a web-process restart. This metadata receipt grants no motion authority and does not persist the preview JPEG stream.

Small foreshortened markers use a live-only bounded recovery path: two canonical sampling profiles, the ArUco dictionary's supported one-bit correction, and at most 32 small native-pixel rejected-quad crops with preserved image offsets. Complete four-marker geometry and agreement with ordinary detections remain mandatory for a new lock; conflicting or duplicate IDs reject recovery. Partial detections from separate sampling profiles are never combined. This improves decoding without resizing the camera image or relaxing physical calibration claims. A backend restart discards the active RAM reference; it never silently resumes the old display lock.

An operator can explicitly request `POST /api/v1/live-camera/registration/resume` with **only `{epoch}`**. The service reads its own private saved receipt; it accepts no client homography or imported calibration through the public API. Resuming a lost RAM reference requires the same camera/epoch, dimensions, map identity/version/hash, a fresh non-regressing native frame and at least two spatially distributed known visible markers agreeing with the **exact old homography**. It does not fit a transform, reconstruct hidden markers or clear a latched view change. Missing/mismatched receipts, insufficient visible evidence and confirmed displacement fail closed; a new four-marker lock is then required. `saved_reference_available` reports a matching-identity candidate receipt, not proof that resume checks will pass. Resume restores only a test display reference, with a new registration identity; it does not restore plan approval, pending commands, stop/GREEN evidence, signal watching, measured car pose or robot calibration.

| Condition | Display behavior |
| :--- | :--- |
| No accepted four-marker lock | Show the camera; withhold the registered route and board-focus mask. A candidate is not a lock. |
| Visible markers match the lock | Use the fixed homography without fitting it again. Partial matching markers retain the same reference. |
| Markers are temporarily hidden or coverage is insufficient | `locked_occluded` / `insufficient_visibility` retains the reference and native live review eligibility, explicitly marks alignment unverified, and does not pause the mission. |
| Visible markers contradict the reference | `locked_occluded` / `marker_disagreement` retains the display reference but inhibits new intelligence admission; no automatic refit occurs. |
| Identity, epoch, resolution or map changes | Latch `view_changed`, withhold the old overlay and require another explicit lock. |
| At least two spatially distributed markers establish a coherent shift across three new accepted frames | Latch `view_changed`; do not automatically refit or silently clear the condition. |
| Stale live frame | Hide the current route projection; keep the source/age warning visible. |

These marker checks are display-inhibition heuristics, not a guarantee of detecting every camera displacement or a physical calibration result. An isolated questionable marker is insufficient to declare a confirmed shift. Conversely, retaining a reference under occlusion does not prove alignment. Do not move the map or camera and assume an old lock remains valid.

Camera preserves the original JPEG perspective. **Board focus** only masks the area outside the registered board; **Full frame** remains available. No rectification, detail synthesis, board resampling or global image blur is introduced. Glass panels intentionally soften their own backdrops and may cover part of the scene.

## Native recovery and expected robot occlusion

A matching active fixed reference supplies an optional search hint for a marker that was never proposed as a rejected quadrilateral. At least two distributed ordinary detections in the **current frame** must first agree with the reference. The detector searches only missing markers' bounded native-pixel regions. Two existing AprilTag corner profiles run first, followed by one native contour profile with threshold constant 3 and a 0.30 ignored cell margin for tiny foreshortened markers. There are at most twelve ROI decodes, with the dictionary's same one-bit correction limit. No new full-frame profile, image resizing or tolerance relaxation is introduced.

Each missing marker is searched independently; failure on one no longer prevents searching the next. A complete result must still pass strict four-marker geometry. When a real marker stays hidden, the best single-profile pool of genuine additional observations may survive as a partial result, within the same RMS ≤3 px / maximum ≤6 px reference checks. Partial pools from different profiles are never combined. Independent full-frame recovery still runs before selecting that partial fallback. Partial recovery creates no new registration candidate or homography. Hidden markers remain missing; projected corners never become observations. Camera/epoch/resolution/map changes, stale input and a latched changed view disable this hint. The original JPEG and locked transform remain unchanged.

The user clarified that robot motion will frequently cover the printed markers. **Marker visibility is not a per-action permission switch.** Register the fixed camera and board before the mission, then retain that exact transform throughout expected covers, including covers of all markers. Fresh native images, the fixed AR route and MUSE planning/action/signal review remain available. Do not stop, pause, refit, fabricate detections or request a robot retreat solely because markers disappeared.

`registration.verification` distinguishes `visible_markers` (at least two distributed agreeing observations), `insufficient_visibility` (fixed reference retained, current alignment unverified), and `marker_disagreement` (visible evidence contradicts the reference). A single doubtful marker does not block continuity when at least two other distributed markers agree; its corners are never used to update the transform. Multiple disagreeing markers, a doubtful marker without distributed support, or malformed/duplicate observations remain contradictory evidence. `capture()` accepts the first two verification modes under the existing fixed-camera/board assumption; contradictory evidence, confirmed view/identity changes, stale images and transport failures still inhibit admission. Preview quality downgrades immediately without mixing newer corners into an older decoded image; recovery waits for the newer image to decode. Missing visibility alone never changes mission state.

Expected visibility changes use the existing compact glass source plate: `Fixed mapping · 4/4 markers`, `Fixed mapping · 2/4 markers`, or `Alignment unverified · 0/4 markers`. They do not repeatedly mount a full-width warning over the road. Actual marker disagreement, stale imagery and a changed view retain prominent alerts and their existing admission/overlay guards. Counts remain fresh observations, rather than being smoothed, cached as detections or filled from the reference.

When markers return, compare them with the same transform. Agreement restores verified status without registration; a coherent distributed shift over three distinct new frames latches `view_changed`. While every marker is hidden, the system **cannot establish that an unseen camera or board movement did not occur**. Fix the camera mount and board mechanically before physical qualification. This application implements test display continuity and simulated admission only, not a measured physical control guarantee.

Car and signal visibility are independent: an obscured car outcome can require `REOBSERVE`, and an unreadable signal remains `UNKNOWN`. Retaining board registration cannot convert either into `PASS` or `GREEN`. Any future observation pose must be a separately qualified bounded robot action, not an automatic retreat triggered by missing board markers.

The [October 28 stability recheck](evidence/vision-stability-20261028.json) records the actual small-marker failure and repair. In a paired twenty-image comparison, complete recovery increased from 10 to 19 frames on both local and GX10 runtimes. A subsequent fresh 120-frame window retained the exact mapping in all frames, with 110 complete and ten three-marker observations. These short checks cover marker decoding and display continuity, not physical car/signal recognition or a moving-robot trial.

## API and capability meaning

The contract is [`contracts/live-camera.ts`](../contracts/live-camera.ts), schema `pushpilot.live-camera.v1`.

| Endpoint | Behavior |
| :--- | :--- |
| `GET /api/v1/live-camera` | Preview state, source/frame identity, age, detections, display registration and `motion_authority: false`. |
| `GET /api/v1/live-camera/frames/{frame_id}/image` | Original JPEG bytes from the bounded RAM cache. |
| `POST /api/v1/live-camera/registration` | Explicit `{epoch, frame_id}` display lock, rejected for stale, changed or insufficient-marker input. |
| `POST /api/v1/live-camera/registration/resume` | Explicit `{epoch}` request to revalidate and reuse the exact server-held display reference; client transform fields are rejected. |
| `GET /api/health` | `camera_preview_connected` reports a currently live preview. Simulation, `robot_connected: false` and `hardware_connected: false` remain separate. |

The legacy workspace `camera` capability refers to qualified control observations, not this preview connection, and remains false. Preview polling, locking and explicit display-reference resume do not change a mission revision, produce a GREEN observation, complete a step, persist a review image or call MUSE. Separate [live-intelligence operations](LIVE_INTELLIGENCE.md) deliberately select unchanged originals into their own evidence ledger for graph planning and review against simulated receipts. **Image tools** retain the independent recorded-image workflow. Neither selected native images nor continuity receipts establish measured physical actions or camera-to-robot calibration.

---

[Source-labelled workflow](MISSION.md) · [Release boundaries](../tools/README.md) · [GX10 deployment](../deploy/README.md)
