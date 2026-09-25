# Gate-0 Spike Results

**Status**: NOT YET RUN

This document tracks the three kill criteria for awsnap v0.1.0 as measured in CloudShell.

---

## Kill Criterion 1: duckdb Installation

**Goal**: `pip install --user duckdb` succeeds in < 2 min and fits quota.

**Command to run**:
```bash
time pip install --user duckdb
```

| Metric | Value |
|--------|-------|
| Install time (seconds) | TBD — run in CloudShell |
| .local disk usage (MB) | TBD — run in CloudShell |
| Success (yes/no) | TBD |

**Pass threshold**: < 120 seconds, < 500 MB

**GO / NO-GO**: [ ] GO [ ] NO-GO

---

## Kill Criterion 2: CloudControl Fallback Coverage

**Goal**: CloudControl collector covers ≥ ~80% of resources vs Config ground truth in a real account, in < 3 min.

**Command to run**:
```bash
awsnap --tier config --verbose
awsnap --tier cloudcontrol --verbose
# Each run prints "Resources: <n> (tier=...)" — compare the two counts.
# spike/gate0.sh runs both and greps that line.
```

| Metric | Config tier count | CloudControl tier count | Coverage % |
|--------|-------------------|------------------------|------------|
| Resource count | TBD | TBD | TBD |
| Collection time (seconds) | TBD | TBD | — |

**Pass threshold**: CloudControl coverage ≥ 80% of Config

**GO / NO-GO**: [ ] GO [ ] NO-GO

---

## Kill Criterion 3: HTML Viewer Execution

**Goal**: Parquet base64-embedded HTML with pinned duckdb-wasm executes a query on the embedded data in Chrome.

**Command to run**:
```bash
# Generate HTML snapshot
awsnap --out ./gate0-out

# Open in browser locally (download from CloudShell)
# Run a canned query (e.g., "By service")
# Assert row count > 0 and results render as table
```

| Metric | Result |
|--------|--------|
| HTML file generated | TBD |
| HTML file size (MB) | TBD |
| Viewer loads (yes/no) | TBD |
| Query executes (yes/no) | TBD |
| Results render as table (yes/no) | TBD |

**Pass threshold**: All yes

**GO / NO-GO**: [ ] GO [ ] NO-GO

---

## Overall Gate-0 Decision

**Team recommendation**: [ ] GO to Phase 1 [ ] Rethink and retry [ ] NO-GO, pivot

**Notes**:
- This document is a template; fill in measured numbers from CloudShell.
- Rows marked `TBD` indicate measurements to be taken during Gate-0 execution.
