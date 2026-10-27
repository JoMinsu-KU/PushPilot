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

The first software workspace does not yet ingest images. Its scene is an original illustration and its signal/review controls inject explicitly labelled simulation observations. Printing alone does not connect a camera.

## Deferred until the installed map is settled

Road routes, stop-line geometry, signal regions, metric AR registration, board-to-BASE transforms, contact/TCP offsets and motion qualification remain separate work. Do not treat this document or a visually plausible overlay as calibration evidence.
