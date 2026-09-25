from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from awsnap.model import Coverage, Resource


def collect_tagging(
    session: boto3.Session,
    region: str,
    collected_at: datetime,
    client: object | None = None,
) -> tuple[list[Resource], Coverage]:
    """Collect resources from ResourceGroupsTaggingAPI."""
    from awsnap.model import Coverage, make_resource, parse_arn

    if client is None:
        # AIDEV-READONLY: tag:GetResources
        client = session.client("resourcegroupstaggingapi", region_name=region)

    resources: list[Resource] = []
    coverage_ok = True
    coverage_note = ""
    started = time.perf_counter()

    try:
        pagination_token: str | None = None

        while True:
            kwargs = {"ResourcesPerPage": 100}
            if pagination_token:
                kwargs["PaginationToken"] = pagination_token

            response = client.get_resources(**kwargs)

            for item in response.get("ResourceTagMappingList", []):
                arn = item.get("ResourceARN", "")
                tags_raw = item.get("Tags", [])

                # Convert tags from [{"Key","Value"}] to dict
                tags_dict: dict[str, str] = {}
                if isinstance(tags_raw, list):
                    for tag in tags_raw:
                        if isinstance(tag, dict):
                            key = tag.get("Key", "")
                            value = tag.get("Value", "")
                            if key:
                                tags_dict[key] = value

                # Parse ARN to get service and resource type
                region_from_arn = ""
                try:
                    arn_parts = parse_arn(arn)
                    service = arn_parts.service
                    region_from_arn = arn_parts.region
                    # Extract resource type from ARN resource part
                    resource_part = arn_parts.resource
                    if "/" in resource_part:
                        resource_type = service + ":" + resource_part.split("/")[0]
                    elif ":" in resource_part:
                        resource_type = service + ":" + resource_part.split(":")[0]
                    else:
                        resource_type = service
                except (ValueError, AttributeError):
                    service = "unknown"
                    resource_type = "unknown"

                resource = make_resource(
                    arn=arn,
                    resource_type=resource_type,
                    region=region_from_arn,
                    name="",
                    tags=tags_dict,
                    raw={},
                    source="tagging",
                    collected_at=collected_at,
                )
                resources.append(resource)

            pagination_token = response.get("PaginationToken")
            if not pagination_token:
                break

    except Exception as e:
        coverage_ok = False
        coverage_note = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))

    coverage = Coverage(
        tier="tagging",
        collector="tagging",
        region=region,
        ok=coverage_ok,
        count=len(resources),
        seconds=round(time.perf_counter() - started, 3),
        note=coverage_note,
    )

    return resources, coverage
