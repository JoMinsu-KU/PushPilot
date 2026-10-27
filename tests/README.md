<sub>[PushPilot](../README.md) / Engineering / Tests</sub>

# Evidence for what works

**A passing packaging test is a packaging claim.**

[Development](../docs/DEVELOPMENT.md) · [Release tools](../tools/README.md) · [Roadmap](../docs/ROADMAP.md)

## Current suite

The repository contains **17 test methods**: 13 release tests in [`test_release_bundle.py`](test_release_bundle.py) and four offline connection-tool tests in [`test_muse_api_check.py`](test_muse_api_check.py). They use temporary Git/ZIP/configuration fixtures and fake provider responses. They do not read the real `.env`, contact equipment, call a model API, change the application's Git author identity, or start a service.

From the repository root, with Python 3.11+ and Git on `PATH`:

```sh
python tools/dev.py check
python tools/dev.py test
```

| Tested boundary | Coverage |
| :--- | :--- |
| Committed source identity | Clean HEAD, commit binding, manifest contents, ignored local-file exclusion. |
| Working-tree state | Rejection of modified, staged, and nonignored untracked files. |
| Output handling | Rejection of output inside the repository and an existing target. |
| Publication path policy | Private tracked paths, allowlisted content, example configuration, Git symlink modes. |
| ZIP verification | Payload hashes, unsafe paths, duplicate/case-colliding entries, symlinks, size limits, malformed manifest. |
| Command interface | Verification CLI returns the expected status. |
| Connection checker | Local-key parsing, missing-model inhibition, bounded requests, exact response matching and credential-echo redaction using fixtures. |

Fixture Git resets run only inside temporary test repositories. These tests do not reset the application repository.

## What a pass does not establish

The current tests do not validate a frontend, mission supervisor, MUSE integration, paper-signal perception, camera registration, AR overlay, pushing control, or physical robot behavior. Those implementations are pending.

Package verification checks archive integrity and policy. It does not establish publication rights, absence of sensitive prose, or a trusted publisher.

## Tests to add with the application

| Implementation | Behavior worth testing |
| :--- | :--- |
| Supervisor | Approval, full stop on GREEN, RED/unknown wait, GREEN admission, post-action review, invalid transitions. |
| Provider adapter | Malformed output, timeout, uncertainty, observation mismatch, local/model disagreement. |
| Evidence store | Immutable causal references, source labels, exact request/result binding, restart reconciliation. |
| Operator UI | Wait/fault/review states, keyboard use, source labels, actual backend state. |
| Replay | Reproduces recorded decisions without dispatching actions. |

Keep simulated tests, recorded-image provider evaluations, and future physical qualification in separate evidence categories. Passing one category must not silently upgrade another.

---

[Contract validation](../contracts/README.md) · [GX10 delivery](../deploy/README.md)
