# Spatial signal design preview

This standalone local page previews one standing paper-style signal beside the south crosswalk, west of Office. Its slim black card has a light edge, red above green, and a fixed south-facing orientation, matching the installed paper signal.

From the repository root in PowerShell, launch the frontend-only preview:

```powershell
Set-Location frontend
node ./node_modules/vite/bin/vite.js --config vite.spatial-preview.config.ts
```

Open **http://localhost:9220/spatial-preview.html**. The server binds to `127.0.0.1:9220` and requires that port to be available. Use **City overview** or **Signal detail** to change views; drag to orbit and scroll or pinch to zoom.

**Base state** is the default: both printed colors remain visible and neither emits light. **Red observed** illuminates only the upper red face. **Green approved** illuminates only the lower green face. The other face retains its printed appearance, and switching back to **Base state** removes the glow. These controls select a visual example and do not represent a camera observation or mission approval. Both illuminated states reuse one card-parallel halo that moves to the selected face and changes color without allocating new resources.

The existing frontend dependencies and private city asset are prerequisites. Keep `frontend/public/models/private/pushpilot-city-clean-roads.glb` and its matching `frontend/public/models/city-display.json` manifest installed. The current asset is 2,296,484 bytes with SHA256 `842a7c32e9c8634a9eef12a741e3d4f5ea7727710b88353dc116095d309d9bf2`; loading verifies the manifest hash. Private artwork is not included in public source. The signal is a separate display-only group and does not change that asset or its hash.

This page runs without a backend or API connection. Its Vite configuration rejects `/api` requests. It does not deploy anything, connect to equipment, change robot state, or send robot commands. Stop the local server with **Ctrl+C**.

The main application source also passes a read-only signal appearance through `App` → `MapScene` → `CityModelView`. The pure `spatialSignalState` adapter consumes existing physical-status and display snapshots; it adds no polling, admission decision, movement command, or signal wait. A fresh display feed must match the mission, plan, revision, workspace session and map, with a valid signal gate and observation timestamp. While the mission is stationary in its signal wait, the latest source-bound MUSE RED observation illuminates the upper red face only when both status and display agree on waiting and no signal check is outstanding. This depicts observed red while waiting; collector publication freshness does not establish image freshness. Active missions need not advertise start availability for this display.

Before admission, raw GREEN, UNKNOWN, confirming and an outstanding signal check keep both printed colors unlit. A stale display feed, disconnected or invalid evidence, or an ended mission restores the base appearance. An admitted GREEN must satisfy the configured frame count and have a valid observation timestamp. The server owns the image-age and admission budget; the renderer does not add a separate timeout. Once the accepted single departure is recontacting or passed, its green approval takes precedence over a later RED/UNKNOWN observation, a reset counter or an older approved image. It adds no new stop or signal wait. Approval is distinct from a claim that the image is a current color observation; feed freshness remains mandatory throughout. The standalone page retains its manual visual controls. These source changes do not deploy or restart a service.

## Operational activation · November 2, 2026

The operator subsequently authorized production activation, coordinated with the robot-operations chat. Frontend source `cf1efa82ec1a81fa127c379c2ba678ffae0a1be9` was rebuilt from the clean commit and activated as overlay `20261102-spatial-signal-cf1efa8` on the existing backend release `20261031-c11-activation-fix`. Content-hashed chunks were installed before an atomic index replacement; the previous index and old chunks were retained. The standalone page and its manual controls were not installed in the operator workspace.

GET-only verification matched all five deployed entry/chunk hashes and confirmed the base two-color signal in Spatial. Web/receiver/API service identities, camera epoch and fixed registration, idle workspace, model and no-command state were retained over activation. No service restart, robot motion, new MUSE request or live GREEN admission was used to verify deployment. The independent receiver connection issue remains outside this UI change. Frontend checks passed 136 tests, TypeScript and both builds; backend checks earlier in the same source work ran 1,177 tests with five skips. An existing tablet tab needs one refresh to load the new entry. Private activation/rollback records remain outside Git.
