# Make inactive outputs eligible for offload

Backups preserve originals. Local storage is reclaimed only after an explicitly
selected directory completes DUAT's offload recovery comparison and retirement.
Increasing backup frequency does not make an unsafe directory eligible.

## Select the smallest useful candidate

Establish that the owning build or agent has finished with the output. Check active
processes, working-set pins, source changes and the contents, rather than using age
or a directory name as permission. Keep source, dirty worktrees, compiler/toolchain
pins, unique binaries, test fixtures and proof evidence local when their workflow
requires that. A whole `target` folder can contain all of these.

For an inactive Cargo build, `target/debug/incremental` may be a suitable cache while
the executable, retained libraries and proof records remain elsewhere. The normal
offload path acquires the existing Cargo profile `.cargo-lock` and repeats process
and pin checks. Missing locks, live users, overlaps with pins or changed identities
must be investigated; never clear them to force eligibility.

Flat Cargo `deps` directories need separate inspection. The manual
`put PATH --offload --retain-binaries` route preserves reviewed non-object files in
a pinned local sibling. The queue does **not** carry that option, so do not enroll
a dependency directory expecting automatic binary retention. A parent containing
that pinned sibling must stay local; choose an eligible child instead.

## Preserve source and record real regeneration context

Check that the actual source, including uncommitted changes and shared Git metadata,
is covered by a successful current backup. Keep that source locally too. A commit
hash cannot describe dirty files. Inspect source maps and scope results, and keep
the source snapshot/dirty-state record with the candidate's private working notes.

Record the source repository, current commit, installed toolchain identity and a
real rebuild command. `provenance` records the current source identity and supplied
recipe; it does not discover historical flags or demonstrate a rebuild. Do not fill
missing fields with guesses to make the worker proceed. When a cache has regrown,
preserve its old provenance record, then inspect and register its current context.

The following is only an example for a project whose actual build uses these
paths and flags. Substitute the owning workflow's verified recipe and toolchain:

```bash
project-vault provenance "$HOME/Projects/example/target/debug/incremental" \
  --repository "$HOME/Projects/example" \
  --rebuild "cd '$HOME/Projects/example' && RUSTC=/usr/bin/rustc CARGO_TARGET_DIR='$HOME/Projects/example/target' /usr/bin/cargo build --locked" \
  --toolchain "$(/usr/bin/rustc -Vv)"
project-vault queue "$HOME/Projects/example/target/debug/incremental"
```

This enrollment is authorization for that candidate's verified offload. It is not
proof of reproducibility or an instruction to delete immediately. If source or
toolchain identity cannot be established, leave the directory for review.

## Let the worker verify and retire

With the reviewed tier service and timer configured, the worker processes explicit
entries when scheduling checks permit. It still requires the archive online with
the correct identity, space for a complete local restore plus reserves, the existing
vault lock, and all normal offload checks. It archives the candidate, restores it,
compares content and metadata, checks it again for activity/pin/source changes, and
verifies its quarantined original before removal. No sampling replaces comparison.

Inspect the dashboard, `project-vault items`, the queue record and the dated receipt:

- `queued` or `waiting`: local storage has not been reclaimed by this entry.
- `needs-review`: inspect the reason; a provenance entry alone cannot remove a pin
  conflict, establish inactivity or fix an archive identity problem.
- `done`: read the linked item receipt and its final `offloaded` state before
  reporting retirement. Report actual measured storage, not a promised cache size.

If a valid smaller child replaces an ineligible parent candidate, keep the parent
out of the runnable queue and retain its diagnostic history. Do not enqueue all
held directories just because their provenance fields can be populated.

Background deferral protects observed foreground work and retrievals; it can delay
reclamation. A job starting after the check may still overlap an in-flight transfer,
which finishes normally at low service priority. DUAT cannot promise zero contention
or reclaim bytes while every safe execution window is occupied.

After retirement, the archive may be the only copy of the output. Retrieve to a new
directory with `project-vault get ITEM_ID --to NEW_PATH` before use. Preserve the
archive, recovery credentials and receipt; do not prune them to free local storage.
