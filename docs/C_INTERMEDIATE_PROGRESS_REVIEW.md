# C course: intermediate visual progress review

Status: activated by explicit operator request on 2026-10-30 in GX10 release `20261030-c-progress-ui`, combined with UI commit `0af55d8`. Only the main web service restarted. The existing HOLD mission, error evidence, Native sequence/pose and exact camera homography were preserved; no robot motion, mission reset or automatic resume occurred. The archived-image evaluations below preceded deployment and did not move hardware. A new loaded course run remains unverified.

## Scope

The optional `observations.route_review_modes.C = "intermediate_progress"` setting selects the new review for the 19 loaded, non-final C steps: 1–6, 9–15, 17, 19–21, and 23–24. Six unloaded steps retain their existing receipt checks. C26 keeps the separate destination-delivery review. Fixed-start placement and stopped signal admission retain their separate contracts. B and D geometry and intermediate policies are unchanged.

The private candidate was loaded through the actual site-trial driver without opening hardware ports. All measured primitives and coordinate data remained equal to the original configuration. The setting changes observation policy, not taught motion or physical repeatability qualification.

## Intermediate judgment

The model receives one labeled side-by-side image containing the complete native BEFORE and AFTER images. C4/C6 can additionally use configured identical-coordinate native detail crops in the same request. The decoded source pixels are preserved; SHA-256 provenance is recorded. No AR, guessed car mask, image synthesis, or generated vehicle position is supplied.

The prompt asks whether the car visibly translated or rotated relative to fixed map features, whether a clear physical problem is visible, and whether visibility supports a conclusion. It does not request numeric angles, compass headings, front/rear identification, lane alignment, or final parking posture. Temporary overlap with printed buildings or sidewalks is not itself a physical collision.

| Result | Policy |
| --- | --- |
| `PROGRESS_OBSERVED` | Advance only after the existing stationary/context/freshness checks; a bound signal gate still waits independently. |
| `NO_PROGRESS` | Bounded re-observation; no invented correction or forced pass. |
| `UNCERTAIN` | Bounded visibility recovery/re-observation; no inferred hidden vehicle pose. |
| `CLEAR_PROBLEM` | Stop progression and preserve the evidence. |

Road, heading, and zone facts that this prompt does not measure remain unknown. The adapter does not fabricate them to satisfy the older policy. A successful progress review does not establish that the next contact point is aligned with the car.

The v2 candidate preserves `clear_problem: null` as unknown but does not stop solely for this field when `PROGRESS_OBSERVED`, visible change, a visible unobscured car, and all existing context/Native guards are satisfied. An explicit physical problem still stops progression; unknown motion, occlusion, stale evidence and failed signal admission do not become acceptable. This is limited to the opt-in intermediate review, not fixed-start, arrival or signal criteria. A later review is not guaranteed to detect a missed problem. No raw unknown value is rewritten as false.

For C14, two archived comparisons using the last clear signal-wait frame instead of the occluded post-recontact frame both returned visible progress. One original response had `clear_problem: null` and was rejected by v1. Both stationary control comparisons returned no progress. The wider reference interval includes signal recontact and the C14 push; it cannot attribute all observed displacement exclusively to the push. These historical responses remain unchanged. The optional `c14_clear_signal_reference` runtime selector retains the latest clear GREEN sample from C13, bound to the same mission, site, session and camera. C14 requires exactly two subsequent issued commands (the admitted recontact and current C14), an increasing frame sequence and an interval no longer than 1,200 seconds. The journal and model request identify the wider interval. Missing/changed lineage does not silently select an unrelated old photo. The cache is intentionally not restored across process restart.

## Manual paper signal

The candidate signal prompt permits a narrow rim or small crescent of the covered color and small hand tremor. The black paddle must visibly cover the central, substantial portion of one known face while the other color is clearly exposed. Both substantially exposed colors, a missing target, uncertain placement, or a substantial shift exposing the covered face remain ambiguous. A swap need not reach the other face to count as a transition.

`signal_target_matches` identifies the physical target, not whether its color agrees with an expected outcome. Old motion prose and nominal heading are omitted from signal context. The same API request also includes the two signal-region crops side by side, padded by 64 native pixels and enlarged by integer pixel replication. These are views of the original samples, not extra time points, generated imagery, or a local color classifier. Two distinct increasing-time images, the stopped-car reference, physical stop checks, and the existing one-time green admission remain required. This changes neither the wait timeout nor the number of crossings.

## Archived evaluation, 2026-10-30

MUSE Spark 1.3, minimal reasoning, 2,200 completion-token limit, no automatic retries. Historical originals were resolved by exact hashes. Recorded images are evaluation evidence only; their answers cannot authorize live movement.

The initial replay made 124 API calls covering 168 historical observations: 71 intermediate comparisons, six fixed-start checks, 44 signal pairs, and three C26 arrival checks. There were no HTTP or schema errors.

- Intermediate output distribution: 66 progress, three no-progress, two uncertain. These are model outputs, not an accuracy score.
- All four archived C17 comparisons returned progress; all three C26 arrival images passed the separate destination check.
- Both C14 uncertain results had the car hidden by the tool in BEFORE. Repeating AFTER cannot repair an occluded historical reference.
- Manual inspection of C4 and C6 no-progress examples shows visible displacement; these are false negatives, not proof of a stalled car. C19 also requires careful source comparison. The simplified prompt is not a guarantee that the full C mission will pass without interruption.
- A later C4/C6-only detail experiment used the same fixed crop in both images for all twelve archived cases. Previously missed cases 101 and 013 returned progress, but case 103 timed out and then returned no-progress on one explicitly recorded retry despite visible displacement. Eleven of twelve final judgments indicated progress; the timeout remains in the evidence. Detail framing does not eliminate inconsistent judgments. The reviewed fixed detail regions are now configured only for C4/C6. See the private `C46_DETAIL_REPLAY.md` report.
- Fixed-start output distribution: two pass, three fail, one uncertain. Historical start failures were retained, not rewritten.

The first relaxed signal candidate was rejected for activation: case 082, a moving mask with a broad exposed red area, was incorrectly called green. Cases 079 and 085 also confused target identity with the expected outcome. All raw responses are preserved. A second text-only revision fixed target-identity confusion but still misread case 082. Adding the signal detail comparison correctly returned UNKNOWN for case 082 in the focused follow-up. That six-case follow-up had two API timeouts; they remain failures, not silent retries or inferred observations. Final full re-evaluation results are recorded in the private audit report.

Final signal replay with detail images: 44 pairs / 88 sample judgments, no HTTP or schema errors; 18 GREEN, four RED, and 66 UNKNOWN. Both visible-red/covered-green pairs were recognized as RED, all nine stable green pairs remained GREEN, and mask-transition case 082 remained UNKNOWN. Most UNKNOWN samples show both printed colors exposed; some lack the signal target. These are archived scene results, not an independently measured general accuracy score. The earlier timeouts and rejected prompt variants are not erased by this later successful run.

Equipment-free checks: 1,123 Python tests completed, two skipped; source validation and frontend TypeScript/Vite build passed. These tests exercise contracts, source-image handling, policy scope, and signal gates; they do not establish real-world perception accuracy.

## Evidence and operational boundary

Private output directory: `output/robot-executor-audit-20261029/` outside the application repository. It contains source hashes, unmodified API responses, candidate configuration, offline configuration validation, and the audit report. Native photos, credentials, and robot coordinates must not be committed to Git.

The combined release passed 1,152 Python tests (five skipped), source checks and the separately checked identical UI build/assets. Post-deployment read-only configuration validation confirmed C4/C6 detail selection, C14 clear reference, v2 progress and all three destinations. The optional display collector reports the original HOLD and passed signal from actual receipts; its Spatial car remains an estimate.

This is not a physical course replay or a repeatability test. The held mission and its historical failure remain unchanged. The software applies to newly initialized missions; it does not reinterpret old FAIL records as passes or establish verified autonomous completion of C.
