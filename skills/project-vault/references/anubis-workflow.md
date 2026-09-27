# Anubis campaign storage lifecycle

## Before building or proving

Read the project's AGENTS.md and identify the real compiler/toolchain and build lane. Keep isolated proof/verifier targets when required by that project; do not merge targets merely to save space. Identify each output path in the campaign notes, its owner, source commit plus dirty state, actual invocation/environment, retained compiler pin and evidence destinations.

Use the storage preflight from SKILL.md. For a new campaign, pin the exact active output directory with `project-vault pin /absolute/output/path` before build work starts. Inspect existing pins first so a later unpin cannot accidentally release another owner's protection. Pins are cooperative path protections, not ownership leases. Source roots that are already pinned stay pinned; do not unpin an entire repository to make a child eligible.

Use inexpensive checks before repeated native execution where appropriate to the task. Native `anubis run` can generate substantial Cargo output. Its cache location depends on the current compiler and environment: inspect `compiler/src/backends/run.rs`, `ANUBIS_RUN_CARGO_TARGET_DIR`, and the task's temporary-directory settings before assuming which cache is in use. Do not change shared environment variables or compiler behavior as a storage shortcut.

## While the campaign runs

Recheck free space between large build/proof batches. If capacity becomes inadequate, pause launching new large jobs and review completed, unowned outputs. Do not evict the active lane. Keep proof receipts and exact binaries referenced by claims, even when their filenames look generated. Avoid copying entire targets into every worktree unless the engineering workflow needs it.

Keep a small handoff in the task's existing notes, outside an offload candidate:

```text
Owner/task and active/completed state:
Exact output path and who owns its pin:
Repository, source commit, dirty-source snapshot if needed:
Compiler/toolchain identity and actual rebuild invocation/environment:
Evidence and unique binaries that must remain local:
Completed cold-item ID, snapshot, retained-local path, retrieval command:
```

Do not put credentials or secret values in this record. Unknown historical provenance stays explicitly unknown; a known cache-regeneration route does not reproduce an old proof claim.

## After completion: choose the narrow candidate

Use the common offload gates in `offload.md` and confirm the owner has finished. Release only the campaign's own output pin if eligible. Preserve pins held for evidence or other tasks.

| Candidate | Required handling |
|---|---|
| Inactive Cargo `debug/incremental` or `release/incremental` | Review actual contents and retained source/toolchain, then `put PATH --offload`; the vault acquires Cargo's profile lock. |
| Inactive flat Cargo `debug/deps` or `release/deps` | Use `put PATH --offload --retain-binaries` after review. The vault keeps every entry except non-executable `.rlib`, `.rmeta`, `.o` in a pinned sibling directory before retirement. If an object archive is itself unique evidence, keep that candidate local. |
| Generated-run `anubis-run-cargo-target-audited-crypto-v3/release` | Special review only: verify the current compiler's external `.anubis-build-mutex` protocol and that required program outputs were copied out. The vault acquires that mutex. A new cache tag or changed implementation requires fresh review. A matching name alone does not authorize offload. |
| Whole target, toolchain, source/worktree, unknown cache | Do not automatically retire. Prefer a narrower eligible child; keep unique binaries, evidence, pins and unknown ownership locally. |

`--retain-binaries` requires a flat directory of regular files and retains non-object files as local hard links under `vault-retained-binaries-ITEM_ID`. The old deps path is retired, so record the retained path for agents; do not promise binaries remain at the original path. A retained directory is pinned, and its parent is consequently protected from wholesale eviction.

Register an honest source/toolchain/recipe record before offloading:

```text
project-vault provenance EXACT_DIRECTORY --repository ACTUAL_REPOSITORY --rebuild 'ACTUAL_INVOCATION' --toolchain 'RECORDED_TOOLCHAIN_IDENTITY'
project-vault put EXACT_DIRECTORY --offload
```

These are templates: replace placeholders with observed values. Do not manufacture a successful rebuild claim. Preserve dirty source through a successful covered backup before retiring its outputs.

The queue worker uses ordinary `put --offload`; it does not select `--retain-binaries`. Run the explicit retention command directly for deps that require retained local files. Queue only reviewed candidates appropriate for ordinary offload. Do not bulk-enroll all targets or automatically release pins.

## Finish with evidence and a retrieval route

Check that the item state is `offloaded`, and inspect its `reclaim_verification`, snapshot and `retained_local` record when present. The CLI appends the offload journal; do not invent or duplicate completed receipts. Compare observed free space before/after without attributing all concurrent disk changes to the offload.

Record the exact item ID in the campaign handoff, with `project-vault get ITEM_ID --to NEW_LOCAL_DIRECTORY`. A future agent should restore the actual historical files it needs, then pin its new active lane. Recreated caches need a new full verification cycle before later retirement.

If the iPad disconnects or another vault operation is running, retain local work and report the waiting state. If full candidate recovery cannot fit, reclaim smaller eligible candidates first. Never substitute sampling, delete the original to make restore space, or put live compiler outputs directly on the iPad.
