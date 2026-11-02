<sub>[PushPilot](../README.md) / Robot / Signal wait</sub>

# Stop once. Observe clearly. Recontact by coordinates.

**Current documentation cutoff: November 2, 2026; published baseline `7aa7753`.** The selected C/Villa and D/Hanok northbound stop uses the far-RIGHT observation reference `SOUTH_JUNCTION_NORTHBOUND_SIGNAL_WAIT`. B/Office's direct frontage route does not inherit this gate merely because it shares the Pizza start.

[One-time departure policy](SINGLE_SIGNAL_DEPARTURE.md) · [Robot operations](ROBOT_OPERATIONS.md) · [C review matrix](C_INTERMEDIATE_PROGRESS_REVIEW.md#current-c-review-matrix)

The private registry keeps two references separate: the last actual vehicle-contact endpoint (with its receipt and Native evidence), and the withdrawn observation pose/joints (with its stationary Native proof and original camera evidence). The wait pose exposes the car and right-side paper signal; it is not the next contact target.

## Current site-trial sequence

1. Complete and Native-verify the stopping contact unit.
2. Release normally, then follow the reviewed coordinate withdrawal to far RIGHT. Do not invent a lateral escape from contact or use tip tracking to position the robot.
3. Observe the two-face printed signal with the black circular paddle/cable tie. RED, UNKNOWN, substantially exposed both colors, neither readable, hand/hose occlusion or a mask transition stays WAIT.
4. One accepted MUSE GREEN decision must cover two distinct fresh, correctly bound stopped frames. The configured prompt allows a narrow covered-color rim or small tremor only when the substantial central face is visibly covered and the other face clearly exposed.
5. Execute exact measured recontact to the last contact endpoint, including its final normal approach. Never replay the earlier seating stroke.
6. Continue the admitted crossing. Selected `single_departure` does not request another color judgment after recontact; later paper colors do not reopen this mission's consumed gate. Native/session/profile/stop guards still apply.

A new mission needs new admission. The separate compatibility policy `fresh_entry` performs a recheck after recontact; it is not the current selected behavior. An observation pose, readable empty region, simulated GREEN or old archived image never grants physical entry.

The operator requested a 120-second physical wait. Do not infer that timer from the 120-second wrist completion budget: the exact deployed private signal-wait configuration still needs verification. The simulation watcher defaults to 300 seconds and has separate authority. See [clock distinctions and the unresolved idle timeout](ROBOT_OPERATIONS.md#distinguish-the-clocks).

## Historical selection: October 29, sequence 478

The operator selected this actual stopped pose after a seventeen-stage rear-seating unit and original whole-unit MUSE PASS. A separate current-image inspection found the entire car visible and the nominal right junction region unobstructed, but **no standing paper signal face**. That record establishes the observation reference at its cutoff, not signal-color qualification or measured stop-line clearance.

The original [wait-stage JSON](evidence/taught-signal-wait-stage-20261029.json) still reports `physical_signal_target_configured: false` for that moment. Later software target/prompt integration does not rewrite it or establish repeatable physical crossing. Keep raw coordinates, images, profiles and full evidence private; the [evidence index](evidence/README.md) identifies the later policy documents separately.
