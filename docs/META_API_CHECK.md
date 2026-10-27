# Meta API connection check

[Documentation](README.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Tools](../tools/README.md)

**Verified scope: authentication, enabled-model discovery and one text completion.** This is an opt-in provider check, not the mission provider adapter or an application server.

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

## Remaining integration work

- Image input and structured review output have not been tested by this check.
- Goal interpretation, mission decisions, evidence/replay and frontend integration remain planned.
- No camera, paper-signal detector, map registration or robot was contacted.
- The API check grants no motion authority.

The provider adapter must add strict request/observation binding, schema validation, source labels, timeouts and decision evidence with its implementation.

## Official references

- [Meta model catalog](https://dev.meta.ai/docs/models)
- [Chat Completions protocol](https://dev.meta.ai/docs/protocols/chat-completions)
- [First-call recipe](https://dev.meta.ai/docs/cookbook/quickstart-chat-completions)

Availability and request support must be rechecked when updating the pinned integration contract.
