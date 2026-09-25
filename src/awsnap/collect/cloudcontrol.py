from __future__ import annotations

import json
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from awsnap.model import Coverage, Resource


def collect_cloudcontrol(
    session: boto3.Session,
    region: str,
    collected_at: datetime,
    account_id: str,
    max_workers: int = 8,
    types: Sequence[str] = (),
    include_global: bool = True,
    client: object | None = None,
) -> tuple[list[Resource], list[Coverage]]:
    """Collect resources from CloudControl."""
    from awsnap.collect.types_curated import CURATED_TYPES, GLOBAL_TYPES
    from awsnap.model import Coverage, make_resource

    if not types:
        types = CURATED_TYPES

    if client is None:
        config = Config(retries={"mode": "adaptive", "max_attempts": 5})
        # AIDEV-READONLY: cloudcontrol:ListResources
        client = session.client("cloudcontrol", region_name=region, config=config)

    all_resources: list[Resource] = []
    coverages: list[Coverage] = []

    def _collect_type(type_name: str) -> tuple[list[Resource], Coverage]:
        resources: list[Resource] = []
        coverage_ok = True
        coverage_note = ""
        resource_count = 0
        started = time.perf_counter()

        # Skip global types in non-first regions when include_global is False
        if type_name in GLOBAL_TYPES and not include_global:
            coverage = Coverage(
                tier="cloudcontrol",
                collector=type_name,
                region=region,
                ok=True,
                count=0,
                seconds=0.0,
                note="global_skipped",
            )
            return [], coverage

        try:
            next_token: str | None = None

            while True:
                kwargs = {"TypeName": type_name, "MaxResults": 100}
                if next_token:
                    kwargs["NextToken"] = next_token

                response = client.list_resources(**kwargs)

                for item in response.get("ResourceDescriptions", []):
                    identifier = item.get("Identifier", "")
                    properties_str = item.get("Properties", "{}")

                    try:
                        properties = json.loads(properties_str)
                    except (json.JSONDecodeError, ValueError):
                        properties = {}

                    # Extract ARN
                    arn = properties.get("Arn") or properties.get("ARN")
                    if not arn:
                        # Synthesize ARN if not in properties
                        service = type_name.split("::")[1].lower()
                        short_type = type_name.split("::")[2].lower()
                        region_for_type = "" if type_name in GLOBAL_TYPES else region
                        # AIDEV-NOTE: synthesized ARNs are not real ARNs, just identifiers
                        arn = (
                            f"arn:aws:{service}:{region_for_type}:{account_id}:"
                            f"{short_type}/{identifier}"
                        )

                    # Extract name
                    name = properties.get("Name")
                    if not name:
                        short_type = type_name.split("::")[2].lower()
                        name = properties.get(f"{short_type}Name")
                    if not name:
                        for key, value in properties.items():
                            if key.endswith("Name") and isinstance(value, str):
                                name = value
                                break
                    if not name:
                        name = identifier

                    # Extract tags
                    tags_dict: dict[str, str] = {}
                    tags_raw = properties.get("Tags", [])
                    if isinstance(tags_raw, list):
                        for tag in tags_raw:
                            if isinstance(tag, dict):
                                if "Key" in tag and "Value" in tag:
                                    tags_dict[tag["Key"]] = tag["Value"]

                    resource = make_resource(
                        arn=arn,
                        resource_type=type_name,
                        region=region if type_name not in GLOBAL_TYPES else "",
                        name=name,
                        tags=tags_dict,
                        raw=properties,
                        source="cloudcontrol",
                        collected_at=collected_at,
                    )
                    resources.append(resource)
                    resource_count += 1

                next_token = response.get("NextToken")
                if not next_token:
                    break

        except Exception as e:
            coverage_ok = False
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))
            coverage_note = error_code

        coverage = Coverage(
            tier="cloudcontrol",
            collector=type_name,
            region=region,
            ok=coverage_ok,
            count=resource_count,
            seconds=round(time.perf_counter() - started, 3),
            note=coverage_note,
        )
        return resources, coverage

    # Determine which types to process
    types_to_process = []
    for t in types:
        if t in GLOBAL_TYPES and not include_global:
            continue
        types_to_process.append(t)

    # Process types in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_collect_type, t): t for t in types_to_process}
        for future in futures:
            resources, coverage = future.result()
            all_resources.extend(resources)
            coverages.append(coverage)

    return all_resources, coverages
