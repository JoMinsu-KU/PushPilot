# GX10 robot commissioning deployment

This is separate from the tablet application, POC runtime and standalone camera. See [behavior and commissioning order](../docs/ROBOT_CONTROL.md). Do not start a physical listener without a newly measured reviewed installation/profile.

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

After preparing a new private profile with measured bounds, pose/joints, TCP and payload:

```sh
python tools/prepare_robot_installation.py --help
python tools/serve_rodi_host.py --runtime <shared/receiver> --profile <new-reviewed-profile.json>
python tools/serve_rodi_host.py --runtime <shared/receiver> --profile <new-reviewed-profile.json> --listen --motion
```

The first host command is offline validation only. The second is the explicit physical listener; PLAY the installed persistent receiver after it is ready. Normal idle goal/profile changes need no script editing or repeated PLAY. A disconnected pendant may require manual PLAY again because its existing script has no reconnect loop.

Do not infer readiness from HTTP health alone. Confirm authenticated status, fresh exact receiver identity, reviewed measured installation, actual pose and joint readback, correct motion mode, no unresolved command and a deliberate arm. Prove endpoint receipt plus vehicle outcome separately.

Closing a service, HOLD and request cancellation do not stop an executing robot motion. Network reconnect never authorizes resending a target. Reconcile unknown outcomes against actual hardware before rearming.
