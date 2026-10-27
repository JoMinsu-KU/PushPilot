<sub>[PushPilot](../README.md) / Engineering / Tools</sub>

# Small tools, explicit boundaries

**Check the workspace. Package committed source. Verify the result.**

[Development](../docs/DEVELOPMENT.md) · [Tests](../tests/README.md) · [Deployment](../deploy/README.md)

## Available commands

Run from the repository root. Tools require **Python 3.11+**; release operations and the current tests also require **Git on `PATH`**. No third-party Python package is required.

| Command | What it does |
| :--- | :--- |
| `python tools/dev.py check` | Parses Python and JSON source syntax; does not import application modules or initialize services. |
| `python tools/dev.py test` | Runs `unittest` discovery in `tests/` with bytecode writing disabled. |
| `python tools/build_release.py --output <archive.zip>` | Packages allowlisted blobs from a clean committed HEAD and writes a hash manifest. |
| `python tools/build_release.py --verify <archive.zip>` | Validates ZIP paths, metadata, policy, sizes, and SHA-256 values without extracting. |

Commands return a nonzero exit code on failure. Successful check/build/verify commands print a compact JSON result. The test runner prints its normal test report.

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

This repository currently produces a **source/bootstrap package**. These tools do not implement installation, SSH transfer, service startup, activation, rollback, or robot commands. Follow the [isolated GX10 plan](../deploy/README.md) when a runtime exists.

Review contents separately for credentials, private media, attribution, and publication rights. Hash integrity does not authenticate a publisher or replace that review.

---

[Release tests](../tests/test_release_bundle.py) · [Contribution record](../CONTRIBUTIONS.md) · [Third-party notices](../THIRD_PARTY_NOTICES.md)
