# Packaging validation

Validated on the original Linux host on 2026-09-27, from this repository checkout.

```text
python3 -m unittest discover -v
Ran 30 tests in 75.330s
OK
```

The suite exercises temporary local restic repositories. It does not use production
archives and does not establish a new production restore or independent disaster recovery.

Additional checks passed: CLI help, example JSON parsing, Git whitespace checks
(Markdown hard line breaks are permitted), and runtime comparisons during initial packaging. A later privacy revision replaced the
white papers with sanitized editions and updated the renderer and documentation.
See `PRIVACY-REVIEW.md` for the publication review scope.

A scan for common private-key and credential-token patterns found no matches in the
packaged files. Live configuration, credentials, archive contents, and local state
were excluded during source selection. This pattern check is not a comprehensive
security audit.
