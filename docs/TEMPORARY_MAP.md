# Little Town temporary workspace

**A replaceable drawing, recorded scene and inspectable simulated route.**

[Development](DEVELOPMENT.md) · [Scene inputs](TEST_INPUTS.md) · [Verification](VERIFICATION.md) · [Contracts](../contracts/README.md)

The user authorized implementation against the temporary print on 2026-10-27. This releases the earlier map hold for a test adapter and camera-to-board image overlays. It does not establish the final production map, robot BASE coordinates, physical stop lines, pushing contact or turn qualification.

## Drawing and route identity

The reviewed data file is `backend/data/little-town-temporary.json`, with map ID `little-town-temporary` and version `2026-10-27.1`. It adapts printed geometry, graph connectivity and marker facts from the existing PushPilot v11 design. Source hash and exact adaptation are recorded inside the file; original artwork, historical POC transforms and obsolete grasp assumptions are excluded.

| Destination | Deterministic route | Drawing centerline | Abstract actions |
|---|---|---:|---:|
| BOOKSTORE | PIZZA → C → BOOKSTORE | 148 mm | 5 |
| BAKERY | PIZZA → C → S → BAKERY | 232 mm | 8 |
| SCHOOL | PIZZA → C → S → SCHOOL | 232 mm | 8 |

Routing starts at PIZZA facing east and follows enabled cardinal drawing edges. The canonical geometry hash binds the board, graph, markers and destination layout. These lengths describe the drawing; they are not TCP travel distances or qualified vehicle trajectories. Centerline containment does not establish car/tool swept clearance.

Each intermediate junction contributes an approach, mandatory simulated stop and admitted crossing. Crossing descriptions retain the intended turn direction. Every junction needs its own accepted demo stop review and fresh scoped GREEN. A previous junction's GREEN or stop verification cannot authorize the next one. Actual stop-line offsets and physical contact-turn motions remain unqualified.

## Recorded scene and test overlay

1. Open **Image tools** and upload a JPEG or PNG, at most 8 MiB and 12 megapixels. No image means the spatial schematic remains available.
2. An optional capture time is explicitly operator-provided. Without it, capture time stays unknown. The receive timestamp never turns a recorded photograph into a live observation.
3. Detect ArUco `DICT_4X4_50` markers 10–13. Four consistent marker regions support a candidate planar projection.
4. Select **Lock test view** to bind the reference frame, image dimensions, map ID/version/hash and matrix to a new registration ID. The photograph's SHA-256 identifies its immutable bytes.
5. Create a goal and inspect its projected route. The photograph and SVG overlay share the original image viewBox, so responsive resizing preserves their alignment without cropping.

Candidate detections do not display a planned photo overlay until the reference is explicitly locked. The spatial schematic is an original code-native rendering of the drawing facts and is available without private artwork.

After locking, visible marker agreement checks the retained matrix. Partial visibility keeps the reference without refitting and warns that hidden areas are unverified. Moved/inconsistent views, missing markers or changed image dimensions withhold the old overlay. A complete new observation can be explicitly registered again. These image-space checks do not establish absolute millimeter accuracy.

The implementation uses a 3 px RMS / 6 px maximum residual check for this test overlay. Those are software image checks, not qualified robot tolerances. Replacing map identity or version invalidates the stored frame, registration and inspection bindings; it also invalidates incompatible mission plans. Raw frame/history records remain preserved for review.

## Actual MUSE image inspection

**Inspect image with MUSE** sends the selected original frame and stated expectation to the backend Meta adapter. The image is sent only on this explicit action; the key remains server-side. The result binds frame hash, map identity, model, expectation and timestamp. A newer scene revision prevents a late response from attaching to the current frame.

The strict response reports `USABLE`, `REOBSERVE` or `UNKNOWN`, visible places, physical-car visibility, a model-reported paper-signal color and limitations. A printed START rectangle or vehicle footprint is not a physical car. Tiny printed traffic-light artwork is not the separate operator paper signal.

**Scene inspection does not approve an action, supply the deterministic signal gate or advance the mission.** Per-action demo reviews remain separately labelled. The complete action-bound fresh-image review and measured local completion integration is still pending. `USABLE` means the image supports scene inspection, not successful vehicle arrival.

No live camera connection or robot transport is opened by the application. The first connected frame is a recorded native 1920×1080 GX10 photograph; its source stays `recorded`. The existing camera and robot services are outside this application lifecycle.

## Replace the temporary map

Set `PUSHPILOT_MAP_PATH` to a reviewed replacement definition and use a new version/installation record. Set `PUSHPILOT_SCENE_DIR` to a private runtime folder if shared state needs a separate location; by default it is beside the SQLite database. Preserve prior frame and decision evidence.

Restart only this application, inspect the replacement identity, prepare a new plan and register its test image explicitly. No prior robot profile, mailbox, TCP pose or camera-to-BASE transform is imported. Final installation and measured physical qualification remain a separate release gate.
