<sub>[PushPilot](../README.md) / Meta intelligence / Prompts</sub>

# Prompts with a traceable consequence

**An interpretation or review matters when it changes the next permitted step.**

[Meta intelligence](../docs/META_INTELLIGENCE.md) · [Contracts](../contracts/README.md) · [Mission](../docs/MISSION.md)

Prompts are implemented beside their validators, not in a complete extracted template directory. This catalogue describes the published source as of **November 2, 2026**. All model-facing instructions are English. Images, user text and observed document content are untrusted data; they cannot replace task instructions or grant movement authority.

## Current catalogue

| Source | Version / boundary | Role |
|---|---|---|
| `backend/meta.py` | Legacy strict `pushpilot_goal_v1` | Symbolic goal/destination interpretation using selected-map labels and aliases |
| `backend/scene.py` | `pushpilot_recorded_scene_v1` | Independent recorded scene USABLE/REOBSERVE/UNKNOWN, places, car and paper-signal evidence |
| `backend/action_review.py` | `pushpilot.recorded-action.prompt.v1` / `pushpilot.recorded-action.result.v1` | Selected recorded BEFORE/AFTER for one pending simulated review |
| `backend/planning_provider.py` | `pushpilot.live-route.prompt.v3` / `pushpilot.live-route.result.v1` | Native image plus selected graph → exact directed route, constraints and clarification |
| `backend/live_review_provider.py` | `pushpilot.live-action.prompt.v1` / `pushpilot.live-action.result.v1`; `pushpilot.live-signal.prompt.v1` / `pushpilot.live-signal.result.v1` | Server-bound native simulation action/signal review |
| `backend/robot_control/mission_vision.py` | `pushpilot.physical-observation.v4` | Physical start/car/arrival and stopped two-face paper-signal observations |
| `backend/robot_control/mission_progress.py` | `pushpilot.intermediate-progress.v2` | Opted-in qualitative C intermediate review with original-image/crop lineage |

City destinations are Office Building, Villa and Hanok from Pizza. Bakery/Bookstore/School are retained Little Town compatibility vocabulary. A live route proposal returns selected-map node IDs, never pixel/TCP coordinates, scripts or approval. The backend validates exact directed connectivity, departure, first-turn, ordered-via and avoided nodes; it does not silently replace an invalid proposal with a shortest route. Route v3 prefers direct connected frontage paths when no detour is requested.

## Evidence vocabularies

| Review | Vocabulary and authority |
|---|---|
| Independent recorded scene | USABLE/REOBSERVE/UNKNOWN; never completes a step or grants GREEN |
| Simulation action | PASS/FAIL/REOBSERVE/UNKNOWN; only the bound pending review |
| Physical observation | PASS/FAIL/UNCERTAIN plus structured visible facts, combined with separate Native/context checks |
| C intermediate | PROGRESS_OBSERVED/NO_PROGRESS/UNCERTAIN/CLEAR_PROBLEM; qualitative change, no exact car angle |
| Stopped physical signal | Positive visible/covered face evidence from two ordered distinct samples; only the matching stopped departure |

Model answers and robot completion have independent sources. A PASS is not a Native receipt; a Native endpoint is not measured car travel. Providers reject malformed/truncated results and expose sanitized failures. No failed actual request silently becomes a demo parser result or scripted PASS.

## Scoped C review policy

The progress prompt compares visible car translation/rotation against fixed map features and asks about clear physical problems. It avoids exact angle, compass heading, front/rear identification and strict printed-road containment as an intermediate proxy. Temporary overlap with printed scenery does not automatically mean a physical collision.

- **C4/C6:** full originals plus identical-coordinate native detail crops. Preserve hashes and original false negatives/timeouts; framing is not a guarantee of correct recognition.
- **C14:** optional clear C13 GREEN reference, bound to the same mission/site/session/camera and exactly recontact plus C14. The wider interval cannot attribute every pixel displacement to C14 alone; missing lineage cannot use an unrelated old photo.
- **C17:** qualitative visible progress, not a demanded rotation angle or guessed vehicle nose.
- **C19:** explicit configured review omission/checked continuation; preserve the original NO_PROGRESS. An omission is not MUSE PASS and never replays completed C19.
- **C26:** separate destination/zone arrival at Villa frontage. Exact parallel posture and further progress are not required; unconfirmed arrival holds/reobserves rather than invoking numeric alignment correction.

`clear_problem: null` stays unknown. Only the opted-in intermediate policy can continue when visible progress, visible unobscured car and all Native/context/freshness conditions pass despite that field alone. Explicit problems, hidden/unknown motion and start/signal/final-arrival requirements remain independent. Later detection of a missed problem is not guaranteed. See [C review policy](../docs/C_INTERMEDIATE_PROGRESS_REVIEW.md) and [C26 endpoint](../docs/C26_DELIVERY_ENDPOINT.md).

## Manual two-face paper signal

The target contains printed RED and GREEN faces; a black circular paddle on a cable tie covers one. Covered means the central substantial portion is positively covered, permitting a narrow exposed rim/small crescent. A thin cable tie or small tremor alone is not a fault or mask transition. Broad exposed color, uncertain placement, both/none or substantial paddle movement remains UNKNOWN/WAIT; missing red alone never implies green.

The physical request includes the stopped reference, two distinct increasing-time full originals and a same-source signal detail comparison. The detail is an integer-enlarged view, not another time point, synthesized image or local classifier. `signal_target_matches` identifies the physical target, not agreement with a desired color. Local checks validate physical stop, request/session, time and Native context.

Under active `single_departure`, one accepted stopped GREEN leads to measured recontact and continuation **without another color wait**. New missions need new admission. [Single signal departure](../docs/SINGLE_SIGNAL_DEPARTURE.md) separates that physical policy from generic simulation gates.

## Receipts and history

Record exact model/prompt/schema, expected outcome, original image IDs/hashes, scoped crops/reference interval, timing, validated original response, decision and applicable command/Native binding. Unknown usage or cost remains unknown. Preserve FAIL/UNKNOWN, rejected variants and timeouts; do not rewrite historical responses after prompt changes. Historical prompts/assets keep their original provenance in [artwork records](../docs/assets/README.md) and actual provider cases in [Meta API evidence](../docs/META_API_CHECK.md).

The finite voice transcription backend is implemented separately; browser capture/editor and ASR/device acceptance remain pending. Speech text must be explicitly accepted before planning, and the plan still needs approval. Voice transcription does not create robot authority.

## Authoring conventions

1. Version changed prompts and matching validators together.
2. Separate instructions from observed/image/user content.
3. Ask for visible evidence and uncertainty, not invented confidence or metric precision.
4. Bind each judgment to its exact source and current pending decision.
5. Keep credentials, raw operational media and private coordinates out of Git and public logs.
6. Evaluate held-out inputs independently; software tests and archived replays do not prove repeatable physical success.

---

[Backend](../backend/README.md) · [Evidence index](../docs/evidence/README.md) · [Current status](../docs/CURRENT_STATUS.md)
