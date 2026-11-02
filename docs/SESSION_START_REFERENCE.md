# Stationary START reference

**Source status: published in baseline `7aa7753`, reviewed November 2, 2026.** This document describes the implemented contract and its dated evidence; publication does not start a mission or reconnect hardware. Use [Robot operations](ROBOT_OPERATIONS.md) for the combined reset/return/resume decision and [Known limitations](KNOWN_LIMITATIONS.md) for unresolved connection and qualification limits.

The original B/C/D teaching packet remains immutable. A receiver reconnect
reports floating-point values that can differ slightly from the accepted taught
START. This used to advertise readiness and then fail the exact primitive-source
check. Rewriting the teaching packet to handle each reconnect is inappropriate.

An optional hash-bound `session_start_reference` records one independently
observed, held, idle START for one receiver session. It binds the original packet
and review hashes, the original common START, the full-precision receiver pose,
and the separate Native evidence. The maximum component difference is 0.005 mm
or degree. This is a fixed admission bound, not a solver or a revised tolerance
for motion verification. Larger displacement requires reconciliation.

The driver derives its in-memory execution representation from that record:
common START resolves to the measured point. Other road/contact endpoints retain
their BASE XY. For an initially split straight push, only its internal subdivision
point is recomputed at the original ratio (within the same 0.005 mm bound), keeping
both stages collinear and the terminal endpoint unchanged. The current fixed height and the existing directed wrist orientation
family are retained throughout execution. The original route, teaching files,
speed/acceleration/stroke limits, workspace bounds, Native checks, receiver
protocol and nineteen-sample wrist checks remain unchanged. Derived command
geometry has its own hashes. This does not qualify repeatability or claim that
the vehicle has been reset.

The record is explicit and session-scoped. A different session is blocked;
there is no automatic rebasing or replay. Activation requires independent fresh
stationary evidence and a normal no-motion profile handoff. During a session,
the usual per-unit exact-source and profile checks still apply. A missing
receiver now reports `ROBOT_CONNECTION_REQUIRED` rather than misleadingly
reporting a changed profile. Actual changed profiles still block execution.

This change does not repair Native FC03 timeouts. A connection closed after the
existing timeout budget still requires an operator PLAY and fresh reconciliation.
