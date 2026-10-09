# DUAT recovery without the original Linux installation

This procedure recovers files and tooling. It is not a tested bare-metal rebuild of
TryOmarchy, native database continuity, or recovery from destruction of the sole iPad.

## Preserve and inspect

Keep Documents installed on the iPad. Establish trusted app file-sharing access and
locate TryOmarchy/Repository and TryOmarchy/Recovery. Pair/unlock the iPad as needed.
The original Mac bridge and mount are machine-specific; a replacement computer must
establish its own access. Do not initialize or rewrite the existing repository.

Read Recovery/latest-kit.json. Its `id` selects Recovery/Kits/ID. Copy that whole kit
to new local scratch. Use a trusted Python 3 installation to check its contents:

```bash
python3 /path/to/kit/Tools/verify_kit.py /path/to/kit
```

The standalone checker imports no vault modules. Its hashes detect divergence from
the bundled manifest; they do not authenticate a maliciously replaced kit/checker.
The manifest hash in latest-kit.json provides another consistency reference, not an
independent signature. Keep the original iPad records unchanged while investigating.

## Inspect the repository using restic directly

Install a compatible restic version. Copy the recovery password
privately to a protected local file; use umask 077 and chmod 600. Never paste its
contents into chat or command arguments. Commands below use placeholder paths:

```bash
restic -r /mounted/TryOmarchy/Repository -p /private/repository-password snapshots
restic -r /mounted/TryOmarchy/Repository -p /private/repository-password check
restic -r /mounted/TryOmarchy/Repository -p /private/repository-password restore SNAPSHOT --target /new/recovery-directory --verify --sparse
```

Use a new destination and sufficient local space. Recover the source snapshot and
all separately required cold snapshots. State/items/*.json maps original paths to
snapshot IDs and manifest digests. Later source snapshots can omit offloaded items.
Do not run forget, prune, repair, or force-unlock as a shortcut around an error.

## Reconstitute the wrapper on a replacement Linux environment

The kit includes Tools, Services, configuration, item receipts, pins and provenance.
New kits also carry the background scheduling helper and service `.conf` drop-ins.
Review restored coordination-file paths and overrides for the replacement machine;
a missing configured coordination file correctly defers background work.
Keep the recovered kit unchanged as an inspection copy. Stage Tools in a new local
working directory. Review configuration home/state/mount/root and vault identity
against the actual replacement machine; changing a path must not change which archive
is selected. The `require_ifuse_mount` setting must remain enabled for this deployed
ifuse workflow. Do not disable it merely to bypass a disconnected-device failure.

Create a new protected state directory. Copy the correct repository-password there
with mode 600. Import inspected State/items and State/provenance copies into it;
prefer up-to-date Recovery/items if newer records exist, preserving both versions
until discrepancies are understood. Restore reviewed pins after translating paths.
Do not automatically start old timers, restore deletion queues, or reuse old process
IDs. Source paths in historical receipts retain their original absolute names.

Point `--config` at the reviewed configuration:

```bash
python3 /new/tools/vault.py --config /new/configuration.json items
python3 /new/tools/vault.py --config /new/configuration.json audit --online
python3 /new/tools/vault.py --config /new/configuration.json get ITEM_ID --to /new/home/recovered-item
```

The new state catalog is created when opened. Cold retrieval verifies the original
manifest and refuses existing targets. Generic source recovery is also available
through the direct restic commands above. Install a matching toolchain and inspect
application-specific instructions before treating recovered files as a running system.

## Acceptance

Record source snapshot IDs, cold-item IDs, recovered locations, audit results,
full-data check results and actual restore results separately. Test an engineering
dependency group including required historical binaries and proof receipts. Only then
re-enable reviewed services and enroll new offloads. Pruning stays disabled.
