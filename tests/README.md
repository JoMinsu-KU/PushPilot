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
npm run build
```

The Python suite uses temporary Git/ZIP/configuration fixtures, isolated SQLite state, FastAPI's test client, and injected provider responses. It does not read the operator's real `.env`, call model APIs, contact equipment, modify the application Git identity, or install/start host services. Fixture resets apply only inside temporary test repositories.

## Implemented coverage

| File | Boundary exercised |
| :--- | :--- |
| [`test_release_bundle.py`](test_release_bundle.py) | Clean committed source, commit/hash binding, dirty-state rejection, ignored-file exclusion, output policy, private paths, symlinks, ZIP paths/collisions/hashes and size limits. |
| [`test_muse_api_check.py`](test_muse_api_check.py) | Local-key parsing with fixtures, bounded checker requests, missing-model inhibition, exact response matching and credential-echo redaction. |
| [`test_mission_core.py`](test_mission_core.py) | Current-plan approval, action/review sequencing, mandatory stop on GREEN, RED/UNKNOWN/stale wait, automatic fresh-GREEN crossing admission, uncertainty, fault, completion, idempotency, stale revisions, goal-replacement inhibition, restart recovery and retained evidence. |
| [`test_workspace_api.py`](test_workspace_api.py) | Pydantic validation, HTTP conflicts, simulation capabilities, no voice claim, routing/traversal protection, no import-time I/O, strict-schema Meta goal requests and sanitized failures. |
| [`test_temporary_map.py`](test_temporary_map.py) | Drawing validation/hash identity, east-facing shortest routes, junction action expansion, fresh per-junction GREEN/stop binding, map replacement and legacy-plan invalidation. |
| [`test_scene.py`](test_scene.py) | Four-marker candidates/explicit locks, partial visibility without refit, changed-view inhibition, image bounds/headers, immutable frame paths, scene-revision binding, late-result rejection, schema validation and private Meta request handling. |
| [`test_action_review.py`](test_action_review.py) | Bound recorded-pair PASS/FAIL/uncertainty consequences, scene/map/frame integrity, superseded response rejection, provider failure and timeout, durable duplicate prevention, idempotent receipts and restart non-replay. |
| [`test_physical_product_routes.py`](test_physical_product_routes.py) | Actual application/store/final-map contracts for Office Building (B), Villa (C) and Hanok (D), with synthetic motion and empty return only. |
| [`test_physical_mission.py`](test_physical_mission.py) | Durable physical coordinator, exact plan/destination binding, Stop during preparation/inference/motion, restart without replay and same-origin API. |
| [`test_mission_policy.py`](test_mission_policy.py), [`test_mission_robustness.py`](test_mission_robustness.py) | Bounded correction selection, uncertainty intervals, separate delivery/parking/return, RIGHT signal wait, recontact and new entry checks; injected faults and randomized cases. |
| [`test_mission_observer.py`](test_mission_observer.py), [`test_mission_vision.py`](test_mission_vision.py) | Actual-request UI state, original image/time provenance, two-image signal review, black-mask transition ambiguity, provider failure and all-route observation preflight. |
| [`test_mission_catalog.py`](test_mission_catalog.py), [`test_mission_driver.py`](test_mission_driver.py), [`test_mission_measurement.py`](test_mission_measurement.py) | Historical geometry/provenance, current-profile binding, final dispatch Stop latch, qualified measurement bounds and diagnostic-only behavior without evidence. |

GREEN/stop authority from an earlier junction cannot authorize the next junction. A later RED observation does not revoke the already admitted simulated crossing. Clock rollback cannot make a future-dated signal observation fresh. Reobservation creates a new review binding without rerunning movement. Provider failure invalidates a pending plan and never substitutes a scripted success.

`dev.py check` validates Python/JSON syntax only. The API/mission tests exercise runtime behavior. The frontend build checks TypeScript and asset generation; it does not replace visual or browser interaction review.

## Separate evidence categories

| Category | What it can establish |
| :--- | :--- |
| Offline automated test | Defined software behavior under the stated injected inputs. |
| Local launcher smoke | The Python service starts and reports simulation health with isolated state. |
| Real text provider request | Endpoint access and the specific goal interpretation/result. |
| UI visual/browser check | Layout and interaction behavior at recorded viewport sizes and states. |
| Recorded-image evaluation | Model behavior on identified, previously captured input media. |
| Synthetic-image provider evaluation | Actual provider/state behavior on explicitly labelled original schematics; no real-car accuracy or physical claim. |
| Future physical qualification | Actual pushing, turning, stopping and completion under measured conditions. |

Real provider tests are opt-in and outside the offline suite. See [Meta checks](../docs/META_API_CHECK.md). No image-review or voice inference claim follows from a successful text-goal request.

## Remaining acceptance work

- Actual provider quality on held-out recorded scenes, plus complete provider receipts.
- Trusted fresh physical action imagery, qualified local findings and local/model disagreement handling. Recorded-pair MUSE integration exists; scene-only inspection never substitutes for its binding or the local gates.
- Voice permission denial, bounded upload/normalization, cancellation, empty recognition, edited text confirmation and late/superseded results.
- Held-out vehicle/signal image evaluation with independent labels.
- Tablet-origin HTTPS and actual microphone capture.
- Independently measured final robot/camera/board registration and every physical pushing/stopping capability. Temporary four-marker fit residual is not absolute physical accuracy.

Visual acceptance must inspect readable source labels, wait/review/fault/recovery states, keyboard focus, responsive panel layouts, arrow alignment, and evidence replay driven by backend state. Replay must not dispatch movement.

The opt-in [three-case action-review harness](../docs/ACTION_REVIEWS.md#reproduce-the-synthetic-pipeline-cases) is separate from the offline suite. It uses original synthetic schematics, isolated databases and actual Meta calls only when `--call-meta` is explicit. Its designed cases do not measure held-out real-car accuracy.

Package verification establishes archive integrity and policy. It does not establish publication rights, absence of sensitive prose, or publisher authenticity. Keep private media and credentials outside fixtures.

---

[Contract validation](../contracts/README.md) · [GX10 delivery](../deploy/README.md)
