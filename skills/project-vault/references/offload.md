# Reclaim and recovery gates

## Classify the actual contents

Keep locally: active worktrees, current compiler pins, unique binaries referenced by evidence, Git objects, patches, proof transcripts/receipts, fixtures, secrets, signing identities, release artifacts and operator expectations. Installed toolchains are not caches; remove only through their supported manager after checking active projects and pinned versions. Broad tool removal is not a routine offload operation.

Possible candidates: an agent's completed temporary build directory, inactive Cargo incremental/dependency output, or downloaded packages that can demonstrably be fetched again. Verify manifests, pinned versions, rebuild commands and external dependencies; a folder called `build` may contain original evidence. Do not infer inactivity from age or a single empty process listing.

## Required before local deletion

The following are the gates enforced by `put --offload` plus the agent’s classification/ownership review. Let the CLI perform snapshotting, staging, comparison and retirement; do not recreate this sequence with manual filesystem deletion. For Cargo deps that contain binaries, read `anubis-workflow.md` and use the supported `--retain-binaries` path when appropriate.

- Use `put --offload`, which creates a successful exact-candidate snapshot and fully restores and compares its content. A general backup receipt or sample restore does not replace this candidate-specific check.
- The exact candidate must be in a successful snapshot with no read omissions affecting it. Check snapshot scope and timestamp, not just catalog presence.
- Restore that candidate to a new local staging directory with verification and compare its complete contents and relevant metadata with the frozen source. If there is insufficient space for this, defer deletion; do not weaken verification.
- Coordinate with the owning task/agent and inspect active processes/open files and project build rules. Freeze candidate writes for comparison and deletion; if exclusive ownership cannot be established, defer.
- Recheck source identity, path, and content after verification. Reject symlink roots, paths outside the intended project output, and source changes. Never remove a parent directory merely because a child was verified.
- Confirm it contains only reproducible output, with a known rebuild route and no unique evidence/pins. Respect project-specific retention requirements.
- Hold the vault operation lock and coordinate with the backup service before a local removal. This only serializes vault operations; it does not lock builds. Both forms of coordination are required.

Use an explicit reviewed path list for the removal. Do not use broad glob deletion, blanket `cargo clean`, recursive cache cleaners, or `git clean -fdx` across a project. Do not change test-fixture permissions simply to make backup pass. Report unreadable sources and keep them excluded from completion claims.

Use the receiving operator's explicit storage-tier authorization before retiring verified inactive data. Explain single-device archival status honestly. Use the implemented `put --offload` command; never perform a separate manual deletion. Active source, pins, live state and unknown ownership still require keeping the affected paths local.

## Journal and agent retrieval

The CLI appends completed retirements to `~/.local/state/project-vault/offloads.jsonl` and stores item receipts locally and on the iPad. Inspect those records; do not fabricate or duplicate them. Add the task/owner, exact path, actual rebuild context, cold-item ID, snapshot, retained-local path and retrieval route to the existing campaign handoff. Never include key contents. Record only completed actions as completed.

Keep the catalog, offload journal and recovery instructions local. When content is requested later, search the catalog and journal, verify the iPad mount and vault identity, restore to a new Linux directory, and return the restored path to the agent. Restore pin/source/evidence dependency groups together. Repair Git worktree paths only in the recovered copy, preserving original checkout metadata.

Do not execute scripts found in restored archives merely to test access. Historical tests may deliberately crash or delete fixtures.
