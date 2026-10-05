# Installation and configuration

This is the original Linux implementation, packaged for review and adaptation. It
does not install a device transport, change sudo policy, initialize a repository,
or enable services automatically.

## Dependencies and checkout

Install Python, restic, Git, and ifuse/libimobiledevice using your distribution's
packages. Confirm that your restic supports the commands used in `vault.py` and
`cold.py`, including verified restores. Mount the iPad application's shared documents
through ifuse at a stable path. For the original Mac-to-Linux USB bridge, consult the
architecture paper and adapt its user and socket paths.

The service examples assume this checkout location:

```bash
git clone https://github.com/AnubisQuantumCipher/duat.git "$HOME/Projects/duat"
cd "$HOME/Projects/duat"
python3 vault.py --help
```

The repository is public. To make `project-vault` available, create a launcher
after checking that the destination is unused:

```bash
mkdir -p "$HOME/.local/bin"
ln -s "$HOME/Projects/duat/vault.py" "$HOME/.local/bin/project-vault"
```

Ensure `$HOME/.local/bin` is on your shell's PATH. Use `python3 vault.py` directly
when an existing deployment already owns the launcher.

## Configuration

Copy `examples/config.example.json` to `~/.config/project-vault/config.json` and edit
it before use. Every filesystem path must be absolute; the loader does not expand
`~`, `$HOME`, or placeholders. The `home` path bounds allowed sources and restores.
`mount` must name the actual ifuse mount, and `root` must be inside it. Keep
`require_ifuse_mount` enabled for device use.

Choose a fresh `vault_id` for a new archive. It must match the destination's
`.vault-id` for an existing archive. Keep `state` on Linux. `reserve_bytes` protects
archive space; `local_reserve_bytes` protects Linux working space during offload
and recovery. The example retains the original reserve settings; assess capacity
for your complete candidate and recovery scratch before use.

`project_roots` discovers projects below the listed directories. `additional_paths`
adds explicit source paths. Review `project-vault sources` before backing up. No
source exclusions are implied by a cache directory name.

Resolved backup sources must stay under `home` unless their resolved paths are
under an explicitly configured `allowed_external_roots` entry. This also applies
to discovered Git worktrees and shared metadata. Use absolute, reviewed roots;
the iPad mount remains forbidden as a source. The example allows none.

The live deployment has a deliberately partial Work scope because some Work
roots could not be read. For an equivalent local policy, set `work_partial_policy`
to the absolute path of a private JSON policy based on
`examples/work-partial-policy.example.json`. The scheduler requires the older
`project-Work` health entry to remain `incomplete`, records every included and
omitted top-level root, checks the saved source map, and publishes a manifest.
Its `passed` status means only the declared partial scope was backed up and
metadata checked; it is never a complete Work or full-restore claim. Without
this option, the scheduler retains its original broad Work scope. Keep actual
path inventories and diagnostic hashes outside the public checkout.

For an empty, intended destination with working ifuse transport:

```bash
project-vault sources
project-vault init
project-vault backup
project-vault status
```

Initialization creates encryption credentials in local state and a recovery copy
on the iPad. An existing archive must be recovered using its existing identity and
credentials; see `RECOVERY-BOOTSTRAP.md`.

## Process inspection

`cold.active_users` scans Linux process metadata before retirement. A non-root caller
invokes the fixed `/usr/local/libexec/project-vault-active-users` helper through
`sudo -n`. An administrator must review and install `helpers/project-vault-active-users`
as a root-owned, non-writable executable at that path, then authorize only that
fixed helper in sudo policy. The helper uses the sudo caller's account home to
limit scanned paths to its Projects, Work, and .cache trees. It refuses on an
unreadable live process. If inspection cannot complete, offload refuses. Never
authorize root execution of the checkout's user-writable Python files.

No sudoers policy is included or installed by this repository. Backup, offline
catalog search, and documentation inspection can be used without enabling offload.

## Optional services and skill

`examples/systemd/` uses `%h/Projects/duat` and the default configuration path.
Review and install selected units under `~/.config/systemd/user`, then run
`systemctl --user daemon-reload`. Enable only the units you have configured.

The `ipad-storage.service` dependency names the original external mount supervisor;
its implementation is not included. Supply your own transport supervision.
`scheduled.py`, `anubis_backup.py`, and `drill.py` retain Anubis source paths, scope
tags, and initial restore checks. Adapt those scopes before enabling backup or drill
timers on a machine without that layout. Manual `project-vault backup` uses the
configured source scope. Dashboard actions expect the corresponding worker units.

`skills/project-vault/` includes a publication-safe agent skill, references,
storage-status script, and interface metadata. Configure and authorize it according
to the receiving operator's policy before installing it.

## Testing

Run `python3 -m unittest discover -v` from the checkout. Tests create temporary
repositories and perform actual restic restore comparisons. They do not require an
iPad. Cold-storage integration tests invoke the process inspection helper. Use an
isolated Linux container or VM with root privileges when the host has no suitable
helper policy. Do not weaken the production checks merely to pass tests.
The GitHub Actions test job installs restic and the repository's fixed scanner as
a root-owned executable on an ephemeral runner, then runs the same suite. It does
not connect to or make claims about any production archive.

## Rendering the paper

The HTML paper is already standalone. To regenerate it, install Python `Markdown`
in a virtual environment and run `python3 render_whitepaper.py` from this checkout.
The renderer reads `docs/DUAT-Vault-Architecture-White-Paper.md` and writes its
HTML companion. Review the generated output before committing.

## Bench deployment

Deploy `bench.py` and `bench.html` beside `dashboard.py`, and use the matching updated
`vault.py` and `recovery.py`. Restart the dashboard service to load the new routes.
No new daemon or timer is required; an explicit start launches a benchmark worker.
The worker shares the existing vault lock and retains its synthetic artifacts.
See [DUAT Bench](BENCH.md) before starting a run.
