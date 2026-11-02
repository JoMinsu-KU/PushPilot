# Explicit C11 boundary recovery

**Source status: published in baseline `7aa7753`, reviewed November 2, 2026.** This document describes the implemented contract and its dated evidence; publication does not start a mission or reconnect hardware. Use [Robot operations](ROBOT_OPERATIONS.md) for the combined reset/return/resume decision and [Known limitations](KNOWN_LIMITATIONS.md) for unresolved connection and qualification limits.

This operation is preparation for one interrupted C12 approach, not automatic
restart or replay of an unknown movement. Original error, command identities,
stage receipts, and MUSE evidence remain in the journals.

The operator requested an empty reverse of the single completed approach to
the completed C11 boundary. Before admitting continuation, the deployment
requires evidence that the next old request was never transmitted, explicit
transport reconciliation, the reverse-motion Native receipt, and fresh Native
agreement at that boundary. A hash-bound private reference resolves only up to
0.005 mm/degree of reconnect readback precision; it is not a START observation,
map calibration, or permission to change taught paths. The boundary source
may resolve its own readback XY; other road XY vertices remain literal.

`POST /api/v1/physical/prepare-boundary` preserves HOLD and performs camera
reference, MUSE car continuity, and current/target IK checks. It does not run a
route action. Preparation advertises `BOUNDARY_READY` only after those checks.
`POST /api/v1/physical/resume` is a separate explicit operation that checks the
same receiver session, sequence, profile and endpoint before starting C12 with
a new command ID. C1–C11 do not replay; the failed C12 command ID stays used.
The signal gate and later reviews retain the original policy.

A service restart never starts a worker. On a separate explicit resume, the
saved preparation can be reconstructed only from matching coordinator and
driver journals, the unchanged receiver session/sequence/profile/endpoint and
camera reference, and a new car-continuity review. A reconnect or any changed
source prevents launch. Neither this operation nor a successful
software test fixes intermittent controller Native-read timeouts or establishes
unattended repeatability.
