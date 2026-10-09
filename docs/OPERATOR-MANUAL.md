# DUAT Vault operator manual

Use the [installation guide](INSTALL.md) to configure the archive and optional services.
The [architecture paper](DUAT-Vault-Architecture-White-Paper.md) explains the verification
boundaries. All paths below are examples for the current operator's home directory.

## Inspect and protect

```bash
project-vault status
project-vault sources
project-vault items
project-vault pin "$HOME/Projects/example/active-output"
```

Keep active source, worktrees, unique binaries, toolchain identity, and evidence locally.
Pins coordinate cooperating workflows; release only a pin whose owner has finished.

## Back up and find

```bash
project-vault backup
project-vault list
project-vault find example-output
project-vault find '*Cargo.toml*' --online
project-vault find '*Cargo.toml*' --online --wait-lock
```

The local catalog is intentionally incomplete. An offline miss does not establish
absence from the archive. Use online search or a known item/snapshot when available.
`--wait-lock` waits for the existing exclusive vault lock instead of failing when
busy, then rechecks device identity before searching. It requires `--online`.
Without it, the busy behavior remains nonblocking. Cancelling a waiting query does
not release the current owner's lock. An acquired search still holds the normal
lock for its duration; neither this option nor repeated retries bypass it.

## Archive and recover

```bash
project-vault put "$HOME/Projects/example/completed-output"
project-vault put "$HOME/Projects/example/completed-output" --offload
project-vault get ITEM_ID --to "$HOME/Work/recovered-output"
```

The initial `put` retains the original. `--offload` requests retirement only after
complete candidate recovery, content/metadata comparison, and activity/pin checks.
`ITEM_ID` is a placeholder; use an identifier returned by your own vault.
Recovery destinations must be new. An old receipt never authorizes deleting regrown data.

For reviewed inactive flat Cargo dependency directories, `--retain-binaries` preserves
non-object files in a pinned local sibling before the complete candidate is archived
and compared. Do not use it to retire active build outputs.

## Background work and health

Backups preserve local files. Only a completed verified offload reclaims them.
Use the [inactive-output guide](OFFLOAD.md) to select a narrow eligible candidate,
preserve its source and record genuine provenance before enrollment.

Record source/toolchain/regeneration context with `project-vault provenance` before
explicit queue enrollment. Workers process reviewed entries; they do not automatically
select arbitrary cache directories. The dashboard listens on loopback and depends on
configured worker units. Inspect per-scope results and receipt timestamps, not just
service enablement. Anubis-specific scheduler scopes need adaptation for other projects.

Background maintenance yields when it observes an active compiler/prover, an unreleased
configured coordination file, a pending retrieval or a busy vault lock. Malformed or
unreadable scheduling records defer it too. Deferral does not mean a backup or offload
completed. Read `state/background-KIND.json` and the service journal for the reason.
Existing transfers finish; subsequent scopes/items wait for a later activation.
The checks are cooperative, so new work can start after a check. Low service priority
reduces contention but does not establish exclusive build admission.

```bash
project-vault audit
project-vault audit --online
project-vault check --full
project-vault recovery-export
```

Reference audit, full repository data reading, and complete restoration establish
different facts. Read the method and scope before reporting success.

## Failures and recovery

On activity, pin conflict, identity mismatch, capacity refusal, or changed source,
keep the local data and investigate. Never clear another process's lock or delete
quarantine/restore scratch by hand. For interrupted retirement, inspect the receipt
and recover the complete item to a new location. See the
[recovery bootstrap guide](../RECOVERY-BOOTSTRAP.md) for replacement-machine recovery.

An offloaded item may have only the iPad archive copy. Its loss can destroy that data.
The recovery password is stored beside the archive by the original design; treat the
entire Recovery folder as private. Do not commit configuration, receipts, catalogs,
credentials, or archive data to a source repository. Pruning is disabled.
