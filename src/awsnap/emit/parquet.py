from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb

from awsnap.model import Resource, RunMetadata


def write_resources_parquet(resources: Sequence[Resource], out_path: Path) -> Path:
    """Write resources to Parquet with ZSTD compression.

    Args:
        resources: Sequence of Resource objects
        out_path: Output path for the Parquet file

    Returns:
        out_path (the Path that was written)
    """
    conn = duckdb.connect(":memory:")

    # Create table with proper schema
    conn.execute(
        """
        CREATE TABLE resources(
            arn VARCHAR,
            service VARCHAR,
            resource_type VARCHAR,
            region VARCHAR,
            name VARCHAR,
            tags VARCHAR,
            raw VARCHAR,
            source VARCHAR,
            collected_at TIMESTAMP
        )
        """
    )

    # Insert resources
    for resource in resources:
        row = resource.as_row()
        conn.execute(
            """
            INSERT INTO resources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    # Export to Parquet with ZSTD compression, sorted by ARN
    out_str = str(out_path)
    escaped_path = out_str.replace("'", "''")
    conn.execute(
        f"COPY (SELECT * FROM resources ORDER BY arn) TO '{escaped_path}'"
        " (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    conn.close()
    return out_path


def write_metadata_parquet(meta: RunMetadata, out_path: Path) -> Path:
    """Write metadata to Parquet with ZSTD compression.

    Args:
        meta: RunMetadata object
        out_path: Output path for the Parquet file

    Returns:
        out_path (the Path that was written)
    """
    conn = duckdb.connect(":memory:")

    # Create table with proper schema
    conn.execute(
        """
        CREATE TABLE metadata(
            account_id VARCHAR,
            run_id VARCHAR,
            awsnap_version VARCHAR,
            tier_used VARCHAR,
            regions VARCHAR,
            resource_count BIGINT,
            coverage_note VARCHAR,
            collected_at TIMESTAMP
        )
        """
    )

    # Convert metadata to dict and insert
    meta_dict = meta.as_dict()
    conn.execute(
        """
        INSERT INTO metadata
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            meta_dict["account_id"],
            meta_dict["run_id"],
            meta_dict["awsnap_version"],
            meta_dict["tier_used"],
            meta_dict["regions"],
            meta_dict["resource_count"],
            meta_dict["coverage_note"],
            meta_dict["collected_at"],
        ),
    )

    # Export to Parquet with ZSTD compression
    out_str = str(out_path)
    escaped_path = out_str.replace("'", "''")
    conn.execute(
        f"COPY (SELECT * FROM metadata) TO '{escaped_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    conn.close()
    return out_path


def read_parquet_rows(path: Path) -> list[tuple]:
    """Read Parquet file and return all rows as list of tuples.

    Args:
        path: Path to the Parquet file

    Returns:
        List of tuples representing rows
    """
    conn = duckdb.connect(":memory:")
    path_str = str(path)
    escaped_path = path_str.replace("'", "''")
    result = conn.execute(f"SELECT * FROM read_parquet('{escaped_path}')").fetchall()
    conn.close()
    return result
