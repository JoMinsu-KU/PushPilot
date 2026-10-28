# Experimental local contact trials — offline preparation

This scope is implemented for future deliberate commissioning. It is not activated by this document or by generating a profile. Actual coordinate calibration and the existing flexible pad's loaded contact geometry must be established before straight pushing and one-sided turning. The user demonstrated that the proposed lower-corner reference is an extended line, so the point-alignment procedure was withdrawn rather than declaring a nonexistent reference. No tool change, added pointer, physical contact trial, absolute TCP registration or vehicle-turn qualification is established here. The active installation remains free-XY teaching only.

`local_contact_commissioning` is separate from free-XY teaching and board-qualified mission execution. Its actual on-site review must cover the current tool, arm, hose, fixed height/orientation, workspace, car and surface, with explicit authorization for experimental contact. Reported car length/width/height retain their reported provenance. No map, camera or calibration ID can be fabricated to enter this scope.

The offline helper reads a reviewed installation and a fresh robot-state file, validates the hash-verified inherited receiver policy, and exclusively writes a new private profile:

```sh
python tools/prepare_local_contact.py --installation <review.json> \
  --robot-state <fresh-pose-and-joints.json> --output <new-private-profile.json> \
  --receiver-root <verified-runtime> --on-site-review
```

This invocation neither grants the physical review nor applies a profile. Any later handoff uses the authenticated single-owner API: install the new contact review, explicitly HOLD while disarmed, submit a no-motion `profile_update` with the exact fresh receiver binding, and await `profile_applied_verified`. The current local teaching profile may transition to contact scope without changing the TCP definition, tool or payload; contact renewal requires a distinct current review. Current full-precision TCP/joints and the exact fixed Z/orientation must match at preparation and final publication admission. The Rodi wire protocol and installed script remain unchanged. Handoff never arms motion.

After separate arming, `commissioning` permits reviewed free approaches up to the actual profile's limit (software maximum 20 mm); `contact_trial` explicitly identifies a contact experiment and additionally caps the step at the review's `trial_max_step_mm` (maximum 5 mm). Both preserve exact current Z and literal orientation. Neither admits routes, ordinary board `push`, wrist rotation or vertical motion. The original free-XY teaching and board guards do not acquire contact-trial authority.

Each completed contact trial records the verified robot endpoint with `vehicle_completion_verified: false`, `vehicle_outcome: "unassessed"` and `board_mission_advanced: false`. It automatically disarms and holds before accepting a later motion. Original before/after camera evidence or actual operator observations belong in the separate trial diagnostics; no metric vehicle pose, MUSE verdict, successful correction or mission arrival is invented. A subsequent trial requires deliberate current-binding rearming after inspecting the physical outcome. Unknown robot outcomes remain blocked for reconciliation, and interrupted commands are never replayed.
