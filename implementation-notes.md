# Implementation notes

One line per decision. Newest last.

- 2026-09-28 Allowlist printed `cloudcontrol:ListResources`, which is not a real IAM action. Cloud Control API is authorized under the `cloudformation:` prefix (Service Authorization Reference: "AWS Cloud Control API (service prefix: cloudformation)"). A policy built from the old allowlist denies every type. Fixed in `report.py`, `bootstrap.sh`, `RDD.md`.
- 2026-09-28 Added `ALLOWLIST_NOTE`: Cloud Control calls the underlying service with the caller's credentials, so each type also needs its handler's read permissions. Rejected enumerating per-type actions (73 types, schema-defined, churns) in favour of pointing at ViewOnlyAccess/ReadOnlyAccess.
- 2026-09-28 A run collecting 0 resources while collectors failed now raises `EmptySnapshotError` after the HTML is written (exit 1) and dumps the coverage table to stderr. Rejected exiting before writing the file: the empty report still carries the coverage table the user needs.
- 2026-09-28 `bootstrap.sh` moved to uv: install uv via the standalone installer when absent, then `uvx --from git+... awsnap`. uv ships its own Python, so the Python-version probe and the boto3 preinstall both disappeared. Rejected keeping a pip fallback; uv-only is the project rule and a clear error beats a silent second code path.
