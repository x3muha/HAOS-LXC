# Test gates

| Gate | Acceptance criterion |
|---|---|
| A | Verified official x86-64 image, correct GPT partition, archive metadata and hashes, audit reviewed. |
| B1 | Isolated probe CT boots systemd, marker is written, no upstream service activity, no host devices, unprivileged mapping. |
| B2 | Reviewed persistence, networking, D-Bus, clean restart with real runtime profile. |
| C | Nested Docker functional with constrained host access; storage matrix tested. |
| D | Supervisor and OS Agent report real capabilities; UI onboarding at 8123; persist configuration. |
| E | Core and app updates, backup and restore, MQTT and network discovery. |
| F | Verified OS update, simulated failure and consistent rollback. |
| G | PBS backup/restore, snapshot/migration and release/license checks. |

Record upstream tag, source and template hashes, PVE version, kernel, CT config, storage, logs and outcomes. Redact sensitive details. Stop on unresolved isolation or data-integrity failures. No gate beyond fixture tests is claimed to have passed.
