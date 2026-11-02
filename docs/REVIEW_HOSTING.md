# Recorded review hosting

The [recorded review](review/index.html) is an equipment-free, read-only explorer of three archived Meta MUSE responses to synthetic input pairs. GitHub Pages serves the existing interface without running the PushPilot backend, calling MUSE or connecting to a robot. It does not establish live inference, physical delivery or benchmark accuracy.

The configured public site address is [jominsu-ku.github.io/PushPilot/](https://jominsu-ku.github.io/PushPilot/). Availability depends on the latest successful Pages deployment.

The dedicated [workflow](../.github/workflows/review-pages.yml) publishes only a four-file artifact:

| Artifact file | Source and purpose |
| :--- | :--- |
| `index.html` | Existing public review, with navigation/font paths rewritten for hosting |
| `fonts/PretendardVariable.woff2` | Unmodified pinned Pretendard Variable v1.3.9 |
| `fonts/OFL.txt` | Complete unmodified SIL Open Font License |
| `.nojekyll` | Empty marker for static hosting |

Original inline response JSON, embedded PNG bytes, scripts and the no-connection Content Security Policy remain unchanged. The build verifies the response against the [public record](evidence/synthetic-action-reviews-20261027.json) and checks each PNG against its original published hash. Repository navigation leads to canonical GitHub `main` files; the artifact does not copy the repository, source tree, private images, API configuration or runtime data.

## Build and preview locally

Python 3.12+ and the standard library are sufficient. No dependency installation or credentials are required.

```bash
python -m unittest discover -s tests -p test_review_site.py -v
python tools/build_review_site.py --output dist/review-site
python -m http.server 8195 --directory dist/review-site
```

Open `http://127.0.0.1:8195/`. Output must be a new or empty directory outside the repository, or exactly the ignored `dist/review-site` directory. The builder refuses nonempty destinations and symlinks/junctions; it does not delete or overwrite an existing build. Use a new output directory for the next build, or explicitly remove the previous generated output yourself after checking its path.

## GitHub deployment

Repository Pages settings must select **GitHub Actions** as the publishing source. The workflow runs on relevant `main` changes or explicit manual dispatch from `main`, tests/builds a narrow artifact, then deploys through the `github-pages` environment. It does not provision custom DNS or change the running GX10 application. A successful source push is separate from a successful Pages deployment; check the deployment result before claiming the hosted link is ready.

Build has read-only source/Pages metadata access; only the deployment job receives `pages: write` and `id-token: write`. Newer runs cancel superseded runs. Official actions are pinned by full commit SHA. No repository credential, MUSE key or private media is embedded in the artifact.

The workflow follows [GitHub's custom Pages workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), using the verified official releases of [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1), [setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0), [configure-pages v6.0.0](https://github.com/actions/configure-pages/releases/tag/v6.0.0), [upload-pages-artifact v5.0.0](https://github.com/actions/upload-pages-artifact/releases/tag/v5.0.0) and [deploy-pages v5.0.1](https://github.com/actions/deploy-pages/releases/tag/v5.0.1), checked November 2, 2026.
