# DUAT Vault

Verified project storage and recovery for a Linux working set backed by an iPad archive.

DUAT Vault wraps restic with explicit source discovery, offline search, working-set pins,
recovery receipts, and guarded offload. Before retiring an eligible local directory, it
archives the complete candidate, restores it, compares content and metadata, rechecks
activity and pins, and verifies the quarantined source before removal.

This repository contains the implementation developed for Omarchy and Anubis engineering,
the Project Vault agent skill, and the architecture white paper. It is MIT licensed and
publicly available on GitHub.

## Read and explore

- [Architecture white paper](docs/DUAT-Vault-Architecture-White-Paper.md)
- [Standalone HTML reading edition](docs/DUAT-Vault-Architecture-White-Paper.html) — download and open locally
- [Installation and configuration](docs/INSTALL.md)
- [Original operator manual](docs/OPERATOR-MANUAL.md)
- [Replacement-machine recovery](RECOVERY-BOOTSTRAP.md)
- [Project Vault agent skill](skills/project-vault/SKILL.md)
- [Source provenance and release scope](docs/PROVENANCE.md)

The white papers are sanitized publication editions. Paths and commands use generic
examples; personal device inventories, production identifiers, storage measurements,
and account details are omitted. See [privacy review](docs/PRIVACY-REVIEW.md).

## DUAT Bench and Live Metrics

Open **Bench & live metrics** from the local dashboard or run `project-vault bench`.
Synthetic-only runs separate payload movement, encrypted backup, verified restore,
and complete round-trip time, with phase rates, labeled peaks, operating telemetry,
and HTML/CSV/JSON exports. See the [benchmark guide](docs/BENCH.md) for measurement
boundaries, reserve checks, and reproducible workload settings.

## Workflow

After configuring and initializing a new vault:

```bash
project-vault put "$HOME/Projects/example/completed-output"
project-vault items
project-vault find completed-output
project-vault pin "$HOME/Projects/example/active-output"
```

`put` keeps the local original. Adding `--offload` requests guarded retirement after
complete recovery comparison. Retrieve an archived item to a new local path:

```bash
project-vault get ITEM_ID --to "$HOME/Work/recovered-output"
```

The dashboard listens on loopback at `http://127.0.0.1:8767`. Background processing
uses explicit queue enrollment. There is no automatic cache discovery for deletion
and no snapshot pruning.

## Requirements and boundaries

The runtime uses Python's standard library plus external Linux tools: Python with
`Path.is_relative_to`, restic, Git, and an ifuse application mount. Cold storage uses
Linux `/proc`, file locks, extended attributes, and libc `renameat2`. Systemd user
services are optional. The HTML renderer additionally needs the Python `Markdown` package.

An iPad mount and any USB/SSH transport must already be configured by the operator.
The included service templates retain the original Anubis integration and need review
before enabling them on a different machine. See the installation guide.

After offload, the iPad may hold the only remaining archive copy. Recovery credentials
are also copied to its Recovery directory by the original design. Process checks and
locks require cooperating writers. Filesystem recovery does not prove application
consistency or successful execution of a recovered toolchain.

## Tests

```bash
python3 -m unittest discover -v
```

Tests use temporary local restic repositories, including full offload/retrieval,
tampering, pin changes, active processes, locking, queue edits, and recovery-kit checks.
Cold-storage tests require process inspection privileges; see [testing](docs/INSTALL.md#testing).
Fixture success does not establish production disaster recovery.

## License

[MIT](LICENSE), copyright AnubisQuantumCipher. Restic, ifuse, and other external
dependencies retain their own licenses and are not vendored here.
