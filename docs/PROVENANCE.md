# Source provenance and release scope

DUAT Vault contains the runtime, tests, dashboard, recovery tools, agent skill,
architecture documentation, and example configuration and service units.
The runtime originated as a Linux implementation with Anubis integration.

Publication documents use generic paths and placeholders. They omit personal machine
inventories, production item/snapshot identifiers, operational logs and measurements,
account storage details, private configuration, and source-paper fingerprints.
The public architecture paper describes implementation behavior and verification
boundaries rather than an operator's production history.

The runtime remains separate from operational state. Credentials, archive data,
catalogs, queues, pins, receipts, and environment inventories are not distributed.
Historical one-off device cleanup and reclamation helpers are also excluded.
The deployment-specific partial Work policy and its path/error inventory are excluded;
the public source contains the policy mechanism and a synthetic example.

The renderer reads the architecture Markdown under `docs` and generates its standalone
HTML companion. Scheduler and drill modules still contain Anubis integration assumptions;
review the installation guide before enabling them elsewhere.
