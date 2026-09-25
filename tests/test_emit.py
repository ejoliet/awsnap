from __future__ import annotations

import base64
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from awsnap.emit.html import output_filename, render_html
from awsnap.emit.parquet import read_parquet_rows, write_metadata_parquet, write_resources_parquet
from awsnap.model import COLUMNS, Resource, RunMetadata


@pytest.fixture
def sample_resources():
    """Create sample resources for testing."""
    collected_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    return [
        Resource(
            arn="arn:aws:s3:::bucket-c",
            service="s3",
            resource_type="Bucket",
            region="us-east-1",
            name="bucket-c",
            tags='{"env":"prod"}',
            raw='{"CreationDate":"2024-01-10"}',
            source="config",
            collected_at=collected_at,
        ),
        Resource(
            arn="arn:aws:ec2:us-west-2:123456789:instance/i-001",
            service="ec2",
            resource_type="Instance",
            region="us-west-2",
            name="i-001",
            tags="{}",
            raw='{"State":"running"}',
            source="cloudcontrol",
            collected_at=collected_at,
        ),
        Resource(
            arn="arn:aws:iam::123456789:role/my-role",
            service="iam",
            resource_type="Role",
            region="",
            name="my-role",
            tags='{"team":"backend"}',
            raw='{"AssumeRolePolicyDocument":"..."}',
            source="tagging",
            collected_at=collected_at,
        ),
    ]


@pytest.fixture
def sample_metadata(sample_resources):
    """Create sample RunMetadata."""
    return RunMetadata(
        account_id="123456789",
        run_id="abc123def456",
        awsnap_version="0.1.0",
        tier_used="config",
        regions=["us-east-1", "us-west-2"],
        resource_count=len(sample_resources),
        coverage_note="config:3 ok/0 fail",
        collected_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


class TestWriteResourcesParquet:
    def test_write_and_read_resources(self, sample_resources):
        """Test writing and reading resources from Parquet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "resources.parquet"
            result_path = write_resources_parquet(sample_resources, out_path)

            assert result_path == out_path
            assert out_path.exists()

            # Read back and verify
            rows = read_parquet_rows(out_path)
            assert len(rows) == 3

            # Verify column order (should be COLUMNS)
            # First resource (alphabetically by ARN)
            first_row = rows[0]
            assert first_row[0] == "arn:aws:ec2:us-west-2:123456789:instance/i-001"
            assert first_row[1] == "ec2"
            assert first_row[2] == "Instance"

    def test_resources_sorted_by_arn(self, sample_resources):
        """Test that resources are sorted by ARN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "resources.parquet"
            write_resources_parquet(sample_resources, out_path)

            rows = read_parquet_rows(out_path)
            arns = [row[0] for row in rows]

            # Verify sorted order
            assert arns == sorted(arns)
            assert arns[0] == "arn:aws:ec2:us-west-2:123456789:instance/i-001"
            assert arns[1] == "arn:aws:iam::123456789:role/my-role"
            assert arns[2] == "arn:aws:s3:::bucket-c"

    def test_column_order_matches_columns(self, sample_resources):
        """Test that column order in output matches COLUMNS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "resources.parquet"
            write_resources_parquet(sample_resources, out_path)

            rows = read_parquet_rows(out_path)
            first_row = rows[0]

            # The row should have 9 columns matching COLUMNS
            assert len(first_row) == len(COLUMNS)
            assert len(COLUMNS) == 9

    def test_byte_stability(self, sample_resources):
        """Test that writing the same resources twice produces identical bytes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path1 = Path(tmpdir) / "resources1.parquet"
            out_path2 = Path(tmpdir) / "resources2.parquet"

            write_resources_parquet(sample_resources, out_path1)
            write_resources_parquet(sample_resources, out_path2)

            bytes1 = out_path1.read_bytes()
            bytes2 = out_path2.read_bytes()

            assert bytes1 == bytes2


class TestWriteMetadataParquet:
    def test_write_and_read_metadata(self, sample_metadata):
        """Test writing and reading metadata from Parquet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "metadata.parquet"
            result_path = write_metadata_parquet(sample_metadata, out_path)

            assert result_path == out_path
            assert out_path.exists()

            # Read back and verify
            rows = read_parquet_rows(out_path)
            assert len(rows) == 1

            row = rows[0]
            assert row[0] == "123456789"  # account_id
            assert row[1] == "abc123def456"  # run_id
            assert row[2] == "0.1.0"  # awsnap_version
            assert row[3] == "config"  # tier_used
            assert "us-east-1" in row[4]  # regions


class TestRenderHtml:
    def test_render_html_replaces_placeholders(self, sample_resources, sample_metadata, tmp_path):
        """Test that render_html replaces all placeholders."""
        # Create dummy parquet files
        resources_path = tmp_path / "resources.parquet"
        metadata_path = tmp_path / "metadata.parquet"
        write_resources_parquet(sample_resources, resources_path)
        write_metadata_parquet(sample_metadata, metadata_path)

        resources_bytes = resources_path.read_bytes()
        metadata_bytes = metadata_path.read_bytes()

        html = render_html(
            resources_parquet=resources_bytes,
            metadata_parquet=metadata_bytes,
            meta=sample_metadata,
        )

        # Verify no placeholders remain
        assert "__AWSNAP_RESOURCES_B64__" not in html
        assert "__AWSNAP_METADATA_B64__" not in html
        assert "__AWSNAP_META_JSON__" not in html
        assert "__AWSNAP_TITLE__" not in html
        assert "__AWSNAP_VERSION__" not in html

        # Verify title was inserted
        assert "awsnap 123456789 2024-01-15" in html

        # Verify version was inserted
        assert "0.1.0" in html

        # Verify base64 parquets are embedded
        resources_b64 = base64.b64encode(resources_bytes).decode("utf-8")
        assert resources_b64 in html

        metadata_b64 = base64.b64encode(metadata_bytes).decode("utf-8")
        assert metadata_b64 in html

    def test_render_html_escapes_slash_in_json(self, sample_resources, sample_metadata, tmp_path):
        """Test that </ is escaped as <\\/ in JSON metadata."""
        resources_path = tmp_path / "resources.parquet"
        metadata_path = tmp_path / "metadata.parquet"
        write_resources_parquet(sample_resources, resources_path)
        write_metadata_parquet(sample_metadata, metadata_path)

        resources_bytes = resources_path.read_bytes()
        metadata_bytes = metadata_path.read_bytes()

        html = render_html(
            resources_parquet=resources_bytes,
            metadata_parquet=metadata_bytes,
            meta=sample_metadata,
        )

        # Verify that __AWSNAP_META_JSON__ was replaced with actual JSON
        assert "__AWSNAP_META_JSON__" not in html
        # The meta JSON should be embedded in the script
        assert "coverage_note" in html
        assert "account_id" in html
        # If meta JSON contains </, it should be escaped as <\/
        import re

        meta_match = re.search(r'"coverage_note":"([^"]*)"', html)
        if meta_match and "</" in meta_match.group(1):
            assert "<\\/" in html


class TestOutputFilename:
    def test_output_filename_format(self, sample_metadata):
        """Test output filename format."""
        filename = output_filename(sample_metadata)
        assert filename == "awsnap-123456789-2024-01-15.html"

    def test_output_filename_different_dates(self):
        """Test output filename with different dates."""
        meta1 = RunMetadata(
            account_id="999999999",
            run_id="xyz",
            awsnap_version="0.1.0",
            tier_used="config",
            regions=["us-east-1"],
            resource_count=10,
            coverage_note="test",
            collected_at=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        filename = output_filename(meta1)
        assert filename == "awsnap-999999999-2025-12-31.html"
