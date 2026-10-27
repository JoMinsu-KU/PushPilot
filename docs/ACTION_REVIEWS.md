<div align="center">

# Action-bound image reviews

**The same intended action can produce a different next state when the visual evidence changes.**

[Documentation](README.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Contracts](../contracts/action-review.ts) · [Verification](VERIFICATION.md)

</div>

---

PushPilot can send a **before/after operator-selected recorded-image pair** to Muse Spark for the pending simulated action. The validated response is applied by the deterministic supervisor, with its approval, map, stop and signal gates intact. This is a recorded-input simulation feature. It does not open a camera, command a robot or establish fresh post-action physical evidence.

Independent **Inspect image with MUSE** scene inspection remains separate. Its USABLE result cannot complete an action.

## Operator workflow

1. Prepare a Bakery, Bookstore or School plan and inspect its temporary route.
2. In **Image tools**, choose **Upload recorded frame** for the before image. Optional capture time is operator-provided provenance.
3. In **Compare the result.**, choose **Use current frame as BEFORE**. The panel retains this immutable frame identity. It can be pinned during preparation.
4. Approve the plan and run one bounded simulated action until `REVIEW_REQUIRED`.
5. Choose **Upload AFTER in Image tools** and upload a distinct after image. It becomes the current scene frame. Both images must belong to the same current map identity.
6. Review **Expected visual outcome**. It describes the visual question; the server separately supplies the bound action. Describe the outcome accurately rather than instructing the model to return a verdict.
7. Choose **Review action with MUSE**. This explicit action sends the pair to the real provider using the backend-only key.
8. Inspect the verdict, explanation and visible before/after pair. **Expected, observed and provenance** expands the full expectation, observation, limitations, identities, model/version, elapsed time and reported token usage.

The right mission panel offers **Review recorded images** as a shortcut. **Open demo review controls** remains available for explicitly demo-sourced software transitions; a provider failure never triggers that fallback automatically. Replay shows the accepted recorded review and its binding as read-only evidence.

The displayed **Simulation only** label applies even when the provider request is real. The application does not independently verify that the selected recordings happened before and after the simulated action. Upload order and editable capture times must not be described as hardware synchronization.

## Decision behavior

| Validated MUSE result | Supervisor consequence |
|---|---|
| PASS | Accept the pending review. The next action still needs all applicable gates; a stop may remain WAITING_SIGNAL. |
| FAIL | Enter FAULT, preserving the explanation. |
| REOBSERVE or UNKNOWN | Enter REOBSERVE. Bind a new observation without replaying movement. |
| Timeout, malformed response, provider failure | Accept no review and preserve the pending action; expose the sanitized error. |
| Mission, scene, frame or map changed while the request ran | Discard the late result with HTTP 409; refresh before another explicit request. |

A STOP image review assesses only the operator-described visible placement. Still images cannot prove speed zero, a controller stop or safe clearance. The simulated stop receipt and fresh junction-scoped simulated GREEN remain independent. RED, UNKNOWN or stale signals continue to inhibit entry after a model PASS.

## HTTP contract

`POST /api/v1/action-reviews` returns a `WorkspaceSnapshot` on success. The exact TypeScript boundary is [`contracts/action-review.ts`](../contracts/action-review.ts); Pydantic validates the request in `backend/app.py`.

| Field | Meaning |
|---|---|
| `request_id` | UUID bound to the exact payload for idempotency. |
| `expected_revision` | Current workspace revision. |
| `review_id` | Exact pending action-review ID. |
| `expected_scene_revision` | Current independent scene revision. |
| `before_frame_id` | Immutable uploaded/recorded before frame. |
| `after_frame_id` | Immutable after frame; must be the current scene frame. |
| `expected_visual` | Operator-supplied visible expectation, 1–1000 characters. |

The mission must be approved, in simulation mode and awaiting this exact pending review. Both frames must match map ID, version and geometry hash. Their stored metadata and bytes are checked against SHA-256; identical frame IDs or identical image bytes are rejected. Two different images can still depict no progress, which the model may return as FAIL.

The adapter performs provider work outside both store locks and applies a total request deadline. A durable reservation prevents concurrent duplicate dispatch. Exact completed retries return the original success or sanitized failure receipt; changed-payload reuse and an already-pending request are rejected. Restart does not redispatch an interrupted provider request or replay its verdict.

The request rechecks current mission/action/review/map/frame bindings after inference. Uploading a new image, changing scene state, cancelling the mission or otherwise changing the bound revisions while MUSE is working invalidates the response. Source and input identity checks do not establish physical capture freshness.

## Provider contract and receipts

The implementation is in [`backend/action_review.py`](../backend/action_review.py):

- Model: `muse-spark-1.3` at the fixed Meta chat-completions origin.
- Prompt version: `pushpilot.recorded-action.prompt.v1`.
- Result schema version: `pushpilot.recorded-action.result.v1`.
- Strict result: `verdict`, `observed`, `summary`, `limitations`; no extra properties.
- Recorded source: `meta`; input kind: `operator_selected_recorded_pair`.
- Scope: `simulated_action_review`, `simulation_only: true`, `motion_authority: false`.

The durable accepted record includes session, plan/revision, action and review IDs; input workspace/scene revisions; map ID/version/hash; before/after metadata and hashes; expected visual text and server-bound action; validated result; measured `elapsed_ms`; and provider-reported token counts when available. Missing usage remains null. No price or cost is inferred. The current receipt is a validated record, not a complete raw provider envelope or a signed physical receipt.

Accepted evidence appears on the current review and its event record, so later steps do not erase the earlier decision's explanation. Raw images remain in private runtime scene storage and are excluded from Git and source bundles.

Image text, operator expectations and action descriptions are untrusted task data. The prompt preserves the schema and authority rules, distinguishes printed decorations from physical objects, and returns visual evidence rather than robot coordinates or execution instructions.

## Reproduce the synthetic pipeline cases

The repository includes original code-generated schematic fixtures for the same expected approach with **success**, **no progress** and **occlusion**. Their images explicitly say synthetic evaluation, with no camera or robot. They contain no verdict labels. These are designed integration cases, not photographs or a held-out real-car accuracy benchmark.

Generate fixtures and a report without contacting a provider:

```bash
python tools/evaluate_action_reviews.py --output ../../output/action-review-fixtures-new
```

With the ignored backend `.env` configured, explicitly make the three actual Meta requests:

```bash
python tools/evaluate_action_reviews.py --output ../../output/action-review-meta-new --call-meta
```

Use a new output directory outside the source repository each time. The harness creates isolated databases and a fresh application session per case; it does not change the running workspace. It uses the actual application action-review endpoint. Only the review calls use Meta; goal interpretation is demo-sourced and all action receipts/signals remain simulated.

`report.json` preserves fixture hashes, declared source, expected/actual verdict and state, bound review evidence and limitations. Default fixture generation makes zero provider requests. The explicit `--call-meta` run makes three; actual results and timing belong in [Meta API evidence](META_API_CHECK.md) and [verification](VERIFICATION.md).

The initial actual run on October 27, 2026 produced PASS → READY for the depicted success case, FAIL → FAULT for no progress, and REOBSERVE → REOBSERVE for occlusion. This was one actual request per designed synthetic condition. It demonstrates the integrated consequence, without establishing real-car accuracy or repeated-run reliability.

## Physical evaluation remains a separate gate

The next visual evaluation needs the actual car, independently labelled real before/after recordings, no-progress and occlusion examples, and held-out input before prompt tuning. A later live path needs controller receipts, a trusted capture window, qualified local measurements and signal inhibition. Neither synthetic image success nor a real provider response on a recording establishes physical pushing, turning, arrival or stopping.

---

[← Meta intelligence](META_INTELLIGENCE.md) · [Next: mission policy →](MISSION.md)
