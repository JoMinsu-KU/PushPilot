<sub>[PushPilot](../README.md) / [Documentation](README.md) / Development</sub>

# A reproducible development path

**Build the map-independent application first. Preserve the boundary to hardware.**

[Architecture](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) · [Deployment](../deploy/README.md)

## Start here

This is the independent application repository. It must build and package without private planning material, handoff archives, historical previews, map assets, or operating evidence.

The current implementation is a bootstrap: standard-library checks, source-release packaging, and release tests. It does not contain an application runtime. Frontend/backend frameworks, provider dependencies, application startup commands, and lockfiles have not been selected.

| Requirement | Purpose |
| :--- | :--- |
| Python 3.11+ | Bootstrap checks and release tooling. |
| Git on `PATH` | Release identity and isolated Git-based tests. |
| No third-party Python dependencies | Current tools use the standard library. |

From the repository root:

```sh
python tools/dev.py check
python tools/dev.py test
```

`check` parses Python and JSON syntax. `test` runs the current 13 release test methods. Passing these commands establishes bootstrap behavior only, not working MUSE, signal perception, AR, or robot control.

## Implementation sequence

1. **Contracts and supervision:** versioned boundaries, explicit transitions, and a source-labelled abstract simulator.
2. **Operator workspace:** actual supervisor state, including approval, waiting, review, uncertainty, faults, and replay.
3. **Meta interaction:** provider adapter, versioned prompts, validated responses, and immutable request/result evidence.
4. **Integrated hardware-free flow:** a symbolic mission, RED wait, accepted GREEN, review rejection, reobservation, and restart.
5. **GX10 delivery:** runtime selection, host inspection, and an isolated release/activation path.
6. **Later physical integration:** map-specific work only after the map hold is released and the final installation is available.

When selecting dependencies, add manifests and lockfiles with reproducible installation and verification commands. Do not install a framework merely to populate an empty component directory.

## Repository discipline

Source, identifiers, comments, logs, prompts, UI copy, accessibility text, errors, and development documentation are English. User discussion may remain Korean.

Commit source, contracts, versioned prompts, meaningful tests, and reviewed examples. Keep credentials, private images, runtime logs, operating profiles, mailboxes, and raw archives outside Git and release packages.

`.env.example` contains proposed empty placeholders. Bootstrap tools do not consume it. Introduce documented configuration behavior with the runtime; copying the file does not enable a feature. Credentials use the existing direct-input path rather than chat.

### Git and authorship

Inspect current repository status and remotes before preparing a source snapshot:

```sh
git status --short --branch
git remote -v
```

Use the user's actual Git identity. Review the intended file list before committing; the snapshot records its real date. Do not invent an author or backdate history. Repository creation, publication, visibility, and software license are separate user choices.

Record reused work and exact changes in [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md). An imported file does not automatically have publication rights or become newly authored by entering this repository.

## Prepare a reviewed source release

Review and commit intended source first. The builder requires a clean committed HEAD, including no staged or nonignored untracked work. Create the output directory outside the repository:

```sh
python -c "from pathlib import Path; Path('../release-bundles').mkdir(parents=True, exist_ok=True)"
python tools/build_release.py --output ../release-bundles/pushpilot-source-v0.1.0.zip
python tools/build_release.py --verify ../release-bundles/pushpilot-source-v0.1.0.zip
```

The builder refuses an existing output path. The manifest binds committed source and hashes; verification checks integrity and path policy without extraction. Neither step transfers files, starts a service, authenticates a publisher, or establishes publication rights.

See [release tooling](../tools/README.md) for exact scope and [GX10 deployment](../deploy/README.md) for later delivery gates.

## Boundaries that remain in force

| Area | Current rule |
| :--- | :--- |
| Map | Final geometry/installation unknown; defer graphs, routes, coordinates, registration, stop/exit lines, signal ROIs, and registered AR. |
| Mission | Symbolic locations and abstract actions; wheel-less surface pushing is the intended physical scenario. |
| Signals | Full stop even on GREEN; RED/unknown/stale/obscured observations inhibit entry. |
| Models | Validated interpretation/review; no generated robot scripts or authoritative coordinates. |
| Evidence | Robot, image, car-pose, signal, and model sources independently labelled. |
| Hardware | No robot contact, profile replay, mailbox restoration, camera ownership, or service restart by default. |
| Stops | UI HOLD and process exit do not imply immediate in-flight stopping. |

## State, evidence, and restart

Future local runtime files belong in ignored `runtime/`; GX10 uses dedicated shared storage. Keep immutable evidence references, causal identifiers, exact provider inputs/results, source labels, and transition causes. Scrub credentials from logs and receipts.

After restart, reconstruct history in a non-executing review state. Pending commands, admitted crossings, and old GREEN observations do not automatically regain authority. Code rollback must preserve the evidence history.

---

[Frontend](../frontend/README.md) · [Backend](../backend/README.md) · [Contracts](../contracts/README.md) · [Prompts](../prompts/README.md) · [Tests](../tests/README.md)
