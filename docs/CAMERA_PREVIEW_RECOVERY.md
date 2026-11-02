# Camera preview recovery

**Bound transport stalls, preserve exact JPEG bytes, and keep stale pixels honest.**

Reviewed against `frontend/src/liveCameraTransport.ts` on November 2, 2026. This describes display transport, not current camera availability. It changes no robot command or MUSE policy.

## Current behavior

| Budget | Source behavior |
|---|---|
| Status response plus JSON body | Shared 1000 ms deadline |
| Original JPEG download plus decode | Shared 1250 ms deadline |
| Successful cycle | Target 250 ms including request/decode; no achieved-frame-rate guarantee |
| Retry | Starts at 125 ms, backs off to at most 1000 ms; success resets it |
| Pixel freshness | 1500 ms including transport/decode; unchanged by resource reuse |

Polling stays sequential. Page visibility changes cancel obsolete work and request current metadata when visible again. Expired frames are not promoted, including expiry during decode. Cleanup cancels pending requests and releases image resources.

Each selected JPEG is fetched once with `cache: no-store`, bounded to 8 MiB and its declared native dimensions. Original downloaded bytes become a short-lived **Blob URL** shared by the decode image and SVG. No canvas redraw, resampling, rectification or re-encoding occurs. The previous resource remains until React commits its replacement, then is revoked. This avoids relying on separate HTML/SVG HTTP cache lookups for the same frame.

Image identity, marker metadata, map and homography remain paired with the **decoded** frame. A repeated frame/Blob cannot make pixels fresh. Real stale pixels hide AR and expose age. Identity/epoch/resolution/map changes withdraw incompatible references; there is no automatic registration or relock.

Ordinary marker covers retain the compact `Fixed mapping` presentation without recurring missing-marker alerts. This is reference continuity, not new alignment evidence. Conflicts and confirmed changes keep their guards. See [Live camera](LIVE_CAMERA.md).

## Evidence and limits

The earlier bounded-request revision used a 125 ms successful cycle and direct cross-element URL reuse. Those historical details are superseded by **250 ms / exact JPEG Blob** transport.

An October 30 read-only check found 80/80 live server snapshots, maximum source age 202 ms, unchanged epoch/homography, and 40/40 successful LAN status-plus-JPEG transfers, maximum total 106 ms. JPEGs reached 687 KB. At the former eight-frame target this was about 44 Mbit/s before overhead; the four-frame target halves display traffic. These observations did not reproduce the operator iPad's Wi-Fi stalls or establish their exact cause.

Tests cover hung status/body responses, cancellation, late results, decode failures/stalls, dimensions, retries, cleanup, marker covers and stale/identity overlay inhibition. Actual iPad Safari sleep/wake, wireless contention and sustained loaded-motion viewing remain separate device checks. Receiver heartbeat/Native timeouts are independent; see [Robot operations](ROBOT_OPERATIONS.md).
