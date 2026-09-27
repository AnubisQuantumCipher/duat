# DUAT Bench and Live Metrics

Open **Bench & live metrics** from the storage desk, or visit `/bench` on the local
dashboard. Choose a synthetic payload size, file count, and compressibility pattern.
Start a benchmark and follow its timeline. Cancel requests stop subsequent work and
terminate an active restic child; existing synthetic files remain for inspection.

The CLI runs the same engine in the foreground:

```bash
project-vault bench --size-mib 16 --files 8 --pattern incompressible
# From a source checkout, with an explicit configuration:
python3 bench.py --config /absolute/config.json run --size-mib 16 --files 8
```

## What is measured

| Phase / value | Measurement boundary |
|---|---|
| Generate synthetic source | SHAKE-256 blocks with a declared seed, or repeated fixed text; generation excluded from round-trip time |
| Transport payload write | Bytes accepted by filesystem write calls; buffered application boundary, not wire bytes |
| Filesystem sync acknowledgement | Time until host `fsync` calls return; not a device durability guarantee |
| Transport payload readback | Full file reads and SHA-256 comparison against the generated manifest; may use caches |
| Initialize isolated repository | Fresh encrypted restic repository, separate random test credential and cache |
| Encrypted backup | Restic logical bytes processed and total wall elapsed; packed added bytes recorded separately |
| Encrypted repository data check | `restic check --read-data` on the isolated synthetic repository |
| Restore with verification | `restic restore --verify` to new local scratch; logical restored byte counter |
| Complete restored manifest comparison | All restored files and retained source re-read and compared for exact file set, sizes and SHA-256 |
| Complete verified round trip | Monotonic elapsed from after generation through all transport, encryption, check, restore and comparison phases; populated only when all gates pass |

The complete manifest phase counts both restored and source reads. Its counted bytes
are therefore different from the logical payload size. Elapsed phase times include
instrumentation and checks. No subtraction estimates an unobserved device-only speed.

Restic `data_added_packed` is its reported added data after compression; it is not a
physical network, complete repository size, or device-committed-object counter.
The filesystem/ifuse backend exposes no authoritative device commit counter or
negotiated link speed. Those values are **unavailable**, including when host fsync
succeeds. Backend-internal retries are also unavailable. Wrapper retries are measured
and remain zero because the engine does not retry failed operations automatically.

## Rate windows and labels

Current rates use differences between consecutive monotonic samples. Sustained rates
use the phase counter divided by complete elapsed phase time. Each phase resets its
counter and rate window. Peak rates require a complete configured window and retain
the actual window start, end and elapsed duration; a short phase has no peak result.
Sampling is periodic, so actual window durations can exceed the target interval.

Filesystem counter rates are labeled **measured**. Live and peak backup/restore rates
are **estimated** because restic reports progress in batches; the final sustained
logical rate uses the observed count and full phase elapsed time. Missing telemetry
is **unavailable**, never an invented zero. Completed and interrupted runs are
**historical**, with their original value classifications retained. The UI does not
display an ended run's last sampled rate as a current live rate.

## Isolation, reserves and retention

Each run uses only generated files under local `state/bench/runs/RUN_ID/work`, plus
an exclusive `Bench/RUN_ID` directory below the configured archive root. The encrypted
test repository, credential, cache, manifest and restore destination are separate
from production. Restic commands name only the isolated repository and do not inherit
restic repository/password environment settings. No production snapshot is created,
retired, forgotten or pruned. Synthetic sources and artifacts also remain after a run.

The engine requires the configured mount and vault identity, refuses symlinked benchmark
roots, acquires a benchmark lock and the existing vault operation lock, and refuses
busy storage. Admission reserves a conservative estimated allowance on both volumes
for payload copies, repository growth and scratch overhead. It never deletes data to
create capacity. Runtime sampling checks reserves, and chunked writes check their
next write budget. Reserve loss, mount loss, corruption and process failures stop the
run and leave it visibly incomplete.

Admission and runtime checks are not a filesystem quota: unrelated writers can consume
space concurrently and an in-flight backend write can run between samples. Preserve
working-set ownership and avoid concurrent storage-heavy jobs. Backend phases have
a timeout. A blocked kernel/FUSE operation can still delay cancellation; an abrupt
worker loss is shown as interrupted, not a successful restore.

Repeated tests accumulate synthetic data. Their source, temporary cache, restored files
and test credentials count in local scratch usage. Review retention separately; there
is no benchmark cleanup or production pruning command. Credentials and private backend
error logs stay in the protected work directory and are excluded from exports.

## Operating conditions

Measurements include local/archive free bytes, synthetic scratch logical and allocated
bytes, host load, available host memory, and exposed host thermal-zone readings.
Device temperature, device power and negotiated link telemetry remain unavailable
where the host/backend does not expose them. No cable label is used as a speed input.
The OS and device caches are uncontrolled; this is recorded for every run. A result
from a local fixture is explicitly labeled `local-fixture`, never as an iPad result.

## Export and reproduce

After a run ends, download:

- **Result card:** standalone HTML suitable for sharing or printing.
- **Raw timestamped CSV:** every emitted sample, with UTC and monotonic elapsed times,
  phase counter, rate classifications, sample interval, space and operating telemetry.
  Blank unsupported counter/sensor cells mean unavailable, not zero.
- **JSON report:** workload settings and generator seed, full synthetic manifest,
  phase times, rate window boundaries, integrity outcomes, software versions, selected
  operating telemetry and the CSV digest. A bounded series supports the live chart;
  the complete sample history is in CSV.

Reports omit usernames, local absolute paths, credentials, raw backend logs and
production archive IDs. They intentionally include the requested operating measurements;
review those measurements before sharing. Result reports remain runtime artifacts and
must not be committed to the source repository.

Re-run the reported payload size, file count and pattern with the same generator and
software version. The manifest makes generated content comparable. Performance itself
is not deterministic: report cache policy and operating conditions when comparing runs.
No synthetic success establishes production disaster recovery or application consistency.

Restic counter definitions: [official scripting and JSON documentation](https://restic.readthedocs.io/en/stable/075_scripting.html).
