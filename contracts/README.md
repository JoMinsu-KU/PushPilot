<sub>[PushPilot](../README.md) / Shared boundaries / Contracts</sub>

# Contracts before adapters

**Keep the interface stable while the UI, provider, simulator, and future robot evolve.**

[Architecture](../docs/ARCHITECTURE.md) · [Backend](../backend/README.md) · [Model interaction](../docs/META_INTELLIGENCE.md)

> **Status: planned.** This directory does not yet contain executable wire schemas. The inventory below defines intended ownership, not an implemented API.

## Contract inventory

| Family | Information it should bind | Principal consumers |
| :--- | :--- | :--- |
| Goal and intent | Operator input, grounded symbolic destination, unresolved ambiguity. | UI, supervisor, MUSE adapter |
| Mission and action | Identity, state, approved abstract plan, one requested action, completion status. | Supervisor, simulator, UI |
| Observation bundle | Capture time, independent source labels, immutable image references, visibility and local findings. | Observer, MUSE adapter, evidence |
| Intersection admission | Verified stop, signal identity and freshness, local result, accepted review, admission scope. | Supervisor, signal observer |
| MUSE request and review | Prompt/model/schema versions, exact inputs, expected and observed outcome, uncertainty, decision. | Provider, supervisor, replay |
| Evidence and replay | Immutable record identity, causal links, request/result references, transition reason. | Evidence store, UI |
| Capability status | What is configured, connected, simulated, unsupported, or unavailable. | Adapters, UI |

## Rules shared by every boundary

1. **Version the contract.** Introduce schema changes with consumers, fixtures, and validation together.
2. **Bind the result.** A result belongs to a specific request, action, observation, and session context.
3. **Preserve independent sources.** Robot state, image, car pose, signal, and model result may each have different origins.
4. **Represent uncertainty.** Unknown, unavailable, invalid, and incomplete information remain distinct from success.
5. **Separate clocks.** Capture/record timestamps support provenance; monotonic durations support local timeouts.
6. **Expose causes.** State transitions reference the evidence and gate outcome that caused them.

## Deliberately absent

The map is on hold. Do not establish active coordinates, road graphs, installed signal ROIs, stop/exit lines, or AR transforms here. Symbolic locations and abstract actions are sufficient for the first application.

The simulator must never create fake native hardware receipts. A future physical adapter needs its own measured implementation and qualification. Raw robot scripts, credentials, and executable model-generated commands do not belong in a review contract.

## Introducing a schema

Add representative valid, invalid, stale, and mismatched examples with each schema. Validate at the intake boundary before a value can alter mission state. Document compatibility and test the consequences of rejection, not only successful parsing.

From the repository root:

```sh
python tools/dev.py check
python tools/dev.py test
```

The bootstrap checker parses JSON syntax only. It is not a schema validator and does not validate any of the planned contracts above.

---

[Prompt versioning](../prompts/README.md) · [Test boundaries](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
