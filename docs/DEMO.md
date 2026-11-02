# See the judgment behind the action

**PushPilot · From sight to action**

A robot can finish a motion without finishing the task. PushPilot pairs a shared AR plan and taught-coordinate execution with **Meta MUSE's interpretation of the visible outcome**. The supervisor records whether that evidence supports continuing, stopping or taking another look.

[Project overview](../README.md) · [Current capabilities](CURRENT_STATUS.md) · [Meta MUSE's role](META_INTELLIGENCE.md) · [Evidence archive](evidence/README.md)

## Watch the physical recordings

The user supplied the following tablet recordings and setup photograph from the demonstration archive. These are actual captures, separate from the synthetic review cases below.

| Watch | What is visible | Scope |
|---|---|---|
| **[Physical action → fresh MUSE review → next step](https://drive.google.com/file/d/1TSuzN94-EOozUoWs5WLEXWVgjVezt0j9/view) · 0:55** | C Step 1 pushes the car; the tool withdraws; Checking car · MUSE changes to a new PASS at 06:42:17; C Step 2 begins. | One continuous action/review/continuation interval from an archived actual tablet recording. Not a full delivery, signal-admission or repeatability claim. |
| [Camera · Villa and empty-tool return](https://drive.google.com/file/d/1Hflx4wuoLFTQvOuHA_Aqk8_FBQhNt1bp/view) · about 2:19 | Actual robot/car, AR route, return receipts and the last recorded MUSE PASS. | The clip begins after arrival, with return already in progress. It does not show the full delivery or new inference during return. |
| [Spatial · route and sequence](https://drive.google.com/file/d/1ZxNHMMrLSJfVC78_qcFdsB_DVkqEp-f3/view) · about 2:14 | Actual rendered application view, selected route and sequence-details dialog during return. | The rendered car is an execution estimate, not measured vehicle tracking. No synchronization with the separate Camera recording is claimed. |

<a href="https://drive.google.com/file/d/1TSuzN94-EOozUoWs5WLEXWVgjVezt0j9/view"><img src="assets/physical-action-muse-review.jpg" width="960" alt="Actual tablet capture showing a new MUSE PASS at 06:42:17 and C Step 2 executing after the car push and clear-view review."></a>

*Click the image for the 55-second recording. Sampled moments: 0:00 push · 0:25 tool withdrawal · 0:35 MUSE review · 0:45 new PASS · 0:50 next step. These are observation positions, not exact transition timestamps. The original brief AR redraw interruption remains visible. [Source/extraction record](assets/PHYSICAL_MEDIA.md)*

<details>
<summary><strong>Actual setup and Spatial view</strong></summary>

<a href="https://drive.google.com/file/d/1Hflx4wuoLFTQvOuHA_Aqk8_FBQhNt1bp/view"><img src="assets/robot-tablet-recording.jpg" width="960" alt="Supporting actual Camera recording of the car at Villa and empty-tool return, with a prior MUSE PASS."></a>

*Supporting post-arrival/empty-return recording; the displayed PASS is a prior result.*

<img src="assets/robot-tabletop-setup.jpg" width="700" alt="User-supplied photograph of the actual robot, rubber pushing tool, printed tabletop and camera installation.">

*Actual setup photograph; it does not establish a completed mission.*

<a href="https://drive.google.com/file/d/1ZxNHMMrLSJfVC78_qcFdsB_DVkqEp-f3/view"><img src="assets/spatial-tablet-recording.jpg" width="960" alt="Actual Spatial tablet recording with the Villa route and return state; the rendered car is an execution estimate."></a>

*Actual application capture of the rendered Spatial view. Click to watch.*

</details>

## Explore three recorded decisions

**[Explore 3 recorded Muse decisions →](https://jominsu-ku.github.io/PushPilot/)**

The public read-only explorer puts **the actual input pair, original MUSE judgment and resulting simulated supervisor state** on one page. Open the link, then select **Progress visible**, **No progress** or **View occluded**. Expand provenance to inspect hashes and the full public record. No download, account, equipment or API key is needed, and no new inference occurs.

For offline use, download/extract or clone this repository and open [`docs/review/index.html`](review/index.html) directly in a browser. The Markdown table below remains an immediate GitHub preview. [Hosting scope and reproduction](REVIEW_HOSTING.md)

| Designed input condition | Original Meta MUSE judgment | Recorded supervisor state | What the example makes visible |
|---|---|---|---|
| The depicted car reaches the target | `PASS` | `READY` | The supplied pair supports the expected depicted progress. |
| The depicted car stays at the start | `FAIL` | `FAULT` | A completed simulated action does not make an unchanged car a success. |
| A foreground occluder hides the relevant area | `REOBSERVE` | `REOBSERVE` | Missing visual evidence remains a request for another observation. |

These are **three actual provider requests on original synthetic schematics**, recorded on October 27, 2026: one designed case per condition. They changed isolated simulated missions. They are not photographs, live inference, a recognition-accuracy benchmark or proof of physical success. The review creates **no physical motion authority**. Full results, wording, timings, token counts and immutable input hashes are preserved in the [public JSON](evidence/synthetic-action-reviews-20261027.json); the [integration record](META_API_CHECK.md#actual-action-review-requests-on-synthetic-inputs) explains the request boundary.

<a href="assets/recorded-action-review.jpg"><img src="assets/recorded-action-review.jpg" alt="Archived PushPilot application panel showing synthetic before-and-after diagrams and an actual recorded MUSE action-review response." width="960"></a>

*Actual archived application panel, with synthetic review inputs. This separate browser check is described in the integration record; it is not a physical robot image.*

## Read the physical evidence

The [measured route catalogue](MEASURED_ROUTE_CATALOGUE.md) preserves historical B/C/D trajectories. The [current site-trial guide](DELIVERY_SITE_TRIAL.md) describes the later delivery-only implementation. These are separate from the synthetic review cases above.

| Destination from Pizza | Historical arrival evidence | Empty-tool return evidence | Scope to keep in mind |
|---|---|---|---|
| **B · Office Building** | Completed contact motions and a separate original MUSE arrival judgment | Completed translations to the original literal START pose | A recorded arrival and return do not establish unattended repeatability. |
| **C · Villa** | Operator-accepted arrival; the original trajectory includes observations, operator decisions and receiver recovery | Completed translations and directed unloaded wrist edges restored START XY and the EAST face | This historical C trajectory is not a demonstration of uninterrupted autonomy. The later active delivery recipe ends at [C26](C26_DELIVERY_ENDPOINT.md). |
| **D · Hanok** | Original MUSE arrival judgment after the clean START reset | A derived return corridor includes an unexecuted reverse transition | Do not describe the derived final-D return as physically verified. |

Arrival, robot endpoint completion and return are distinct records. The current delivery-first scope does not guarantee final parallel parking or numeric vehicle alignment. Hardware trials depend on the private installation, reviewed geometry and current source state. [Known limitations](KNOWN_LIMITATIONS.md)

### When completed motion is not a successful task

The original [D extended-contact trial](evidence/taught-D-extended-contact-20261029.json) records **11 actual motion stages and all Native endpoints verified**, but the separate MUSE result is **FAIL**, `arrived: false`, with `OVERLAPS_ISLAND`. Its provider receipt and original BEFORE/AFTER hashes are public in that record; private images and taught coordinates are not republished. The operator then requested a clean START reset. This historical result is distinct from the successful action/review clip above.

For an operator, the useful distinction is visible: **the controller finished its motion; the reviewed vehicle outcome still failed the then-current requirement**. This single example explains the review layer without claiming general model accuracy or an autonomous recovery. The [published real-image failure summary](META_INTELLIGENCE.md#published-real-image-failure-analysis) also retains C4/C6 missed movement, C14 occlusion, a rejected signal-mask judgment and provider timeouts, together with the narrow responses adopted for each.

## Follow the decision, then inspect the implementation

| Question | Inspect |
|---|---|
| What does Meta MUSE contribute? | [Goal understanding, route reasoning, signal judgment and visual review](META_INTELLIGENCE.md) |
| How does the application distinguish a plan from permission to move? | [Architecture](ARCHITECTURE.md) and [mission contract](MISSION.md) |
| How does one GREEN admission connect to a crossing? | [Single signal departure](SINGLE_SIGNAL_DEPARTURE.md) |
| How are review exceptions made explicit? | [Current C review matrix](C_INTERMEDIATE_PROGRESS_REVIEW.md#current-c-review-matrix) |
| What happens after a failed or interrupted action? | [Robot operations](ROBOT_OPERATIONS.md) and [explicit review continuation](EXPLICIT_REVIEW_CONTINUATION.md) |
| Where are the dated results and unresolved checks? | [Public evidence index](evidence/README.md) and [known limitations](KNOWN_LIMITATIONS.md) |

The read-only explorer makes no API or hardware requests. Its synthetic input PNGs are byte-identical regenerations from the original [fixture generator](../tools/action_review_fixtures.py), verified against every hash in the public record. The provider results are reproduced unchanged; selecting a case only changes which archived case is displayed.
