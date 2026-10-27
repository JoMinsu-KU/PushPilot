<sub>[PushPilot](../README.md) / [Documentation](README.md) / Live camera preview</sub>

# A live view, with a separate evidence boundary

**Native camera pixels in the workspace. No implied robot observation or automatic MUSE request.**

[Frontend](../frontend/README.md) · [Backend](../backend/README.md) · [Development](DEVELOPMENT.md) · [Recorded action reviews](ACTION_REVIEWS.md) · [Verification](VERIFICATION.md)

PushPilot now has an opt-in live camera preview alongside recorded images and the spatial illustration. A standalone helper reads one explicitly selected Linux camera; an existing loopback connection supplies its original JPEGs to the application. The live preview is independent of recorded `SceneStore` media, MUSE requests, action-review evidence and mission state. Connecting it does not enable robot control, physical signal admission or fresh post-action verification.

The current arrangement runs only the standalone camera helper on GX10, with an SSH forward to the Windows-hosted application. The full application has not been deployed to GX10. Actual connection observations and registration outcomes belong in [verification](VERIFICATION.md); implementation of a lock does not establish that the current physical view has been successfully registered.

## Data path and startup

| Stage | Responsibility |
| :--- | :--- |
| `tools/camera_preview.py` | Explicitly own one V4L2 device, read native 1920 × 1080 MJPEG through an `ffmpeg` child with video copy, and expose the latest JPEG on loopback. |
| SSH local forward | Carry the helper's loopback HTTP service to another loopback port on the application host. No public camera listener is required. |
| `backend/live_camera.py` | Poll the configured service, validate source/frame identity, keep eight immutable JPEG frames in RAM, detect markers and expose a preview-only API. |
| Camera UI | Select Live or Recorded, decode a new image before displaying it, show age/source/registration status and preserve native perspective and overlay coordinates. |

Live preview is **disabled by default**. Starting the application does not open a camera, start the helper, change device permissions or restart an existing camera/robot/POC service. The helper requires Linux, Python and `ffmpeg`; it uses the standard library and does not require the application's Python environment. Resolve the actual device and reviewed camera identity privately before starting it. If authentication is needed, use the existing direct-input terminal workflow.

The following commands are an explicit operator workflow, not an automatic deployment script. Ports are examples; check availability and ownership first.

On the camera host, deliberately start the helper from the reviewed source:

```sh
python3 tools/camera_preview.py --device /dev/video0 \
  --camera-id '<reviewed-camera-identity>' --port 8084
```

On the application host, establish the existing SSH connection's local forward:

```sh
ssh -N -L 127.0.0.1:8895:127.0.0.1:8084 gx10
```

Then start the built application against that already-running loopback service:

```sh
python tools/serve.py --port 8893 \
  --live-camera-url http://127.0.0.1:8895
```

PowerShell users can put each command on one line rather than using the POSIX continuation characters. `PUSHPILOT_LIVE_CAMERA_URL` is the equivalent explicit process-environment configuration. The URL must be numeric loopback HTTP with an explicit port, without credentials, paths, query strings or fragments. DNS names, remote addresses and redirects are rejected. No provider key is needed for preview.

The helper binds `127.0.0.1`, has an advisory device lock, and refuses an existing owner when `fuser` is available. It never terminates another owner. It does not resize, decode, re-encode or save images. Closing its terminal or stopping it cleans up its own `ffmpeg` child; it does not restart itself or other services. Changing the frontend is not a reason to restart the camera helper.

## Source, time and freshness

Each accepted frame has a camera identity, camera-process epoch, increasing sequence, application frame identifier, native dimensions, SHA-256, host-receive time and age. A new helper process has a new epoch. The receive timestamp is when the camera host dequeued the JPEG, **not the sensor exposure time**. Sequence and host age do not establish a robot-action capture window.

The application freshness limit is **1500 ms**, including reported upstream age, HTTP transport time and elapsed local monotonic time. Receiving the same sequence again does not refresh its age. A stale/disconnected image is labelled stale rather than presented as current. The helper has its own 2000 ms stale threshold; the application applies the stricter preview threshold. These are software display limits, not qualified physical-control timing tolerances.

The helper requests native 1920 × 1080 MJPEG at 30 frames per second. The application and UI target status/frame polling around 125 ms. Requested capture rate and polling interval are configuration values, **not measured delivered frame rate or end-to-end latency**. Do not report an achieved frame rate without a corresponding measurement.

The installed static-view check and short backend delivery sample are recorded in [verification](VERIFICATION.md). They do not establish browser presentation rate or exposure-to-display latency. Browser request, response and image-decode time count conservatively toward preview age; a delayed response cannot renew freshness.

The helper retains only its latest JPEG; the backend retains eight immutable frames in memory. They are not written to `SceneStore`, SQLite or server image files. Expired backend frame IDs return 404. Unique preview-image responses may be privately cached by the browser for 30 seconds to support decode-before-swap; this is not persistent mission evidence. Do not publish raw live images, hardware identities or private connection details in source or documentation assets.

## Fixed display registration

Live display registration is separate from a recorded-image lock. **Lock live view** requires a fresh selected frame and the current frame to contain all four consistent printed markers. The explicit lock binds the camera identity, epoch, resolution and map ID/version/hash. It is held in memory and grants no motion authority.

Small foreshortened markers use a live-only bounded recovery path: two canonical sampling profiles, the ArUco dictionary's supported one-bit correction, and at most 32 small native-pixel rejected-quad crops with preserved image offsets. Complete four-marker geometry and agreement with ordinary detections remain mandatory; conflicting or duplicate IDs reject recovery. Partial detections from separate sampling profiles are never combined. This improves decoding without resizing the camera image or relaxing physical calibration claims. A backend restart discards its in-memory reference and requires explicit relocking even if the camera process continues with the same epoch.

| Condition | Display behavior |
| :--- | :--- |
| No accepted four-marker lock | Show the camera; withhold the registered route and board-focus mask. A candidate is not a lock. |
| Visible markers match the lock | Use the fixed homography without fitting it again. Partial matching markers retain the same reference. |
| Markers are temporarily hidden or evidence is insufficient | `locked_occluded` retains the fixed display reference, explicitly marks current alignment unverified and remains display-only. Occlusion alone does not trigger refitting. |
| Identity, epoch, resolution or map changes | Latch `view_changed`, withhold the old overlay and require another explicit lock. |
| At least two spatially distributed markers establish a coherent shift across three new accepted frames | Latch `view_changed`; do not automatically refit or silently clear the condition. |
| Stale live frame | Hide the current route projection; keep the source/age warning visible. |

These marker checks are display-inhibition heuristics, not a guarantee of detecting every camera displacement or a physical calibration result. An isolated questionable marker is insufficient to declare a confirmed shift. Conversely, retaining a reference under occlusion does not prove alignment. Do not move the map or camera and assume an old lock remains valid.

Camera preserves the original JPEG perspective. **Board focus** only masks the area outside the registered board; **Full frame** remains available. No rectification, detail synthesis, board resampling or global image blur is introduced. Glass panels intentionally soften their own backdrops and may cover part of the scene.

## API and capability meaning

The contract is [`contracts/live-camera.ts`](../contracts/live-camera.ts), schema `pushpilot.live-camera.v1`.

| Endpoint | Behavior |
| :--- | :--- |
| `GET /api/v1/live-camera` | Preview state, source/frame identity, age, detections, display registration and `motion_authority: false`. |
| `GET /api/v1/live-camera/frames/{frame_id}/image` | Original JPEG bytes from the bounded RAM cache. |
| `POST /api/v1/live-camera/registration` | Explicit `{epoch, frame_id}` display lock, rejected for stale, changed or insufficient-marker input. |
| `GET /api/health` | `camera_preview_connected` reports a currently live preview. Simulation, `robot_connected: false` and `hardware_connected: false` remain separate. |

The legacy workspace `camera` capability refers to qualified control observations, not this preview connection, and remains false. A live preview is not a trusted action-bound camera adapter. It does not change a mission revision, produce a GREEN observation, complete a step, persist a review image or call MUSE. **Image tools** and before/after review still use deliberately selected immutable recorded images. Adding live frames to those evidence paths requires a separate capture-and-receipt design and verification.

---

[Source-labelled workflow](MISSION.md) · [Release boundaries](../tools/README.md) · [GX10 deployment](../deploy/README.md)
