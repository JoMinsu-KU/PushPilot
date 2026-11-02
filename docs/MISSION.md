<div align="center">

# The mission

**A small car. A visible plan. A decision at the intersection.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Current status](CURRENT_STATUS.md)

</div>

---

The demonstration begins at **PIZZA**, in the fixed departure box in front of the shop. A robot **pushes a wheel-less car along the surface**; it does not pick up or carry it. The operator chooses a destination, reviews the interpreted intent and explicitly starts the applicable mission. During a configured Robot mission the executor uses taught coordinates, withdraws for MUSE review and handles its admitted signal wait without conversational-agent decisions.

As of **November 2, 2026**, the current-site physical branch is implemented and dated B/C/D arrivals are documented. It is an opt-in **site trial**, not a claim of repeatable unattended success. Default startup still provides equipment-free simulation. See [current status](CURRENT_STATUS.md), [measured routes](MEASURED_ROUTE_CATALOGUE.md) and [known limitations](KNOWN_LIMITATIONS.md).

## The three destinations

| Taught route | Destination | Current intent |
|---|---|---|
| **B** | **Office Building** | Direct road in front of Pizza and Office |
| **C** | **Villa** | Shared first turn/northbound controlled approach, then the Villa frontage |
| **D** | **Hanok** | Shared first turn/northbound controlled approach, then the Hanok frontage |

The City drawing is `seoul-city-a3`, version `2026-10-28.4`. Its route geometry is a display/intent interface. Private, hash-bound BASE recipes supply physical motion. Drawing distances, AR progress and the Spatial execution estimate are not measured car travel or a board-to-BASE calibration.

## Operator journey

| Phase | Operator sees | System establishes |
|---|---|---|
| **Observe** | Source-labelled Camera or Spatial and readiness | Current evidence, installed source and applicable branch |
| **Plan** | From/To, route and interpreted request | Supported map-scoped intent; physical recipe availability is checked separately |
| **Approve** | Explicit approval/start for the selected mode | Current session, plan/revision, map and applicable execution binding |
| **Act** | Actual physical sequence/receipt progress, or explicitly simulated steps | One admitted action with known command source |
| **Verify** | MUSE review, signal wait, delivery or hold cause | Native completion plus the applicable visible outcome and local checks |

Typed goals work today. The finite voice-upload backend is implemented; browser recording/editing and actual ASR/device acceptance remain pending. Voice candidate acceptance and plan approval are separate decisions. English UI copy is preserved; original-language user input remains data. [Voice input](VOICE_INPUT.md) describes the remaining interaction.

## Physical delivery sequence

1. Prepare the fixed common START and place the car in the departure box. A robot START observation is not evidence that the human reset the car.
2. Review the current live MUSE plan in **PLAN_READY**, then choose **Start robot mission** to approve/start Robot execution. This binds the selected B/C/D destination, plan, installed map, receiver session and private taught packet; the simulation `/approve` operation is a separate flow.
3. Execute coordinate-based contact motion under the original speed, acceleration, height, posture and stage limits.
4. Release normally, move to the reviewed observation pose and obtain the applicable MUSE review. A failed or occluded review does not replay the contact.
5. At the controlled approach, stop and withdraw far RIGHT so the car and signal can be seen. Wait for an accepted stopped GREEN.
6. Recontact through the measured path and continue under the one-time departure admission. Do not wait for a second GREEN after recontact.
7. Verify the destination outcome. The active release is **delivery_only**; C ends at **C-step-26** with destination/zone review, omitting C27/C28 and numeric alignment correction.
8. Return the empty tool to the original common START using the configured return path and receipts. The car stays at the destination; another run requires its physical reset.

Parallel parking, a numeric final heading and general slip-correction qualification are deferred. An unconfirmed C26 arrival reobserves/holds with `GOAL_ARRIVAL_UNCONFIRMED`; it does not enter numeric alignment correction. A successful tool endpoint alone cannot establish car delivery.

## One stopped GREEN, one departure

| Observation at the configured stopped approach | Behavior |
|---|---|
| GREEN before reaching the checkpoint | Stop first; no earlier color grants departure |
| Visible RED with GREEN covered | Remain stopped and observe again |
| Both colors substantially exposed, neither identifiable, missing target or mask transition | WAIT/UNKNOWN |
| RED positively covered and GREEN clearly visible in the required distinct source samples | May accept GREEN after stop/session/frame/context checks |
| GREEN accepted, measured recontact completed | Continue without a second color wait |
| Color changes after this admission | Does not revoke the admitted departure; stop/session/Native guards still apply |
| New mission or invalidated recovery context | Old GREEN cannot supply new authority |

The black circular paddle and cable tie are expected scene content. A narrow exposed color rim or small hand tremor is permitted when the intended cover is clear. Broad exposure or a substantial shift remains ambiguous. MUSE judges visual color; local checks validate applicability, source and stopping. No second local color classifier is required. This is stop-line admission, not immediate interruption of a moving robot when paper changes color. [Single signal departure](SINGLE_SIGNAL_DEPARTURE.md) defines the active policy.

Physical signal budgets, provider deadlines, simulated signal watch and controller timeouts differ. The public source does not establish the requested physical 120-second wait as a verified installation value. Idle Native reads can still terminate the persistent connection; [robot operations](ROBOT_OPERATIONS.md) records this unresolved limit.

## What a review means

The C intermediate review asks whether visible translation/rotation and a clear physical problem support continuation; it does not demand a numeric angle, front/rear identity or exact printed-road heading. C4/C6 use identical-coordinate detail crops; C14 may use the same-mission clear C13 reference across recontact plus C14; C17 is qualitative. C19's explicit configured review omission is logged as an omission and never rewritten as PASS. `clear_problem: null` stays unknown; its narrow intermediate acceptance rule requires visible progress and all other guards. Start, signal and final arrival remain independent. [C review policy](C_INTERMEDIATE_PROGRESS_REVIEW.md) preserves original false negatives, occlusions and rejected variants.

Native receipts answer whether the robot command completed. MUSE answers what the supplied scene supports. Neither substitutes for the other. A held mission retains original error evidence; explicit review continuation or C11 preparation has strict no-replay conditions. Reset retires old state and does not itself return the robot. [Robot operations](ROBOT_OPERATIONS.md) is the preparation/recovery guide.

## Simulation and historical examples

The default Little Town adapter supports PIZZA/BAKERY/BOOKSTORE/SCHOOL graph simulation. Those older routes, drawing lengths and recorded screenshots are retained in [Temporary map](TEMPORARY_MAP.md) and the dated [verification record](VERIFICATION.md); they are not the current physical destination list.

The simulator creates PUSH/STOP/CROSS/VERIFY receipts and can use labelled demo verdicts, selected recorded-pair review or deliberate live-frame services. Each configured simulated junction retains its own stop/review/signal gate. That generic simulation behavior is separate from the current physical single-admission recipe. An actual image or provider PASS cannot transform a simulated receipt into robot completion.

## Presentation

The English tablet workspace retains the industrial light/glass design, Pretendard, restrained orange accents and scene-first layout. Camera remains natural perspective; no low-quality top-view reconstruction is required. Route sequence, lower summaries, signal/MUSE activity and replay use physical-service data in Robot mode; missing data stays pending. Spatial shows the same planned intent and a labelled receipt-driven execution estimate. The glasses companion remains a concept.

---

[Meta intelligence →](META_INTELLIGENCE.md) · [Robot operations](ROBOT_OPERATIONS.md) · [Evidence](evidence/README.md)
