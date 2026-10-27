<sub>[PushPilot](../README.md) / Operator workspace / Route display</sub>

# One route, with its current state in view

**Map-derived geometry and supervised progress share the same drawing.**

[Temporary map](TEMPORARY_MAP.md) · [Design system](DESIGN_SYSTEM.md) · [Contracts](../contracts/README.md) · [Verification](VERIFICATION.md)

The AR route is generated from the selected map and plan. It is not a fixed Bakery illustration or a replay of taught TCP poses. MUSE interprets a goal using the selected map's allowed destination identifiers; deterministic graph routing supplies the route and action sequence. The frontend presents that plan and the supervisor's state without inferring a vehicle position from the image.

## Geometry and progress have separate sources

| Input | Responsibility | Boundary |
|---|---|---|
| Map definition | Drawing nodes, directed edges, dimensions, markers and display labels | Drawing facts; no robot coordinates |
| Route visualization | Map-derived push/cross segments and illustrative junction stop lines | `drawing_only`; no qualified trajectory or stopping distance |
| Workspace snapshot | Approved plan, current action, completed actions, review and signal wait | Simulation state; not a measured car pose |
| Camera display registration | Projection of matching drawing geometry onto the selected camera source | Test display alignment; no camera-to-BASE calibration |

The optional `route.visualization` payload uses schema `pushpilot.route-display.v1`. Segment identifiers bind motion steps through `PlanStep.route_segment_id`; STOP and VERIFY retain their own action semantics. This avoids indexing an arbitrary route point array as though every action were one road edge. A crossing can contain the drawing turn through a junction, while approach and departure pushes occupy their own portions.

Illustrative stop lines are derived from the map's junction size and incoming edge, with the offset limited to that edge. They help explain where the simulated mandatory stop belongs. They are not independently taught stop lines, measured clearance or robot stopping targets. Board-space geometry is projected through the same valid display homography as the route, never moved with unrelated screen offsets.

| Visualization field | Drawing content |
|---|---|
| `schema_version`, `source` | `pushpilot.route-display.v1`, `drawing_only` |
| `segments[]` | Stable `id`, `push` or `crossing`, node/junction bindings, ordered `points_mm`, drawing `length_mm` |
| `junctions[]` | Node/label, center, incoming stop point/line, exit point, approach and crossing segment identifiers |

The incoming stop and outgoing exit offsets are each at most half the junction size or half their adjacent edge length, whichever is smaller. This prevents neighboring display divisions from reversing on a short road. The route's original node sequence and total centerline distance remain available separately; display subdivision is not a change to robot control or the supervisor's action count.

## What changes during a mission

The display distinguishes **completed**, **current** and **remaining** route portions through line treatment, direction arrows and a text legend. Color is supplementary. A current action can be waiting for review or a signal; highlighting it never implies that the car is moving.

| Supervisor context | Display meaning |
|---|---|
| Plan awaiting approval | Planned route; approval is still required |
| Current push or crossing | Emphasized planned portion associated with the current action |
| Mandatory stop | Junction stop context, before entry, even if GREEN was already selected |
| RED or UNKNOWN signal wait | Junction wait context; no continuation permission is inferred from the image |
| GREEN after accepted stopping/review | The supervisor may admit the scoped crossing; GREEN alone is insufficient |
| Pending or uncertain review | Review/re-observation context; the action is not silently marked successful |
| Completed action | Accepted simulated progress; it does not establish physical arrival |

Signal and review annotations retain their own sources. The live image may show the real workspace while route progress and signal inputs remain simulation. An independent recorded-image MUSE inspection cannot advance that progress. A validated recorded-pair MUSE result can affect the simulated supervisor through its existing gates. Live preview does not automatically capture or submit images for either path.

Older persisted plans without the visualization payload remain readable: they show the complete planned route without invented action-to-geometry progress. Prepare a new plan to obtain segment bindings. Changed map identity/version/hash inhibits mismatched route projection rather than redrawing an old plan over a new installation.

## Replace the map without rewriting the interface

The frontend reads location names from map metadata, while goal interpretation receives its supported identifiers, labels and aliases. Destination choices, route labels and the schematic therefore follow the selected map instead of a hardcoded list of shops. The current temporary drawing is still Little Town; this change does not release a new physical layout.

Use the replacement workflow in [Temporary map](TEMPORARY_MAP.md#replace-the-temporary-map). Keep the map, plan and camera display registration bound to the same identity/version/hash. Artwork-only changes still need a reviewed version and a check of the installed print and marker geometry. Moving or reprinting the board can invalidate camera alignment even when road coordinates are unchanged.

Only the current deterministic route to a selected destination is implemented. Via-point requests, user-selected alternatives, obstacle-aware rerouting, measured vehicle tracking and physical push/turn execution remain later work. A new map must satisfy the supported cardinal graph and temporary, non-executing contract; the JSON adapter is not a general road-network editor.

Software and viewport results belong in [Verification](VERIFICATION.md). No test count or attractive AR overlay establishes real-car accuracy or physical mission success.
