"""Browser test: open emitted HTML, run a canned query, assert rows render.

Needs `pip install playwright pytest-playwright && playwright install chromium`
and network access to jsDelivr (duckdb-wasm bundle). Skipped otherwise.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from awsnap.emit.html import render_html
from awsnap.emit.parquet import write_metadata_parquet, write_resources_parquet
from awsnap.model import RunMetadata, make_resource

pytest.importorskip("playwright")

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _build_html(tmp_path: Path) -> Path:
    resources = [
        make_resource(
            arn=f"arn:aws:s3:::bucket-{i}",
            resource_type="AWS::S3::Bucket",
            region="",
            name="",
            tags={} if i % 2 else {"env": "prod"},
            raw={},
            source="cloudcontrol",
            collected_at=NOW,
        )
        for i in range(5)
    ]
    meta = RunMetadata(
        account_id="123456789012",
        run_id="abc",
        awsnap_version="0.0.0",
        tier_used="cloudcontrol",
        regions=["us-east-1"],
        resource_count=len(resources),
        coverage_note="ok",
        collected_at=NOW,
    )
    rp = write_resources_parquet(resources, tmp_path / "r.parquet")
    mp = write_metadata_parquet(meta, tmp_path / "m.parquet")
    html = render_html(
        resources_parquet=rp.read_bytes(), metadata_parquet=mp.read_bytes(), meta=meta
    )
    out = tmp_path / "viewer.html"
    out.write_text(html, encoding="utf-8")
    return out


@pytest.mark.browser
def test_canned_query_renders_rows(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    html = _build_html(tmp_path)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html.as_uri())
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('ready')",
            timeout=60_000,
        )
        page.get_by_role("button", name="Untagged").click()
        page.wait_for_selector("#results-container table tbody tr", timeout=30_000)
        rows = page.locator("#results-container table tbody tr").count()
        browser.close()
    assert rows == 2
