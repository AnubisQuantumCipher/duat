# Validation

The publication package and DUAT Bench were exercised with local synthetic restic
repositories. No production snapshots or source folders were retired or pruned.

Validation covers complete encrypted round trips, source retention, corruption refusal,
offline and reserve refusal, reserve loss during a run, production-lock exclusion,
symlink refusal, cancellation, prevention of overwriting prior runs, exact peak-window
boundaries, and exports free of test credentials and source paths.

The full suite also covers the original vault, queue, recovery-kit, manifest and pin
behavior. Headless Chromium exercised the benchmark through the HTTP/UI interface,
including a completed synthetic run, HTML/CSV/JSON exports, origin/token checks,
invalid export paths, and desktop/mobile layouts without page errors or horizontal
overflow. The installed dashboard was separately checked over loopback.

These are fixture and UI checks, not measured iPad throughput or production disaster
recovery. Deployment-specific operating records remain outside this repository.

The privacy review checks publication files for personal deployment markers and
credential patterns. Benchmark output, runtime credentials, raw private backend logs,
and local operation reports are excluded from version control.

The current source suite also checks opt-in backup roots outside the configured
home, fixed-helper process inspection, and a synthetic partial Work scope with
source-map verification. The partial-scope fixture does not establish complete
Work coverage or a scheduled full restore.

## Background cooperation and lock waiting

The public patch passed `python3 -m unittest discover -v`: **61 tests, OK** on
Linux/aarch64 with the fixed process-inspection helper and disposable local restic
repositories. `TMPDIR` was placed beneath the user's `.cache` so the existing
scanner path policy applied unchanged. No assertions or production guards were
disabled. The backup, tier, scrub and drill service examples passed
`systemd-analyze --user verify` in a valid user runtime environment; CLI help for
the vault, find, bench and background policy also exited successfully.

Regressions exercise deferral for busy locks, active compiler/prover names,
unreleased or malformed coordination records, pending or malformed retrievals and
unreadable retrieval storage. They check that deferral leaves the existing lock
owner and pending queue untouched. Separate processes exercise lock waiting,
cancellation and normal exclusion after acquisition. Mocked CLI tests check that
device revalidation precedes repository access and that changed identity refuses
access. Recovery tests compare exported service drop-in bytes and retain the
previous tamper and failed-export checks.

These checks establish the tested cooperative behavior. They do not establish
atomic build exclusion, zero contention, successful production offload or recovery,
or the effectiveness of every scheduler setting on every host. Source backup,
candidate classification, complete candidate restore comparison and final retirement
remain distinct requirements.
