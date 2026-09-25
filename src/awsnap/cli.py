from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import boto3

from awsnap import __version__
from awsnap.collect import collect, resolve_regions
from awsnap.emit.html import output_filename, render_html
from awsnap.emit.parquet import write_metadata_parquet, write_resources_parquet
from awsnap.model import RunMetadata, summarize_coverage
from awsnap.report import print_allowlist, print_coverage, print_download_hint, upload_and_presign

# Size threshold for warning (200 MB)
SIZE_WARN_BYTES = 200 * 1024 * 1024


def _sts_account_id(session: boto3.Session) -> str:
    """Get AWS account ID from STS.

    Args:
        session: boto3 Session

    Returns:
        AWS account ID string
    """
    # AIDEV-READONLY: sts:GetCallerIdentity
    sts = session.client("sts")
    response = sts.get_caller_identity()
    return response["Account"]


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for awsnap CLI.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="awsnap",
        description="Snapshot an AWS account into one offline, SQL-queryable HTML file.",
    )

    parser.add_argument(
        "--regions",
        type=str,
        default="",
        help='Regions (CSV or "all"; default: current region)',
    )

    parser.add_argument(
        "--tier",
        type=str,
        choices=["auto", "config", "cloudcontrol", "tagging"],
        default="auto",
        help="Collection tier (default: auto)",
    )

    parser.add_argument(
        "--out",
        type=str,
        default="~/awsnap",
        help="Output directory (default: ~/awsnap)",
    )

    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=None,
        help="S3 bucket for uploading (optional)",
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Max workers for collectors (default: 8)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-collector timing and coverage",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def run(args: argparse.Namespace, session: boto3.Session | None = None) -> Path:
    """Run awsnap collection and output.

    Args:
        args: Parsed arguments from ArgumentParser
        session: Optional boto3 Session (default: create new session)

    Returns:
        Path to generated HTML file
    """
    # Setup
    session = session or boto3.Session()
    print_allowlist(args.s3_bucket)

    # Get account ID and timestamps
    account_id = _sts_account_id(session)
    collected_at = datetime.now(timezone.utc)
    run_id = uuid4().hex[:12]

    # Resolve regions
    regions = resolve_regions(session, args.regions if args.regions else None)

    # Collect resources
    collect_output = collect(
        session,
        regions=regions,
        tier=args.tier,
        account_id=account_id,
        collected_at=collected_at,
        max_workers=args.max_workers,
    )

    # Create metadata
    coverage_note = summarize_coverage(collect_output.coverage)
    metadata = RunMetadata(
        account_id=account_id,
        run_id=run_id,
        awsnap_version=__version__,
        tier_used=collect_output.tier_used,
        regions=regions,
        resource_count=len(collect_output.resources),
        coverage_note=coverage_note,
        collected_at=collected_at,
    )

    # Create output directory
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write parquets to temp files, then embed in HTML
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Write parquets
        resources_parquet_path = tmp_path / "resources.parquet"
        metadata_parquet_path = tmp_path / "metadata.parquet"

        write_resources_parquet(collect_output.resources, resources_parquet_path)
        write_metadata_parquet(metadata, metadata_parquet_path)

        # Read parquets as bytes
        resources_bytes = resources_parquet_path.read_bytes()
        metadata_bytes = metadata_parquet_path.read_bytes()

    # Render HTML
    html_content = render_html(
        resources_parquet=resources_bytes,
        metadata_parquet=metadata_bytes,
        meta=metadata,
    )

    # Write HTML file
    output_name = output_filename(metadata)
    output_path = out_dir / output_name
    output_path.write_text(html_content, encoding="utf-8")

    # Warn if file is too large
    file_size = output_path.stat().st_size
    if file_size > SIZE_WARN_BYTES:
        sys.stderr.write(
            f"Warning: output file size {file_size / 1024 / 1024:.1f} MB > 200 MB. "
            "Consider using --regions to narrow the collection.\n"
        )

    # Verbose output
    if args.verbose:
        print_coverage(collect_output.coverage)

    # Upload to S3 if bucket specified
    if args.s3_bucket:
        url = upload_and_presign(session, output_path, args.s3_bucket)
        print(f"S3 URL: {url}")

    print(f"Resources: {metadata.resource_count} (tier={metadata.tier_used})")

    # Print download hint
    print_download_hint(output_path)

    return output_path


def main(argv: list[str] | None = None) -> int:
    """Main entry point for awsnap CLI.

    Args:
        argv: Optional command-line arguments (default: sys.argv[1:])

    Returns:
        Exit code (0 on success, 1 on error)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        run(args)
        return 0
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
