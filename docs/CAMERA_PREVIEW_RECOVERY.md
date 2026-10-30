# Camera preview recovery

The tablet preview now bounds status requests and image preloads independently.
A lost HTTP response or suspended decode can no longer leave the polling loop
waiting indefinitely. This is a display transport change, with no robot or MUSE
control changes.

## Behavior

- Status fetch and JSON body share a 1,000 ms deadline.
- Native JPEG decode retains its 1,250 ms deadline. Failed or cancelled preloads
  clear their image source so hidden downloads do not accumulate.
- An isolated failure retries after 125 ms. Repeated failures back off to at most
  1,000 ms; a successful request resets the backoff.
- Successful polling targets a 125 ms period including fetch and decode time.
- Returning to a visible tablet tab cancels an obsolete pending operation and
  requests current metadata. Polls stay sequential; cleanup cancels active work.
- Already expired frames are not decoded or promoted. A frame that expires
  during decoding is also rejected.

Original JPEG URLs, bytes, dimensions, image/marker pairing, map identity and
the fixed homography are preserved. The existing private immutable image cache
remains in use; no blob conversion, resize, rectification or re-encoding occurs.
Freshness still counts transport and decode time against the original 1,500 ms
limit. A real outage still hides AR and labels the last image stale. Camera/view
identity changes still withdraw the previous mapping immediately. There is no
automatic registration or relock.

## Evidence and limits

Before the change, an 80-sample, 24-second GX10 read-only check found 80 live
responses, no request errors and one unchanged homography. Frame age was
109.9 ms median and 206.4 ms maximum. Marker coverage briefly dropped to three;
the fixed mapping remained available. This did not reproduce a live camera or
mapping failure, and does not establish behavior during a loaded robot run.

Fault tests cover hung status responses, stalled JSON bodies, cancellation,
late responses, decode stalls and failures, incorrect dimensions, retry
recovery and unchanged freshness. Existing mapping tests cover marker covers,
confirmed view changes, frame/map mismatch and stale-frame AR inhibition.
Physical coordinates, motion commands, MUSE policies and signal admission are
outside this change. Actual iPad Safari sleep/wake and sustained loaded motion
remain separate on-device checks.
