<sub>[PushPilot](../README.md) / Application / Backend</sub>

# The mission supervisor

**Turn grounded observations into explicit, reviewable mission decisions.**

[Architecture](../docs/ARCHITECTURE.md) · [Mission](../docs/MISSION.md) · [Contracts](../contracts/README.md)

> **Status: planned.** No backend server, model API call, camera owner, signal detector, mission runtime, or robot transport is implemented in this directory. Framework selection remains open.

## Ownership

| Boundary | Backend responsibility |
| :--- | :--- |
| Mission supervision | Validate goal and approval; own state transitions and the next permitted abstract action. |
| Action simulation | Produce explicitly simulated results using the future execution contract. |
| Observation intake | Bind source-labelled images, car observations, and paper-signal observations to the current action. |
| MUSE integration | Assemble versioned context, invoke the selected provider, validate its response, and preserve the actual result. |
| Decision evidence | Append immutable observations, requests, reviews, and transition causes. |
| Operator API and replay | Present current state and history without granting the client independent execution authority. |

The model interprets intent and reviews outcomes. Deterministic supervisor gates retain admission authority. A model response must not supply executable robot code or authoritative metric coordinates.

## A complete action boundary

```text
Accepted goal + approved abstract plan
                  │
                  ▼
          Check execution gates
                  │
                  ▼
       Run one bounded abstract action
                  │
                  ▼
      Confirm completion and collect observation
                  │
                  ▼
        Local checks + fresh-image MUSE review
                  │
                  ▼
       Record decision → advance / wait / reobserve / fault
```

At a configured intersection, require verified stopping before signal evaluation. RED, unknown, stale, or obscured observations inhibit entry. Fresh GREEN plus accepted local and MUSE checks admits the qualified crossing. The current scenario does not promise interruption when RED appears after admission during a crossing.

## Records that explain each transition

Persist stable mission, action, observation, provider-request, and review identifiers. Bind reviews to the expected outcome, exact image references and hashes, source labels, capture time, prompt/model/schema versions, actual provider response, validation result, and resulting transition cause.

Wall-clock capture times support provenance. Monotonic elapsed time supports local timeouts. A missing value is unknown, not zero or success.

| Condition | Required consequence |
| :--- | :--- |
| Provider timeout or malformed response | Preserve the failed attempt; withhold continuation. |
| Stale image or changed observation binding | Obtain a new observation and review. |
| Obscured scene or uncertain vehicle state | Wait or request reobservation. |
| Local checks and MUSE disagree | Preserve both results and inhibit the next action. |
| Restart | Reconstruct history in a non-executing review state. |
| Pending action from a prior process | Reconcile explicitly; never replay automatically. |

## Implementation boundaries

Implement the supervisor, simulator, provider adapter, evidence store, and API as separable responsibilities. Their package layout should follow working interfaces rather than speculative empty modules. Add explicit dependency manifests and lockfiles when the framework and provider client are selected.

Keep symbolic locations and abstract actions while the map is on hold. Metric registration, installed signal regions, final road routes, physical contact control, and robot transport are later integrations. No ordinary startup path may contact a robot or restart the POC camera or receiver.

## Local validation

From the repository root:

```sh
python tools/dev.py check
python tools/dev.py test
```

The current suite covers repository/release preparation, not these future behaviors. State-transition, provider-failure, and restart tests must arrive with the implementation.

---

[Frontend boundary](../frontend/README.md) · [MUSE prompts](../prompts/README.md) · [Deployment](../deploy/README.md)
