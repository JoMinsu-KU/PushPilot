# Meta API connection check

[Documentation](README.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Tools](../tools/README.md)

**Verified scope: authentication, enabled-model discovery, structured application goals and one recorded-image scene inspection.** Action-bound image outcome reviews and voice remain unverified.

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

## Remaining integration work

- Recorded image input and structured scene inspection are verified in the limited case above; action-bound fresh-image outcome review and held-out accuracy evaluation remain pending.
- The application now implements typed-goal interpretation, simulation decisions and event replay. Complete provider request/response provenance, usage and latency records remain additional work.
- These provider checks did not contact a live camera or robot. Temporary test-view registration used a separately recorded image; a deterministic real paper-signal detector is not implemented.
- The API check grants no motion authority.

The adapters use validated structured output, explicit source labels and HTTP timeouts. Scene inspection has immutable frame binding and rejects late results after a scene revision changes. Fresh action/observation binding, deterministic measured completion, disagreement handling and complete provider receipts remain additional work. Neither goal interpretation nor scene inspection grants motion authority.

## Official references

- [Meta model catalog](https://dev.meta.ai/docs/models)
- [Chat Completions protocol](https://dev.meta.ai/docs/protocols/chat-completions)
- [First-call recipe](https://dev.meta.ai/docs/cookbook/quickstart-chat-completions)
- [Image understanding](https://dev.meta.ai/docs/image-understanding)
- [Structured output](https://dev.meta.ai/docs/structured-output)

Availability and request support must be rechecked when updating the pinned integration contract.
