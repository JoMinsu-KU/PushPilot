# Meta API connection check

[Documentation](README.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Tools](../tools/README.md)

**Verified scope: authentication, enabled-model discovery, structured application goals, one recorded-image scene inspection, and action-bound review on three synthetic image pairs.** Real-car outcome accuracy, fresh live observations and voice remain unverified.

## Verified request

A real check completed on **October 27, 2026 at 12:57 KST**:

| Check | Observed result |
|---|---|
| Official base URL | `https://api.meta.ai/v1` |
| Authenticated `GET /models` | HTTP 200; 2,299 ms |
| Selected Standard model | `muse-spark-1.3` |
| `POST /chat/completions` | HTTP 200; 3,333 ms |
| Expected response | `PUSHPILOT_API_OK`, exact match |
| Finish reason | `stop` |
| Reported tokens | 18 prompt + 35 completion = 53 total |
| Automatic retries | 0 |

These are single-request observations, not latency percentiles or an accuracy benchmark. Provider cost was not returned and is not recorded as zero. A sandbox-restricted network attempt failed before the successful network-enabled check.

## Run manually

Save the key as `META_API_KEY` in the repository-local ignored `.env`. This is the application's local variable name; the checker passes its value as a bearer token to Meta. Do not pass a key on the command line.

```sh
python tools/check_muse_api.py
```

The script uses the Python standard library. It reads the fixed local file, contacts only the documented Meta HTTPS origin, disables redirects, queries the model catalog and selects an available Standard Spark version from its documented list. It makes at most one bounded text completion with minimal reasoning and a 128-token completion limit. It does not retry automatically.

Output is a credential-redacted JSON summary. The key is never part of the prompt, response report or committed configuration. Importing the module and running the ordinary test suite make no provider calls. Local network access must be available; failure to reach the host does not establish that the key is invalid.

## Application goal adapter

On **October 27, 2026 at 14:07 KST**, an explicit request through the application's `/api/v1/goals` boundary used the server-held key and `muse-spark-1.3`. The input was:

> Push the car from Pizza to the bakery. Stop at the intersection and wait for green.

The strict `json_schema` response was accepted, returning HTTP 200 and a `PLAN_READY` snapshot in simulation. The adapter interpreted destination `BAKERY` and returned the English summary: “Push the car from PIZZA to the bakery, stopping at the intersection for green.” End-to-end elapsed time was 3,880 ms for this single check, including the local test harness. This is not a latency benchmark.

The check used an isolated temporary SQLite database, did not approve or execute the plan, and sent no image, audio or robot data. No hardware was contacted. The public record omits credentials and provider identifiers. Offline tests inject provider responses, including malformed output, upstream rejection and timeout.

## Temporary-map image inspection

On **October 27, 2026 at 15:59 KST**, an explicit request from the running workspace sent a recorded native **1920×1080** print photograph and an English expectation through `/api/v1/scene/reviews`. The backend used `muse-spark-1.3`, a base64 JPEG image block and a strict `json_schema` response. The selected frame belonged to the approximate 15:01 KST camera capture group, so it was labelled recorded rather than live.

The accepted response reported:

| Field | Actual result |
|---|---|
| Verdict | `USABLE`, for scene inspection only |
| Visible places | PIZZA, BOOKSTORE, SCHOOL, BAKERY |
| Separate physical model car | `false` |
| Operator paper signal | `UNKNOWN` |
| Motion authority | `false` |

The result correctly distinguished the printed START footprint and traffic-light artwork from a physical vehicle and separate paper card. It did not establish a completed action or move a mission forward. The inspection record binds frame SHA-256, map ID/version/hash, expected scene, model and timestamp. Raw photographs remain outside Git. Provider usage and end-to-end request latency were not recorded for this check; no zero-cost or accuracy-rate claim is made.

A further actual text-goal request at **16:04 KST** interpreted “Push the car from Pizza to the Bookstore.” as destination `BOOKSTORE`. It created a `PLAN_READY` plan for `PIZZA → C → BOOKSTORE`, with 148 mm drawing centerline and five simulated actions. No plan approval or physical execution was part of that request.

## Map-scoped goal interpretation

On **October 27, 2026 at 19:39 KST**, the browser requested a plan for the self-authored [Harbor replacement fixture](../tests/fixtures/harbor-map.json). Its map metadata supplied a north-facing DOCK start and four different allowed destination IDs, labels and aliases. “Push the car from the Dock to the gallery.” was accepted as `MUSEUM`, with the summary “Push the car from the Dock to the City Museum.” The application built `DOCK → J_WEST → J_EAST → MUSEUM`, kept approval pending and rendered five drawing segments. No map coordinates, camera image, audio or robot data were sent to MUSE. This is one goal-interpretation case, not a task-accuracy evaluation.

The initial request from a network-restricted test server failed visibly without a plan. A direct provider diagnostic with network access succeeded in 5,019 ms, followed by the successful network-enabled browser request above. This single diagnostic duration is not a latency benchmark. No failed call was replaced with a demo interpretation.

At **19:42 KST**, an actual MUSE Bakery request on the current application produced `PLAN_READY`, `PIZZA → C → S → BAKERY` and five drawing segments over the live camera preview. Approval remained false. This verifies goal-to-display integration; the live image itself was not submitted for review, and no robot action occurred.

## Actual action-review requests on synthetic inputs

On **October 27, 2026 at 17:04 KST**, the application sent three original synthetic schematic pairs to `muse-spark-1.3` through `POST /api/v1/action-reviews`. Each pair used the same expectation: the white test car should progress right from PIZZA into the orange C APPROACH TARGET. Inputs explicitly say **SYNTHETIC EVALUATION** and contain no verdict labels. They were generated by [`tools/action_review_fixtures.py`](../tools/action_review_fixtures.py), without supplied artwork or photographs.

| Designed condition | Actual MUSE verdict | Supervisor state | Provider elapsed | Reported prompt / completion / total tokens |
|---|---|---|---:|---|
| Car depiction reaches target | `PASS` | `READY` | 3,795 ms | 2,391 / 268 / 2,659 |
| Depicted car position is unchanged | `FAIL` | `FAULT` | 4,713 ms | 2,399 / 272 / 2,671 |
| Foreground occluder hides the relevant area | `REOBSERVE` | `REOBSERVE` | 6,100 ms | 2,392 / 269 / 2,661 |

These were **actual provider responses**, not injected verdicts. Each accepted review changed only its isolated simulated mission. Records bind both immutable image hashes, the map ID/version/hash, plan/action/review identity, operator expectation, server action, prompt/schema versions, parsed result, reported tokens and measured provider elapsed time. Capture times remained unknown. The [public result record](evidence/synthetic-action-reviews-20261027.json) retains the exact validated results and input hashes; runtime databases and images stay outside Git.

This is **one designed case per condition**, not a held-out accuracy evaluation, repeatability study or latency benchmark. It does not test an actual car, physical motion, paper-signal detection, stop verification or contact turning. No cost is inferred from token counts. The ordinary offline suite makes no such calls.

An additional actual browser request at **17:09 KST** exercised the same synthetic success pair through the visible BEFORE selection, AFTER upload and **Review action with MUSE** control. It returned PASS, accepted one simulated PUSH review and exposed the pair and provenance in Replay. The provider interval was 2,696 ms with reported token counts 2,395 prompt + 300 completion = 2,695 total. This fourth request is a UI integration check, separate from the three-condition evaluation above. The [captured application panel](assets/recorded-action-review.jpg) contains the original synthetic diagrams and actual response.

Run the explicit evaluation with a new output directory outside the repository:

```bash
python tools/evaluate_action_reviews.py --output ../evaluation-run --call-meta
```

Omitting `--call-meta` only creates the labelled fixtures and manifest. The actual-provider mode makes three requests and never opens a camera or robot. See [Action reviews](ACTION_REVIEWS.md).

## Remaining integration work

- Recorded image input and structured scene inspection are verified in the limited case above; action-bound fresh-image outcome review and held-out accuracy evaluation remain pending.
- The application implements typed-goal interpretation, recorded-pair action review, simulation decisions and event replay. Action-review receipts now retain prompt/schema versions, both image identities, result, elapsed time and reported tokens. Equivalent complete receipts for older goal/scene paths remain additional work.
- These provider checks did not contact a live camera or robot. Temporary test-view registration used a separately recorded image; the dedicated post-stop live MUSE signal-review path is not implemented. The clarified scenario uses MUSE as the color judge, with local stop/provenance/binding validation; see [MUSE signal gate](MUSE_SIGNAL_GATE.md).
- The API check grants no motion authority.

The adapters use validated structured output, explicit source labels and HTTP timeouts. Scene inspection rejects late results after a scene revision changes. The recorded-action path releases both stores during its provider request, applies a 50-second total timeout, and rejects results after the mission, review, map or scene changes. Recorded-pair binding does not establish fresh physical action/observation binding. Deterministic measured completion, real-image evaluation and physical disagreement handling remain additional work. Neither goal interpretation nor independent scene inspection grants motion authority.

## Official references

- [Meta model catalog](https://dev.meta.ai/docs/models)
- [Chat Completions protocol](https://dev.meta.ai/docs/protocols/chat-completions)
- [First-call recipe](https://dev.meta.ai/docs/cookbook/quickstart-chat-completions)
- [Image understanding](https://dev.meta.ai/docs/image-understanding)
- [Structured output](https://dev.meta.ai/docs/structured-output)

Availability and request support must be rechecked when updating the pinned integration contract.
