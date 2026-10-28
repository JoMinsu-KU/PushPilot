# GX10 robot commissioning deployment

This is separate from the tablet application, POC runtime and standalone camera. See [behavior and commissioning order](../docs/ROBOT_CONTROL.md). Do not establish a physical execution session without a newly measured reviewed installation/profile. The explicit profile-wait mode below keeps its preparation process alive, but does not open the pendant port before that profile is valid.

**Installed October 28, 2026, 01:17 KST:** `pushpilot-robot-control.service` is active/enabled, serving the isolated API from `6cfe6d2` at GX10 loopback 8897. Startup is disarmed, receiver disconnected, no installation loaded and no commands created. The separate physical listener remains stopped. Dependencies and 64 equipment-free tests passed on Python 3.12.3 ARM64; authenticated status, rejection behavior and existing web/camera retention were checked. See [the scoped evidence](../docs/evidence/robot-control-20261028.json). User lingering is disabled; startup after reboot without login is unverified. No shared login/boot policy was changed.

**Historical profile-wait startup, October 28:** source `98b2a19` was installed separately for `pushpilot-rodi-host.service`, manually started without boot activation. It opened the pendant port while its explicit reviewed profile path was absent. No BEGIN, mailbox consumption or motion occurred. The API/web PIDs and exact camera reference/epoch remained unchanged. All 474 equipment-free tests passed on GX10; the private protocol hashes were independently checked. [Historical startup evidence](../docs/evidence/rodi-profile-wait-20261028.json) records that limited state.

**Protocol correction, October 28:** actual pendant HELLO packets subsequently confirmed `poc-persistent-v1`, but the missing-profile branch closed without BEGIN. This is not persistent operation and unnecessarily strands the installed script. Profile waiting now validates and retries local configuration before binding/listening; the preparation process stays alive with `listening: false`. It opens the port only after a genuine reviewed profile is available and then uses the original persistent exchange. The exact pendant `45102` numeric error remains unproven. See [the POC receiver review](../docs/POC_RECEIVER_REVIEW.md) and [correction evidence](../docs/evidence/rodi-startup-correction-20261028.json) for deployed status and verification boundaries.

## Files and process arrangement

- Dedicated root: `~/pushpilot-robot-control/` with `releases/<commit>/` and private `shared/`.
- Public Python wrapper and exact dependency lock in the release.
- Hash-verified inherited runtime under `shared/receiver/`; no old profiles, mailboxes or runs.
- `shared/control.sqlite3`, `shared/control.token`, and new measured profiles stay private.
- API binds GX10 loopback `127.0.0.1:8897`, one Uvicorn worker. Use SSH or an explicitly selected SSH forward; the Windows local tunnel may use a different port.
- Real receiver listener keeps the existing installed script's address/port. Only one host may bind it. Do not stop an existing owner to make room.

Install the matching pinned dependencies in a separate virtual environment:

```sh
python3 -m venv ~/pushpilot-robot-control/venv
~/pushpilot-robot-control/venv/bin/python -m pip install -r deploy/requirements-robot-control.lock
```

On the local handoff machine, import only allowlisted exact source files:

```sh
python tools/install_robot_runtime.py --help
```

Transfer those verified runtime files privately into `shared/receiver/`. No archive containing old live state is unpacked into the receiver. The API's private loader validates every module hash again before importing it.

## Start the API without opening robot sockets

From the matching release directory:

```sh
~/pushpilot-robot-control/venv/bin/python tools/serve_robot_control.py \
  --backend legacy --receiver-root ~/pushpilot-robot-control/shared/receiver \
  --state ~/pushpilot-robot-control/shared/control.sqlite3 \
  --token-file ~/pushpilot-robot-control/shared/control.token --port 8897
```

This opens the local HTTP service and exclusive mailbox ownership only. With no host session it reports disconnected/disarmed. It does not read Native hardware, launch Rodi/camera, restore a profile or submit a target. An optional user service may restart **this API only** after failure; every start disarms and refuses replay. Never auto-start the physical host using a historical profile. See [API service template](pushpilot-robot-control.service.example).

## Deliberate physical host startup tomorrow

### Keep preparation alive while current measurements are being prepared

```sh
python tools/serve_rodi_host.py --runtime <shared/receiver> \
  --profile <new-absent-reviewed-profile.json> --listen --motion --wait-for-profile
```

Use a new explicit private path, never an old profile. When it is missing/invalid, this mode waits and revalidates once per second without creating a pendant socket, reading Native state or consuming commands. It preserves the current session pointer and historical mailboxes. `host-status.json` reports `waiting_reviewed_profile`, `listening: false`, `ready: false` and `waiting_for_manual_play: false`. A running process is not a ready receiver. Do not ask the operator to PLAY at this stage.

The installed script's local motion flag is true; `--motion` matches that protocol flag and does not invent a reviewed profile. A false `allow_motion`/`site_verified` placeholder cannot complete the installed BEGIN check. Do not manufacture true qualification flags merely to retain idle. After a genuine profile becomes valid, the host reports `waiting_for_manual_play` and `listening: true`; then one fresh manual PLAY can establish the original persistent session. No script editing is required for this qualified path. Approximately +/-2 mm operator-reported clearance and stationary telemetry alone do not establish reviewed installation/contact geometry.

The [separate host service template](pushpilot-rodi-host.service.example) uses `Restart=on-failure` to restore host preparation, not commands. Start it deliberately; do not enable automatic boot with an old profile. Keep the existing API/camera/web processes running. Its code release may differ from the already running API; record both identities independently.

### Establish persistent idle with a reviewed profile

After preparing a new private profile with measured bounds, pose/joints, TCP and payload:

```sh
python tools/prepare_robot_installation.py --help
python tools/serve_rodi_host.py --runtime <shared/receiver> --profile <new-reviewed-profile.json>
python tools/serve_rodi_host.py --runtime <shared/receiver> --profile <new-reviewed-profile.json> --listen --motion
```

The first host command is offline validation only. The second is the explicit physical listener; PLAY the installed persistent receiver after it is ready. Normal idle goal/profile changes need no script editing or repeated PLAY. A disconnected pendant may require manual PLAY again because its existing script has no reconnect loop.

Do not infer readiness from HTTP health alone. Confirm authenticated status, fresh exact receiver identity, reviewed measured installation, actual pose and joint readback, correct motion mode, no unresolved command and a deliberate arm. Prove endpoint receipt plus vehicle outcome separately.

Closing a service, HOLD and request cancellation do not stop an executing robot motion. Network reconnect never authorizes resending a target. Reconcile unknown outcomes against actual hardware before rearming.
