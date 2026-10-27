<p><sub><a href="README.md">PushPilot</a> / Development</sub></p>

# Contributing to PushPilot

Build an understandable operator workflow, then support every capability claim with inspectable evidence. Start with the [documentation hub](docs/README.md), [architecture](docs/ARCHITECTURE.md) and [development workflow](docs/DEVELOPMENT.md).

## Choose the right boundary

| Change | Home |
|---|---|
| Operator interaction and presentation | `frontend/` |
| Mission transitions, provider adapters and records | `backend/` |
| Shared schemas and event interfaces | `contracts/` |
| Versioned model instructions | `prompts/` |
| Behavioral and boundary verification | `tests/` |
| Developer/release tools | `tools/` |
| Target configuration and activation design | `deploy/` |
| Architecture, behavior and reviewer guidance | `docs/` |

These are ownership boundaries. Application modules are introduced as they are implemented; do not create empty service implementations or dependency manifests that imply a working runtime.

## Before making a change

- Read [AGENTS.md](AGENTS.md) and retain English code, copy, tests and documentation.
- Keep the current map hold: work with symbolic goals, abstract actions and labelled inputs. Final routes, calibration, installed signal regions and spatial AR remain deferred.
- Keep the repository self-contained. Add inherited code/assets deliberately with their provenance; never copy a private workspace or operating directory wholesale.
- Treat model interpretation, deterministic execution gates and measured physical evidence as separate responsibilities.

## Validate the result

Run from the repository root:

```bash
python tools/dev.py check
python tools/dev.py test
git diff --check
```

Add meaningful tests for new behavior and relevant failure cases. A documentation-only change needs link, example-command and visual checks; it does not need a test that repeats the text. Update the build-status table and [roadmap](docs/ROADMAP.md) when evidence changes the status of a feature.

For model changes, record prompt/schema versions, actual request/result bindings and independently labelled evaluations. Preserve the distinction between mock responses, recorded observations, live provider calls and physical runs. Never put a real credential in tests, traces, examples or public issues.

## Make review useful

Explain the user-visible problem, the resulting behavior and the checks performed. Include limitations that affect the claim. Screenshots must identify illustration/simulation when applicable; a model decision shown as live must come from the recorded actual request.

Use [CONTRIBUTIONS.md](CONTRIBUTIONS.md) to record origin and actual new work. Use [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for imported material and dependency notices. A wrapper around an inherited component is a new wrapper, not a new implementation of the entire component.

## Release boundary

Publication and GX10 activation are separate from local development. Use the [release tool](tools/README.md) and [deployment guide](deploy/README.md), keeping source clean and committed. Code rollback must not restore stale pending commands or overwrite observation history.

No repository license has been selected. Do not add a license, promise permission for inherited material or imply a supported production service without the corresponding project decision.
