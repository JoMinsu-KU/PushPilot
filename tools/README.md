<sub>[PushPilot](../README.md) / Engineering / Tools</sub>

# Small tools, explicit boundaries

**Check the workspace. Package committed source. Verify the result.**

[Development](../docs/DEVELOPMENT.md) · [Live camera](../docs/LIVE_CAMERA.md) · [Tests](../tests/README.md) · [Deployment](../deploy/README.md)

## Catalogue and access boundaries

**Reviewed November 2, 2026, including Native recovery source `bcac769`.** Run from the repository root with Python 3.12+ and the pinned environment. Table entries are files/tools, not instructions to activate equipment. `--help` describes the current arguments; do not assume every helper exposes a command-line interface.

| Group | Tools / files | External access and effect |
| --- | --- | --- |
| Source-only checks and packaging | `dev.py check`, `dev.py test`, [build_release.py](build_release.py) | Syntax, offline suite, committed-source archive/verification. No equipment/provider calls; release tools need Git. Tests do not activate services. |
| Public recorded-review site | [build_review_site.py](build_review_site.py) | Builds only the existing review HTML, pinned Pretendard font/license and static marker. Preserves original responses/image hashes; [hosting guide](../docs/REVIEW_HOSTING.md). No backend or equipment code is loaded. |
| Drawing and route preparation | [validate_map.py](validate_map.py), [preview_taught_roads.py](preview_taught_roads.py), [calibrate_robot_board.py](calibrate_robot_board.py) | Offline map/graph or measured-pair analysis. Outputs are candidates/private measurements, not physical calibration acceptance or motion authority. |
| Private model preparation | [install_city_model.py](install_city_model.py), [clean_city_roads.py](clean_city_roads.py) | Read a reviewed supplied GLB/package and write private model derivatives. No package scripts or network. Follow the current [Spatial manifest](../docs/SPATIAL_3D.md); the historical installer alone may not match the current viewer. |
| Private source/profile preparation | [install_robot_runtime.py](install_robot_runtime.py), [prepare_robot_installation.py](prepare_robot_installation.py), [prepare_local_commissioning.py](prepare_local_commissioning.py), [prepare_local_contact.py](prepare_local_contact.py), [prepare_contact_turn.py](prepare_contact_turn.py) | Offline allowlisted import/profile generation using explicit measured review. Does not measure clearance, apply a profile or open robot sockets. |
| Private recipe analysis | [build_measured_mission_catalog.py](build_measured_mission_catalog.py), [build_delivery_release.py](build_delivery_release.py), [screen_delivery_clearance.py](screen_delivery_clearance.py), [revise_delivery_endpoint.py](revise_delivery_endpoint.py), [revise_c_progress_review.py](revise_c_progress_review.py) | Offline catalogue/compiler/screening helpers, some imported as functions. Retain source hashes and old outcomes. Geometry screening is not contact physics or activation. |
| Synthetic review fixtures | [action_review_fixtures.py](action_review_fixtures.py), [evaluate_action_reviews.py](evaluate_action_reviews.py) without `--call-meta` | Self-authored fixture generation and offline case setup only. Outputs remain outside source; real photographs/coordinates are not fixtures. |
| Provider requests | [check_muse_api.py](check_muse_api.py), `evaluate_action_reviews.py --call-meta` | Explicit real Meta API calls; key stays server-side/private and calls can consume credits. Not part of offline checks or hardware qualification. |
| Read-only robot acquisition | [read_robot_pose.py](read_robot_pose.py), [capture_fixed_start.py](capture_fixed_start.py) | Contacts Native FC03; fixed-start capture also reads the local robot API. No movement. Coordinate freshness and target ownership still matter; do not introduce a competing Native poller during a live mission. |
| Camera acquisition and target | [capture_camera_intrinsics.py](capture_camera_intrinsics.py), [camera_calibration_target.html](camera_calibration_target.html) | Reads the existing preview for bounded private checkerboard captures; requires separately proven optics identity. Target HTML displays a pattern. No robot commands, but real camera acquisition is not an offline test. |
| Application/mock startup | [serve.py](serve.py), `serve_robot_control.py --backend mock` | Starts local HTTP services. Main app defaults to simulation; explicitly configured live-camera/physical adapters can read their services. It does not install services, PLAY Rodi or automatically start a route. |
| Real camera helper | [camera_preview.py](camera_preview.py) | Explicit Linux capture with device permission and ffmpeg; owns its own capture child. No MUSE or robot commands. Do not restart it for a frontend change. |
| Commissioning API/client | `serve_robot_control.py --backend legacy`, [robotctl.py](robotctl.py) | Real backend owns the mailbox ledger and reads current host state. Client status/events are reads; arm/command/profile/reconcile operations mutate control state and can issue physical motion. Verify selected target and private token. |
| Persistent host | [serve_rodi_host.py](serve_rodi_host.py) | Without `--listen --motion`, validates the supplied profile offline. With both flags, opens the real pendant listener and uses Native/wire IO. `--wait-for-profile` waits before binding. Deployed legal-idle recovery retains the session during known read outages and requires fresh stationary samples; no automatic PLAY, reconnect or motion replay. [Scope](../docs/HOST_NATIVE_RECOVERY.md) |
| Physical commissioning runners | [run_coordinate_unit.py](run_coordinate_unit.py), [run_taught_executor.py](run_taught_executor.py) | Offline validation unless `--execute` is explicit. Execution uses real robot/camera/provider ports and new private journals. Coordinate-unit runner matches current whole-unit mechanics; taught runner is the separate compatibility per-action path. |

All Python tools and the camera target in `tools/` are covered above. Commands fail nonzero on rejected input; this does not imply a controller stopped. Never run a live provider check, real capture, profile activation or physical runner as part of a documentation/source validation task.

Meta MUSE is the configured visual reasoning service for route interpretation and original-image progress, signal and arrival review. A provider failure remains an error/pending review; no silent mock fallback supplies a PASS. [Action reviews](../docs/ACTION_REVIEWS.md) separates recorded simulation from the live physical observer.

## Common source checks

```sh
python tools/dev.py check
python tools/dev.py test
cd frontend
npm ci
npm test
npm run build
```

Build with Node 24 locally; GX10 serves compiled assets with Python. `serve.py` defaults to loopback 8080 and one worker. `--api-only` omits static assets. `PUSHPILOT_MAP_PATH`, `PUSHPILOT_SCENE_DIR` and optional `PUSHPILOT_LIVE_CAMERA_URL` select current private map/media/preview inputs; `PUSHPILOT_PHYSICAL_CONFIG` explicitly opts into a reviewed private physical driver. An unconfigured checkout has no Robot authority. See [deployment prerequisites](../deploy/README.md#private-deployment-prerequisites).

The native preview helper preserves JPEG bytes in a bounded latest-frame buffer and labels host-receive time separately from sensor exposure. Preview itself never authorizes a movement. The [operations runbook](../docs/ROBOT_OPERATIONS.md) covers actual START/reset/resume/reconnect decisions; reset is not a return command.

## Build a source release

Review and commit the intended source with the user's real Git identity. The builder requires a committed HEAD and a clean tree, including no staged changes or nonignored untracked files. Finish and commit the intended snapshot rather than removing work to satisfy the tool.

Create the output directory **outside this repository** first. This Python command works in PowerShell and a POSIX shell:

```sh
python -c "from pathlib import Path; Path('../release-bundles').mkdir(parents=True, exist_ok=True)"
python tools/build_release.py --output ../release-bundles/pushpilot-source-v0.1.0.zip
python tools/build_release.py --verify ../release-bundles/pushpilot-source-v0.1.0.zip
```

Choose a new filename for every bundle; the CLI rejects an existing target. The example filename's version is a human label. The manifest binds the actual Git commit and generated release identity.

## Inside the archive

The builder reads committed Git blobs. Its source allowlist covers selected root files and the `frontend`, `backend`, `contracts`, `prompts`, `tests`, `deploy`, `docs`, and `tools` directories. It adds `release-manifest.json` with the Git HEAD and each source file's size and SHA-256.

Tracked private/credential paths, symlinks, submodules, and special files fail the build even outside the allowlist. Ignored local files are not packaged. Unsupported top-level content is excluded; review the manifest before publication.

Verification rejects unsafe or colliding paths, unsupported ZIP entries, unexpected/missing files, hash mismatches, and oversized content without extracting. Current limits are 10,000 entries, 32 MiB per source entry, 128 MiB total uncompressed content, and a 4 MiB manifest.

## A release is not a deployment

The release builder produces a **committed source package**. It excludes ignored compiled `frontend/dist`, dependencies, local configuration, and SQLite state. A runnable frontend delivery additionally needs assets built from the same clean commit.

`serve.py` starts the application locally; it does not install dependencies, transfer files, configure a system service, select an active release, implement rollback, or issue robot commands. Follow [GX10 delivery](../deploy/README.md) for the selected Python/static-frontend arrangement and remaining host checks.

Review contents separately for credentials, private media, attribution, and publication rights. Hash integrity does not authenticate a publisher or replace that review.

---

[Release tests](../tests/test_release_bundle.py) · [Contribution record](../CONTRIBUTIONS.md) · [Third-party notices](../THIRD_PARTY_NOTICES.md)
