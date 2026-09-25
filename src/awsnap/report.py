from __future__ import annotations

import sys
from pathlib import Path

import boto3

from awsnap.model import Coverage

API_ALLOWLIST: tuple[str, ...] = (
    "sts:GetCallerIdentity",
    "config:DescribeConfigurationRecorderStatus",
    "config:SelectResourceConfig",
    "cloudcontrol:ListResources",
    "tag:GetResources",
    "ec2:DescribeRegions",
)


def print_allowlist(s3_bucket: str | None, out=sys.stdout) -> None:
    """Print the AWS API allowlist required by awsnap.

    Args:
        s3_bucket: Optional S3 bucket name to add s3:PutObject permission
        out: Output file-like object (default sys.stdout)
    """
    lines = ["API allowlist for awsnap:"]
    for api in API_ALLOWLIST:
        lines.append(f"  {api}")

    if s3_bucket:
        lines.append(f"  s3:PutObject (bucket {s3_bucket} only)")

    out.write("\n".join(lines) + "\n")


def print_coverage(coverage: list[Coverage], out=sys.stdout) -> None:
    """Print coverage report as aligned table.

    Args:
        coverage: List of Coverage objects
        out: Output file-like object (default sys.stdout)
    """
    if not coverage:
        return

    # Header
    header = (
        f"{'tier':<15} {'collector':<15} {'region':<12} {'ok':<4} "
        f"{'count':<6} {'seconds':<10} {'note':<20}\n"
    )
    out.write(header)
    out.write("-" * 82 + "\n")

    # Rows
    for cov in coverage:
        ok_str = "yes" if cov.ok else "no"
        row = (
            f"{cov.tier:<15} {cov.collector:<15} {cov.region:<12} {ok_str:<4} "
            f"{cov.count:<6} {cov.seconds:<10.2f} {cov.note:<20}\n"
        )
        out.write(row)


def upload_and_presign(session: boto3.Session, path: Path, bucket: str, expires: int = 3600) -> str:
    """Upload file to S3 and return presigned URL.

    Args:
        session: boto3 Session
        path: Path to file to upload
        bucket: S3 bucket name
        expires: URL expiration time in seconds (default 3600)

    Returns:
        Presigned URL
    """
    # AIDEV-WRITE: s3:PutObject (opt-in, user bucket only)
    s3 = session.client("s3")
    key = path.name

    with open(path, "rb") as f:
        s3.put_object(Bucket=bucket, Key=key, Body=f.read())

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )

    return url


def print_download_hint(path: Path, out=sys.stdout) -> None:
    """Print hint for downloading the file.

    Args:
        path: Path to the output file
        out: Output file-like object (default sys.stdout)
    """
    out.write(f"Download: Actions → Download file → {path}\n")
