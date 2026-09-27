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
