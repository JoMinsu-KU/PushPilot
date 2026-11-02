# Spatial signal design preview

This standalone local page previews one standing paper-style signal beside the south crosswalk, west of Office. Its slim black card has a light edge, green above red, and a fixed south-facing orientation.

From the repository root in PowerShell, launch the frontend-only preview:

```powershell
Set-Location frontend
node ./node_modules/vite/bin/vite.js --config vite.spatial-preview.config.ts
```

Open **http://localhost:9220/spatial-preview.html**. The server binds to `127.0.0.1:9220` and requires that port to be available. Use **City overview** or **Signal detail** to change views; drag to orbit and scroll or pinch to zoom.

**Base state** is the default: both printed colors remain visible and neither emits light. **Green approved** illuminates only the upper green face; the red face retains its printed appearance. Switch back to **Base state** to remove the glow. These controls select a visual example and do not represent a camera observation or mission approval.

The existing frontend dependencies and private city asset are prerequisites. Keep `frontend/public/models/private/pushpilot-city-clean-roads.glb` and its matching `frontend/public/models/city-display.json` manifest installed. The current asset is 2,296,484 bytes with SHA256 `842a7c32e9c8634a9eef12a741e3d4f5ea7727710b88353dc116095d309d9bf2`; loading verifies the manifest hash. Private artwork is not included in public source. The signal is a separate display-only group and does not change that asset or its hash.

This page runs without a backend or API connection. Its Vite configuration rejects `/api` requests. It does not deploy anything, connect to equipment, change robot state, or send robot commands. Stop the local server with **Ctrl+C**.

The main application source also passes a read-only signal appearance through `App` → `MapScene` → `CityModelView`. The pure `spatialSignalState` adapter consumes existing physical-status and display snapshots; it adds no polling, admission decision, movement command, or signal wait. Only a fresh display feed bound to the same mission, plan, revision, workspace session and map can show an accepted admission. Before admission, raw GREEN, waiting/confirming and an outstanding signal check keep both printed colors unlit. A stale display feed, disconnected evidence or an ended mission also restores the base appearance. An admitted GREEN must satisfy the configured frame count and have a valid observation timestamp. The server owns the image-age and admission budget; the renderer does not add a separate timeout to an accepted phase. Once the accepted departure is recontacting or passed, its approval stays visible despite the normal counter reset or an older approved image. Approval is distinct from a claim that the image is a current color observation; feed freshness remains mandatory throughout. The standalone page retains its manual visual controls. This source integration does not deploy or restart a service.
