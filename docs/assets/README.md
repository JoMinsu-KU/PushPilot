# Documentation artwork

These self-contained SVG illustrations establish the PushPilot repository's visual direction. They use dark navy, electric cyan, simple geometric line work, and system-font fallbacks so the source stays editable and GitHub can display it without a build step.

| Asset | Canvas | Purpose |
| --- | --- | --- |
| [`hero.svg`](hero.svg) | 1280 × 480 | Repository cover: a shared plan, observable evidence, and a human review surface. |
| [`workflow.svg`](workflow.svg) | 1280 × 254 | Proposed Observe → Plan → Approve → Act → Verify interaction. |

## Provenance

Both assets were authored for this application repository on October 27, 2026 as original, code-native vector illustrations. No third-party photographs, stock illustrations, fonts, vendor logos, or generated raster media are embedded. The abstract robot, car, interface panels, and brand mark are drawn directly with SVG geometry.

The artwork is an illustration of the proposed product experience. It is not a screenshot, a camera observation, a connected device, a model response, a final map, or evidence of physical execution. The hero and workflow include visible concept labels to preserve that distinction when viewed outside this README.

## Editing rules

- Keep the English labels readable at GitHub's normal content width.
- Preserve the explicit concept and bootstrap status labels.
- Do not add map coordinates, finalized road geometry, invented performance figures, or simulated results presented as real evidence.
- Keep SVGs self-contained: no external assets, scripts, remote fonts, or `foreignObject` elements.
- Update each SVG's accessible `<title>` and `<desc>` when its meaning changes.

No software or artwork license has been selected for this repository. Original authorship is a provenance statement, not a license grant.
