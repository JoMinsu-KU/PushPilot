<sub>[PushPilot](../README.md) / Backend / Live intelligence</sub>

# Original frames, selected roads, explicit decisions

The backend connects deliberate native-camera observations to MUSE route proposals, action comparisons and stopped-signal judgments. The resulting execution remains **simulation only**. A real camera image is not a physical robot receipt, measured vehicle pose or qualified motion permission.

[Camera preview](LIVE_CAMERA.md) · [Signal policy](MUSE_SIGNAL_GATE.md) · [Voice input](VOICE_INPUT.md) · [Contracts](../contracts/live-intelligence.ts)

## Three separate decisions

| Operation | MUSE receives | Local acceptance |
|---|---|---|
| Live plan | Original JPEG, exact accepted user query, selected map graph, frame/registration identity and optional route constraints | Validate the response, compile the exact selected directed node sequence, check declared and explicit constraints, then recheck workspace/map/camera identity. Operator approval remains required. |
| Live action review | Server-bound original BEFORE and AFTER JPEGs, the action context and the expected visible result | Match the approved simulated action, current pending review, frame provenance and camera registration before applying the verdict. |
| Stopped signal review | A new original JPEG, the current simulated stop receipt and the configured approach-specific signal target | Check the same approved stop context, request, map, registration and result-age policy. MUSE supplies the visual color judgment. |

The preview loop does not call MUSE or persist every frame. Only an explicit operation selects and copies native JPEG bytes into the private evidence ledger. There is no image resizing, board rectification, display-mask capture or JPEG recompression on this path.

Display-reference continuity is separate: an explicit four-marker lock stores a private server receipt, and `POST /api/v1/live-camera/registration/resume` accepts only `{epoch}` to revalidate its exact old homography after lost RAM state. The current camera/epoch, dimensions and map must match, with at least two distributed visible markers agreeing and no latched view change. No fitting or arbitrary client transform is accepted. A matching `saved_reference_available` flag alone does not establish successful resume. The new display registration identity cannot restore old plan approval, inference/stop/signal authority or robot coordinates; these operations still revalidate their own current bindings. See [live camera continuity](LIVE_CAMERA.md#fixed-display-registration).

## HTTP surface

All mutation commands carry a UUID `request_id` and the exact current integer `expected_revision`. JSON objects reject unknown command fields. Successful operations return a workspace snapshot; an accepted clarification, RED or UNKNOWN judgment is not a successful mission or an admitted crossing.

| Method and path | Request additions | Purpose |
|---|---|---|
| `POST /api/v1/plans/live` | `text`, `source: "typed" | "voice"`, optional `transcript_id`, optional `route_constraints` | Request one live-image/graph route proposal during preparation. |
| `POST /api/v1/live-actions/advance` | None | Pin BEFORE and complete exactly one non-crossing abstract simulated action. |
| `POST /api/v1/live-actions/run` | None | Combine one live advance or reobservation with its fresh AFTER/MUSE review. This is one bounded operation, not an autonomous mission runner. |
| `POST /api/v1/live-actions/reviews` | `review_id`, `expected_visual` | Select a new AFTER frame and request a bound MUSE comparison. |
| `POST /api/v1/live-actions/reobserve` | None | After an uncertain review, preserve the action's original BEFORE and create a new pending review identity. No action is repeated. |
| `POST /api/v1/live-signals/reviews` | None | While stopped, select a new frame and judge the configured signal for the current approach. |
| `POST /api/v1/live-signals/wait` | Optional `max_attempts: 1..3`, optional `interval_seconds: 0.5..10` | Run a finite series of new stopped-signal observations, stopping on an admitted crossing or an invalidating state change. |
| `POST /api/v1/live-signals/watch` | Optional `max_attempts: 1..60`, `interval_seconds: 0.5..10`, `max_duration_seconds: 1..900` | Start bounded background observations for the current approved stop context and return immediately. |
| `POST /api/v1/live-signals/watch/stop` | None | Cancel this observation task; this is not a physical robot stop. |
| `GET /api/v1/live-signals/watch` | None | Return `{signal_watch, motion_authority: false}`; `signal_watch` is null when no watch exists. |
| `GET /api/v1/live-intelligence/operations` | None | Inspect the latest 100 journal entries, including pending, accepted, rejected and interrupted operations. |
| `GET /api/v1/live-evidence/frames/{id}/image` | None | Retrieve the immutable original JPEG selected for an explicit operation. |

`POST /api/v1/goals` with `provider: "meta"` uses live planning when the live-camera path is enabled. Set `planning_mode: "live"` to require it explicitly, or `planning_mode: "symbolic"` to choose legacy text-only destination interpretation. When the camera is unconfigured and the mode is omitted, the legacy default remains symbolic for compatibility. A failed live request never falls back to symbolic or demo planning. Voice confirmation uses the live MUSE path. Demo planning and manually injected simulation data remain separately sourced.

Example request against a selected map:

```json
{
  "request_id": "047798c1-e995-411a-8f26-2906b3e8f321",
  "expected_revision": 12,
  "text": "Go to School using the road on the left side of the map.",
  "source": "typed",
  "route_constraints": {
    "departure": "west",
    "first_turn": "any",
    "via_nodes": [],
    "avoid_nodes": []
  }
}
```

The example demonstrates the command shape, not a route validated on a final installation. Directional constraints refer to the currently selected map. A left turn means a maneuver relative to the incoming route at the first junction; a west departure means the fixed left side of that map. Ambiguous natural language requires clarification.

## Route proposal to AR geometry

The provider returns exactly:

```json
{
  "destination": "SCHOOL",
  "summary": "Use the road on the left side of the map to School.",
  "route_nodes": ["PIZZA", "W", "SW", "SCHOOL"],
  "requires_clarification": false,
  "constraints": {
    "departure": "west",
    "first_turn": "any",
    "via_nodes": [],
    "avoid_nodes": []
  },
  "scene_assessment": {
    "status": "clear",
    "detail": "The selected map is visible. Physical vehicle position is not established."
  }
}
```

These example IDs belong to the temporary drawing, not the future physical layout. The provider's allowed identities are generated from the selected map, including `UNKNOWN` as a destination requiring clarification. A clarification has an empty route. No pixel coordinates, TCP positions, scripts or approval fields are accepted.

`MapDefinition.route_from_nodes` compiles exactly the proposed path. Each adjacent pair must be an available directed road, the first node must be the declared start, the last must be the selected destination, and the simple path cannot repeat nodes. The backend checks departure, the first junction maneuver, ordered via nodes and avoided nodes. It does not silently replace an invalid proposal with a shortest route. These checks validate the structured interpretation; they do not prove that MUSE interpreted natural language correctly.

Prompt `pushpilot.live-route.prompt.v3` prefers the most direct connected path for a destination-only request, without unnecessary turns or invented mandatory central-junction visits. Explicit direction, via, avoid and detour requests still take priority and their exact selected graph path is preserved. City version `2026-10-28.3` places destinations on their front roads: the direct Office preview is `PIZZA → S → OFFICE_BUILDING`, while Villa and Hanok can reach their front roads through C. The direct Office route does not exercise the central paper-signal approach; its generic simulated junction checks do not invent a reviewed physical signal target.

The backend derives route drawing coordinates, segmented display geometry and maneuver descriptions from the validated path. The frontend can consume that geometry through the existing registered camera transform. MUSE does not draw the AR polyline and cannot alter the map's coordinates. A changed final map requires a new reviewed map definition and explicit camera registration; old plans are not transported to a replacement print.

Planning is permitted only in non-executing preparation. A replacement immediately clears the prior approvable plan before capture or inference starts. An uncertain scene becomes a clarification with no route. Camera, provider or graph failure leaves no silently restored prior plan or demo fallback.

## Live action comparison

The sequence is explicit:

1. Approve the current plan.
2. Live advance selects and persists an original BEFORE frame, then records one **simulated** bounded action receipt.
3. Live review selects a different camera sequence whose conservative host-observation timing follows the review request. AFTER is therefore selected after the simulated action receipt.
4. MUSE compares the original pair against the supplied expectation.
5. The supervisor rechecks the current request/action/review/map/registered-camera context before applying the result.

`PASS` supports the stated visible result. `FAIL` contradicts it. `REOBSERVE` or `UNKNOWN` withholds continuation and permits another observation without repeating movement. A simulated PUSH with an unchanged real image must not be called a successful physical push. A printed vehicle illustration is not a separate model car.

The before/action binding is durable, but it is also bound to the current process boot. Restart does not make an old live pair eligible for automatic continuation. Existing recorded-pair review is a separate explicitly selected evidence source.

`/live-actions/run` exposes the capture/advance/review sequence as one backend request. It completes only one non-crossing simulated action, or creates a new observation after an uncertain review without repeating the action. It requires the current revision and approval. Its internal request identities are derived from the outer request so a retry cannot execute another action or dispatch another inference. If capture or inference fails after an action receipt exists, inspect the current pending review and retry that review explicitly; do not repeat the action.

When that request accepts a live-backed STOP review and reaches `WAITING_SIGNAL`, the application automatically starts the bounded signal watch only if the current view and reviewed approach-specific target are configured. Missing target metadata leaves the simulated mission stopped. This automatic start is bound to the original run request, so retrying that request does not start another watch.

## Mandatory stop and MUSE signal judgment

The current STOP must have an accepted review and a matching server-created **simulation** stop receipt. The route identifies the junction and incoming road node. The selected map must configure a signal target for that exact pair before a live signal request can be made.

The map metadata uses approach-specific entries such as:

```json
{
  "id": "paper-signal-for-approach",
  "junction_id": "JUNCTION_ID",
  "approach_from": "INCOMING_NODE_ID",
  "description": "The separate operator-controlled red/green paper card for this approach.",
  "bounds_mm": [10, 20, 25, 35]
}
```

The bounds and identities are illustrative, not installation coordinates. The current temporary map intentionally has no reviewed active-paper signal targets. The backend rejects live signal judgment until those targets are configured; printed traffic-light artwork does not qualify automatically.

MUSE returns only `color`, `visible`, `summary` and `limitations`. `RED` or `GREEN` requires an unambiguously identified readable target and `visible: true`. `UNKNOWN` uses `visible: false`. Occlusion, multiple plausible targets, ambiguous color or an unreadable controlling signal produces UNKNOWN. There is no second local color classifier.

The server projects the reviewed target rectangle through the selected frame's registered homography and includes that image polygon with its exact frame identity. An out-of-frame or invalid projected target is rejected. The native full image is still sent unchanged; a polygon is a location hint rather than proof that the target is unobscured or correctly recognized.

A valid RED or UNKNOWN keeps the mission stopped. A valid current GREEN can admit the single bound simulated crossing after local checks, without another operator approval. The signal image also becomes that crossing's BEFORE frame. Crossing completion still needs its own action review. Later signal changes apply to the next admission; this prototype does not implement physical in-flight red interruption.

Each signal request selects a new frame after its stopped observation request. At most one signal judgment is pending for a stop context. A later preview image alone does not supersede a pending request. Cancellation, a different stop, changed registration or an expired result does.

`/live-signals/wait` supplies a bounded wait cycle: at most three deliberate MUSE observations, each selecting a new frame, with a configured interval between attempts. Defaults are three attempts and two seconds between attempts. It returns after an admitted crossing, an exhausted attempt count, a provider/input failure or an invalidating context change. A caller may start another bounded wait request only while the current stopped context remains eligible. There is **no infinite background signal polling or autonomous full-mission runner**; preview polling does not trigger MUSE requests.

For waiting through a longer RED period, `/live-signals/watch` starts an asynchronous background task with **30 judgments, a two-second interval and a 300-second total budget by default**. Explicit limits are at most 60 judgments, intervals from 0.5 to 10 seconds and a total budget from 1 to 900 seconds. Attempts and elapsed time both cap the work; this is not an unlimited stream of paid requests. Every attempt uses a new server-bound frame through the same signal-review service. RED or UNKNOWN continues watching within the budget. A valid GREEN admits the current simulated CROSS and ends the watch; **CROSS remains pending its own action review**, and no later mission action runs automatically.

The workspace exposes `signal_watch` with an ID, `running | green_admitted | held | cancelled | exhausted | interrupted` status, attempt count, budgets, start time and explanatory detail. Provider failure or unusable view holds the watch without fallback or automatic restart. Mission/plan/stop-context changes and explicit watch cancellation prevent another query. Stopping the watch cancels observation work only, not a physical robot. Application shutdown/restart marks a running watch interrupted and never resumes it. Starting another watch after a terminal status requires a new eligible request; preview polling cannot start one.

## Provenance, journal and failure behavior

The private SQLite database stores original selected JPEG BLOBs and immutable observation IDs/hashes. Evidence URLs belong to that ledger, not the eight-frame preview cache. Selection metadata records the original native frame identity, sequence, epoch, camera, map identity, registration, host receive timestamp and age at selection. `sensor_exposure_time_known` remains false.

Post-action and post-stop ordering uses a conservative local bound derived from acceptance time minus upstream/transport age. It does not compare unsynchronized Windows and GX10 wall clocks, and it does not claim a known exposure time. The preview's 1500 ms freshness threshold and the signal result's default 30-second acceptance policy are simulation limits, not qualified physical-control tolerances.

The operation journal reserves a request before inference. Equal request IDs with equal payloads return the original completed receipt; they do not resend MUSE requests. The same ID with another payload is rejected. A duplicate pending request does not start another inference. Selected input metadata is attached to the journal before dispatch so failed operations can still be traced to their original frames.

Inference runs outside the workspace lock. Completion revalidates the workspace revision, session, current plan/step or pending-plan identity, selected map and camera registration. A cancelled or superseded operation cannot apply its late result. Cancellation is not a physical emergency stop and does not imply that an already dispatched provider request incurred no work.

On restart, pending journal entries become interrupted. The application does not replay inference, pending actions, approvals or old signal judgments. The evidence database remains private and must stay out of Git and release packages. It contains deliberate selected images and decision data; the preview still writes no frames by itself.

Providers use bounded HTTP timeouts, strict local result validation, response-size limits and sanitized errors. Provider keys remain backend-only. Raw provider responses, credentials and image data are not copied into operator error messages. A failed actual request never becomes a fabricated demo result.

## Verification boundary

Provider contract tests use original code-drawn synthetic JPEG fixtures and in-process HTTP transports. They test byte/hash preservation, frame ordering, schema rejection, refusal/truncation, response limits and sanitized errors. Service tests cover request and state bindings. They do not measure real MUSE image recognition, latency, paper-signal accuracy, physical arrival or robot stopping.

Historical text-goal and recorded-image provider successes do not establish success for these new live endpoints. The next installation checks require reviewed signal targets, real red/green/unknown and occlusion images, measured provider timing and the actual tablet interaction. Robot transport, physical pushing/turning and camera-to-BASE qualification remain separate work.
