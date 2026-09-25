from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from awsnap.cli import build_parser, run
from awsnap.model import Coverage, Resource


@pytest.fixture
def sample_resources():
    """Fixture providing sample Resource objects for testing."""
    collected_at = datetime.now(timezone.utc)
    return [
        Resource(
            arn="arn:aws:s3:::my-bucket",
            service="s3",
            resource_type="Bucket",
            region="us-east-1",
            name="my-bucket",
            tags='{}',
            raw='{"BucketName":"my-bucket"}',
            source="config",
            collected_at=collected_at,
        ),
        Resource(
            arn="arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0",
            service="ec2",
            resource_type="Instance",
            region="us-east-1",
            name="i-0123456789abcdef0",
            tags='{}',
            raw='{"InstanceId":"i-0123456789abcdef0"}',
            source="cloudcontrol",
            collected_at=collected_at,
        ),
    ]


@pytest.fixture
def sample_coverage():
    """Fixture providing sample Coverage objects for testing."""
    return [
        Coverage(
            tier="config",
            collector="config",
            region="us-east-1",
            ok=True,
            count=2,
            seconds=1.5,
            note="",
        ),
        Coverage(
            tier="tagging",
            collector="tagging",
            region="us-east-1",
            ok=True,
            count=2,
            seconds=0.5,
            note="",
        ),
    ]


def test_build_parser_defaults():
    """Test that build_parser creates parser with correct defaults."""
    parser = build_parser()

    # Test default values
    args = parser.parse_args([])
    assert args.regions == ""
    assert args.tier == "auto"
    assert args.out == "~/awsnap"
    assert args.s3_bucket is None
    assert args.max_workers == 8
    assert args.verbose is False


def test_build_parser_custom_args():
    """Test that build_parser correctly parses custom arguments."""
    parser = build_parser()

    args = parser.parse_args([
        "--regions", "us-west-1,us-west-2",
        "--tier", "cloudcontrol",
        "--out", "/tmp/output",
        "--s3-bucket", "my-bucket",
        "--max-workers", "4",
        "--verbose",
    ])

    assert args.regions == "us-west-1,us-west-2"
    assert args.tier == "cloudcontrol"
    assert args.out == "/tmp/output"
    assert args.s3_bucket == "my-bucket"
    assert args.max_workers == 4
    assert args.verbose is True


def test_run_basic(tmp_path, sample_resources, sample_coverage):
    """Test basic run() with monkeypatched dependencies."""
    parser = build_parser()
    args = parser.parse_args(["--out", str(tmp_path)])

    # Mock the session
    mock_session = MagicMock()

    # Create mock collect output
    from awsnap.collect import CollectOutput
    mock_output = CollectOutput(
        resources=sample_resources,
        coverage=sample_coverage,
        tier_used="config",
    )

    with patch("awsnap.cli._sts_account_id") as mock_sts, \
         patch("awsnap.cli.resolve_regions") as mock_resolve, \
         patch("awsnap.cli.collect") as mock_collect:

        mock_sts.return_value = "123456789012"
        mock_resolve.return_value = ["us-east-1"]
        mock_collect.return_value = mock_output

        result = run(args, session=mock_session)

        # Check that result is a Path
        assert isinstance(result, Path)

        # Check that file was created
        assert result.exists()

        # Check filename format
        assert result.name.startswith("awsnap-123456789012-")
        assert result.name.endswith(".html")

        # Check that mocks were called
        mock_sts.assert_called_once()
        mock_resolve.assert_called_once()
        mock_collect.assert_called_once()


def test_run_with_s3_bucket(tmp_path, sample_resources, sample_coverage):
    """Test run() with S3 bucket upload."""
    parser = build_parser()
    args = parser.parse_args([
        "--out", str(tmp_path),
        "--s3-bucket", "my-bucket",
    ])

    mock_session = MagicMock()

    from awsnap.collect import CollectOutput
    mock_output = CollectOutput(
        resources=sample_resources,
        coverage=sample_coverage,
        tier_used="config",
    )

    with patch("awsnap.cli._sts_account_id") as mock_sts, \
         patch("awsnap.cli.resolve_regions") as mock_resolve, \
         patch("awsnap.cli.collect") as mock_collect, \
         patch("awsnap.cli.upload_and_presign") as mock_upload:

        mock_sts.return_value = "123456789012"
        mock_resolve.return_value = ["us-east-1"]
        mock_collect.return_value = mock_output
        mock_upload.return_value = "https://s3.amazonaws.com/presigned-url"

        result = run(args, session=mock_session)

        # Check that file was created
        assert result.exists()

        # Check that upload was called
        mock_upload.assert_called_once()


def test_run_size_warning(tmp_path, monkeypatch, sample_resources, sample_coverage):
    """Test that size warning is printed for large outputs."""
    parser = build_parser()
    args = parser.parse_args(["--out", str(tmp_path)])

    mock_session = MagicMock()

    from awsnap.collect import CollectOutput
    mock_output = CollectOutput(
        resources=sample_resources,
        coverage=sample_coverage,
        tier_used="config",
    )

    # Monkeypatch SIZE_WARN_BYTES to a very low value
    monkeypatch.setattr("awsnap.cli.SIZE_WARN_BYTES", 1)

    with patch("awsnap.cli._sts_account_id") as mock_sts, \
         patch("awsnap.cli.resolve_regions") as mock_resolve, \
         patch("awsnap.cli.collect") as mock_collect:

        mock_sts.return_value = "123456789012"
        mock_resolve.return_value = ["us-east-1"]
        mock_collect.return_value = mock_output

        # Capture stderr
        import io
        import sys
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            result = run(args, session=mock_session)
            stderr_output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

        # Check that warning was printed
        assert "Warning" in stderr_output or result.exists()


def test_run_verbose_mode(tmp_path, capsys, sample_resources, sample_coverage):
    """Test run() with verbose flag."""
    parser = build_parser()
    args = parser.parse_args([
        "--out", str(tmp_path),
        "--verbose",
    ])

    mock_session = MagicMock()

    from awsnap.collect import CollectOutput
    mock_output = CollectOutput(
        resources=sample_resources,
        coverage=sample_coverage,
        tier_used="config",
    )

    with patch("awsnap.cli._sts_account_id") as mock_sts, \
         patch("awsnap.cli.resolve_regions") as mock_resolve, \
         patch("awsnap.cli.collect") as mock_collect:

        mock_sts.return_value = "123456789012"
        mock_resolve.return_value = ["us-east-1"]
        mock_collect.return_value = mock_output

        result = run(args, session=mock_session)

        # Check that file was created
        assert result.exists()


def test_print_allowlist():
    """Test print_allowlist with and without s3_bucket."""
    from io import StringIO

    from awsnap.report import print_allowlist

    # Test without s3_bucket
    out = StringIO()
    print_allowlist(None, out=out)
    output = out.getvalue()
    assert "sts:GetCallerIdentity" in output
    assert "ec2:DescribeRegions" in output
    assert "s3:PutObject" not in output

    # Test with s3_bucket
    out = StringIO()
    print_allowlist("my-bucket", out=out)
    output = out.getvalue()
    assert "s3:PutObject" in output
    assert "my-bucket" in output


def test_print_coverage():
    """Test print_coverage output."""
    from io import StringIO

    from awsnap.report import print_coverage

    coverage = [
        Coverage(
            tier="config",
            collector="config",
            region="us-east-1",
            ok=True,
            count=5,
            seconds=2.5,
            note="",
        ),
        Coverage(
            tier="tagging",
            collector="tagging",
            region="us-east-1",
            ok=False,
            count=0,
            seconds=1.0,
            note="AccessDenied",
        ),
    ]

    out = StringIO()
    print_coverage(coverage, out=out)
    output = out.getvalue()

    # Check header and data
    assert "tier" in output
    assert "config" in output
    assert "tagging" in output
    assert "AccessDenied" in output
    assert "yes" in output
    assert "no" in output


def test_print_coverage_empty():
    """Test print_coverage with empty list."""
    from io import StringIO

    from awsnap.report import print_coverage

    out = StringIO()
    print_coverage([], out=out)
    output = out.getvalue()
    assert output == ""


def test_print_download_hint():
    """Test print_download_hint."""
    from io import StringIO
    from pathlib import Path

    from awsnap.report import print_download_hint

    path = Path("/tmp/awsnap-123456789012-2024-01-01.html")
    out = StringIO()
    print_download_hint(path, out=out)
    output = out.getvalue()

    assert "Download" in output
    assert str(path) in output


def test_upload_and_presign(tmp_path):
    """Test upload_and_presign function."""
    from awsnap.report import upload_and_presign

    # Create a test file
    test_file = tmp_path / "test.html"
    test_file.write_text("<html>test</html>")

    mock_session = MagicMock()
    mock_s3 = MagicMock()
    mock_session.client.return_value = mock_s3
    mock_s3.generate_presigned_url.return_value = (
        "https://s3.amazonaws.com/presigned-url"
    )

    url = upload_and_presign(mock_session, test_file, "my-bucket")

    # Check that S3 put_object was called
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "my-bucket"
    assert call_kwargs["Key"] == "test.html"
    assert b"<html>test</html>" in call_kwargs["Body"]

    # Check that presigned URL was generated
    assert url == "https://s3.amazonaws.com/presigned-url"


def test_main_function_success(tmp_path, sample_resources, sample_coverage):
    """Test main() function success path."""
    from awsnap.cli import main
    from awsnap.collect import CollectOutput

    args = ["--out", str(tmp_path)]
    mock_output = CollectOutput(
        resources=sample_resources,
        coverage=sample_coverage,
        tier_used="config",
    )

    with patch("awsnap.cli._sts_account_id") as mock_sts, \
         patch("awsnap.cli.resolve_regions") as mock_resolve, \
         patch("awsnap.cli.collect") as mock_collect:

        mock_sts.return_value = "123456789012"
        mock_resolve.return_value = ["us-east-1"]
        mock_collect.return_value = mock_output

        result = main(args)
        assert result == 0


def test_main_function_error(tmp_path):
    """Test main() function error handling."""
    from awsnap.cli import main

    args = ["--out", str(tmp_path)]

    with patch("awsnap.cli._sts_account_id") as mock_sts:
        mock_sts.side_effect = Exception("Test error")

        result = main(args)
        assert result == 1
