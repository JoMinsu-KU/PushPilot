# Selected physical demonstration media

**Real captures selected from the user's archive on November 2, 2026 (Asia/Seoul).**

[Demo guide](../DEMO.md) · [Artwork inventory](README.md) · [Hashes and source IDs](physical-media.json)

The user explicitly approved publishing the initial three selected captures and associated Drive video links, then separately approved the 55-second physical-action clip and its new representative capture, on November 2, 2026. They are separate from the original private operational archives, original evidence JSON and generated product illustrations. No model-evaluation PDF or other unrelated folder content is included.

## Representative physical action and fresh review

**[Watch the continuous 55-second clip](https://drive.google.com/file/d/1TSuzN94-EOozUoWs5WLEXWVgjVezt0j9/view)**

The actual Camera tablet archive contains the selected contiguous source interval **01:10–02:05**. It shows C Step 1 physically pushing the car east from Pizza, the tool withdrawing, **Checking car · MUSE**, a **new PASS at 06:42:17**, and **C Step 2 · Robot command in progress**. The earlier displayed PASS was 06:40:53. The review result changes within this interval; it is not a prior result displayed throughout empty return.

| Position in selected clip | Sampled visible state |
|---|---|
| 0:00 | C Step 1 pushing the car; prior PASS remains displayed. |
| 0:15 | Car farther east relative to the pink departure outline. |
| 0:25 | Tool withdrawing left; car becomes unobstructed. |
| 0:35 | Checking car · MUSE; next action awaits execution. |
| 0:45 | New PASS timestamp 06:42:17. |
| 0:50 | C Step 2 executing with the new PASS. |

These are sample positions, not exact state-transition boundaries or synchronized sensor times. The archived host-state sequence independently confirms observation in flight, a newly recorded progress result, and the next MOVING state. Device review times and host receive times have distinct meanings; no precise clock alignment is asserted.

The published MP4 is a **55.000-second, 1,376 × 1,032, 15 fps H.264/yuv420p viewing derivative**, 9,418,812 bytes, with no audio or source container metadata. Its 825 frames all decoded successfully; progressive-download layout and actual loopback browser playback were checked. Processing is one continuous cut, half-size resampling, frame-rate resampling and encoding. There are no inserted frames, annotations, replacement results, generative edits or reordered events. The original brief AR redraw interruption around source 01:15 is retained.

[`physical-action-muse-review.jpg`](physical-action-muse-review.jpg) is the full frame at selected-clip 0:50 (source 02:00), showing the new PASS and Step 2. JPEG encoding is the only additional processing; EXIF, XMP, IPTC and location metadata are absent. The original long recording is not linked or bundled here; its full-file hash is not asserted because it was inspected using bounded reads. The approved short derivative is hosted in the user's existing Drive archive, with its existing inherited sharing unchanged. It is not bundled in Git.

This clip demonstrates **one physical action, fresh review and continuation**. It does not establish full-route arrival, signal admission, parking alignment or repeatability. No new model request, robot motion, camera adjustment or operational service restart was performed to prepare it.

## Camera recording

[Watch the source tablet recording](https://drive.google.com/file/d/1Hflx4wuoLFTQvOuHA_Aqk8_FBQhNt1bp/view)

- Source: Drive file `1Hflx4wuoLFTQvOuHA_Aqk8_FBQhNt1bp`, originally named `카메라뷰_2.MP4`, 258,155,682 bytes.
- Reported duration: approximately 2 minutes 19 seconds; decoded canvas 2752 × 2064.
- The inspected early, middle and late frames show the actual car near Villa, the physical tool/hoses, the AR path and an empty-tool return in progress. The tablet displays the last MUSE PASS and signal-passed state.
- The beginning already shows return receipts. This is a **post-arrival/return recording**, not a continuous start-to-arrival demonstration. Displaying a prior PASS is not a new inference during return. The clip is not used to claim verified completion of every return stage.
- [`robot-tablet-recording.jpg`](robot-tablet-recording.jpg), the earlier README thumbnail retained as supporting material, is a full frame extracted at a requested position of 30 seconds. It has no crop, resized geometry, added annotation, replacement UI or generated pixels. Decoding/JPEG encoding is the only processing.

## Spatial recording

[Watch the source Spatial tablet recording](https://drive.google.com/file/d/1ZxNHMMrLSJfVC78_qcFdsB_DVkqEp-f3/view)

- Source: Drive file `1ZxNHMMrLSJfVC78_qcFdsB_DVkqEp-f3`, originally named `ScreenRecording_10-31-2026 00-21-17_1.MP4`, 232,769,024 bytes.
- Reported duration: approximately 2 minutes 14 seconds; decoded canvas 2752 × 2064.
- The inspected frames show Spatial, the Villa route, the recorded review state and a sequence-details dialog during return.
- This is an **actual application recording of a rendered 3D view**. Its car is the application's execution estimate. It is not a second physical camera, measured car tracking or a synchronized multi-view comparison with the Camera recording.
- [`spatial-tablet-recording.jpg`](spatial-tablet-recording.jpg) is the first decoded full frame, with only decoding/JPEG encoding.

## Physical setup photograph

[`robot-tabletop-setup.jpg`](robot-tabletop-setup.jpg) comes from the user's supplied archive photograph, originally named `KakaoTalk_Photo_2026-10-31-03-25-27 001.jpeg`. Metadata and the auxiliary gain-map trailer were removed before publication; the primary JPEG compressed image data and decoded pixels remain identical. The original photograph is identified by its source checksum rather than a public download link. It shows the actual robot, rubber tool, printed tabletop and camera installation. It does not itself establish a successful vehicle mission.

## Provenance and limits

The [machine-readable manifest](physical-media.json) records image dimensions, SHA-256 values, selected source IDs, video checksums and extraction positions. No generative editing, compositing or visual enhancement was used. Approved video links remain in Drive rather than copying video bytes into Git. Existing sharing settings were inspected and not changed.

Device clocks and Drive timestamps differ. We do not assert precise acquisition dates from filenames or synchronization across recordings. The selection date above is known; historical B/C/D trial records retain their own dates and acceptance criteria.

The videos are playback links, not a deployed browser control endpoint. Watching them cannot command the robot. The original public records preserve historical model disagreements and operator decisions. These media are not relabelled as a repeatability study, an unattended-production qualification or a recognition benchmark.

The supplied map/model/scene material remains inherited. Publishing these selected user-supplied captures does not claim new authorship of that material or a general redistribution license for its source artwork and model files.
