# Pretendard Variable

**Unmodified upstream font, self-hosted for the PushPilot interface.**

The user selected Pretendard for product typography. This directory vendors the complete Pretendard Variable v1.3.9 WOFF2, with Korean and Latin text support, and the official upstream license. It is not a PushPilot-designed font or a locally modified/subset font.

| Field | Value |
| :--- | :--- |
| Upstream | [orioncactus/pretendard, v1.3.9](https://github.com/orioncactus/pretendard/tree/v1.3.9) |
| Author | Kil Hyung-jin |
| Font | [`PretendardVariable.woff2`](PretendardVariable.woff2) |
| File size | 2,057,688 bytes |
| SHA-256 | `9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4` |
| Variable weight range | 45–920, as declared by the upstream CSS |
| License | [SIL Open Font License 1.1](OFL.txt) |
| Copyright | © 2021 Kil Hyung-jin, with Reserved Font Name Pretendard |
| Vendored | 2026-10-27, Asia/Seoul; font bytes and license kept unmodified |

## Pinned official sources

- [Full variable WOFF2](https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2)
- [Variable CSS](https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/web/variable/pretendardvariable.css), which identifies the font-family, weight range and WOFF2 path
- [Original license](https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/LICENSE), preserved locally as `OFL.txt`

PushPilot loads the font from its own origin with `@font-face` and a preload. It makes no font CDN request and requires no system font installation on GX10 or the client device. Product text uses `Pretendard Variable` with system sans-serif fallbacks; machine-readable JSON/evidence retains monospace formatting. Loading a font does not change the requirement that authored UI and development material remain English.

Vite copies this directory into `frontend/dist/fonts/pretendard/`. Preserve the font's copyright notice and complete `OFL.txt` in source archives and deployed static distributions. The font's license does not select a license for PushPilot's original source or artwork.
