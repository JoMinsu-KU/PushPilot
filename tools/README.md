<sub>[PushPilot](../README.md) / Engineering / Tools</sub>

# Small tools, explicit boundaries

**Check the workspace. Package committed source. Verify the result.**

[Development](../docs/DEVELOPMENT.md) · [Tests](../tests/README.md) · [Deployment](../deploy/README.md)

## Available commands

Run from the repository root with **Python 3.12+**. Install `requirements.lock` for application startup and the full test suite. Source syntax checks, source packaging, and the standalone connection checker use the standard library; release operations and release tests also require **Git on `PATH`**.

| Command | What it does |
| :--- | :--- |
| `python tools/dev.py check` | Parses Python and JSON source syntax; does not import application modules or initialize services. |
| `python tools/dev.py test` | Runs offline `unittest` discovery in `tests/` with bytecode writing disabled. |
| `python tools/serve.py` | Serves built `frontend/dist` and the simulation API on loopback port 8080, one worker. |
| `python tools/serve.py --api-only` | Starts the API without requiring compiled frontend assets. |
| `python tools/build_release.py --output <archive.zip>` | Packages allowlisted blobs from a clean committed HEAD and writes a hash manifest. |
| `python tools/build_release.py --verify <archive.zip>` | Validates ZIP paths, metadata, policy, sizes, and SHA-256 values without extracting. |
| `python tools/check_muse_api.py` | Opt-in live Meta check: reads the ignored local key, queries models and sends one bounded text completion. |

Commands return a nonzero exit code on failure. Successful check/build/verify commands print a compact JSON result. The test runner prints its normal test report.

The Meta checker explicitly contacts a provider and may consume API credits. It is never invoked by `dev.py check` or `dev.py test`. The application launcher makes no automatic provider request; an operator can deliberately select a backend Meta goal request or a frame-bound recorded-scene inspection. See [connection setup and observed results](../docs/META_API_CHECK.md). The standalone checker is separate from `backend/meta.py` and is not an image-review test.

Build the frontend locally using Node 24 and `npm ci && npm run build` in `frontend/`. GX10 serves those compiled assets using Python without Node. The launcher supports explicit `--host`, `--port`, and `--state-path`, validates them before startup, disables reload, and starts no equipment processes. Locked runtime dependencies include OpenCV and NumPy for temporary-map marker detection. `PUSHPILOT_MAP_PATH` selects temporary geometry; `PUSHPILOT_SCENE_DIR` selects private uploaded-frame/registration/inspection storage. See [Development](../docs/DEVELOPMENT.md).

## Build a source release

Review and commit the intended source with the user's real Git identity. The builder requires a committed HEAD and a clean tree, including no staged changes or nonignored untracked files. Finish and commit the intended snapshot rather than removing work to satisfy the tool.

Create the output directory **outside this repository** first. This Python command works in PowerShell and a POSIX shell:

```sh
python -c "from pathlib import Path; Path('../release-bundles').mkdir(parents=True, exist_ok=True)"
python tools/build_release.py --output ../release-bundles/pushpilot-source-v0.1.0.zip
python tools/build_release.py --verify ../release-bundles/pushpilot-source-v0.1.0.zip
```

Choose a new filename for every bundle; the CLI rejects an existing target. The example filename's version is a human label. The manifest binds the actual Git commit and generated release identity.

## Inside the archive

The builder reads committed Git blobs. Its source allowlist covers selected root files and the `frontend`, `backend`, `contracts`, `prompts`, `tests`, `deploy`, `docs`, and `tools` directories. It adds `release-manifest.json` with the Git HEAD and each source file's size and SHA-256.

Tracked private/credential paths, symlinks, submodules, and special files fail the build even outside the allowlist. Ignored local files are not packaged. Unsupported top-level content is excluded; review the manifest before publication.

Verification rejects unsafe or colliding paths, unsupported ZIP entries, unexpected/missing files, hash mismatches, and oversized content without extracting. Current limits are 10,000 entries, 32 MiB per source entry, 128 MiB total uncompressed content, and a 4 MiB manifest.

## A release is not a deployment

The release builder produces a **committed source package**. It excludes ignored compiled `frontend/dist`, dependencies, local configuration, and SQLite state. A runnable frontend delivery additionally needs assets built from the same clean commit.

`serve.py` starts the application locally; it does not install dependencies, transfer files, configure a system service, select an active release, implement rollback, or issue robot commands. Follow [GX10 delivery](../deploy/README.md) for the selected Python/static-frontend arrangement and remaining host checks.

Review contents separately for credentials, private media, attribution, and publication rights. Hash integrity does not authenticate a publisher or replace that review.

---

[Release tests](../tests/test_release_bundle.py) · [Contribution record](../CONTRIBUTIONS.md) · [Third-party notices](../THIRD_PARTY_NOTICES.md)
