# awsnap

> One command in AWS CloudShell → your entire AWS account as a single, offline, SQL-queryable HTML file (DuckDB-WASM + embedded Parquet).

![Python](https://img.shields.io/badge/python-3.9+-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)
![Status](https://img.shields.io/badge/status-spec-orange)

**README type: A — Spec.** An agent implements from this document. No code exists yet. Resolve Open Questions and pass Gate-0 before Phase 1.

---

## Purpose

**Problem**: Answering "what exists in this AWS account right now?" requires installing and configuring a tool (Steampipe, CloudQuery), or clicking through consoles. Sharing that answer with an auditor, a teammate, or your future self (drift diff) is even harder — the answer lives in a live tool, not an artifact.

**Solution**: `awsnap` runs inside AWS CloudShell (pre-authenticated, Python preinstalled, zero install friction), inventories the account through read-only APIs, and emits one self-contained `awsnap-<account>-<date>.html`: resource inventory as embedded Parquet, queryable with SQL via DuckDB-WASM in any browser. The account becomes a file — portable, diffable, shareable.

**Scope**: Single AWS account, single or multi-region, read-only. Users: DevOps/SRE/security engineers, auditors, consultants doing account handoffs.

**Prior art (honest delta)**: Steampipe and CloudQuery own live "SQL over cloud." `awsnap`'s delta is packaging only: a dead portable artifact + zero-install entry point. Do not claim conceptual novelty anywhere in public copy.

---

## Architecture

```
CloudShell (pre-authed)
  bootstrap.sh (curl | sh, pinned tag)
    └── awsnap (Python pkg)
          ├── collect/          tiered collectors → list[Resource]
          │     1. AWS Config   select-resource-config (SQL, complete) — if recorder on
          │     2. CloudControl list-resources over curated type list — fallback
          │     3. TaggingAPI   get-resources — union (tags enrichment)
          ├── model.py          normalize → Resource rows
          ├── emit/parquet.py   duckdb COPY TO parquet (zstd)
          ├── emit/html.py      template + base64(parquet) → single HTML
          └── report.py         print download path + optional presigned S3 URL
```

**Data flow**: AWS APIs → normalized rows → `snapshot.parquet` → embedded in `viewer.html` template → downloaded via CloudShell Actions → opened locally in browser → DuckDB-WASM queries the embedded Parquet.

| Component | Responsibility |
|-----------|---------------|
| `collect/` | Tiered inventory; each collector reports coverage + timing |
| `model.py` | Single `Resource` schema; ARN parsing; dedup across collectors |
| `emit/parquet.py` | One Parquet file, zstd, stable column order (diffable) |
| `emit/html.py` | Inject base64 Parquet + metadata into `viewer.html.tmpl` |
| `viewer.html.tmpl` | DuckDB-WASM init, SQL editor, canned queries, results grid |
| `cli.py` | argparse entrypoint; flags below |

---

## Recommended Stack

| Layer | Chosen | Why | Rejected |
|-------|--------|-----|----------|
| Browser SQL | **DuckDB-WASM** (pinned version) | Reads Parquet natively, Arrow-fluent, tested in Chrome/Firefox/Safari; fastest on analytical queries in browser benchmarks vs SQLite-WASM/Arquero. Proven in hindsight/QueryDeck/permafrost. https://github.com/duckdb/duckdb-wasm | sql.js/SQLite-WASM (no native Parquet, slower analytics); Perspective (viz-first, heavier) |
| Parquet writer | **duckdb (pip)** | One dep, writes zstd Parquet via `COPY TO`, doubles as local query check | pyarrow (larger wheel, second dep); pandas (unneeded) |
| Collectors | **boto3**: Config → CloudControl → TaggingAPI tiers | TaggingAPI alone insufficient — GetResources does not return untagged resources (https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/API_GetResources.html). Resource Explorer rejected: requires index setup | Resource Explorer (setup friction); per-service list calls (unbounded scope) |
| Distribution | **curl \| sh** bootstrap (pinned tag) + PyPI (`pipx run` / `uvx`) | CloudShell has Python + pip preinstalled; zero-friction goal | Docker (overkill in CloudShell); binary release (build burden) |
| Viewer runtime delivery | **CDN (jsDelivr, pinned)** for wasm bundle; Parquet embedded | Keeps HTML small. ⚠️ duckdb-wasm autoloads the Parquet extension at runtime (fetch) — "offline after first open," not fully offline. See Open Questions | Fully inlined wasm (file bloat; revisit v1.1) |

> 💡 One round of overrides welcome before implementation.

---

## Repository Layout

```
awsnap/
├── src/awsnap/
│   ├── __init__.py
│   ├── cli.py
│   ├── model.py
│   ├── collect/
│   │   ├── __init__.py        # tier orchestration + coverage report
│   │   ├── config_sql.py
│   │   ├── cloudcontrol.py
│   │   ├── tagging.py
│   │   └── types_curated.py   # ~60 CloudControl type names, data not code
│   ├── emit/
│   │   ├── parquet.py
│   │   └── html.py
│   └── templates/viewer.html.tmpl
├── bootstrap.sh               # what users curl; pins version, prints API allowlist
├── tests/                     # moto/stubbed collectors; golden HTML test
├── spike/gate0.md             # Gate-0 results, kept in repo
├── pyproject.toml
├── Makefile
└── README.md                  # becomes Type C at publication
```

---

## Prerequisites

| Requirement | Value | Notes |
|-------------|-------|-------|
| Runtime | AWS CloudShell (AL2023) | Also works in any shell with AWS creds |
| Python | ≥ 3.9 | Verify CloudShell's actual version in Gate-0 |
| boto3 | preinstalled? | Gate-0 check; fallback `pip install --user boto3` |
| duckdb | pip, `--user` | Install time/size measured in Gate-0 |
| IAM | `ViewOnlyAccess` or equivalent | CloudShell inherits console permissions — state loudly in user docs |
| Storage | < 1 GB home quota | CloudShell persistent storage limit |

**API allowlist (print at startup, part of trust story)**: `sts:GetCallerIdentity`, `config:SelectResourceConfig`, `config:DescribeConfigurationRecorderStatus`, `cloudcontrol:ListResources`, `tag:GetResources`, `ec2:DescribeRegions`. Optional: `s3:PutObject` on user-supplied bucket only when `--s3-bucket` given.

---

## Quick Start (target UX)

```bash
# In AWS CloudShell:
curl -sL https://raw.githubusercontent.com/<org>/awsnap/v0.1.0/bootstrap.sh | sh
# → prints API allowlist, collects, writes ~/awsnap/awsnap-<acct>-<date>.html
# → prints: "Download: Actions → Download file → <path>"
# Alternative: pipx run awsnap   /   uvx awsnap
```

---

## Configuration Reference

CLI flags only; no config file in v1. No secrets anywhere.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--regions` | csv | current region | `all` = every enabled region |
| `--tier` | enum | `auto` | `auto` \| `config` \| `cloudcontrol` \| `tagging` |
| `--out` | path | `~/awsnap/` | Output directory |
| `--s3-bucket` | str | — | Upload + print presigned URL (1 h) |
| `--max-workers` | int | `8` | Collector parallelism |
| `--verbose` | flag | off | Per-collector timing + coverage |

---

## Interface Contract

### Resource schema (Parquet columns, stable order — diffability is a feature)

| Column | Type | Notes |
|--------|------|-------|
| `arn` | str | Primary key after dedup |
| `service` | str | Parsed from ARN |
| `resource_type` | str | CloudControl/Config type name |
| `region` | str | |
| `name` | str | Best-effort |
| `tags` | JSON str | Sorted keys |
| `raw` | JSON str | Full properties payload; sorted keys |
| `source` | str | `config` \| `cloudcontrol` \| `tagging` |
| `collected_at` | timestamp | UTC, one value per run |

Metadata table (single row): `account_id`, `run_id`, `awsnap_version`, `tier_used`, `regions`, `resource_count`, `coverage_note`.

### Viewer contract
- Loads embedded Parquet into DuckDB-WASM on open; SQL editor + results grid.
- ≥ 6 canned queries: resources by service; untagged resources; by region; security groups open to 0.0.0.0/0 (when `raw` has it); newest resources; source-tier coverage.
- Works in current Chrome/Firefox/Safari. No telemetry, no external calls except pinned CDN wasm fetch.

---

## Error Handling

| Error | Behavior |
|-------|----------|
| `AccessDenied` per collector/type | Log, skip, count in coverage report — never abort the run |
| Config recorder off | Silent fallthrough to CloudControl tier |
| CloudControl `TypeNotFound`/`UnsupportedAction` | Skip type, record in coverage |
| Throttling | boto3 adaptive retry mode; cap total runtime, report partial |
| Output > 200 MB | Warn; suggest `--regions` narrowing (HTML embed practicality) |

All partial results are valid results: the metadata row must say what was and wasn't covered.

---

## Testing

- `make test`: unit tests with stubbed boto3 (moto where supported, botocore stubs elsewhere); ARN parsing; dedup; Parquet golden file; HTML template injection.
- `make smoke`: against a real sandbox account — asserts runtime < 3 min and coverage report sane.
- Viewer: one Playwright test — open HTML, run canned query, assert row count > 0.
- No test hits real AWS in CI.

---

## Non-Goals (v1)

- Cost data (Cost Explorer overlay) — v2
- Multi-account / Organizations — paid tier per commercialization plan
- Relationship graph (SG ↔ instance ↔ role) — v2
- Fully-offline wasm bundle — v1.1 decision
- Any write/mutate AWS action — never
- Azure/GCP — later

---

## Open Questions

- [ ] **Name**: is `awsnap` free on PyPI and as a GitHub org/repo? Also check AWS trademark comfort ("aws" prefix in a product name — consider `acctsnap`/`awsnap.dev` fallback). Resolve before any publication.
- [ ] CloudShell Python version and whether boto3 is importable without install (Gate-0).
- [ ] Curated CloudControl type list: which ~60 types, and measured coverage % vs a Config-enabled account (Gate-0).
- [ ] Parquet-extension autoload in duckdb-wasm: pin/inline it, or accept CDN fetch on open?
- [ ] HTML size ceiling for smooth browser open (test 10k / 100k resources).
- [ ] License: MIT implied by portfolio pattern — confirm.

---

## Agent Build Instructions

> Implement end-to-end from this README only. Gate-0 first; its results decide GO/NO-GO and the coverage messaging.

### Build Order

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| **0 — Gate-0 spike** | `spike/gate0.md` with measurements | See kill criteria below |
| 1 | Scaffold, `pyproject.toml`, Makefile, CI | `make lint` passes (ruff) |
| 2 | `model.py` + collectors, stubbed tests | `make test` green; coverage report emitted |
| 3 | Parquet + HTML emit, viewer template | Golden HTML opens, canned queries run |
| 4 | `cli.py`, `bootstrap.sh`, presigned-URL path | `make smoke` on sandbox < 3 min |
| 5 | Ship-check + Type C README | ship-check skill passes; no keys/IDs in repo |

### Gate-0 kill criteria (≈45 min in CloudShell)

1. `pip install --user duckdb` succeeds in < 2 min and fits quota — else NO-GO on zero-friction claim.
2. CloudControl fallback tier covers ≥ ~80 % of resources vs Config ground truth in a real account, in < 3 min — else reposition as "requires AWS Config" (weaker) or NO-GO.
3. Parquet base64-embedded HTML with pinned duckdb-wasm executes a query on the embedded data in Chrome — else NO-GO (expected low-risk; pattern proven in hindsight).

### Constraints

- Python ≥ 3.9 compatible (CloudShell reality beats 3.11 preference); typed signatures; `ruff` clean.
- stdlib + boto3 + duckdb only at runtime. No pandas, no requests.
- Read-only AWS calls exclusively; every call site annotated `# AIDEV-READONLY: <api>`.
- `AIDEV-...` comments for non-obvious decisions; no comments restating code.
- Secrets: none exist in this tool; never log credentials or session tokens.
- `bootstrap.sh` pins a release tag and prints the API allowlist before executing anything.

### Acceptance Criteria

- [ ] Gate-0 documented in `spike/gate0.md` with real numbers; GO recorded
- [ ] `make test` ≥ 80 % coverage; `make lint` clean
- [ ] Fresh CloudShell: paste one command → HTML in home dir in < 3 min (mid-size account)
- [ ] HTML opens offline-after-first-load; all canned queries return
- [ ] Coverage report accurate when Config off, when AccessDenied occurs, when a region is disabled
- [ ] Two snapshots of the same account produce byte-stable column order (diffable)
- [ ] ship-check passes before repo goes public

---

## Next Steps

1. Resolve name availability (PyPI + GitHub + trademark comfort).
2. Run Gate-0 in a sandbox account; commit `spike/gate0.md`.
3. If GO: Phase 1 scaffold; hand this README to the build agent.
4. Draft launch post skeleton (HN/dev.to) only after Gate-0 numbers exist — the post is the numbers.
