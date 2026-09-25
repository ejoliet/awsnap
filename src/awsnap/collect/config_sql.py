from __future__ import annotations

import json
import time
from datetime import datetime
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from awsnap.model import Coverage, Resource


def recorder_on(
    session: boto3.Session, region: str, client: object | None = None
) -> bool:
    """Check if AWS Config recorder is on for a given region."""
    try:
        if client is None:
            # AIDEV-READONLY: config:DescribeConfigurationRecorderStatus
            client = session.client("config", region_name=region)
        response = client.describe_configuration_recorder_status()
        return any(
            r.get("recording") for r in response.get("ConfigurationRecordersStatus", [])
        )
    except Exception:
        return False


def collect_config(
    session: boto3.Session,
    region: str,
    collected_at: datetime,
    client: object | None = None,
) -> tuple[list[Resource], Coverage]:
    """Collect resources from AWS Config."""
    from awsnap.model import Coverage, make_resource

    if client is None:
        # AIDEV-READONLY: config:SelectResourceConfig
        client = session.client("config", region_name=region)

    resources: list[Resource] = []
    coverage_ok = True
    coverage_note = ""
    started = time.perf_counter()

    try:
        expression = (
            "SELECT arn, resourceType, resourceName, awsRegion, tags, configuration"
        )
        next_token: str | None = None

        while True:
            kwargs = {"Expression": expression, "Limit": 100}
            if next_token:
                kwargs["NextToken"] = next_token

            response = client.select_resource_config(**kwargs)

            for item_str in response.get("Results", []):
                item = json.loads(item_str)
                arn = item.get("arn", "")
                resource_type = item.get("resourceType", "")
                name = item.get("resourceName", "")
                region_item = item.get("awsRegion", "")
                tags_raw = item.get("tags", [])
                configuration = item.get("configuration", {})

                # Convert tags from list of {key,value} or {"key":..,"value":..}
                tags_dict: dict[str, str] = {}
                if isinstance(tags_raw, list):
                    for tag in tags_raw:
                        if isinstance(tag, dict):
                            if "key" in tag and "value" in tag:
                                tags_dict[tag["key"]] = tag["value"]
                            elif "Key" in tag and "Value" in tag:
                                tags_dict[tag["Key"]] = tag["Value"]

                resource = make_resource(
                    arn=arn,
                    resource_type=resource_type,
                    region=region_item,
                    name=name,
                    tags=tags_dict,
                    raw=configuration,
                    source="config",
                    collected_at=collected_at,
                )
                resources.append(resource)

            next_token = response.get("NextToken")
            if not next_token:
                break

    except Exception as e:
        coverage_ok = False
        coverage_note = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))

    coverage = Coverage(
        tier="config",
        collector="config",
        region=region,
        ok=coverage_ok,
        count=len(resources),
        seconds=round(time.perf_counter() - started, 3),
        note=coverage_note,
    )

    return resources, coverage
