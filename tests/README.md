<sub>[PushPilot](../README.md) / Engineering / Tests</sub>

# Evidence for what works

**Software checks establish the behavior they exercise. Physical claims need measured physical evidence.**

[Development](../docs/DEVELOPMENT.md) · [Release tools](../tools/README.md) · [Roadmap](../docs/ROADMAP.md)

## Run the offline suite

Install `requirements.lock` into an isolated Python 3.12+ environment, with Git on `PATH`, then run from the repository root:

```sh
python tools/dev.py check
python tools/dev.py test
cd frontend
npm ci
npm test
npm run build
```

The Python suite uses temporary Git/ZIP/configuration fixtures, isolated SQLite state, FastAPI's test client, and injected provider responses. It does not read the operator's real `.env`, call model APIs, contact equipment, modify the application Git identity, or install/start host services. Fixture resets apply only inside temporary test repositories.

## Implemented coverage

**Catalogue reviewed November 2, 2026 against public baseline `7aa7753`.** Every top-level Python test module is indexed below. These are equipment-free tests with fake transports/providers, temporary state and source fixtures. The presence of a hardware/provider adapter test does not mean that adapter was run against equipment.

| Group | Modules | Boundary exercised |
| --- | --- | --- |
| Source/release and provider checker | [test_release_bundle.py](test_release_bundle.py), [test_muse_api_check.py](test_muse_api_check.py) | Committed-source packaging/hash policy and bounded key/request handling with injected IO. |
| Read-only review publication | [test_review_site.py](test_review_site.py) | Narrow static artifact, original response/image hashes, no-connection CSP, pinned font/license and safe output handling. |
| Workspace and simulated mission | [test_mission_core.py](test_mission_core.py), [test_workspace_api.py](test_workspace_api.py), [test_action_review.py](test_action_review.py), [test_voice.py](test_voice.py) | Approval/revision/stop/review/restart behavior, recorded-input binding, API validation and text-only voice boundaries. |
| Maps and provider planning | [test_temporary_map.py](test_temporary_map.py), [test_map_api.py](test_map_api.py), [test_planning_routes.py](test_planning_routes.py), [test_planning_provider.py](test_planning_provider.py), [test_city_a3_map.py](test_city_a3_map.py), [test_spatial_only_map.py](test_spatial_only_map.py) | Map identity/replacement, exact connected routes, B/C/D frontage intent, provider contract and separate 3D display metadata. |
| Scene and display registration | [test_scene.py](test_scene.py), [test_display_registration.py](test_display_registration.py), [test_display_revision.py](test_display_revision.py), [test_live_reference.py](test_live_reference.py), [test_live_occlusion.py](test_live_occlusion.py) | Original frames, lock/reference identity, expected occlusion, changed-view inhibition and exact display revision. |
| Native preview and browser recovery | [test_live_camera.py](test_live_camera.py), [test_camera_preview.py](test_camera_preview.py), [test_live_capture_order.py](test_live_capture_order.py), [test_live_detector.py](test_live_detector.py), [test_live_backend_api.py](test_live_backend_api.py) | Native bytes/source timing, capture ordering, detector fallbacks and preview API failures using injected inputs. |
| Live MUSE and signal watcher | [test_live_intelligence.py](test_live_intelligence.py), [test_live_occlusion_intelligence.py](test_live_occlusion_intelligence.py), [test_live_review_provider.py](test_live_review_provider.py), [test_live_planning_errors.py](test_live_planning_errors.py), [test_signal_watch.py](test_signal_watch.py) | Bound real-adapter requests with fake provider replies, two-frame signal policy, stale-source/no-fallback behavior and separate simulation watcher budgets. |
| Route and actual-state display | [test_route_display.py](test_route_display.py), [test_physical_display.py](test_physical_display.py), [test_spatial_preview_metadata.py](test_spatial_preview_metadata.py) | Shared Camera/Spatial route phases and telemetry sourcing; no fake physical distances or command authority. |
| Private 3D asset tooling | [test_city_model_install.py](test_city_model_install.py), [test_clean_city_roads.py](test_clean_city_roads.py) | Reviewed asset hash/format, restricted package extraction and geometry/marking-preserving private road cleanup. |
| Robot API, runtime and startup | [test_robot_control_service.py](test_robot_control_service.py), [test_robot_control_gates.py](test_robot_control_gates.py), [test_robot_installation.py](test_robot_installation.py), [test_robot_legacy.py](test_robot_legacy.py), [test_rodi_profile_wait.py](test_rodi_profile_wait.py) | Durable command/admission/unknown-outcome behavior, exact import hashes and wait-before-listen startup. Fake equipment only. |
| Coordinate acquisition and calibration | [test_read_robot_pose.py](test_read_robot_pose.py), [test_capture_fixed_start.py](test_capture_fixed_start.py), [test_calibrate_robot_board.py](test_calibrate_robot_board.py), [test_robot_registration.py](test_robot_registration.py), [test_planar_teaching.py](test_planar_teaching.py), [test_robot_camera_intrinsics.py](test_robot_camera_intrinsics.py), [test_capture_camera_intrinsics.py](test_capture_camera_intrinsics.py) | Stationary acquisition, measured/held-out fits, reference identity and camera optics contracts. No physical fit accepted by these tests. |
| Local/contact/wrist commissioning | [test_local_commissioning.py](test_local_commissioning.py), [test_local_contact_commissioning.py](test_local_contact_commissioning.py), [test_contact_turn_commissioning.py](test_contact_turn_commissioning.py), [test_wrist_commissioning.py](test_wrist_commissioning.py), [test_robot_tcp_path.py](test_robot_tcp_path.py), [test_pushing.py](test_pushing.py), [test_corner_contact.py](test_corner_contact.py), [test_visual_probe.py](test_visual_probe.py) | Bounded local profiles, literal posture/height, directed wrist/FK guards, contact geometry and diagnostic-only probe behavior. |
| Taught runner and action units | [test_taught_roads.py](test_taught_roads.py), [test_taught_executor.py](test_taught_executor.py), [test_taught_ports.py](test_taught_ports.py), [test_coordinate_units.py](test_coordinate_units.py), [test_vehicle_observation.py](test_vehicle_observation.py) | Compatibility runner versus whole-unit lifecycle, one-shot intent, source-bound IO, original image review, visibility recovery and no replay. |
| Physical product and site trial | [test_physical_product_routes.py](test_physical_product_routes.py), [test_physical_mission.py](test_physical_mission.py), [test_site_trial_driver.py](test_site_trial_driver.py), [test_delivery_release.py](test_delivery_release.py), [test_delivery_endpoint.py](test_delivery_endpoint.py), [test_delivery_clearance.py](test_delivery_clearance.py) | Real application binding under synthetic motion, private recipe consistency, C26 delivery-only terminal review, empty return and geometric screening. |
| Policy and observation decisions | [test_mission_policy.py](test_mission_policy.py), [test_mission_policy_site_trial.py](test_mission_policy_site_trial.py), [test_mission_robustness.py](test_mission_robustness.py), [test_mission_observer.py](test_mission_observer.py), [test_mission_vision.py](test_mission_vision.py), [test_mission_measurement.py](test_mission_measurement.py) | Generic qualified policy versus site-trial delivery-only mode, single-departure/fresh-entry distinction, mask ambiguity, measurement qualification and fault injection. |
| Catalogue/profile/current-source driver | [test_mission_catalog.py](test_mission_catalog.py), [test_mission_driver.py](test_mission_driver.py), [test_mission_profile.py](test_mission_profile.py) | Archive/provenance, current-profile handoff, exact primitive joins, Native/receipt validation and final-dispatch Stop latch. |
| C review and explicit recovery | [test_mission_progress.py](test_mission_progress.py), [test_mission_resume.py](test_mission_resume.py), [test_boundary_recovery.py](test_boundary_recovery.py), [test_session_start_reference.py](test_session_start_reference.py), [test_start_reference.py](test_start_reference.py) | C4/C6 detail, C14 wider clear reference, qualitative progress/null scope, exact C19 omission, review-only continuation, C11 boundary, stationary START precision and reset/source binding. |

The frontend's `npm test` runs `frontend/tests/*.test.mjs` with Node's test runner. It covers shared route/navigation/image-source/display behavior and presentation contracts. `npm run build` checks TypeScript and asset generation; neither substitutes for a browser/tablet visual review. Run both from `frontend/` after `npm ci`.

No offline test contacts Meta, Native, Rodi or a camera. Real provider/capture/physical tools are separately classified in [Tools](../tools/README.md#catalogue-and-access-boundaries); do not add them to routine source verification. A synthetic receipt or model reply is software evidence only.

## Release checkpoints

The initial November 2 source publication at `7aa7753` reported 1,177 Python tests run with five skipped, 126 frontend tests and a successful frontend build. The later Native recovery checkpoint `bcac769` records 1,199 backend tests run with five skipped and zero failures, 143 frontend tests with zero failures, and a passing build. [Verification](../docs/VERIFICATION.md) keeps these checkpoints distinct. Older counts remain valid for their own source cutoff; record the actual new result when checking a later commit.

GREEN admission, native endpoint receipt, MUSE car review and empty START return are distinct test contracts. Under configured `single_departure`, accepted GREEN is consumed once and recontact does not reopen a color wait. Optional C19 review omission is exact-step scoped; it never creates a synthetic PASS. Unknown movement remains unresolved, regardless of a successful policy replay.

## Separate evidence categories

| Category | What it can establish |
| :--- | :--- |
| Offline automated test | Defined software behavior under the stated injected inputs. |
| Local launcher smoke | The Python service starts and reports simulation health with isolated state. |
| Real text provider request | Endpoint access and the specific goal interpretation/result. |
| UI visual/browser check | Layout and interaction behavior at recorded viewport sizes and states. |
| Recorded-image evaluation | Model behavior on identified, previously captured input media. |
| Synthetic-image provider evaluation | Actual provider/state behavior on explicitly labelled original schematics; no real-car accuracy or physical claim. |
| Historical physical commissioning | Actual recorded pushing/turning/arrival/return within the original measured source and cutoff; not unattended repeatability. |
| New physical qualification | Independently reviewed current-site response, clearance and repeated delivery/return outcomes, beyond software tests. |

Real provider tests are opt-in and outside the offline suite. See [Meta checks](../docs/META_API_CHECK.md). No image-review or voice inference claim follows from a successful text-goal request.

## Remaining acceptance work

- Held-out provider accuracy with independent labels and complete receipts; existing archived evaluations are specific-image outcomes, not a general accuracy benchmark.
- Repeatable real-site car/signal perception and disagreement handling. Bound live Meta MUSE progress/signal/arrival review is implemented; independent scene inspection and recorded-input simulation never replace its mission lineage or Native/local gates.
- Voice permission denial, bounded upload/normalization, cancellation, empty recognition, edited text confirmation and late/superseded results.
- Held-out vehicle/signal image evaluation with independent labels.
- Tablet-origin HTTPS and actual microphone capture.
- Current-site delivery/return repeatability and independently measured correction/contact-clearance evidence. Historical B/C/D arrivals exist; they do not accept the rejected global board-to-BASE fit or qualify parallel parking. Temporary marker residual is not metric accuracy.
- No-motion idle/reconnect fault-injection and soak verification for a future Native-timeout lifecycle repair; that repair is currently unimplemented.

Visual acceptance must inspect readable source labels, wait/review/fault/recovery states, keyboard focus, responsive panel layouts, arrow alignment, and evidence replay driven by backend state. Replay must not dispatch movement.

The opt-in [three-case action-review harness](../docs/ACTION_REVIEWS.md#reproduce-the-synthetic-pipeline-cases) is separate from the offline suite. It uses original synthetic schematics, isolated databases and actual Meta calls only when `--call-meta` is explicit. Its designed cases do not measure held-out real-car accuracy.

Package verification establishes archive integrity and policy. It does not establish publication rights, absence of sensitive prose, or publisher authenticity. Keep private media and credentials outside fixtures.

---

[Contract validation](../contracts/README.md) · [GX10 delivery](../deploy/README.md)
