# Contributing

Run the existing unittest suite in an isolated Linux environment with restic and
Git available. Describe what behavior changed and which recovery checks exercised it.

Preserve refusal behavior, source and destination identity checks, working-set pins,
complete candidate restoration and comparison, receipt publication, and lock ownership.
Do not replace a complete recovery check with sampling or bypass a refusal to obtain
a passing result. Add regression tests when changing retirement or recovery behavior.

Keep private configuration, credentials, archives, and operational state out of Git.
Historical production observations belong to the documented deployment and must not
be presented as fresh test results. Changes to operator policy or the agent skill
must clearly identify the scope and required authorization.
