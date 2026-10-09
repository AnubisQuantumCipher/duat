---
name: project-vault
description: Manage DUAT project storage by checking local capacity, protecting active outputs, verifying offload candidates, and retrieving archived artifacts. Use for storage-heavy engineering work or explicit archive and recovery tasks.
---

# DUAT project storage

Keep active work and unique evidence locally. Use the configured vault for explicit
archive and recovery operations. This skill does not grant permission to retire data;
use the operator's actual authorization and policy for each workflow.

## Preflight

Run `scripts/storage_status.py` relative to this skill directory. It reads local
configuration and state without traversing project sources or contacting the archive.
Review free space, reserves, pins, queue state, operation records, and dated receipts.
A historical passing receipt does not establish current backup health.

Before large work, identify exact output paths and owners and pin active paths with
`project-vault pin PATH`. Allow space for build growth and complete restore scratch.
Never reduce reserves or recovery checks to make a candidate fit. Inspect only relevant
directories; do not scan entire home directories or live application databases by default.

For Anubis workflows, read [references/anubis-workflow.md](references/anubis-workflow.md).
Application-specific build isolation, toolchain identity, and evidence rules still apply.

## Archive and offload

Read [references/offload.md](references/offload.md) before local retirement.

- Classify actual contents and ownership; a cache name, age, or quiet process scan alone is insufficient.
- Preserve source, dirty changes, toolchain identity, unique binaries, and proof evidence.
- Record genuine regeneration context with `project-vault provenance`; do not invent historical build flags.
- Release only pins owned by a completed workflow when the operator's policy permits it.
- Use `project-vault put PATH` to archive and compare while retaining the source.
- Use `project-vault put PATH --offload` only for an authorized, eligible candidate.
- Check the completed receipt and original/quarantine/scratch state before reporting retirement.

Busy/offline operations wait. Do not clear another process's lock, remount during an
operation, or delete original, quarantine, or restore scratch manually. Every retired
candidate needs its own full recovery comparison. Never blanket-delete caches.

## Retrieve

```bash
project-vault items
project-vault find QUERY
project-vault get ITEM_ID --to NEW_LOCAL_DIRECTORY
```

The compact catalog is incomplete. Use `find PATTERN --online` when the archive is
available. `get` to the original location requires that path to be absent. A regrown
path is new state; recover elsewhere. Never replace a historical artifact with a newly
built one while claiming it was recovered, or execute recovered scripts merely to test access.

When another vault operation owns the lock, `find PATTERN --online --wait-lock`
waits for it and revalidates the device before searching. Do not remove locks or
restart their owners. Background maintenance defers around observed builds and
retrievals, with checks between backup scopes/offload items; this is cooperative
scheduling, not a guarantee of future idle time.

Backups alone free no local storage. Use the repository's
[inactive-output guide](https://github.com/AnubisQuantumCipher/duat/blob/main/docs/OFFLOAD.md) to establish eligibility and explicit
queue enrollment. A queued candidate is not reclaimed space, and a historical
offload receipt does not cover regenerated files at the same path.

## Boundaries and handoff

Use local Linux storage for active builds and restored files. The app mount is an
archive transport. Do not replace active roots with symlinks to archive storage.
Preserve the device application and its data. An offloaded item may have only one
physical archive copy. The recovery credential can reside beside that archive;
keep operational configuration, receipts, and credentials private.

Metadata audits, repository data scrubs, candidate recovery, whole-scope file restore,
and application/build validation are separate claims. Report the receipt's method and
scope. Leave handoff notes through the operator's chosen mechanism, without secrets.
Consult the repository README, architecture paper, and recovery bootstrap guide for
installation-specific configuration. No personal installation policy is bundled here.
