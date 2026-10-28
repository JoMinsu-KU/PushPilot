# Physical taught-course executor

`backend/robot_control/taught_executor.py` is an offline-tested coordinator and
port contract. It is not connected to the web application's simulated action
runner, and its tests do not qualify any physical road or destination.

## Actual commissioning evidence

One physical B / Office-frontage course is complete, with an independent robot
endpoint receipt and separate original-image MUSE arrival review. This remains
one demonstrated pass, rather than a repeatability or full-city qualification.
[B course evidence](evidence/taught-B-course-20261029.json).

Three withdrawn-tool wrist experiments completed: planned J6 changes of -5,
-85 and +90 degrees restored the original orientation. Original READY-side and
GO-side reports retain nineteen controller FK samples each, 114 in total. The
largest reported TCP radius is 0.003267 mm against the unchanged inherited
0.5 mm bound. This is a controller FK check, not physical metrology, whole-tool
clearance qualification or a car turn.
[Wrist evidence](evidence/wrist-reposition-20261029.json).

The first C attempt then completed seven straight strokes of 17.717237 mm
(124.020659 mm total TCP travel) to the proposed south-junction approach. Each
original-pair MUSE review supported rightward car progress with no yaw visible.
The first auxiliary car-pixel diagnostic remained UNCERTAIN: its 3.435 px
threshold spread exceeded the unchanged 3 px limit. That diagnostic was not
promoted to metric car-motion evidence.

A same-orientation first corner experiment completed withdrawal, a 14 mm south
shift, reapproach, a 3 mm east stroke and observation withdrawal. The turn review
returned REOBSERVE with no visible yaw. A later stationary original pair
supported an unchanged car, flat on the road; it did not turn the earlier
uncertain result into a successful turn. C/D arrival and a 90-degree car turn
remain incomplete. Later experiments are excluded from this evidence cutoff.
[First C trial evidence](evidence/taught-C-first-turn-trial-20261029.json).

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
only. A changed direction, face, orientation or discontinuous contact anchor
requires a separately measured `MeasuredTransition`; absent that record the
coordinator rejects the route with `CONTACT_TURN_REQUIRED`. The deployed separate
`LocalContactTurnInstallation` scope supports explicit experimental translation
and reviewed fixed-XYZ wrist edges. That experimental capability alone does not
qualify a car turn. The executor consumes actual measured transition evidence;
it never disguises a turn as free commissioning, calls the car-removed teaching
scope with a car present, or assumes an unmeasured face-to-TCP offset.

Each transition is keyed by its exact directed `incoming` and `outgoing` graph
edges, such as `["PIZZA", "S"]` followed by `["S", "C"]`. It has a review hash
and a continuous sequence of `MeasuredTransitionAction` entries. The first full
pose must equal the incoming road's endpoint; the last must equal the outgoing
road's contact start. A transition recorded for a different junction/approach
cannot silently be reused.

Every action supplies `id`, `kind`, measured `start_base`/`end_base`, an actual
`qualification_sha256` and its own `expected_visual`:

- `translate` is one <=20 mm measured contact/recontact/reposition action, with
  literal Z and orientation unchanged. A smaller installed limit rejects it;
  it is not silently subdivided into a different unmeasured procedure.
- `rotate` retains exact current XYZ and supplies `edge_id`, actual
  `expected_source_joint_deg`, `expected_target_joint_deg` and
  `rotation_runtime_sha256`. The latter is SHA-256 of the actual installed
  `rotation_runtime` object encoded as sorted compact JSON using
  `taught_ports.encoded()`. The full reviewed Euler endpoint and directed joint
  vectors must match the installed edge; current source joints retain the
  existing 0.5-degree comparison limit. The target joints are checked after
  completion. A measured wrist edge can cross an Euler representation branch;
  the supplied full literal endpoint is preserved and direction comes from its
  reviewed joint edge. No wrapped angle, shortcut or pure-RZ approximation is
  invented from the displayed Euler values.

The runner issues each action separately as `contact_turn_trial` under the actual
validated contact-turn installation/profile. Ordinary road strokes in that scope
also keep that purpose. Every action gets one endpoint receipt, independent
Native evidence and its own original-pair MUSE review before the next. A free
wrist/reposition action may correctly expect the car to remain stationary;
`expected_progress` then means that specific expected outcome was supported.
Final vehicle heading/alignment is a separate visible expectation of the
measured contact-turn action, not inferred from wrist rotation.

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

`advance()` attempts one bounded straight stroke or one measured transition
action, then reviews it. For road strokes the distance
is the minimum of the requested cadence, currently configured installation
limit, demonstrated primitive limit and remaining segment. The default cadence
is 10 mm; the software ceiling remains 20 mm. Literal current Z and orientation
are copied to the next target. Existing smaller scopes remain binding. The
coordinator neither edits profiles nor increases speed, acceleration or limits.

The first pose must match the measured course start. Later actual TCP positions
must match the prior accepted result; external/manual displacement is not car
progress. Every operation rechecks current binding and original image evidence.
MUSE latency is followed by a fresh Native/receiver baseline check.

## Conditional junction observation clearance

The operator requested one small automatic side withdrawal when the car is
occluded at the first intersection. `TaughtAdapter.observation_clearances` is an
optional registry of actual measured `MeasuredObservationClearance` records;
none is bundled or inferred from camera pixels. Each record contains `id`,
`junction_id`, exact directed `incoming`, measured `contact_pose`, its actual
`qualification_sha256`, `withdrawal_actions` and optional independently measured
`recontact` metadata. The withdrawal path contains one to eight explicit bounded
translations, each <=20 mm, retaining literal Z/orientation and joining the
previous endpoint exactly. The legacy single `withdrawal` field remains
compatible. Every action has a separately reviewed tool-clearance path and an
expectation that the car remains stationary. Every policy/action/recontact
qualification hash must resolve to retained original private evidence.

By default, `contact_pose` is the incoming road's actual taught endpoint. A policy
may instead bind `transition_id` and `transition_action_id` together to the exact
completed action inside that junction; the stored contact pose must match its
endpoint. The actual junction is resolved from that transition's incoming edge,
not its spanning course labels. The path must have a measured lateral component
relative to the triggering contact translation. An optional measured
`contact_direction_base_xy` supplies that direction explicitly; it is required
for a wrist-only target because Euler yaw does not establish contact direction.
Transition IDs and clearance IDs are globally unique within the adapter.

The trigger requires an already verified robot endpoint, explicit validated MUSE
`occlusion_cause=TOOL` together with `UNCERTAIN` or `car_visible=false`, the first
configured junction on this exact selected route and the matching full contact
pose. Generic uncertainty, unrelated loss of visibility and PASS without expected
progress do not authorize withdrawal. FAIL/excessive yaw, a provider failure, a
changed receiver/profile/pose, a later junction, a missing measured path or a
smaller installed limit never cause an inferred side movement. The same
clearance cannot be retriggered in the course.

`CLEARANCE_READY` retains the original action/receipt/images/review and stored
contact pose. The finite runner automatically calls `advance()` for that one
measured action at a time. After each completed path action, it saves the new
UUID, original receipt, Native endpoint and original before/after image metadata
before allowing the next `advance()`. The current low-speed profile and exact
Z/orientation remain binding; the path does not expand the workspace, change
safety settings, rotate or disguise contact as free commissioning. A read-only
`recheck_endpoint()` or `reobserve()` can finish evidence/bookkeeping and return
`CLEARANCE_READY`, but cannot dispatch the next withdrawal action itself.

A dedicated real MUSE sequence then receives three unchanged originals:
original-action before, the fresh covered contact view immediately before the
FIRST withdrawal action, and the newer clear view after the FINAL path endpoint.
All intermediate receipt/frame records are retained. The prompt explicitly
separates current car visibility, evidence supporting the original action and
whether the car remained unchanged during the ENTIRE withdrawal path; comparing
only the last short segment could miss an earlier unintended nudge. Native
endpoint proof alone does not prove car stationarity. A tool movement cannot
be counted as vehicle progress. Current visibility refers to the new clear
image; it does not require the earlier covered image to expose the car, nor
permit unseen stationarity to be invented.

Missing/stale/reused frames or model failure retain `WAIT_CLEARANCE_REVIEW` and
can obtain newer images without repeating withdrawal or losing the first path
view and completed step receipts. A failed durable endpoint-record write also
retains the known receipt for read-only bookkeeping recovery. A known robot receipt
followed by supplementary Native failure retains `WAIT_ENDPOINT_CONFIRMATION`
and its existing read-only recovery. An ambiguous withdrawal cannot be replayed
or followed by an automatic reverse command. Restart never resumes it.

A supported clear view leaves `WAIT_RECONTACT`, preserving the exact stored
contact pose. `recontact_eligible` requires a PASS, readable car, separately
supported original action, supported unchanged car pose, the model's visual
consistency flag and an independently measured recontact action. The model flag
alone grants no movement authority. This implementation deliberately issues no
return from `WAIT_RECONTACT`; the hardware owner must independently bind that
next physical operation to the current state. The route index is not advanced
while the pusher remains withdrawn. These are explicit integration limits;
fresh visible evidence does not silently qualify a missing recontact path or
claim that a destination/turn completed.

## State and recovery

| State | Meaning | Next permitted operation |
| --- | --- | --- |
| `READY` | No pending physical action | One `advance()` |
| `CLEARANCE_READY` | First junction has an eligible TOOL-occluded review and an unfinished measured side path | One next measured withdrawal action via `advance()` |
| `DISPATCH_UNRESOLVED` | A dispatch may have occurred; endpoint not proved | Explicit robot reconciliation; no replay or vision-only release |
| `WAIT_ENDPOINT_CONFIRMATION` | The original verified API/wire receipt is saved, but supplemental Native endpoint evidence failed | Explicit read-only `recheck_endpoint()`; never send the motion again |
| `WAIT_REVIEW` | Robot endpoint proved; car outcome is missing/uncertain | `reobserve()` with a newer original after-frame, without moving again |
| `WAIT_CLEARANCE_REVIEW` | A withdrawal endpoint is proved; its frame/bookkeeping or final sequence judgment is missing/uncertain | Read-only `reobserve()`; no next waypoint dispatch |
| `WAIT_RECONTACT` | Clear-view judgment stored with contact pose and explicit eligibility | Independently bound measured recontact; no automatic return |
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
source. Optional `adapter.transitions` entries use the fields described above;
their transition and individual action qualification hashes must also resolve
to retained originals. The actual overall review uses schema
`pushpilot.taught-course-qualification.v1`, with `scope=fixed_pose_contact_corridor`
for a straight adapter or `scope=measured_contact_route_with_transitions` for an
adapter containing transitions,
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
  "native_observation_source": "host_journal",
  "command_timeout_s": 60
}
```

The robot token is sent only to the configured numeric loopback origin, with
proxies and redirects disabled. MUSE loads `META_API_KEY` from the existing
private environment file and uses the documented fixed Meta origin without
redirects. No key is printed or included in prompts/logs. The provider receives
the two original JPEGs and a physical action prompt; its exact original envelope,
HTTP status and latency are archived immediately after the response, before
finish-reason/schema/content parsing. Malformed content and truncated responses
therefore retain the full original failed provider envelope. The schema and any
validated parsed result are archived separately. Failed inference never becomes a demo
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

`native_observation_source=host_journal` is an optional file-only observation
adapter for installations where an additional FC03 client interferes with the
persistent host's existing client. The compatibility default is `quiet_query`;
select the reviewed source explicitly. The host-journal adapter opens no robot
socket and does not replace the host's mandatory READY/GO/endpoint guards.

The inherited source ordering establishes the proof: `server.exchange()`
publishes idle P1, sends idle TX, receives idle_ok RX, calls the stationary
Native guard, sleeps one second, then publishes idle P2 on the next loop.
`transport.read_stationary()` returns only after two consecutive eligible
Native reads; `stationary_read_timeout` resets that pair. Individual
`native_readonly` rows are logged before validation, so two rows without the
later publication cannot themselves prove the guard completed.

`prove_host_journal_cycle()` is pure and requires
`P1 < TX < RX < N1 < N2 < P2`, matching session/sequence/profile/schema/robot and
physical-execution flags, program before/after `[2]`, exact flags
`[1,1,0,0,0,0]`, six finite zero speeds and literal pose agreement within
0.100001 units to both current actual and planned TCP. P2's `actual_joint` must
equal N2's measured joints exactly because publication copies that returned
guard row. `planned_joint` is never substituted. Timeout resets require two
new rows; missing, stale, conflicting, interrupted or newer failed cycles are
withheld. A new incomplete idle heartbeat may coexist with an already completed
fresh proof only if it contains no contradicting measurement or failure.

`host_journal_native_capture()` verifies runtime bytes without executing them,
reads only the current-session pointer/current run state and a bounded original
journal segment, waits at most four seconds for a new completed publication,
then coherently rereads pointer/state and requires no pending mailbox. The real
ports additionally recheck authenticated API held/disarmed/idle/no-active state
around collection. Native sample age uses the GX10 host monotonic clock and
retains the actual source sample time; reading the file does not refresh it.
Exact pointer/state/journal bytes are retained as base64 with hashes and the
journal byte offset, together with selected rows, timeout records and verified
source hashes. Failed observations also retain the available original bytes.

The helper is independently callable from an explicitly controlled private
runner. Its `journal` argument only needs `artifact(label, value)` returning an
archived path/hash. `publication_after_ns` can bind a previously observed P1;
when omitted the helper records the initial publication and requires a newer
completed one. This recovery observes existing actual host Native evidence and
never resends a physical command or performs an additional FC03 query.

## Validation

Actual first-junction commissioning is recorded separately in
[the October 29 evidence summary](evidence/first-junction-observation-clearance-20261029.json).
Front-side NORTH/NW pushing produced visible counterclockwise rotation toward
NORTH. After the actual 17 mm and 10 mm pushes, two 12.5 mm EAST observation
withdrawals each had separate Native endpoint records; three-original MUSE
reviews supported flat-road rotation and unchanged car pose during withdrawal.
These current-site experiments do not establish a precise physical 90 degree
turn, stable northbound pushing, C/D delivery or an already connected physical
web mission. No actual private coordinate registry is bundled with this code.

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
Mixed-route tests cover directed junction selection, full pose/joint/runtime
binding, unchanged Z, action-specific stationary-car expectations, per-action
reviews, uncertainty without repeating a wrist action, and a failed/unknown
rotation outcome. These remain synthetic tests; no physical turn registry is
bundled or declared qualified by this implementation.
Observation-clearance tests cover first-junction-only triggering, measured
lateral paths/current scope limits, explicit tool-occlusion causes, exact
transition/action and junction identities, globally unique registry IDs,
multi-step per-endpoint bookkeeping and preserved first-path/receipt provenance,
three-original provider requests, current visibility versus unknown stationarity,
fresh frames, failed model queries, unknown withdrawal outcomes, known-receipt
Native recovery without dispatching a following step, durable-write failure
recovery, full malformed/truncated provider response retention and the absence
of automatic or blind return.
