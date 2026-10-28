# Physical taught-course executor

`backend/robot_control/taught_executor.py` is an offline-tested coordinator and
port contract. It is not connected to the web application's simulated action
runner, and its tests do not qualify any physical road or destination.

## Route ownership

The input is one `ApprovedRoute`: the exact MUSE-selected `node_ids`, destination,
map identity, plan revision, original provider receipt and operator approval
receipt. `compile_taught_route()` validates that exact connected directed path
with `MapDefinition.route_from_nodes()`. It never selects a replacement route.

A separately reviewed `TaughtAdapter` binds the current graph revision to actual
directed BASE contact corridors. Each `MeasuredRoad` references the original
physical qualification evidence, selected rubber face and demonstrated stroke
limit. Coordinates are private installation data, independent of map pixels or
an accepted board-to-BASE fit. A new artwork/graph identity invalidates the
adapter; it does not migrate an old robot installation.

For the active city graph, symbolic paths include:

| Destination | Canonical default path | Required measured behavior |
| --- | --- | --- |
| Office Building | `PIZZA → S → OFFICE_BUILDING` | Straight frontage pushing |
| Villa | `PIZZA → S → C → VILLA` | Contact turn at S and a turn toward Villa at C |
| Hanok | `PIZZA → S → C → HANOK` | Contact turn at S and a turn toward Hanok at C |

These rows describe graph intent, not qualified TCP coordinates. Taught B/C/D
endpoint references cannot be promoted to measured vehicle centers. The adapter
must record their actual symbolic correspondence and selected contact geometry.
Proposed intersections from `taught_roads.py` remain proposals until physically
reviewed. One successful short push does not qualify a whole corridor.

Current `LocalContactInstallation` permits fixed-Z, fixed-orientation translation
only. This coordinator therefore rejects a changed direction, changed face,
changed orientation or discontinuous road anchor with `CONTACT_TURN_REQUIRED`.
It cannot disguise a turn as free commissioning, call the noncontact teaching
scope with a car present, or assume an unmeasured face-to-TCP offset. A later
measured contact-turn runtime must add explicit turn/recontact primitives and
tests before those paths can be admitted.

## IO integration

Implement `ExecutorPorts` in the private physical runner. Keep the existing robot
API, persistent receiver, independent Native checks and camera process intact.

1. `snapshot()` returns an idle, held, disarmed receiver binding, full-precision
   TCP, joints, independent stationary/eligible Native FC03 coordinates and the
   archived Native record hash. Both coordinate representations must agree
   within their existing 0.1-unit quantization allowance. It also supplies the
   actual current installation/tool/car/surface and configured stroke limit.
2. `capture()` selects and archives a new unchanged original native JPEG, exact
   hash, sequence, epoch and capture timestamp. Display crop/AR pixels are not
   inference inputs. Missing markers do not themselves invalidate a fixed view;
   an actual changed view/epoch must be rejected by the camera adapter.
3. `append_event()` and `save_checkpoint()` persist private evidence durably.
   The coordinator records an intent and unresolved checkpoint before the sole
   dispatch attempt. The port must not start a command until those writes return.
4. `execute_once(intent)` performs existing admission/IK/profile/Native checks,
   explicitly arms and posts that new UUID once, then returns the original bound
   endpoint receipt. It must never retry an ambiguous transport/motion outcome,
   perform an extra hidden push or enlarge a profile. A timed-out result remains
   unresolved until independent reconciliation.
5. `hold()` inhibits following commands. This is not an emergency-stop function
   and must not be described as one.
6. `review()` sends the original before/after JPEGs and physical-action context
   to MUSE once per completed stroke. Preserve the provider receipt and exact
   image hashes. Use a physical action prompt; the existing simulated action
   review prompt is not appropriate. Report actual car visibility, expected
   progress, excessive yaw and explicit goal arrival separately from the robot
   receipt. A provider error must never become a demo result.

`advance()` attempts one bounded straight stroke, then reviews it. The distance
is the minimum of the requested cadence, currently configured installation
limit, demonstrated primitive limit and remaining segment. The default cadence
is 10 mm; the software ceiling remains 20 mm. Literal current Z and orientation
are copied to the next target. Existing smaller scopes remain binding. The
coordinator neither edits profiles nor increases speed, acceleration or limits.

The first pose must match the measured course start. Later actual TCP positions
must match the prior accepted result; external/manual displacement is not car
progress. Every operation rechecks current binding and original image evidence.
MUSE latency is followed by a fresh Native/receiver baseline check.

## State and recovery

| State | Meaning | Next permitted operation |
| --- | --- | --- |
| `READY` | No pending physical action | One `advance()` |
| `DISPATCH_UNRESOLVED` | A dispatch may have occurred; endpoint not proved | Explicit robot reconciliation; no replay or vision-only release |
| `WAIT_ENDPOINT_CONFIRMATION` | The original verified API/wire receipt is saved, but supplemental Native endpoint evidence failed | Explicit read-only `recheck_endpoint()`; never send the motion again |
| `WAIT_REVIEW` | Robot endpoint proved; car outcome is missing/uncertain | `reobserve()` with a newer original after-frame, without moving again |
| `NEEDS_RECONCILIATION` | Car failure/excessive yaw or process restart | Independent review and a newly established course instance |
| `WAIT_HUMAN_RESET` | Goal TCP and separate MUSE car-arrival check accepted | Notify the operator and wait for manual car/reset setup |

An occluded car or provider timeout does not terminate receiver heartbeat or
repeat the completed stroke. `reobserve()` retains the original before-frame
and selects a genuinely newer after-frame. Unexpected robot movement/session
changes invalidate that review. This is distinct from an unresolved robot
command, which cannot be released by a new image.

Any existing checkpoint makes a newly created coordinator require reconciliation,
including a checkpoint that previously said READY or arrived. No process restart
automatically resumes a route. After the operator resets the car and contact
pose, archive the completed journal, independently verify the new current start
and create a fresh course journal/instance. Do not erase or overwrite historical
evidence to make a restart look new.

A known verified receipt is archived before collecting the supplemental Native
endpoint. A timeout of that additional read therefore retains
`WAIT_ENDPOINT_CONFIRMATION`, not an invented unknown wire outcome and not
success. An explicit `recheck_endpoint()` collects a new independent stationary
series, checks the same session/sequence/profile/endpoint and then reviews the
original before image with a fresh after image. It cannot release a mismatched
or missing wire receipt. This method performs no motion POST. The CLI stops on
such a read failure by default; it does not hide a Native retry.

The currently implemented coordinator rejects a production traffic-light route
through a junction with `SIGNAL_RUNTIME_REQUIRED`. A deliberately separate
`commissioning_without_signals=True` course can qualify the motion first, as
requested on site. This flag does not implement the later physical mandatory
stop, stopped-image MUSE RED wait / GREEN crossing scenario. That scenario needs
bound real stop receipts, approach-specific paper targets and measured crossing
primitives before production admission.

## Concrete runner and private bundle formats

`backend/robot_control/taught_ports.py` supplies actual stdlib IO.
`tools/run_taught_executor.py` is an explicitly invoked finite runner. Importing
either module performs no hardware or network calls. Offline validation is the
default; add `--execute` only for an approved physical run:

```sh
python tools/run_taught_executor.py \
  --route-file /private/course/approved-route.private.json \
  --adapter-file /private/course/adapter.private.json \
  --map-file backend/data/seoul-city-a3.json \
  --commissioning-without-signals

# The same verified inputs, with explicit physical execution and fresh journal:
python tools/run_taught_executor.py \
  --route-file /private/course/approved-route.private.json \
  --adapter-file /private/course/adapter.private.json \
  --map-file backend/data/seoul-city-a3.json \
  --config-file /private/course/io.private.json \
  --output-dir /private/course/run-unique \
  --commissioning-without-signals --stroke-mm 10 --execute
```

Keep all files in these examples outside the source repository. No usable
physical adapter or accepted qualification is bundled in Git. Example paths are
placeholders. The runner cannot manufacture the following source records.

The approved-route JSON has exactly these top-level fields:

- `schema`: `pushpilot.physical-approved-route.v1`.
- `route`: all `ApprovedRoute` fields, including exact canonical `node_ids`,
  plan revision, MUSE receipt ID, physical approval ID and explicit
  `commissioning_without_signals` mode.
- `provider_evidence`: `{ "path": "original-planning.private.json", "sha256": "…" }`.
  This references the unchanged exported live-planning record with `source=meta`,
  `input_kind=live_native_frame_and_graph`, its original `provider_result` and
  matching `map_context`. Its ID must match `muse_provider_receipt`, and its
  original route must match the exact selected nodes/destination without a
  clarification requirement. The original planning record may accurately retain
  `simulation_only=true` and `motion_authority=false`: symbolic plan intent is
  useful, while its simulated action approval remains insufficient for motion.
- `physical_approval`: another path/hash reference to an actual operator record
  with schema `pushpilot.operator-physical-course-approval.v1`, `source=operator`,
  `approved=true`, `simulation_approval=false`, the exact plan ID/revision,
  destination/node IDs/map identity/mode and a nonempty
  `operator_instruction_reference`. Preserve the human instruction that supplies
  this authorization; neither MUSE nor a simulation approval creates it.

The adapter bundle has `schema=pushpilot.taught-physical-adapter.v1`, `adapter`
with all `TaughtAdapter` fields and `MeasuredRoad` entries, and
`qualification_evidence` containing original path/hash references. Every road's
qualification hash and the adapter review hash must resolve to a retained
source. The actual overall review uses schema
`pushpilot.taught-course-qualification.v1`, `scope=fixed_pose_contact_corridor`,
`qualification=accepted`, `physical_execution=true` and a matching
`map_identity` object with `id`, `version`, `hash`. Those labels must summarize
actual independent evidence; writing them is not itself qualification.

The IO configuration contains only paths and fixed reviewed view/context values:

```json
{
  "runtime": "/private/receiver",
  "token_file": "/private/control.token",
  "meta_env_file": "/private/application.env",
  "camera_epoch": "CURRENT_REVIEWED_CAMERA_EPOCH",
  "registration_id": "CURRENT_REVIEWED_VIEW_ID",
  "expected_visual": "Describe the actual physical car, expected image-space progress and visible destination reference.",
  "robot_origin": "http://127.0.0.1:8897",
  "camera_origin": "http://127.0.0.1:8080",
  "command_timeout_s": 60
}
```

The robot token is sent only to the configured numeric loopback origin, with
proxies and redirects disabled. MUSE loads `META_API_KEY` from the existing
private environment file and uses the documented fixed Meta origin without
redirects. No key is printed or included in prompts/logs. The provider receives
the two original JPEGs and a physical action prompt; its exact original envelope,
schema and parsed result are archived. Failed inference never becomes a demo
PASS. An after-motion provider timeout may use a bounded new-image reobservation;
an ambiguous command POST or endpoint error never causes another motion POST.

The real Native collector verifies all inherited executable runtime bytes,
uses three different idle heartbeat quiet windows and saves each FC03 series.
Its first failed read aborts and leaves a failed record; it neither alters the
host's mandatory checks nor restarts the receiver. Frame/Native/status/payload,
wire result, joints, provider inputs/results and all decisions are private
artifacts. The append-only journal has a verified hash chain, one owner lock,
`fsync` writes and atomic durable checkpoints. Existing evidence is never cleared
to obtain a fresh run.

## Validation

`tests/test_taught_executor.py` uses synthetic BASE coordinates, JPEG byte
fixtures and fake ports only. It checks exact route/adapter identity, rejection
of unmeasured turns/signals, per-review stroke limits, durable one-shot intent,
independent Native/receipt binding, fresh original images, occlusion/provider
recovery without replay, manual-movement detection, restart reconciliation and
the separate car-arrival/human-reset gate. It makes no hardware success claim.
`tests/test_taught_ports.py` exercises the real API/profile/Native/camera/provider
adapters with fake transports only, including distinct API/wire IDs, one-shot
POST failure behavior, exact original image bytes, provider uncertainty/errors,
quiet-window read failure without retry, token confinement, journal integrity
and rejection of simulated approval as physical authorization.
