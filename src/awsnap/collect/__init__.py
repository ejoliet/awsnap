from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import boto3

from awsnap.model import Coverage, Resource, dedup


@dataclass
class CollectOutput:
    """Output from collect() operation."""

    resources: list[Resource]
    coverage: list[Coverage]
    tier_used: str


def resolve_regions(session: boto3.Session, regions_arg: str | None) -> list[str]:
    """Resolve region list from argument."""
    if not regions_arg:
        region = session.region_name or "us-east-1"
        return [region]

    if regions_arg == "all":
        # AIDEV-READONLY: ec2:DescribeRegions
        ec2 = session.client("ec2", region_name="us-east-1")
        response = ec2.describe_regions(AllRegions=False)
        return sorted(r["RegionName"] for r in response.get("Regions", []))

    return [r.strip() for r in regions_arg.split(",")]


def collect(
    session: boto3.Session,
    *,
    regions: list[str],
    tier: str,
    account_id: str,
    collected_at: datetime,
    max_workers: int = 8,
) -> CollectOutput:
    """Collect resources from AWS.

    Tiers:
    - 'config': Use AWS Config if recorder is on
    - 'cloudcontrol': Use CloudControl
    - 'tagging': Use ResourceGroupsTaggingAPI
    - 'auto': Use config if available, fall back to cloudcontrol, then tagging
    """
    from awsnap.collect.cloudcontrol import collect_cloudcontrol
    from awsnap.collect.config_sql import collect_config, recorder_on
    from awsnap.collect.tagging import collect_tagging

    all_resources: list[Resource] = []
    all_coverage: list[Coverage] = []
    tier_used_per_region: dict[str, str] = {}

    for region in regions:
        region_resources: list[Resource] = []
        region_coverage: list[Coverage] = []

        if tier == "config":
            if recorder_on(session, region):
                resources, coverage = collect_config(
                    session, region, collected_at
                )
                region_resources.extend(resources)
                region_coverage.append(coverage)
                tier_used_per_region[region] = "config"
            else:
                # Create a coverage entry for skipped config
                region_coverage.append(
                    Coverage(
                        tier="config",
                        collector="config",
                        region=region,
                        ok=True,
                        count=0,
                        seconds=0.0,
                        note="recorder_off",
                    )
                )
                tier_used_per_region[region] = "config"

        elif tier == "cloudcontrol":
            include_global = regions[0] == region
            resources, cloudcontrol_coverage = collect_cloudcontrol(
                session,
                region,
                collected_at,
                account_id,
                max_workers=max_workers,
                include_global=include_global,
            )
            region_resources.extend(resources)
            region_coverage.extend(cloudcontrol_coverage)
            tier_used_per_region[region] = "cloudcontrol"

        elif tier == "tagging":
            resources, coverage = collect_tagging(session, region, collected_at)
            region_resources.extend(resources)
            region_coverage.append(coverage)
            tier_used_per_region[region] = "tagging"

        elif tier == "auto":
            if recorder_on(session, region):
                resources, coverage = collect_config(
                    session, region, collected_at
                )
                region_resources.extend(resources)
                region_coverage.append(coverage)
                tier_used_per_region[region] = "config"
            else:
                include_global = regions[0] == region
                resources, cloudcontrol_coverage = collect_cloudcontrol(
                    session,
                    region,
                    collected_at,
                    account_id,
                    max_workers=max_workers,
                    include_global=include_global,
                )
                region_resources.extend(resources)
                region_coverage.extend(cloudcontrol_coverage)
                tier_used_per_region[region] = "cloudcontrol"

            # Always add tagging for enrichment
            resources, coverage = collect_tagging(session, region, collected_at)
            region_resources.extend(resources)
            region_coverage.append(coverage)

        all_resources.extend(region_resources)
        all_coverage.extend(region_coverage)

    # Determine tier_used string
    tier_values = set(tier_used_per_region.values())
    if len(tier_values) == 1:
        tier_used = tier_values.pop()
    else:
        tier_used = "mixed"

    # Dedup resources
    deduped = dedup(all_resources)

    return CollectOutput(
        resources=deduped, coverage=all_coverage, tier_used=tier_used
    )
