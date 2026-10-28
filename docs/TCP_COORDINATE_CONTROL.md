<sub>[PushPilot](../README.md) / Engineering / TCP coordinate control</sub>

# Teach a fixed frame once. Compute the road between endpoints.

The October 28 operator correction supersedes gripper-image tracking as the execution basis. The map is a flat surface; its oblique camera appearance does not make a road curved. The executor uses controller TCP coordinates and a fixed map-to-BASE relation. It must not locate the rubber tip in each image to decide where the robot is.

| Responsibility | Source |
|---|---|
| Robot position and completed motion | Persistent receiver receipt plus independent Native TCP readback |
| Road target and intermediate TCP points | Fixed map frame and taught endpoint coordinates |
| Vehicle position, drift, turn progress and arrival | Separate fresh vehicle observations / MUSE review |
| Stopped signal colour | Fresh MUSE judgement with the configured approach and stop gates |

## A small set of references replaces dense teaching

Establish one known map origin and two non-collinear map directions in TCP/BASE coordinates. For an axis-aligned teaching layout, the origin and one known-distance point on each map axis supply the two basis vectors. Other road endpoints and midpoints are calculated from those references; do not teach every possible route or every short step separately. Reserve a few independent checks for errors and retain failed checks.

The planar relation is `TCP_XY = origin_BASE + u * basis_u + v * basis_v`. A road leg from taught TCP endpoint A to B uses `P(t) = A + t * (B - A)`. If a road runs along a map axis, its other map coordinate is constant. Both BASE X and Y may nevertheless change when the map axes are rotated relative to BASE; this is independent of the camera's perspective.

The current TCP definition can serve as the virtual reference for noncontact road teaching. A separate visually detected gripper centre is unnecessary for that motion. A nominal midpoint from the gripper drawing can initialize a tool reference but is not a measurement of the installed compliant contact surface. Keep an assumed origin/offset labelled nominal until the actual map correspondence is checked. Known BASE displacements alone do not establish the map's absolute origin.

## Short straight segments use coordinates

`backend/robot_control/tcp_path.py` supplies a pure fixed-pose segment splitter. It takes endpoint TCP poses and a maximum step length, preserves literal Z and orientation, and calculates every target directly from A and B. It has no image, segmentation, MUSE, service or motion-dispatch dependency. It neither qualifies endpoints nor enlarges an installation/profile.

The existing receiver remains responsible for bounded low-speed Linear moves. Verify each issued operation by its exact request/session/profile binding, endpoint receipt and Native coordinates. Do not infer robot completion from the camera or silently replay an interrupted command. Shorter segments make vehicle outcome checks and correction opportunities more frequent; they do not mechanically guarantee that a freely sliding car remains straight.

## Vision verifies the task outcome

Expected gripper occlusion must not break the persistent robot session, trigger map refitting or replace TCP coordinates with pixel estimates. Finish an already admitted bounded operation according to controller semantics. If vehicle outcome or signal evidence is unavailable afterward, withhold the next dependent action and obtain a bounded new observation. Unknown evidence is not success, and a software HOLD is not an immediate physical stop.

Vehicle yaw/cross-track error can inform the next qualified contact correction, remaining turn or route decision. The selected pushing face, approach/repositioning envelope, actual slip/rotation response and stopping geometry still need separate contact tests. No contact or rotation is authorized by this noncontact teaching result.

## Current physical evidence

After stopping the tablet-checkerboard approach, three new noncontact movements completed: BASE X +10 mm, then Y +10 mm and Y +10 mm. Each stayed on previously traversed segments with unchanged literal Z/orientation, profile and low-speed limits. Native readback and `motion_endpoint_verified` receipts confirmed the endpoints; the receiver advanced from sequence 26 to 29 and finished held/disarmed/idle. Original frames, full poses and receipts remain private.

This establishes those TCP movements and a new intermediate coordinate sample. It does not establish an accepted whole-map transform, a physically verified road destination, vehicle transport or a 90-degree contact turn. Dense additional sampling and gripper-image tracking were stopped at the operator's correction. The original physical accuracy targets remain unchanged.
