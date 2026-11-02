<sub>[PushPilot](../README.md) / Operator workspace / Route display</sub>

# One route, with its source and current state in view

**Map-derived geometry, real execution receipts and vehicle estimates remain distinct.**

[City map](CITY_A3.md) · [Map replacement](MAP_REPLACEMENT.md) · [Spatial](SPATIAL_3D.md) · [Execution display](DESIGNER_LIVE_DISPLAY.md) · [Contracts](../contracts/README.md)

Reviewed November 2, 2026. MUSE selects a structured path in the active graph; the backend validates and compiles the exact connected node sequence. The AR line is not a fixed illustration, an inferred live-car track or a replay of taught TCP positions. Camera and Spatial show that same selected 2D path.

MUSE is central to scene-grounded planning and visual review: explicit live planning combines the unchanged original frame with the selected graph, while action/signal judgments bind their own captured evidence. Deterministic checks preserve route connectivity and execution context; the model's judgment, Native tool receipts and Spatial vehicle estimate must remain inspectable as separate sources.

## Selected graph route

The reviewed site map is `seoul-city-a3` v`2026-10-28.4`, explicitly selected at startup. Source-default Little Town is retained for compatibility and equipment-free examples.

| City destination | Default node order | Nominal drawing distance |
|---|---|---:|
| Office Building | `PIZZA → S → OFFICE_BUILDING` | 204.732041 mm |
| Villa | `PIZZA → S → C → VILLA` | 313.600114 mm |
| Hanok | `PIZZA → S → C → HANOK` | 313.630045 mm |

Default City departure is east from Pizza's front box. `route_from_nodes()` also validates explicit alternatives: 2–64 known nodes, declared start/destination, allowed directed edges, no repeated nodes and no skipped intermediate road nodes. Structured `departure`, `first_turn`, ordered `via_nodes` and `avoid_nodes` must match the selected path. The first turn is the maneuver at the first encountered junction, including straight. An explicit path is not silently replaced by a shortest path; the configured-heading restriction belongs to the default demo router. Unsupported or contradictory constraints fail validation.

This supports exact alternative-path **planning/display**, not arbitrary obstacle avoidance or execution of every path by the private robot recipes. The operator reviews interpretation and the visible route before the relevant approval/Start action. A valid drawing path alone cannot qualify a physical maneuver.

## Geometry and progress sources

| Input | Responsibility | Boundary |
|---|---|---|
| Map definition | Nodes, directed edges, drawing distances, labels, markers/panels | No robot BASE targets |
| Route visualization | Stable push/cross segments, points and stop-line illustrations | `drawing_only`, not a swept car/tool path |
| Simulation workspace | Approval, symbolic current/completed actions, review/signal context | Not physical vehicle travel |
| Physical status | Actual sequence, current step, Native receipt totals, MUSE/signal state, faults | A completed tool command does not independently measure the car |
| Optional physical display | Journal-verified contact progress projected onto drawing legs | Execution estimate, not actual position/yaw |
| Camera registration / city manifest | Drawing-to-image / drawing-to-model display projection | Neither is camera-to-BASE calibration |

The optional `route.visualization` schema is `pushpilot.route-display.v1`. `PlanStep.route_segment_id` binds motion actions to stable display segments; STOP and VERIFY retain separate semantics. This avoids treating each action-list index as a road edge. Display subdivision does not change total centerline distance or physical recipe command count.

| Field | Content |
|---|---|
| `schema_version`, `source` | `pushpilot.route-display.v1`, `drawing_only` |
| `segments[]` | Stable ID, push/crossing, node/junction bindings, ordered `points_mm`, drawing length |
| `junctions[]` | Center, label, incoming stop point/line, exit and bound approach/crossing segments |

Stop/exit offsets are limited to half the junction size or adjacent edge length, whichever is smaller. Lines are projected with the same geometry as their route. They are not measured stopping targets and must not be shifted with unrelated CSS offsets to look convenient.

## Mission presentation

Simulation uses segment bindings for completed/current/remaining line treatment and mandatory stop/review/signal context. Physical mode instead shows its actual executor sequence and Native receipt totals; it does not relabel simulated completion as measured car travel. A highlighted action can be waiting or held; emphasis never means the car is moving.

Robot mode consumes its own existing signal lifecycle. At the taught wait/observation pose the tool clears the applicable view, the physical policy judges fresh signal evidence and waits on RED/UNKNOWN. Once the configured departure gate passes, recontact and subsequent stages do not start another watcher for that gate. `Signal passed` remains meaningful even after green sample counters clear. Simulation may retain per-junction gates; these policies must not be mixed. See [Robot operations](ROBOT_OPERATIONS.md) and [Single signal departure](SINGLE_SIGNAL_DEPARTURE.md).

Spatial's optional vehicle illustration moves only on newly confirmed contact receipts. Approach/withdrawal, unloaded wrist, signal/MUSE waits, HOLD, stale feeds and empty home return freeze it. Delivered cars remain illustrated at the destination while the empty robot returns. The label **Execution estimate / Display only** is mandatory; interpolation cannot establish arrival, slip or parking alignment.

Independent scene inspection cannot advance a mission. Recorded pairs can affect only their bound simulated review; explicit physical reviews use their own native-image evidence and policy. Preview polling itself neither calls MUSE nor completes actions.

## Replacement and fidelity

Names, choices and route geometry follow map metadata. A changed map identity/version/hash withholds incompatible plans/registration. Older plans without visualization remain readable as planned-only; no progress binding is guessed. Use [Map replacement](MAP_REPLACEMENT.md), preserving old definitions and evidence.

Camera keeps the unchanged JPEG's intrinsic coordinate system, perspective and aspect ratio. Image, mask and AR share local pan/zoom. Partial/complete expected marker covers retain the same fixed reference quietly; conflicting, changed or stale views keep their guards. Spatial uses its exact rendered camera and verified display manifest, without editing physical map hashes. Neither presentation creates robot coordinates.

Do not hot-swap an executing map or import prior installation poses. Each new physical installation separately requires reviewed START/contact geometry and executable recipes. The existing B/C/D site trials and C26 endpoint do not make every drawing alternative executable. Software/display results and dated hardware evidence belong in [Verification](VERIFICATION.md) and [Current status](CURRENT_STATUS.md).
