<sub>[PushPilot](../README.md) / Delivery / GX10</sub>

# Local development → reviewed release → GX10

**One source repository. Isolated releases. Preserved operating evidence.**

[Development](../docs/DEVELOPMENT.md) · [Release tools](../tools/README.md) · [Architecture](../docs/ARCHITECTURE.md)

> **Status: proposal only.** No remote directory, runtime, port, service, or permission has been checked or provisioned by this scaffold. This application has not been deployed or started.

## Delivery model

Develop and test locally, use GitHub for reviewed source/history, and deploy reviewed release snapshots to GX10. GX10 is the intended runtime host, not the primary development folder.

[![Proposed delivery flow: local source checks, tests and review lead to a committed source ZIP and hash manifest; future transfer, verification and isolated GX10 installation precede health checks and deliberate activation.](../docs/assets/delivery-flow.png)](../docs/assets/delivery-flow.png)

*Proposed delivery design. Packaging is implemented; remote transfer, runtime installation and activation are future work. Select the image for the full-size view.*

The sequence is **local checks and reviewed commit → source ZIP and manifest → verified new GX10 release → isolated installation and health checks → deliberate activation**. The source bundle never activates itself.

The current ZIP is a source/bootstrap artifact. Installation and activation become meaningful after the frontend/backend runtime and its locked dependencies are implemented.

## Planned application services

The first application uses an operator browser and one modular backend containing voice transcription, MUSE interpretation/review, the mission supervisor, simulation and evidence. External Meta Spark and Meta Voice are separate provider adapters using server-held credentials. See [service composition](../docs/SERVICE_COMPOSITION.md) and [voice input](../docs/VOICE_INPUT.md).

Voice capture requires HTTPS trusted by the target tablet and secure-context/microphone preflight at the actual deployed origin. Localhost development is a distinct case; a plain LAN HTTP address must not be treated as microphone-ready. Select TLS serving and lock audio conversion dependencies with the runtime. Neither is provisioned by these documents.

## Prepare a bundle locally

From the repository root, with Python 3.11+ and Git on `PATH`:

```sh
python tools/dev.py check
python tools/dev.py test
```

After a reviewed commit and with a clean tree, create the external output directory and build a new archive:

```sh
python -c "from pathlib import Path; Path('../release-bundles').mkdir(parents=True, exist_ok=True)"
python tools/build_release.py --output ../release-bundles/pushpilot-source-v0.1.0.zip
python tools/build_release.py --verify ../release-bundles/pushpilot-source-v0.1.0.zip
```

The manifest identifies the exact Git HEAD and source hashes. Neither command contacts GX10. Use a new filename if the example already exists.

## Proposed host layout

Use the existing SSH alias **`gx10`**. Resolve the account and address through local SSH configuration rather than hardcoding LAN details in application code. Select and verify a dedicated `<deploy-root>` on the host.

```text
<deploy-root>/
├── releases/
│   └── <release-id>/         Reviewed source and isolated runtime
├── current -> releases/<id> Proposed active-release pointer
└── shared/
    ├── config/              Installed local configuration
    ├── secrets/             Restricted host-only credentials
    ├── evidence/            Immutable application evidence
    └── logs/                Logs with credential scrubbing
```

[`gx10.example.json`](gx10.example.json) is an example plan, not an executable deploy script or current host-state claim. Review it for the actual environment before copying it into local configuration. Establish ownership, permissions, disk availability, backups, retention, bind address, and a nonconflicting port before activation.

## Activation checklist

| Gate | Required review |
| :--- | :--- |
| Host inspection | Read-only inspection of runtime availability, disk, existing services, and occupied ports. |
| Source review | Exact commit, manifest, rights, attribution, and absence of sensitive content. |
| Transfer and verification | Integrity verification; extraction into a new release directory without overwriting releases or shared state. |
| Runtime installation | Declared, locked dependencies in an isolated environment; host-only secrets through the direct-input channel. |
| Application checks | New map-independent application health, source labels, and hardware-free review flow. |
| Activation | Select the active release after successful checks and the corresponding deployment authorization. |
| Recovery | Retain prior code; preserve shared evidence and reconcile runtime state before execution. |

The service manager, startup command, and activation/rollback scripts remain unselected until the runtime and actual host have been reviewed. This bootstrap provides no automatic deployment or autostart command.

## Operating boundaries

- Use a new application directory and isolated shared state.
- Preserve existing POC web, motion-test, camera, and persistent-receiver environments.
- Do not restart Rodi or the camera to deploy a frontend or supervisor.
- Keep robot transport and physical execution unavailable in the map-independent stage.
- A code rollback must not restore pending commands, old GREEN observations, or overwrite evidence.
- UI HOLD, process exit, and service shutdown are not immediate physical robot stop mechanisms.

---

[Mission gates](../docs/MISSION.md) · [Test evidence](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
