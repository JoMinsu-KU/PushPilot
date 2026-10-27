# Temporary scene inputs

The application keeps map geometry independent of mission supervision. A temporary printed scene can test image ingestion and semantic review without establishing robot coordinates or a production route.

## Little Town print candidate

Reviewed on 2026-10-27, Asia/Seoul, from a user-supplied PDF:

| Property | Value |
|---|---|
| Filename | `PushPilot_Little_Town_Production_A3_EN.pdf` |
| SHA-256 | `d7c834a27b61480eee8d9bfbd8fe4f71e0e168d17ef5e728ef99280ba177c7ff` |
| Document | One A3 landscape page, 420 × 297 mm |
| Drawing | Labelled 400 × 250 mm scene, four corner markers and a 100 mm scale |
| Named places | PIZZA, BOOKSTORE, SCHOOL, BAKERY |
| Use | Candidate temporary input for camera and MUSE experiments |
| Included in this repository | No; the supplied artwork remains outside the public source boundary |
| Physical or model validation | None established by inspecting the PDF |

Print A3 landscape at **100% / Actual size**, with page fitting and shrinking disabled. Measure the printed 0–100 mm scale: it must be 100 mm. Secure the sheet flat, avoid glare and keep the corner markers visible. A replacement print or moved sheet receives a new installation identity even if the PDF bytes are identical.

For a later observation, retain the input version, installation identity, image timestamp, camera identity, source type (`uploaded`, `recorded`, or `live`) and model/prompt version. Keep raw private frames outside Git. A model result over a photograph is provider evidence, not a physical mission result.

## What this test can establish

- Whether the actual image is readable, including named destinations and a wheel-less car when available.
- Whether a real red/green paper signal is distinguishable in the chosen lighting and viewpoint.
- Whether a model can compare a requested outcome with the supplied image and report insufficient visibility.

The temporary-map workspace now ingests private recorded images and supports explicit test overlays and MUSE scene inspection. Paper-signal gate inputs and action verdicts remain labelled simulation/demo observations. Printing alone does not connect a live camera. See [temporary-map behavior](TEMPORARY_MAP.md).

## Deferred until the installed map is settled

Final production routes, stop-line geometry, signal regions, metric robot registration, board-to-BASE transforms, contact/TCP offsets and motion qualification remain separate work. The user authorized temporary drawing routes and test-only image registration on 2026-10-27. Do not treat a visually plausible overlay as physical calibration evidence.

## Recorded camera evidence

The print was observed on GX10 with a Brio 500. Placement was adjusted until the entire paper and four markers were visible. A native 1920×1080 capture group completed at approximately **15:01 KST on 2026-10-27**. The initial installed GX10 OpenCV 4.6 detector found all four IDs in two of three frames. The pinned application OpenCV 5 detector with default corners found all four in one of three, demonstrating that detector-version changes need their own validation. These small non-simultaneous checks are not an accuracy benchmark.

The application uses the complete second frame as a recorded input. Its subpixel-refined four-marker projection has a **1.4333 px image-space RMS residual**. This is fit residual, not independently measured millimeter accuracy. No physical car or separate paper signal was present. At **15:59 KST**, actual MUSE inspection identified all four shops, reported no separate physical car and returned signal `UNKNOWN`; [provider record](META_API_CHECK.md).

Original photographs and operational capture records remain outside Git. The public repository includes adapted geometry facts and a self-authored spatial schematic, not the raw print artwork or camera photographs. The recorded capture time is operator-provided; an image's upload time is not live freshness evidence.
