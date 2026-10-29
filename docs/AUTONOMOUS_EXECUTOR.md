<sub>[PushPilot](../README.md) / Robot / Autonomous mission executor</sub>

# Measured motion. Observed outcomes.

The physical mission path connects the tablet's current live MUSE plan to a deterministic coordinator, a measured motion library, original-frame observation, and the existing robot commissioning service. It does not use a conversational agent to choose the next coordinates. After the initial start, a released mission can wait, reobserve, select a qualified correction, verify parking, and return the empty tool without a per-step human approval.

**Implementation status: software implemented and tested offline; complete physical release remains unqualified.** Loading the existing coordinate archives does not activate a robot mission. The deployed simulation path remains distinct, and the Robot option is available only when the private physical release and current hardware state pass readiness checks.

## The control cycle

| Stage | Decision and evidence |
|---|---|
| Start | Match the exact workspace session, MUSE plan revision, destination, directed route and map hash. Confirm the current robot source and fixed-start car placement. |
| Move | Execute one released coordinate primitive. Preserve existing fixed Z/posture and speed/stroke limits; verify every endpoint with the current Native owner. No tool-tip image tracking or intermediate vision gate. |
| Withdraw | Follow the primitive's measured normal release and observation path. Do not invent a sideways escape from a contact pose. |
| Review | Send original images and the expected car outcome to MUSE. Compare car-only numeric measurements when independently qualified. |
| Correct | Select a measured primitive whose entire observed error interval lies inside its validated response envelope. Require predicted improvement and limit repeated/non-improving attempts. |
| Park | Require goal arrival and an independently bounded parallel-axis error within the declared tolerance (default 15 degrees, including uncertainty). White-body geometry alone does not resolve the nose direction. |
| Return | Leave the car in place. Use the shortest reviewed clear empty-tool path to START, including across flat printed buildings; road following is not required. Report completion only after its endpoint is verified. |

The policy never calculates a new TCP from a guessed hidden car pose. Camera presentation transforms and the rejected global board-to-BASE fit remain outside motion authority. Every active motion primitive is bound to exact measured geometry and the current installation/profile review.

The road constraint applies to the vehicle during delivery. An empty tool may cross flat printed artwork when the path is clear; the return planner need not follow the vehicle's road graph or retrace every delivery turn. Preserve the current fixed Z and literal posture, existing speed/stroke limits, fresh Native source and endpoint checks, and current profile coverage. Review the full gripper, arm and hose clearance against the remaining car, standing signal and other physical objects. Flat artwork is traversable space, but an image or a known TCP endpoint alone does not prove that swept clearance. A change in the actual post-correction pose requires a return bound to that new source.

## Paper signal and the black mask

The physical signal has permanent red and green faces. The operator covers one face with a black circular paddle on a cable tie.

| Visible result | Executor behavior |
|---|---|
| Red clear; green positively identified as covered | Stay at the selected far-RIGHT observation park. |
| Green clear; red positively identified as covered | Require two distinct fresh original frames before recontact. |
| Both colors visible | Wait; never choose the stronger color. |
| Neither face readable, partial cover, hand, hose or a changing mask | Wait and request new images. The occluder itself is not a traffic color or a controller fault. |
| Camera/view identity changed or control state unknown | Hold further commands and preserve the evidence. |

Two successive images are captured before **one** MUSE request. Each image receives its own schema result and original timestamp. This avoids two sequential inference delays while preserving the two-frame rule. The default source-age limit is 15 seconds and may be explicitly configured up to 30 seconds; provider return time never replaces capture time.

The stop sequence is: **complete the contact unit → normal release → far-RIGHT wait → stable exclusive green → measured recontact to the last contact endpoint → new stopped two-frame signal check → crossing**. The incoming recontact and the outgoing release are separate measured paths. Recontact never replays the prior seating push. If the new entry check is red/uncertain/occluded, the executor uses the reviewed release back to RIGHT; repeated unsuccessful entry attempts eventually hold rather than oscillating indefinitely.

Normal red/unknown waiting at RIGHT does not consume a motion retry budget. Each provider request is bounded; three consecutive provider/service failures hold the mission. Stop remains available. A paper mask is not a physical interlock, and photographs do not establish an obstruction-free swept volume.

## Occlusion and alignment

For a car-only review, qualified LEFT or RIGHT empty-tool observation alternatives may be selected according to the occluder and current source. Each alternative includes a reviewed restoration path if later motion starts from another context. A signal stop keeps its selected RIGHT observation requirement. An unmeasured retreat is never inferred by reversing arbitrary loaded motion.

The optional `planar_car_axis_v1` adapter uses the existing white-body detector, fixed image-to-car-plane projection and threshold sensitivity. It requires independent holdout position/axis evidence for the exact camera, map, car, working Z, ROI and transform. The current car must remain inside the validated image coverage. Missing or failed evidence produces diagnostics only. A nominal board homography or a qualitative MUSE PASS is insufficient to certify millimetres or a 15-degree parking tolerance.

Corrections use declared yaw/lateral response ranges and bounded uncertainty. The policy rejects a candidate when its response would increase either error, when the observation interval falls outside the candidate's envelope, or when repeated actual corrections do not improve the error. The response model is not trained from TCP travel: the car can slip and rotate independently of the tool.

## Failure and restart behavior

- One service owner, one physical mission, one primitive at a time.
- Persist each logical intent before dispatch; every physical stage has a fresh UUID and exact receipt binding.
- Unknown motion results, failed Native confirmation, changed source/profile/map, and process loss cannot automatically replay a command.
- Stop latches before network IO and is rechecked at the final arm/command boundary and between stages. A software hold inhibits subsequent commands; it is not a certified emergency stop or proof that an in-flight primitive instantly stopped.
- A crash/restart leaves the mission in HOLD/reconciliation. Reopening the browser never resumes a physical mission.
- Camera/MUSE failures do not restart the camera, Rodi or receiver heartbeat.
- Physical start uses a same-origin browser POST. The commissioning token and all operational coordinates remain server-side and private.

## Product interface

`GET /api/v1/physical/status` exposes mission state, real pending vision activity, signal stability, delivery/alignment and empty return separately. `POST /api/v1/physical/start` binds the exact existing plan; `POST /api/v1/physical/stop` sets the stop latch. Simulation approval and simulated stop/green receipts never authorize hardware.

The existing glass cards show **Checking signal · MUSE**, **Red · Waiting**, **Confirming green**, **Recontacting**, **Aligning at destination**, and **Returning to start**. The scan animation runs only during an actual outstanding observation request. Camera pixels, perspective and AR geometry are unchanged. Current physical progress does not overwrite simulated AR progress without an explicit mapping.

## Current evidence and release gaps

The expanded private importer reverified 636 recorded completed robot motions, 47 hash-chain journals and 690 referenced original members. It extracted 45 primary primitives, 83 phase paths, 14 directed wrist edges and eight explicitly empty paths, plus 401 individual historical stage candidates. The selected RIGHT wait has a measured nine-stage approach back to its actual last contact point.

All three vehicle deliveries are evidenced. B includes 12 original contact motions and an 11-stage empty return to START. C includes 212 original delivery motions, one separately reconciled interrupted move, and an 18-translation/two-wrist empty return. Its accepted final car position is the operator's recorded arrival, even though the old MUSE arrival flag was false. C uses its complete original trajectory; it is not constructed by joining the newer D first turn to an older C branch. The original missing-DONE result and fresh Native recovery remain separate evidence, with their small literal pose residual preserved. D's final clean START history contains 158 completed motions and its original MUSE arrival.

The initial audit omitted 16 early C motions by selecting an incomplete extracted folder, 11 NORTH3 motions because its archive window began after their completion, and the separate 11-stage B return directory. The expanded importer includes the original early ZIP and locally hash-verified copies of the omitted GX10 records. These were evidence-selection omissions, not absent physical deliveries.

Those records include failed/uncertain trials and intervening operator decisions. They do **not** supply a clean repeatable autonomous course or numeric vehicle response envelopes. In particular:

1. Independent car-axis/lateral error bounds and correction-response envelopes still need physical validation.
2. No new complete D/Hanok empty-tool return has yet been recorded in this catalogue. The older 17-stage, approximately 262 mm clearance-corridor candidate is not a mandatory route. The user's clarified policy permits a shorter clear path across flat printed artwork; a direct candidate from the historical D observation pose is approximately 187 mm. Both remain proposals, and neither may be replayed from a changed post-correction pose. Bind and review the return from the actual current Native source before execution, then preserve its new completion evidence separately.
3. The actual two-face paper signal, selected view/ROI, and entry-view readability have not been commissioned.
4. A private whole-course release must bind current profile/installation coverage, clearance and kinematic evidence to every chosen primitive. The importer does not create that release.

Historical B/C/D arrivals remain preserved. A single arrived car and precise robot TCP receipts do not demonstrate repeatable car parking. Failed fragments cannot be relabelled as successful connectors to complete a recipe.

## Files and deployment

| Component | Source |
|---|---|
| Pure decision policy | `backend/robot_control/mission_policy.py` |
| Measured catalogue and importer | `mission_catalog.py`, `tools/build_measured_mission_catalog.py` |
| Current-profile physical driver | `backend/robot_control/mission_driver.py` |
| Native-frame MUSE observer | `mission_observer.py`, `mission_vision.py` |
| Independently qualified car measurement | `backend/robot_control/mission_measurement.py` |
| Durable product coordinator/API | `backend/physical_mission.py`, `backend/physical_api.py` |
| Browser contracts and status | `contracts/physical.ts`, `frontend/src/usePhysicalMission.ts` |

An operator-maintained private JSON release is selected through the process environment variable `PUSHPILOT_PHYSICAL_CONFIG`. Without it the physical API stays disabled. The `pushpilot.physical-mission-driver.v1` schema requires site/coordinate bindings, existing real-port configuration using `host_journal`, an absolute private journal root, a hash-bound catalogue, source/target contexts, independently qualified primitives, exact route bindings, measurement configuration, observation references, and accepted current-profile coverage. Schema loaders and offline fixture builders in `tests/test_mission_driver.py` document the exact shape; **synthetic fixtures must never be installed on hardware**.

Keep the profile, secret paths, source archives, original photographs, qualification surveys and SQLite journals outside Git. Compile the frontend locally, verify Python 3.12/ARM64 imports on GX10, and update only the application release. Do not restart Rodi/camera services to activate UI changes. Complete missing commissioning evidence before enabling Robot start.
