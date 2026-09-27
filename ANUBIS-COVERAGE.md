# Application-specific backup scope

Source coverage comes from configuration and the source map for each snapshot.
`project_roots` discovers projects under configured directories. `additional_paths`
adds explicit paths. Registered Git worktrees and shared Git metadata are discovered
by the wrapper. Inspect `project-vault sources` before relying on coverage.

The included `anubis_backup.py` and scheduler contain Anubis-specific source paths,
scope tags, and an initial restore check. They are integration code, not a record of
an operator's installed projects. Adapt this scope before enabling those services in
another environment. This repository publishes no personal installation inventory.

Live databases require their application's own consistency procedures. A snapshot
of project files is not a complete system image or proof of application recovery.
Completion requires an actual successful snapshot and the relevant verification.
