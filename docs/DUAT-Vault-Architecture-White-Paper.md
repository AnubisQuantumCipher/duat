# DUAT Vault

## Verified Project Storage and Recovery

**Architecture white paper and operator handbook**  
Public architecture edition · Implementation: `project-vault` · Backup engine: **restic**

> **The operating principle:** keep the active engineering working set on Linux; preserve versioned history on the iPad; retire an eligible local directory only after restoring its complete archived contents and comparing them with the source.

## Abstract

DUAT Vault provides versioned project backup, explicit verified offload, and recovery for Linux using an iPad application-sharing archive. The executable is named `project-vault`.

The system combines restic snapshots, ifuse transport, a compact local catalog, persistent offload and retrieval queues, protective pins, provenance records, and a loopback dashboard. Ordinary backups preserve versions without deleting working files. Explicit offloads archive an eligible directory, restore its complete contents into local scratch, compare content and metadata, and then retire the original through a guarded quarantine procedure.

This publication describes the source implementation and its operating boundaries. It contains no deployment inventory or production recovery receipts. A successful fixture test does not establish recovery for a reader's archive. After offload, the iPad may be the sole archive copy; a separate independent archive is needed to withstand its loss.

## Reading guide and evidence rules

Read **The daily operating model** for routine use, **Verified offloading** for retirement safeguards, and **Recovery procedures** before restoring data.

Paths and commands are examples or implementation defaults. Replace placeholders with configuration appropriate to your installation. No example item or snapshot identifier refers to a real archive. This publication omits personal account information, hardware inventory, storage measurements, operational history, and production identifiers.

A receipt is a record of an operation. Its scope and method bound the claim it supports. Metadata checking, full repository data reading, candidate restore comparison, whole-scope file restoration, and application recovery are different tests. Historical success never substitutes for a current check.

Agent notes provide continuity but are not primary recovery evidence. External documentation describes upstream behavior and does not certify this wrapper.

## The problem the system solves

Anubis development produces more than source code. Compiler builds, isolated Cargo targets, incremental state, temporary worktrees, pinned toolchains, proof outputs, test artifacts, and agent campaigns all consume storage. Isolation can be justified: competing agents should not corrupt one another’s outputs, and a claim may depend on a particular binary or proof receipt. However, an abandoned target directory can remain large long after its campaign ends.

A backup does not inherently solve that growth. If Linux retains all original outputs while restic stores another version on the iPad, Linux remains occupied. Backup alone does not reduce the local working set. Something must make an explicit decision about the local working set and safely remove eligible originals.

Conversely, deleting every directory named `target` or `.cache` would be unsound. A cache can contain the only surviving historical executable, a pin used to reproduce a claim, a unique receipt, or an active compiler’s work. DUAT therefore treats names as discovery hints and requires classification of the exact candidate.

An iPad with sufficient free space can serve as an archive endpoint. Its practical role is an archive endpoint reached through application file sharing. Active Linux tools and source remain on the Linux filesystem, where their execution and filesystem assumptions hold. Retrieval is explicit: an agent locates an archived item, restores it locally, and resumes work from the recovered directory.

## The daily operating model

### While working

Keep source repositories, active worktrees, current compiler pins, unique binaries, identities, proof receipts, and the evidence needed to reproduce claims on Linux. Pin active output lanes before long builds. Record where a campaign writes temporary data. Run the storage status helper before initiating a large new workload.

Hourly scheduled backups preserve configured project scopes. They add or reuse versioned restic content; they do not automatically remove the working files. A successful Anubis scope is not a blanket success for every project.

### When a campaign finishes

Identify the exact inactive output directory. Confirm that its source, toolchain identity, and regeneration route are retained. Prefer a verified incremental-cache child when its parent also contains binaries or evidence that must stay local. Enroll the reviewed directory or invoke `put --offload` directly. The candidate-specific recovery comparison happens before local removal.

A normal successful offload leaves a local item record and a small sibling receipt, plus recovery metadata on the iPad. The original directory is absent. Linux free-space readings are recorded around the operation, with concurrent-workload limitations stated.

### When an agent needs something again

Search the compact catalog or cold-item inventory. With the iPad available, retrieve the item by ID into a new local destination. An existing path is protected from overwrite. If a compiler has recreated the original cache, restore the older archive elsewhere. A previous receipt never authorizes deleting newly generated contents at the same path.

### When disconnected

Local source remains usable. Local records can still reveal what was archived and where it belonged. Archive bytes cannot be retrieved until the bridge and iPad mount return. The system does not transparently page missing files across the cable, and a symlink is not a substitute for recovery.

## Goals, scope, and boundaries

| Concern | Implemented approach | Boundary |
|---|---|---|
| Versioned project history | Tagged restic snapshots and source maps | Configured scope, not the entire machine |
| Linux storage reclamation | Explicit full-compare directory offload | Reviewed candidates only |
| Agent discoverability | Local catalog, receipts, CLI, skill, dashboard | Compact catalog omits deep entries |
| Recovery | Snapshot restore and manifest-checked cold retrieval | Requires iPad, credential, and local space |
| Activity protection | Pins, process inspection, Cargo lock where applicable | Cooperative workflow still required |
| Interrupted work | Persistent jobs, queue states, removal-intent receipts | No universal transactional rollback |
| Data health | Metadata checks, scheduled full scrub, restore drill | Last receipt and scope govern each claim |
| Retention | Keep snapshots; pruning disabled | Storage growth still needs management |
| Disaster resilience | Archive and recovery material on iPad | No independent archive destination |

DUAT is not a raw iPad disk driver, a bootable Linux image, an application-consistent backup of every database, an immutable remote vault, a hostile-user security boundary, or an automatic filesystem tier that makes arbitrary absent paths readable on demand. These boundaries determine which engineering tasks it can safely support.

## Physical and transport architecture

The archive is accessed through an iPad application's file-sharing interface. Linux uses ifuse to expose that application directory as a filesystem. Restic operates on the configured repository below the mount.

```text
Linux working set
  -> project-vault / restic
  -> configured ifuse mount
  -> paired iPad application file sharing
  -> archive repository and recovery records
```

A Linux virtual machine may access a host's USB multiplexing service through an SSH Unix-socket bridge. Configure host, user, port, socket path, pairing, and reconnect behavior for the actual environment. The bridge and mount supervisor are external infrastructure, not installed by this repository.

The mount must be a functioning ifuse mount with the expected vault marker. A directory with the expected name is insufficient: the destination guard refuses access when the mount or identity check fails. Pairing, device unlock state, application access, and transport availability can each prevent access.

ifuse supports application Documents sharing through its `--documents` option. This is application-scoped access rather than a raw iPad disk export. See [ifuse documentation](https://github.com/libimobiledevice/ifuse).

### Performance boundaries

No device specification or transfer benchmark is published here. Cable capability alone does not determine throughput across SSH, usbmuxd, file sharing, FUSE, hashing, encryption, and local restore writes. Measure sequential transfer, metadata-heavy operations, backup, full readback, and full candidate recovery separately in the intended environment.

## Logical architecture

```text
                              OWNER / AGENTS
                                    |
             +----------------------+--------------------+
             |                      |                    |
        project-vault CLI      browser dashboard    agent skill / notes
             |                      |                    |
             +---------- explicit requests -------------+
                                    |
             +----------------------+--------------------+
             |                      |                    |
       scope scheduler        cold-item engine      retrieval worker
       versioned backup       verify / retire       recover / publish
             |                      |                    |
             +----------- shared operation lock --------+
                                    |
                               restic engine
                                    |
                         iPad TryOmarchy/Repository
                                    |
                          encrypted archive content

LOCAL CONTROL RECORDS                       IPAD RECOVERY RECORDS
catalog.sqlite                              Recovery/items/*.json
items, queue, pins, requests                 source maps / configuration
provenance, operation state                  check and reclaim receipts
password file                               recovery password / Tools
```

The data plane is restic reading source files and writing or reading repository data. The control plane is the Python wrapper, its queues and locks, systemd schedules, and UI. The recovery plane is the metadata that connects an original path to a snapshot, manifest, item ID, and retrieval procedure.

Separating these concerns matters. Losing the local catalog should not be equivalent to losing the archive. Conversely, a catalog entry by itself does not contain the archived bytes. A timer expresses an intention to run; it does not establish that data was saved. A recovery receipt connects an operation to its result, but must still be interpreted with its time and verification method.

## Storage layout

| Location | Purpose |
|---|---|
| `~/Projects/duat/` | Python implementation, dashboard, tests, operational documentation |
| `~/.local/bin/project-vault` | CLI entry point |
| `~/.config/project-vault/config.json` | Mount, repository root, source selection, reserve and policy configuration |
| `~/.local/state/project-vault/` | Local catalog, queues, receipts, journals, caches, recovery scratch, credential |
| `~/.config/systemd/user/project-vault-*` | Backup, offload, retrieval, dashboard, scrub and drill units |
| `~/.codex/skills/project-vault/` | Agent-facing storage workflow and helper scripts |
| `~/iPad/TryOmarchy/Repository/` | restic repository |
| `~/iPad/TryOmarchy/Recovery/` | Recovery records, configuration, source maps, tools and credential |
| `~/iPad/TryOmarchy/Archives/` | Legacy archive material from earlier transfer work |
| `~/Documents/DUAT-Vault-Architecture-White-Paper.md` | Editable source of this paper |
| `~/Documents/DUAT-Vault-Architecture-White-Paper.html` | Standalone reading and printing edition |

Files in `Repository` are managed by restic. They are not a human-browsable mirror of project directories. The Documents app may show repository folders and packs instead of familiar source trees. Use `find`, `items`, and recovery commands to locate and recover content. Never rearrange or selectively delete repository packs in the iPad’s file interface.

The local SQLite catalog contains snapshot metadata, selected file paths, and events. Separate JSON records preserve cold-item identity and operation states. The state directory also holds the restic cache and temporary verification trees, which can themselves consume Linux storage.

## Backup engine and source coverage

The backup engine is restic. Confirm compatibility with the commands used by the implementation before deployment.

Restic supplies encrypted, deduplicated snapshot storage. DUAT supplies source selection, coordination, verification policy, retirement, and user-facing records around it. Snapshot identities are important recovery addresses. The wrapper retains explicit IDs rather than relying exclusively on a global “latest.” Upstream restic documents snapshot inspection, grouping, and repository operations. [restic repository documentation](https://restic.readthedocs.io/en/stable/045_working_with_repos.html)

### How the source set is formed

The example configuration names `~/Projects` and `~/Work` as project roots; additional paths are operator-selected. Source discovery resolves relevant targets, discovers registered Git worktrees and common Git metadata, removes redundant nested source roots, and records the mapping between intended inputs and stored paths.

This is important for linked worktrees. Saving the visible checkout without its shared Git metadata may leave an incomplete development environment. It is also important for installed launchers that resolve to actual executable locations. Discovery is not a promise to back up every linked payload in every custom application; inspect the source map for the particular snapshot.

An application-specific configuration can cover source, external worktrees, configuration, installed tools, and state. Missing configured paths are skipped. A missing path that was deliberately offloaded is different from an accidentally missing source; its cold receipt is the recovery address.

The wrapper does not apply a blanket build-output exclusion. That choice preserves data broadly but can make scope snapshots large. Reviewed offloading and working-set management are still necessary.

### What coverage does not establish

The configured roots do not make this a whole-home or whole-operating-system image. Arbitrary folders added elsewhere are not automatically protected. Add documents to `additional_paths` explicitly if they need coverage; recovery-kit export also looks for the named architecture papers in Documents. Other Documents files are not automatically covered; placement in Documents alone is insufficient.

Backing up application source does not establish consistent recovery of its live databases. Use application-native continuity procedures for those stores.

Active source can change during an ordinary backup. A resulting filesystem snapshot is not necessarily an atomic application transaction or a simultaneously frozen dependency group. For a reproducibility claim, record the exact snapshot, commit, toolchain, relevant artifacts, and verification procedure; coordinate a quiet checkpoint where the application requires it.

## Versioned backup lifecycle

An ordinary backup checks destination availability and identity, acquires the local operation lock, discovers sources, checks the iPad reserve, and invokes restic. The backup command uses scope tags, `--skip-if-unchanged`, and grouping by `host,paths,tags`. It then performs a repository metadata check and refreshes the local catalog. Source maps are saved locally and into recovery storage.

Including tags in grouping fixes a concrete issue discovered during operation: identical roots under different scopes could otherwise reuse an unchanged comparison group without yielding a snapshot belonging to the expected new scope. The wrapper now also rejects the absence of a matching snapshot with a clear error instead of treating a missing ID as valid.

The scheduled runner processes Anubis as its extended scope, then separate project scopes and Work. Each scope has an independent health entry. An unreadable source can make one scope incomplete while unrelated scopes continue. Busy, disconnected, or repository-lock conditions defer work. Previous successful snapshot references are retained where available.

A `passed` scope health record says that a snapshot was saved and repository metadata checked. It is not equivalent to reading every stored byte or restoring the entire project. The scheduler may exit without every scope becoming current; inspect scope records and timestamps rather than relying only on service exit state.

## Verified offloading

Verified offloading is the defining storage-reclamation operation. `project-vault put PATH` archives and fully compares a candidate while retaining its source. Adding `--offload` permits the guarded local retirement after comparison succeeds.

### Eligibility and admission

A candidate must be an existing real directory strictly below Projects, Work, or `.cache`. Symlink roots or path components are refused. Repository/worktree roots and nested Git metadata are refused. Special filesystem objects are rejected by inventory. Pins protect both descendants and ancestors through overlap checks, so an agent cannot evade a pinned child by selecting its parent.

Activity inspection checks relevant processes’ working directories, executables, file descriptors, and mapped files through a read-only privileged process scan. If the scan cannot safely inspect a relevant live process, the operation refuses. For an exact `debug/incremental` or `release/incremental` candidate, the implementation also acquires the existing Cargo profile lock. A missing or symlinked lock file is not treated as permission to proceed.

CLI pin edits now share `pins.lock` with the final validation, quarantine, and deletion window. A pin accepted before final retirement is observed there; a request arriving after the window begins waits and cannot undo a completed offload. Concurrent pin edits no longer lose each other’s updates. Direct manual JSON edits bypass this protocol. These mechanisms reduce races. They do not make arbitrary concurrent writers safe. Agents must still coordinate ownership and pin active lanes. The privileged scan executes local Python code; the overall design assumes trusted local code and agents, not an adversarial user modifying that code.

Local free space must accommodate the complete verification restore plus the configured/default working reserve. Local and archive reserves come from configuration, with a local fallback in the implementation. The admission estimate uses logical file sizes rather than an optimistic assumption about deduplication savings. A very large directory can therefore be ineligible even when storing its new archive blocks would be cheap.

### The manifest

The candidate inventory records regular-file contents with SHA-256, sizes, file modification timestamps, permission modes, owners, groups, extended attributes, directory entries including empty directories, and symbolic-link targets. It checks whether a file’s identity, size, or timestamps changed while hashing. A digest of the full manifest is retained with the cold-item receipt.

The comparison does not establish every conceivable filesystem property. Hardlink topology, sparse allocation layout, access/change timestamps as restored properties, and directory modification times are not covered by the manifest in the same way as regular-file bytes. The term “full comparison” means the entire candidate is compared under this implemented inventory schema. It does not imply a bitwise image of the source filesystem.

### Transfer and verification sequence

```text
review exact candidate + retained provenance
                 |
validate path / pins / activity / Cargo guard / free space
                 |
record complete source manifest
                 |
create uniquely tagged restic cold snapshot
                 |
restore entire candidate into local verification scratch
                 |
compare restored inventory AND current source to manifest
                 |
confirm mount identity; persist local + iPad receipt; read back
                 |
     put only: retain original and finish
                 |
     --offload: recheck activity and pins
                 |
persist removal intent -> no-replace rename to quarantine
                 |
recheck quarantine manifest / activity / recreated source / mount
                 |
remove exact quarantine -> record completion and reclamation
```

The snapshot receives a `cold-<item-id>` tag, and the implementation requires the expected tagged snapshot rather than guessing a global latest snapshot. A job directory tied to the source path preserves information about an interrupted transfer. When the recorded source manifest still matches, an interrupted verification restore can reuse its snapshot and partial scratch tree. Changed inputs require a new candidate identity.

The recovery restore uses restic verification and sparse restoration. The wrapper independently inventories the recovered directory and compares it with the original inventory. It also inventories the current source again, rejecting changes that occurred after initial inspection. Upstream restic describes verified restoration and recovery into a selected target; the manifest comparison is additional local implementation behavior. [restic restore documentation](https://restic.readthedocs.io/en/stable/050_restore.html)

Before local retirement, recovery receipts are written locally and to the iPad, and the remote JSON is read back for equality. The mount’s identity is checked again. These are useful observable gates; they are not a guarantee about the iPad’s physical flash durability under every possible power failure.

### Quarantine and crash boundaries

A removal-intent record identifies the original and the proposed quarantine before the source is renamed. Linux `renameat2` with no-replace semantics prevents accidental replacement of an existing quarantine destination. The renamed directory remains on the same local filesystem while the wrapper performs its final comparison and activity checks.

If a failure occurs before deletion begins, the implementation can attempt to return the quarantine to the original name. Once recursive deletion begins, a failure may leave a partial quarantine and a recovery-required record. It would be incorrect to say every possible failure leaves the original intact. The verified archive is the recovery source in that state. Preserve the remaining quarantine until a complete restoration has been recovered and checked into a separate path.

JSON updates now use a uniquely named temporary sibling file, file flush and fsync, replacement, and parent-directory fsync where supported. Unique names prevent concurrent writers from colliding over one temporary filename. App/FUSE filesystems can reject directory fsync as unsupported; the implementation tolerates only those specific unsupported-operation errors and surfaces other I/O errors. These updates do not make the collection of records, renames, and deletions one transaction, or prove iPad flash durability after sudden power loss.

### What counts as reclaimed

A final offload receipt records the item ID, source path, snapshot and tag, manifest digest, provenance, state, and free-space samples. The current implementation also records checks for absence of the original, quarantine, and generated verification scratch, plus a free-space comparison indicator. Earlier receipts may predate some fields.

Path retirement and global free-space change answer different questions. Another build can consume space while an offload frees it. Sparse files, open deleted files, and unrelated writes can also affect observed disk usage. The sampled filesystem delta is useful operational evidence, but is not a precise attribution of every byte to the candidate. Do not equate logical source size with guaranteed physical reclamation.

## Retrieval and ordinary snapshot recovery

Cold-item retrieval uses `project-vault get ITEM_ID` or an original path recorded in the item index. An explicit ID is preferable when several historical versions share a path. With `--to`, the destination must be new. The cold retrieval path checks local capacity, restores the snapshot into temporary local storage, inventories the recovered candidate, compares the manifest digest with the item receipt, and publishes the recovered directory using a no-replace rename.

Restoring to the original path records a restored-local state. Restoring elsewhere records where and when that happened without pretending the original path is now present. A returned item is not automatically re-enrolled for eviction. Its next lifecycle decision belongs to the active workflow.

Ordinary `project-vault restore SNAPSHOT PATH --to NEW_DIRECTORY` supports recovery of a selected path from versioned snapshots. It validates membership, refuses an existing destination, escapes literal path matching, and uses restic’s restore verification. The original absolute hierarchy appears below the new destination. This command does not use the cold candidate’s full manifest gate. Do not describe these restore modes as identical.

A missing local catalog hit is not evidence that a file was never backed up. Use an online full metadata search and the actual source maps. If recovery reports a mismatch, preserve the error and receipt records for diagnosis; do not waive the comparison merely because the filename looks correct. The cold retrieval helper uses temporary storage that is cleaned on failure, so retaining failed restored bytes requires a separately planned diagnostic procedure.

## Catalog, provenance, and agent memory

### Compact local catalog

The first broad file catalog grew enough to become a storage problem of its own. The compact design now bounds indexed rows and avoids descending into deep output-heavy path categories for indexing purposes. The implementation caps total file rows at `100000`, scope rows at `10000`, and indexed path depth at `9`; it omits descendants of target-style build directories, `.git`, `node_modules`, incremental state, fingerprints, and dependency directories from the compact working view.

This is a storage bound, not necessarily a traversal-time bound: the restic listing may still be traversed. Snapshot metadata and cold-item receipts remain separate.

Offline search is fast and intentionally incomplete. Search hits carry their own snapshot identities. Online `find` asks restic for complete filename metadata. A global latest snapshot can belong to another project, so use the snapshot associated with the desired hit or scope.

### Provenance records

Provenance associates a candidate with a source repository, current commit, dirty status, a declared rebuild command, and a toolchain identity. Reviewed incremental-cache records also retained dependency-file evidence and its digest.

A current clean checkout and plausible regeneration route do not prove the exact historical compiler invocation that produced old bytes. The records explicitly preserve that distinction. The archive retains the original bytes; the recipe gives a route for future regeneration. Rebuilding and retrieving are different operations, especially where a proof claim cites a historical executable.

### Agent skills and notes

The project-vault skill tells agents to check space before heavy work, classify candidates, honor pins, use verified offload, and search or retrieve archived dependencies. Agent notes point successors to the procedure and durable evidence locations. Neither replaces the receipts, manifests, or repository.

Memory notes must not contain credentials. An agent should report whether it actually restored an artifact, merely found a catalog entry, or only recalled a note. These distinctions prevent a confident narrative from being mistaken for recovered evidence.

## Concurrency, scheduling, and recovery coordination

| Mechanism | Responsibility |
|---|---|
| `operation.lock` | Serializes cooperating repository operations on Linux |
| `scheduler.lock` | Prevents overlapping scheduled backup runners |
| `tier-queue.lock` | Prevents overlapping offload workers |
| `queue-edit.lock` | Serializes short persistent queue edits |
| `pins.lock` | Serializes CLI pin edits with final local retirement |
| `requests.lock` | Prevents overlapping retrieval workers |
| Cargo `.cargo-lock` | Coordinates supported incremental-cache candidates with Cargo |
| restic repository locks | Repository-level concurrency coordination |

Queue enrollment captures path identity, including device and inode. A reused pathname whose identity changed needs review. Active duplicate requests are avoided. Cancellation refuses to pretend an already running task was stopped. The offload worker retries explicit reviewed entries; it does not discover arbitrary directories and delete them according to age.

A pause takes effect after the current directory completes. Retrieval requests can receive priority between offload items. Busy storage, lost connectivity, activity, inadequate reserve, or recognized repository-lock contention lead to waiting where handled. Unexpected verification failures require review rather than silent deletion.

Stale-lock recovery is conservative. While holding the local operation lock, the scheduler reads repository lock metadata. Only a lock belonging to this hostname with a valid process ID established absent is considered for ordinary restic unlock. Live, foreign, unknown, or uninspectable owners are retained. The implementation never uses a blanket `unlock --remove-all` in this recovery path. Hostname/PID checks are practical coordination, not a distributed proof against every process-identity race.

### Example schedule definitions

| Unit | Schedule or lifecycle | Work |
|---|---|---|
| `ipad-storage.service` | Persistent supervisor; restart policy | Maintain project iPad mount |
| `project-vault-dashboard.service` | Persistent local service | Serve dashboard |
| `project-vault-backup.timer` | Hourly, persistent | Versioned per-scope backups |
| `project-vault-tier.timer` | Boot delay `2min`; inactive interval `10min` | Drain reviewed offload queue |
| `project-vault-requests.timer` | Boot delay `1min`; inactive interval `1min` | Process queued retrievals |
| `project-vault-scrub.timer` | Sunday `04:00`, persistent | Full repository data check |
| `project-vault-drill.timer` | Monthly on day `1`, `05:00`, persistent | Whole Anubis recovery drill |
| `project-vault-verify-now.service` | Explicitly started helper | Scrub followed by drill |

Calendar schedules use the deployment’s systemd calendar context. Timer definitions express scheduling intent. Check enablement, service state, journals, and receipt times to determine whether a particular run occurred. Several workers use low CPU/I/O priority and restrictive umasks. Those settings reduce contention; they do not eliminate the cost of hashing and recovery writes.

## Dashboard and local security model

The Project Vault dashboard is served at `http://127.0.0.1:8767`. Its read model summarizes local capacity, connectivity, project health, operation phases, cold items, pins, queue states, and retrieval jobs. It reads existing records rather than recursively walking the archive merely to render the page.

State-changing requests require an allowed Host value, a matching local Origin, and a per-process action token. Request size is bounded at `8192` bytes. Actions are a fixed set, and subprocess invocation uses argument arrays rather than arbitrary shell text. Response headers discourage caching and framing; rendered text is escaped.

The dashboard is a local control surface. It is not deployed as an authenticated public web service, and its local token is not a security boundary against another process running as the same user. Do not expose the port to a network without a separate security design. A connected badge establishes the presence of the expected mount type, which is weaker than a successful marker check and much weaker than a verified archive restore.

Operation phases and process I/O counters help distinguish backup, catalog, restore, and comparison work. They are not reliable completion-time estimates. An old running record whose owner is gone is surfaced as interrupted; the persisted timestamp remains important.

## DUAT Bench and Live Metrics

DUAT Bench is an explicit synthetic workload runner accessed through `project-vault bench`
or the dashboard's **Bench & live metrics** page. Each run owns a generated local
source, a dedicated archive directory, a fresh encrypted test repository, separate
credentials and cache, and a new restore destination. It uses the existing vault lock
and refuses offline, busy, or insufficient-capacity conditions. Benchmarks never retire
production sources or prune production snapshots; synthetic artifacts are retained too.

The phase timeline separates source generation, filesystem payload write, host sync
acknowledgement, payload readback comparison, isolated repository initialization,
encrypted backup, full encrypted repository data reading, verified restoration, and
complete manifest comparison of restored files and the retained source. The measured
round-trip clock begins after generation and ends only when every recovery gate passes.
An upload alone is never labeled verified recovery.

Live and sustained rates are labeled by their byte counter. Complete peak windows retain
actual start/end times; short phases have unavailable peaks. Restic logical progress and
packed added data are distinct from filesystem payload and physical wire traffic.
Batched backend live rates are estimated. Device-committed-object throughput and negotiated
link speed remain unavailable when the backend exposes no authoritative counters.
No cable label supplies a speed measurement.

The dashboard distinguishes measured, estimated, unavailable, and historical values.
It shows free space, retained scratch usage, wrapper retries, unavailable backend-internal
retries, host load, available memory, and thermal readings where exposed. Cache state is
uncontrolled and reported. A local fixture result is explicitly identified as a fixture.

Exports include a standalone shareable HTML result card, complete timestamped raw CSV
samples, and a JSON report with workload recipe, synthetic manifest, phase measurements,
software identity, integrity results and sample digest. Public exports omit local paths,
credentials and production identifiers. Operating measurements remain part of the requested
report and should be reviewed before sharing. See the repository's `docs/BENCH.md` for
reproduction commands, counter definitions, and reserve/cancellation boundaries.

## Verification hierarchy

| Observation | What it establishes | What it does not establish |
|---|---|---|
| Cable connected / Finder sees iPad | Physical recognition and device discovery in that context | Working Linux repository |
| Mount present | Filesystem mounted at expected path/type | Correct marker, healthy archive, durable latest writes |
| Vault identity accepted | Configured destination marker matches | Protection against malicious same-user replacement |
| Snapshot saved | Backup produced a snapshot for the operation | All scopes complete or all files readable in partial cases |
| Metadata check passed | Repository structural checks passed at that time | Every data byte read |
| `check --read-data` passed | Repository data read/check succeeded at that time | Application recovery or protection of later writes |
| Sample file restored | That selected recovery path worked | Recovery of unrelated output directories |
| Cold candidate full comparison | Entire candidate matched its recorded inventory schema | Whole-machine or application-consistent recovery |
| Whole-scope drill passed | Entire selected snapshot recovered under drill procedure | Independent copy, bootability, or native database consistency |

Restic distinguishes structural checking from full data reading with `check --read-data`. That distinction is why the scrub receipt names its method. [restic checking documentation](https://restic.readthedocs.io/en/stable/045_working_with_repos.html)

The current drill restores the files present in its selected scope snapshot. Directories removed by earlier offloads can be absent from that later snapshot while remaining recoverable through separate cold-item snapshots. The drill does not automatically enumerate and retrieve every historical cold item. A successful future run would therefore establish recovery of that selected snapshot, not reconstruction of every previously archived campaign.

The whole-scope drill deliberately refuses to replace a full recovery with a token sample when space is insufficient. This is a valuable failure mode: it leaves the broad recovery claim unproven rather than issuing a misleading success.

## Capacity management and performance economics

Archive capacity and Linux working capacity serve different purposes. The iPad can hold retained history while Linux supplies active builds and recovery scratch. Available iPad space does not remove the need for local restoration space. A full candidate must fit locally long enough to prove recovery before its source is retired.

Large candidates should be reviewed at meaningful subdirectory boundaries. Incremental caches can be suitable when separately reproducible, inactive, and covered by the existing Cargo guard. Arbitrary splitting of a dependency group may make recovery harder; preserve its source, toolchain, and evidence relationships in the handoff.

Space can decline after successful offloading because builds regenerate caches, new toolchains are installed, logs and caches grow, source scope expands, and verification temporarily duplicates candidate bytes. The local restic cache and catalog also consume space. A lingering verification directory should be investigated through its owning job and process state; its name alone does not authorize deletion.

The policy avoids automatic snapshot pruning. Consequently, historical versions and uniquely tagged cold snapshots can accumulate even when Linux is well managed. Restic deduplication helps when content repeats, but it does not create unlimited capacity. Compression and deduplication ratios are workload-dependent, and this paper assigns no guaranteed ratio.

A future retention policy must protect every snapshot referenced by a cold-item receipt. An offloaded item may depend on that snapshot as its only surviving copy. A generic age-based expiration policy can therefore destroy retrievability even while the local catalog continues to list the item. Plan retention from reachability by recovery records, then review the proposed changes and verify recoverability before deletion.

## Failure model and response

| Failure | Expected behavior or risk | Operator response |
|---|---|---|
| iPad disconnected or locked | Repository access fails or waits | Reconnect, unlock, keep Mac awake; allow supervisor recovery |
| Mount directory exists without real mount | Destination checks should refuse | Verify actual mount type and marker; never copy into fallback directory |
| Wrong vault identity | Operation refuses | Resolve destination mismatch; do not rewrite marker to force acceptance |
| Source changes during comparison | Candidate offload refuses | Coordinate quiet ownership; create a new verified attempt |
| Candidate actively used | Inspection or Cargo guard refuses | Leave local; retry after owning job finishes |
| Pin overlaps candidate | Offload refuses | Review ownership; do not bypass pin |
| Insufficient local recovery space | Admission or drill waits/refuses | Choose smaller eligible candidate or provide recovery capacity |
| Repository lock contention | Defer; conservative stale-lock review | Inspect owner; never indiscriminately force unlock |
| Crash during verification | Job/scratch may remain | Inspect records; resume only with matching candidate state |
| Crash during removal | Partial quarantine possible | Restore verified snapshot elsewhere before cleanup |
| Local catalog lost | Offline discovery impaired | Recover receipt copies and rebuild catalog from repository |
| iPad lost, reset, or Documents deleted | Sole offloaded archives can be lost | Independent archive required to survive this event |
| Credential lost everywhere | Encrypted repository may be unrecoverable | Recover from separately retained credential if available |
| All iPad files accessed by another party | Adjacent recovery credential enables decryption | Treat complete app-folder access as sensitive |
| Live database copied without coordination | Files may not constitute consistent application state | Use native application backup/continuity procedure |

No automatic checksum can recover bytes when the sole physical device containing them is destroyed. Integrity verification and redundancy address different risks. DUAT prioritizes retaining unique active material locally and offloading reproducible inactive outputs first.

## Recovery procedures

### Routine inspection

```bash
project-vault status
project-vault items
project-vault list
python3 /home/USER/.codex/skills/project-vault/scripts/storage_status.py
systemctl --user status project-vault-backup.service
journalctl --user -u project-vault-backup.service -n 80 --no-pager
```

Run user-service commands in the appropriate user session with its actual runtime directory and session bus. Check receipt timestamps and individual project states. Avoid running another repository operation while one is active.

### Find and recover an archived item

```bash
project-vault find example-output
project-vault items

# Replace ITEM_ID with a result from your own vault; use a new destination.
project-vault get ITEM_ID \
  --to /home/USER/Work/recovered-output
```

If that recovery directory already exists, choose another new destination after inspecting it; do not erase it just to make the command pass. Retrieval verifies the archive against the item’s manifest. Record where recovered content was published so later agents can locate it.

### Recover a selected path from a versioned snapshot

```bash
project-vault find '*Cargo.toml*' --online
project-vault restore SNAPSHOT_ID /absolute/original/path \
  --to /home/USER/Work/recovery-inspection
```

`SNAPSHOT_ID` and the path are placeholders to replace with a matching actual result. The recovered original hierarchy appears below `recovery-inspection`. Use explicit scope-matching IDs; do not assume the repository’s latest snapshot belongs to Anubis.

### Archive a completed reproducible output

```bash
# Example paths: substitute a real reviewed, inactive candidate and its owner.
project-vault provenance /home/USER/.cache/example-output \
  --repository /home/USER/Projects/example \
  --rebuild 'the actual retained regeneration command' \
  --toolchain 'the observed compiler and toolchain identity'

project-vault put /home/USER/.cache/example-output --offload
```

The example is a template, not evidence that `example-output` is disposable. The direct CLI still requires an operator or agent to classify the directory correctly. Use `project-vault queue PATH` for reviewed background processing. Record the returned item ID and snapshot in the campaign handoff.

### Protect an active lane

```bash
project-vault pin /home/USER/Work/current-campaign
# Only after its owner confirms completion:
project-vault unpin /home/USER/Work/current-campaign
```

Do not unpin the active round2 lane merely to create room. A parent cannot be retired on the strength of a receipt for one child. A regrown cache requires a new full verification attempt.

### Check repository data

```bash
project-vault check
project-vault check --full
```

The first command checks metadata; the second reads repository data as well. Both require connectivity and serialized repository access. They can take substantial time. A passing full check does not substitute for an application recovery test. Scheduled scrub and drill receipts are separate from arbitrary manual checks and should be interpreted by their actual method and timestamp.

### Recover after an interrupted offload

Inspect the item receipt, cold job state, operation record, and quarantine path. Establish whether deletion began. Do not delete a remaining quarantine or manually change a state to `offloaded`. Find the exact snapshot and restore it to a new directory with the recorded cold-item retrieval procedure. Validate the recovered content before deciding what remnants can be removed. Preserve logs when verification fails.

If the local item record is absent but an iPad Recovery copy exists, recover that metadata before using the wrapper. Treat metadata reconstruction as a controlled repair, with the original records preserved. The current product does not expose a universal one-command reconciliation wizard for every crash boundary.

### Recover after Linux loss

The intended recovery assets are the intact iPad repository, its recovery password, configuration, source maps, item receipts, and the versioned kit selected by `Recovery/latest-kit.json`. Consult `Tools/RECOVERY-BOOTSTRAP.md` in that kit for the staged recovery procedure. This scenario is an operational recovery plan, not a production drill that has already passed.

Before using a copied kit, run `python3 /path/to/kit/Tools/verify_kit.py /path/to/kit` with a trusted Python installation and inspect the result. This checks its contents against the bundled manifest; it does not independently authenticate the checker or manifest.

On a replacement Linux environment, first establish trusted device access and mount the same Documents app storage. Preserve the repository before changing it. Obtain the correct restic credential privately from the retained recovery material; never paste it into a chat, command argument, or log. Inspect snapshots with restic and restore the vault implementation and required source to a new local location. Recover local configuration and item records from their iPad copies, adjusting machine-specific paths only through a reviewed migration.

The credential must match the existing repository. Do not initialize a new empty repository over the old location to silence a missing-password error. The wrapper intentionally refuses an existing repository when its expected local password is missing.

After enough local capacity is available, perform structural checking, full data checking, and a complete dependency-group restore. Re-establish compiler pins and application-specific continuity separately. Recovering files does not reinstall every package, restore a bootloader, or prove that a live database is consistent.

### Define a complete engineering recovery group

For a particular Anubis campaign, create an explicit recovery manifest before claiming it is reproducible. Identify the source scope snapshot and commit, dirty-source preservation if applicable, required compiler pins, historical binaries, proof receipts, tool configuration, and every cold-item ID referenced by that campaign. A later ordinary snapshot can omit already offloaded directories, so its file list alone is not that manifest.

Recover the selected source snapshot and the required cold items into new local locations. Check the cold manifests through `get`; then follow the owning project's documented verification procedure for toolchain identity, evidence validity, dependency paths, and any reproducibility claim. Merely running a newly rebuilt compiler is not a substitute for recovering a historically cited binary. Application-native database recovery remains separate.

Acceptance should name the recovered snapshot and item IDs, the actual verification commands and results, unresolved dependencies, and the new paths. Record whether the test recovered files only, successfully ran the intended tools, or reproduced the specific claim. This group-level acceptance procedure is a recommended operating discipline; the current monthly drill does not automate this complete campaign reconstruction.

### Recover after iPad loss

Files still present on Linux remain available. A deliberately offloaded original may exist only in the lost iPad repository. Without an independent archive endpoint, those bytes cannot be recovered from another copy. Regeneration may be possible for reproducible outputs when their source and toolchains survive; that does not recreate unique historical evidence automatically.

This is the primary resilience gap. The paper documents it explicitly instead of labeling a single-device archive an ultimate disaster-recovery system.

## Confidentiality and trust

The restic repository is encrypted, and its local password file is protected by restrictive permissions. The system also places a recovery password beside the repository on the iPad for usability after Linux loss. This arrangement improves recoverability from loss of the Linux credential but means that access to the complete iPad recovery folder can provide both ciphertext and the means to decrypt it.

Do not share the entire Recovery folder publicly. A sanitized architecture paper can name credential locations without exposing values. Private SSH keys, device trust material, and repository passwords belong outside logs and memory notes.

The mount marker protects against common operator mistakes and accidental local fallback. It is not a cryptographic attestation that no hostile same-user process changed a directory. Queue locks and pins similarly coordinate trusted agents; they do not prevent all malicious local modification. Any privileged scan permission and the ownership of the Python code it invokes should be included in a future security review.

## Remaining work and design priorities

### Independent recovery copy

An independent destination for source, archives, recovery records, and separately protected credentials is needed to survive loss of the sole archive device. Another folder on the same device does not provide that independence.

### Complete dependency-group recovery

A replacement-environment drill should recover the required source and cold items, restore toolchain identity, and execute application or build validation. Whole-scope file restoration alone does not establish application consistency or successful rebuilding.

### Freshness and alerting

Operators need per-scope last success, waiting drill state, stale scrub state, and interrupted-retirement records. Timer enablement does not establish successful execution.

### Retention with cold-item protection

Pruning remains disabled. Any future retention design must preserve every snapshot reachable from cold-item records, review prospective deletion, and establish independent recoverability before removing archive data.

### Portable deployment

Scheduler and drill modules retain explicit Anubis integration. The process-inspection helper also needs a suitably protected privileged deployment. Review these assumptions before distributing the system beyond a trusted local environment.

### Performance characterization

Measure actual workloads and scratch-space pressure. Preserve complete recovery and comparison gates while tuning.

## Reliability revision: fixes and additions

The architecture review led to implementation changes, rather than only editorial changes. This revision retains the existing storage policy: active source and pins stay local, offloading remains explicit and verified, and pruning remains disabled.

### Cold archive reference audit

`project-vault audit` inspects local cold records, malformed entries, interrupted retirement states, and remaining quarantines. Recreated original paths are reported as informational regrowth with a warning not to reuse an old deletion receipt. `project-vault audit --online` additionally compares local and iPad item records and checks that every referenced snapshot exists with the expected cold tag and original root. Differences are reported for review; neither side is silently overwritten. Detected issues produce a nonzero CLI exit status.

The report carries `protected_cold_snapshots` so maintainers can see the snapshot references that must survive retention planning. It does not enable retention or authorize deletion, and it does not read all archive data. A passing reference audit has a narrower meaning than a scrub or restore.

### Versioned recovery kits

`project-vault recovery-export` collects the runtime modules, bootstrap guide, configuration, service definitions, cold receipts, provenance, selected health records, and architecture paper into `Recovery/Kits/ID`. It records per-file SHA256 hashes, reads the completed files back, and publishes `Recovery/latest-kit.json` only after verification and another destination check. An incomplete new kit does not replace the prior publication pointer. Older kits are retained; identical content can reuse a verified published kit.

Each kit contains `Tools/verify_kit.py`, which can check a copied kit with Python’s standard library without importing the vault modules. The manifest and pointer establish consistency, not independent authenticity. Recovery credentials remain at their existing locations rather than being duplicated into each kit. Legacy `Recovery/Tools` is retained for historical compatibility; the versioned kit pointer is the current recovery-tool entry point.

The scheduled runner now performs a cold-reference audit and kit export after its scope-processing pass. Busy or offline operations defer and leave a maintenance result. The dashboard shows the audit, kit and maintenance receipt states. A refreshed kit does not establish that every project scope succeeded.

### Concurrency and reporting fixes

Record publication uses unique temporary filenames and fsync as described in Verified offloading. Pin updates and final retirement share a lock. The final path-recreation check also treats a broken symlink as an occupied original path. The offload worker no longer says a source was necessarily retained after every possible exception; its notification directs the operator to the receipt and quarantine, accounting for partial deletion failures.

Scrub attempts now save a waiting or failed state while preserving `last_success` separately. Repository lock contention is classified as waiting for scrubs and drills. The drill’s success boundary explicitly excludes cold snapshots removed from the selected scope. The stale Recovery README and policy wording have been corrected.

### Documentation coverage and recovery discipline

Configure the paper as an additional backup path when desired. Recovery-kit export includes matching architecture papers from Documents without covering every file in that folder. The bootstrap guide gives staged direct-restic and wrapper recovery commands, preserves conflicting metadata for review, and prohibits automatically restarting historical deletion queues on a replacement machine.

Automated checks cover concurrent JSON publication, failed-publication preservation, concurrent pins, pin/retirement serialization, scrub deferral semantics, kit corruption and failed-publication behavior, and missing or inconsistent cold references. Fixture tests do not establish replacement-machine recovery.

## Creating recovery space through verified offload

Reviewed inactive build objects can be candidates for verified offload when their retained source, toolchain, and evidence remain protected.

### Preserving local executables while archiving dependency objects

The new `put --offload --retain-binaries` option applies only to a flat regular-file Cargo `debug/deps` or `release/deps` directory. The existing Cargo profile lock protects the operation. It creates and verifies local hard links for every entry except non-executable `.rlib`, `.rmeta`, and `.o` objects. The retained directory, `vault-retained-binaries-ITEM_ID`, is pinned and recorded in the cold-item receipt. Executables, shared libraries, dependency records, and other regular files retain their local bytes and metadata. Their retained location is explicit; the original deps layout remains recoverable with `get`.

The whole original dependency directory still passes the existing snapshot, full restore, hash/metadata comparison, receipt-readback and quarantine gates before retirement. This feature changes which physical bytes remain locally referenced; it does not weaken archive verification or make an active directory eligible. Non-flat contents require review.

### Generated native-run caches

The cold-storage integration recognizes a shared target named `anubis-run-cargo-target-audited-crypto-v3`. Before treating that target as eligible, confirm that the compiler has copied required outputs elsewhere and that the target contains no unique evidence.

For this recognized target's `release` directory, the vault now acquires Anubis's existing `.anubis-build-mutex` in the parent target directory. It writes its own live owner PID, refuses any existing mutex, and removes only its own unchanged ownership record and empty mutex on exit. Participating Anubis runners wait while the cache is archived and compared. This is cooperative coordination, not protection against arbitrary unrelated writers.

### Recovery claim after reclamation

A recovery campaign can save a fresh working-scope snapshot after reviewed offloads and attempt to restore the entire snapshot with verification into local scratch. All selected cold directories separately undergo complete recovery comparison before their local copies are removed. A successful working-scope drill must not be described as simultaneous recovery of every historical cold snapshot.

Read each operation receipt before claiming completion. A running state is not a completion receipt.

## Appendix: implementation map

| File in `~/Projects/duat/` | Role |
|---|---|
| `vault.py` | Configuration, destination checks, source discovery, restic wrapper, catalog, CLI |
| `cold.py` | Candidate inventory, activity checks, guarded offload, cold retrieval |
| `pins.py` | Concurrent pin edits and final-retirement coordination |
| `recovery.py`, `verify_kit.py` | Cold-reference audits and versioned recovery-kit publication/verification |
| `RECOVERY-BOOTSTRAP.md` | Replacement-Linux recovery procedure and acceptance boundaries |
| `provenance.py` | Source/toolchain/regeneration records |
| `queue_store.py` | Persistent enrollment and short queue-edit locking |
| `tier_queue.py` | Background reviewed offload processing |
| `requests_worker.py` | Persistent retrieval processing |
| `scheduled.py` | Independent project-scope orchestration |
| `anubis_backup.py` | Extended Anubis scope and initial recovery checks |
| `lock_recovery.py` | Conservative same-host stale-lock handling |
| `health.py` | Read-only dashboard state assembly |
| `render_whitepaper.py` | Regenerate the standalone paper from its Markdown source |
| `dashboard.py`, `dashboard.html` | Local HTTP control and interface |
| `bench.py`, `bench.html` | Isolated synthetic benchmarks, live metrics and exports |
| `scrub.py` | Full repository data-check receipt |
| `drill.py` | Whole-scope restore admission and execution |
| `compact_catalog.py` | Catalog maintenance |
| `ANUBIS-COVERAGE.md` | Coverage explanation |
| `test_vault.py`, `test_cold.py`, `test_maintenance.py`, `test_queue.py`, `test_polish.py` | Targeted implementation tests |

The repository contains the reusable implementation; historical device-maintenance and reclamation scripts are not part of this distribution.

## Appendix: evidence locations and interpretation

All local state paths below are relative to `~/.local/state/project-vault/`.

| Record | Interpretation |
|---|---|
| `project-health.json` | Per-scope state, snapshot, timestamp, retained prior success where available |
| `scrub.json` | Latest attempt method/state/time and separate last successful time after the revision |
| `recovery-audit.json` | Local or online cold-reference audit, issues, and protected snapshot IDs |
| `recovery-kit.json`, `recovery-maintenance.json` | Published kit readback and scheduled recovery-maintenance status |
| `restore-drill.json` | Whole-scope drill state and capacity refusal or result |
| `anubis-recovery-check.json` | Initial recovery check history; not repeated full verification of every later snapshot |
| `items/*.json` | Original path, cold ID, snapshot, manifest digest, verification and state |
| `cold-jobs/` | Candidate job manifests and resumable verification state |
| `offloads.jsonl` | Append-only operation history written by the wrapper |
| `source-maps/` | Snapshot-specific source mapping |
| `catalog-scopes.json` | Compact catalog scope information |
| `offload-queue.json` | Explicit enrolled candidates and processing states |
| `pinned-paths.json` | Current working-set protection |
| `operation.json`, `cold-operation.json` | Last recorded active phase or terminal state |

Corresponding recovery copies exist for important records under `~/iPad/TryOmarchy/Recovery`. Local and remote copies can differ if interrupted while updating; compare their identities and state transitions during recovery. A copied receipt is still a record of an operation, not a newly performed verification.

The source tests cover backup/restore, tampering, destination checks, worktrees, catalogs, scope grouping, candidate round trips, changed-source and pin refusals, interrupted restore, locking, queue edits, and drill admission. Run them in an isolated environment. Fixture success does not establish production disaster recovery.

## Appendix: command reference

| Command | Meaning |
|---|---|
| `project-vault audit [--online]` | Audit local receipts; optionally compare iPad records and snapshot references; failing exit status for identified issues |
| `project-vault recovery-export` | Publish a versioned recovery kit after complete file-hash readback |
| `project-vault status` | Local summary and recorded items/queue |
| `project-vault sources` | Resolve configured source mapping |
| `project-vault backup` | Run ordinary configured backup |
| `project-vault list` | List cataloged snapshots |
| `project-vault catalog` | Refresh catalog while online |
| `project-vault find QUERY` | Search compact local index and cold records |
| `project-vault find PATTERN --online` | Search complete repository filename metadata |
| `project-vault put PATH` | Archive and compare entire candidate; keep source |
| `project-vault put PATH --offload` | Same verification, then guarded retirement |
| `project-vault put PROFILE/deps --offload --retain-binaries` | Preserve non-object files locally, then fully verify and retire reviewed Cargo deps |
| `project-vault items` | List cold-item records offline |
| `project-vault get ID_OR_PATH` | Recover cold item to its original path if absent |
| `project-vault get ID_OR_PATH --to NEW_PATH` | Recover cold item elsewhere |
| `project-vault provenance PATH --repository REPO --rebuild COMMAND --toolchain IDENTITY` | Record regeneration context |
| `project-vault queue PATH` | Enroll an exact reviewed directory |
| `project-vault pin PATH` | Protect overlapping working-set paths |
| `project-vault unpin PATH` | Release protection after ownership review |
| `project-vault check` | Repository metadata check |
| `project-vault check --full` | Full repository data reading/checking |
| `project-vault restore SNAPSHOT PATH --to NEW_DIRECTORY` | Selected-path snapshot recovery |
| `project-vault plan` | Advisory candidate discovery; no automatic deletion |

`init` is an initialization command, not a remedy for an unreadable existing archive. It creates recovery material under guarded conditions and must not be used to replace a repository whose credential or mount is missing.

## Glossary

**Archive:** retained content that may no longer have a Linux original.  
**Backup:** a recoverable additional version while its working original may remain.  
**Cold item:** an exact directory associated with a dedicated snapshot and manifest receipt.  
**FUSE:** the Linux mechanism through which ifuse exposes application files as a mounted filesystem.  
**Manifest:** the complete candidate inventory under the implementation’s defined metadata schema.  
**Offload:** archive, recover, compare, and then retire the eligible local directory.  
**Pin:** a local policy record that refuses overlapping retirement.  
**Provenance:** source and toolchain context; its strength depends on what was actually recorded.  
**Quarantine:** a same-filesystem renamed source used during guarded retirement.  
**Scope:** a named group of backup source paths with its own health record.  
**Scrub:** full repository data reading and checking.  
**Snapshot:** a restic identity for a retained filesystem view.  
**Working set:** the files needed locally for current engineering work.

## References and maintenance of this paper

Implementation references are the repository modules, example configuration and units, and packaged agent skill. Upstream documentation:

- [restic: working with repositories and checking integrity](https://restic.readthedocs.io/en/stable/045_working_with_repos.html).
- [restic: restoring from backup](https://restic.readthedocs.io/en/stable/050_restore.html).
- [restic: command and data references](https://restic.readthedocs.io/en/stable/100_references.html).
- [libimobiledevice: ifuse application file sharing](https://github.com/libimobiledevice/ifuse).

Update this paper when source coverage, transport, verification gates, recovery credentials, retention policy, or service behavior changes. Preserve older editions when they help explain historical receipts. Recheck operational measurements instead of carrying old free-space figures forward as current facts.

## Conclusion

DUAT Vault connects a Linux working set with an explicitly recoverable archive. Its central operation is the guarded transition from a saved snapshot to a complete recovered-and-compared candidate whose eligible local original can be retired.

Its assurance is specific to the checked candidate, method, and operation. Cooperative concurrency, local recovery capacity, archive-device survival, and credential availability remain explicit boundaries. Use actual receipts and recovery exercises to establish the state of an installation.
