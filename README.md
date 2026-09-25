# awsnap

One command in AWS CloudShell → your entire AWS account as a single, offline, SQL-queryable HTML file (DuckDB-WASM + embedded Parquet).

**Status: pre-release, Gate-0 not yet run.** The full spec lives in [RDD.md](RDD.md). Gate-0 kill criteria and how to measure them: [spike/gate0.md](spike/gate0.md).

## Try it (from source)

```bash
# In AWS CloudShell (or any shell with read-only AWS creds):
curl -sL https://raw.githubusercontent.com/ejoliet/awsnap/main/bootstrap.sh | AWSNAP_VERSION=main sh
# → prints the API allowlist, collects, writes ~/awsnap/awsnap-<account>-<date>.html
```

IAM needed: `ViewOnlyAccess` or equivalent. Every AWS call is read-only; the allowlist is printed before anything runs. Optional `--s3-bucket` adds `s3:PutObject` on that bucket only.

## Develop

```bash
make venv && make lint && make test
```
