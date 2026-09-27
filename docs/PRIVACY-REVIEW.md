# Publication privacy review

The publication edition removes personal names and home paths, device inventory,
account storage details, production archive and recovery-kit identifiers, measured
storage usage, build-lane inventories, and operational history from the documentation.
The HTML paper is generated from the sanitized Markdown. The skill contains general
operator guidance rather than an individual's pre-existing authorizations.

The repository contains source, synthetic test fixtures, generic configuration and
service examples, and documentation. Runtime state, credentials, private configuration,
archives, catalogs, and receipts are excluded. Credential file paths and runtime code
that generates or reads passwords describe functionality; they are not secret values.

The review checked text artifacts for known personal/deployment markers, production
identifiers, private-key blocks, common credential-token formats, and credentials in
URLs. A local comparison against the vault's actual password found no occurrence;
the password was neither printed nor stored in this repository. The initial source
commit was also checked for these credential categories, with no matches found.

The public GitHub project/account identity is intentionally retained in repository
links, the MIT copyright notice, and GitHub noreply commit attribution. Test identities
and example paths are synthetic. Anubis integration names remain where they are part
of the implementation's behavior.

Pattern scanning and review cannot guarantee detection of every possible secret.
Review future contributions and generated artifacts before committing them. Keep
private operational records outside the source tree and preserve the ignore rules.
