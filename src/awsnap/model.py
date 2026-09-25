from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

COLUMNS: tuple[str, ...] = (
    "arn",
    "service",
    "resource_type",
    "region",
    "name",
    "tags",
    "raw",
    "source",
    "collected_at",
)
SOURCE_PRECEDENCE: dict[str, int] = {"config": 0, "cloudcontrol": 1, "tagging": 2}


@dataclass(frozen=True)
class ArnParts:
    partition: str
    service: str
    region: str
    account: str
    resource: str


def parse_arn(arn: str) -> ArnParts:
    """Parse an ARN into its components.

    Args:
        arn: ARN string, e.g., "arn:aws:s3:::bucket"

    Returns:
        ArnParts with partition, service, region, account, resource

    Raises:
        ValueError: if ARN does not have 6+ colon-separated parts or doesn't start with "arn"
    """
    parts = arn.split(":")
    if len(parts) < 6 or parts[0] != "arn":
        raise ValueError(f"Invalid ARN: {arn}")

    partition = parts[1]
    service = parts[2]
    region = parts[3]
    account = parts[4]
    resource = ":".join(parts[5:])

    return ArnParts(
        partition=partition, service=service, region=region, account=account, resource=resource
    )


def canonical_json(obj: object) -> str:
    """Serialize object to JSON with sorted keys and compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Resource:
    arn: str
    service: str
    resource_type: str
    region: str
    name: str
    tags: str
    raw: str
    source: str
    collected_at: datetime

    def as_row(self) -> tuple:
        """Return resource values as tuple in COLUMNS order."""
        return (
            self.arn,
            self.service,
            self.resource_type,
            self.region,
            self.name,
            self.tags,
            self.raw,
            self.source,
            self.collected_at,
        )


def make_resource(
    *,
    arn: str,
    resource_type: str,
    region: str,
    name: str,
    tags: dict[str, str],
    raw: dict,
    source: str,
    collected_at: datetime,
) -> Resource:
    """Create a Resource with defaults and validation.

    Args:
        arn: Resource ARN
        resource_type: Resource type
        region: Region (falls back to ARN region if empty)
        name: Resource name (falls back to last segment of ARN if empty)
        tags: Tags dict
        raw: Raw properties dict
        source: Collector source (config/cloudcontrol/tagging)
        collected_at: Collection timestamp

    Returns:
        Resource instance
    """
    parts = parse_arn(arn)
    service = parts.service

    if region == "":
        region = parts.region

    if name == "":
        # AIDEV-NOTE: extract last path segment from resource
        resource_parts = parts.resource.split("/")
        name = resource_parts[-1]

    tags_json = canonical_json(tags)
    raw_json = canonical_json(raw)

    return Resource(
        arn=arn,
        service=service,
        resource_type=resource_type,
        region=region,
        name=name,
        tags=tags_json,
        raw=raw_json,
        source=source,
        collected_at=collected_at,
    )


def dedup(resources: Iterable[Resource]) -> list[Resource]:
    """Deduplicate resources by ARN, preferring lower SOURCE_PRECEDENCE.

    If winner has empty tags and any loser has non-empty tags, take loser's tags.
    Returns sorted by ARN for stable/diffable output.

    Args:
        resources: Iterable of Resource objects

    Returns:
        Deduplicated list of Resource objects sorted by ARN
    """
    # Group by ARN
    by_arn: dict[str, list[Resource]] = {}
    for res in resources:
        if res.arn not in by_arn:
            by_arn[res.arn] = []
        by_arn[res.arn].append(res)

    result: list[Resource] = []

    for _arn, candidates in by_arn.items():
        # Find winner with lowest SOURCE_PRECEDENCE
        winner = min(candidates, key=lambda r: SOURCE_PRECEDENCE.get(r.source, 999))

        # Check if winner has empty tags and any loser has non-empty tags
        if winner.tags == "{}":
            for loser in candidates:
                if loser is not winner and loser.tags != "{}":
                    # AIDEV-NOTE: take loser's tags, reconstruct winner with new tags
                    winner = Resource(
                        arn=winner.arn,
                        service=winner.service,
                        resource_type=winner.resource_type,
                        region=winner.region,
                        name=winner.name,
                        tags=loser.tags,
                        raw=winner.raw,
                        source=winner.source,
                        collected_at=winner.collected_at,
                    )
                    break

        result.append(winner)

    # Sort by ARN for stable/diffable output
    result.sort(key=lambda r: r.arn)

    return result


@dataclass
class Coverage:
    tier: str
    collector: str
    region: str
    ok: bool
    count: int
    seconds: float
    note: str = ""


@dataclass
class RunMetadata:
    account_id: str
    run_id: str
    awsnap_version: str
    tier_used: str
    regions: list[str]
    resource_count: int
    coverage_note: str
    collected_at: datetime

    def as_dict(self) -> dict:
        """Convert to dict with regions joined and collected_at as isoformat."""
        return {
            "account_id": self.account_id,
            "run_id": self.run_id,
            "awsnap_version": self.awsnap_version,
            "tier_used": self.tier_used,
            "regions": ",".join(self.regions),
            "resource_count": self.resource_count,
            "coverage_note": self.coverage_note,
            "collected_at": self.collected_at.isoformat(),
        }


def summarize_coverage(coverage: list[Coverage]) -> str:
    """Generate a human-readable summary of coverage.

    Format: "tier:ok_count ok/fail_count fail [notes]; ..."
    Notes grouped by note text per tier.

    Args:
        coverage: List of Coverage objects

    Returns:
        Summary string
    """
    # Group by tier
    by_tier: dict[str, list[Coverage]] = {}
    for cov in coverage:
        if cov.tier not in by_tier:
            by_tier[cov.tier] = []
        by_tier[cov.tier].append(cov)

    parts: list[str] = []

    for tier in sorted(by_tier.keys()):
        covs = by_tier[tier]
        ok_count = sum(1 for c in covs if c.ok)
        fail_count = sum(1 for c in covs if not c.ok)

        # Group notes by text
        notes_by_text: dict[str, int] = {}
        for cov in covs:
            if not cov.ok and cov.note:
                notes_by_text[cov.note] = notes_by_text.get(cov.note, 0) + 1

        # Build note summary
        note_str = ""
        if notes_by_text:
            note_parts = [f"{note} x{count}" for note, count in sorted(notes_by_text.items())]
            note_str = f" ({'; '.join(note_parts)})"

        parts.append(f"{tier}:{ok_count} ok/{fail_count} fail{note_str}")

    return "; ".join(parts)
