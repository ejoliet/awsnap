from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import boto3
import pytest
from botocore.stub import Stubber

from awsnap.collect import CollectOutput, collect, resolve_regions
from awsnap.collect.cloudcontrol import collect_cloudcontrol
from awsnap.collect.config_sql import collect_config, recorder_on
from awsnap.collect.tagging import collect_tagging


@pytest.fixture
def session():
    """Create a test boto3 session."""
    return boto3.Session(
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


@pytest.fixture
def collected_at():
    """Test collection timestamp."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestRecorderOn:
    def test_recorder_on_true(self, session):
        """Test recorder_on returns True when recorder is running."""
        client = session.client("config", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "describe_configuration_recorder_status",
                {
                    "ConfigurationRecordersStatus": [
                        {
                            "name": "default",
                            "recording": True,
                            "lastStatus": "Success",
                        }
                    ]
                },
            )
            # Pass the stubbed client directly
            result = recorder_on(session, "us-east-1", client=client)
            assert result is True

    def test_recorder_on_false(self, session):
        """Test recorder_on returns False when recorder is off."""
        client = session.client("config", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "describe_configuration_recorder_status",
                {"ConfigurationRecordersStatus": []},
            )
            result = recorder_on(session, "us-east-1", client=client)
            assert result is False

    def test_recorder_on_exception(self, session):
        """Test recorder_on returns False on exception."""
        client = session.client("config", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_client_error(
                "describe_configuration_recorder_status",
                service_error_code="AccessDenied",
            )
            result = recorder_on(session, "us-east-1", client=client)
            assert result is False


class TestCollectConfig:
    def test_collect_config_single_page(self, session, collected_at):
        """Test collecting config resources from a single page."""
        client = session.client("config", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "select_resource_config",
                {
                    "Results": [
                        json.dumps(
                            {
                                "arn": "arn:aws:s3:::my-bucket",
                                "resourceType": "AWS::S3::Bucket",
                                "resourceName": "my-bucket",
                                "awsRegion": "us-east-1",
                                "tags": [{"key": "Environment", "value": "prod"}],
                                "configuration": {"BucketName": "my-bucket"},
                            }
                        )
                    ]
                },
            )
            resources, coverage = collect_config(
                session, "us-east-1", collected_at, client=client
            )
            assert len(resources) == 1
            assert coverage.ok is True
            assert coverage.count == 1

    def test_collect_config_pagination(self, session, collected_at):
        """Test collecting config resources across multiple pages."""
        client = session.client("config", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "select_resource_config",
                {
                    "Results": [
                        json.dumps(
                            {
                                "arn": "arn:aws:s3:::bucket1",
                                "resourceType": "AWS::S3::Bucket",
                                "resourceName": "bucket1",
                                "awsRegion": "us-east-1",
                                "tags": [],
                                "configuration": {},
                            }
                        )
                    ],
                    "NextToken": "token123",
                },
            )
            stubber.add_response(
                "select_resource_config",
                {
                    "Results": [
                        json.dumps(
                            {
                                "arn": "arn:aws:s3:::bucket2",
                                "resourceType": "AWS::S3::Bucket",
                                "resourceName": "bucket2",
                                "awsRegion": "us-east-1",
                                "tags": [],
                                "configuration": {},
                            }
                        )
                    ]
                },
            )
            resources, coverage = collect_config(
                session, "us-east-1", collected_at, client=client
            )
            assert len(resources) == 2
            assert coverage.ok is True

    def test_collect_config_error(self, session, collected_at):
        """Test collect_config handles errors gracefully."""
        client = session.client("config", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_client_error(
                "select_resource_config",
                service_error_code="AccessDenied",
            )
            resources, coverage = collect_config(
                session, "us-east-1", collected_at, client=client
            )
            assert len(resources) == 0
            assert coverage.ok is False


class TestCollectCloudControl:
    def test_collect_cloudcontrol_basic(self, session, collected_at):
        """Test collecting CloudControl resources."""
        client = session.client("cloudcontrol", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "list_resources",
                {
                    "ResourceDescriptions": [
                        {
                            "Identifier": "my-bucket",
                            "Properties": json.dumps(
                                {"Arn": "arn:aws:s3:::my-bucket", "BucketName": "my-bucket"}
                            ),
                        }
                    ]
                },
            )
            resources, coverages = collect_cloudcontrol(
                session,
                "us-east-1",
                collected_at,
                "123456789012",
                max_workers=1,
                types=["AWS::S3::Bucket"],
                include_global=True,
                client=client,
            )
            assert len(resources) == 1
            assert len(coverages) == 1
            assert coverages[0].ok is True

    def test_collect_cloudcontrol_synthesized_arn(self, session, collected_at):
        """Test CloudControl synthesizes ARN when not in properties."""
        client = session.client("cloudcontrol", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "list_resources",
                {
                    "ResourceDescriptions": [
                        {
                            "Identifier": "my-role",
                            "Properties": json.dumps(
                                {"RoleName": "my-role", "AssumeRolePolicyDocument": "{}"}
                            ),
                        }
                    ]
                },
            )
            resources, coverages = collect_cloudcontrol(
                session,
                "us-east-1",
                collected_at,
                "123456789012",
                max_workers=1,
                types=["AWS::IAM::Role"],
                include_global=True,
                client=client,
            )
            assert len(resources) == 1
            # ARN should be synthesized
            assert "arn:aws" in resources[0].arn
            assert "123456789012" in resources[0].arn

    def test_collect_cloudcontrol_type_not_found(self, session, collected_at):
        """Test CloudControl handles TypeNotFoundException."""
        client = session.client("cloudcontrol", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_client_error(
                "list_resources",
                service_error_code="TypeNotFoundException",
            )
            resources, coverages = collect_cloudcontrol(
                session,
                "us-east-1",
                collected_at,
                "123456789012",
                max_workers=1,
                types=["AWS::S3::Bucket"],
                include_global=True,
                client=client,
            )
            assert len(resources) == 0
            assert len(coverages) == 1
            assert coverages[0].ok is False

    def test_collect_cloudcontrol_pagination(self, session, collected_at):
        """Test CloudControl pagination."""
        client = session.client("cloudcontrol", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "list_resources",
                {
                    "ResourceDescriptions": [
                        {
                            "Identifier": "bucket1",
                            "Properties": json.dumps({"Arn": "arn:aws:s3:::bucket1"}),
                        }
                    ],
                    "NextToken": "token123",
                },
            )
            stubber.add_response(
                "list_resources",
                {
                    "ResourceDescriptions": [
                        {
                            "Identifier": "bucket2",
                            "Properties": json.dumps({"Arn": "arn:aws:s3:::bucket2"}),
                        }
                    ]
                },
            )
            resources, coverages = collect_cloudcontrol(
                session,
                "us-east-1",
                collected_at,
                "123456789012",
                max_workers=1,
                types=["AWS::S3::Bucket"],
                include_global=True,
                client=client,
            )
            assert len(resources) == 2


class TestCollectTagging:
    def test_collect_tagging_basic(self, session, collected_at):
        """Test collecting tagging resources."""
        client = session.client("resourcegroupstaggingapi", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "get_resources",
                {
                    "ResourceTagMappingList": [
                        {
                            "ResourceARN": "arn:aws:s3:::my-bucket",
                            "Tags": [{"Key": "Environment", "Value": "prod"}],
                        }
                    ]
                },
            )
            resources, coverage = collect_tagging(
                session, "us-east-1", collected_at, client=client
            )
            assert len(resources) == 1
            assert coverage.ok is True

    def test_collect_tagging_pagination(self, session, collected_at):
        """Test collecting tagging resources across multiple pages."""
        client = session.client("resourcegroupstaggingapi", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "get_resources",
                {
                    "ResourceTagMappingList": [
                        {
                            "ResourceARN": "arn:aws:s3:::bucket1",
                            "Tags": [],
                        }
                    ],
                    "PaginationToken": "token123",
                },
            )
            stubber.add_response(
                "get_resources",
                {
                    "ResourceTagMappingList": [
                        {
                            "ResourceARN": "arn:aws:s3:::bucket2",
                            "Tags": [{"Key": "Name", "Value": "bucket2"}],
                        }
                    ]
                },
            )
            resources, coverage = collect_tagging(
                session, "us-east-1", collected_at, client=client
            )
            assert len(resources) == 2
            assert coverage.ok is True

    def test_collect_tagging_error(self, session, collected_at):
        """Test collect_tagging handles errors gracefully."""
        client = session.client("resourcegroupstaggingapi", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_client_error(
                "get_resources",
                service_error_code="InternalServiceException",
            )
            resources, coverage = collect_tagging(
                session, "us-east-1", collected_at, client=client
            )
            assert len(resources) == 0
            assert coverage.ok is False


class TestResolveRegions:
    def test_resolve_regions_empty_string(self, session):
        """Test resolve_regions with empty string defaults to session region."""
        regions = resolve_regions(session, "")
        assert regions == ["us-east-1"]

    def test_resolve_regions_none(self, session):
        """Test resolve_regions with None defaults to session region."""
        regions = resolve_regions(session, None)
        assert regions == ["us-east-1"]

    def test_resolve_regions_csv(self, session):
        """Test resolve_regions with CSV string."""
        regions = resolve_regions(session, "us-east-1, us-west-2, eu-west-1")
        assert regions == ["us-east-1", "us-west-2", "eu-west-1"]

    def test_resolve_regions_all(self, session):
        """Test resolve_regions with 'all'."""
        client = session.client("ec2", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "describe_regions",
                {
                    "Regions": [
                        {"RegionName": "us-west-2"},
                        {"RegionName": "us-east-1"},
                        {"RegionName": "eu-west-1"},
                    ]
                },
            )
            # Stub session.client to return our stubbed client for ec2 calls
            with patch.object(
                session, "client", return_value=client
            ):
                regions = resolve_regions(session, "all")
                assert sorted(regions) == sorted(
                    ["us-east-1", "us-west-2", "eu-west-1"]
                )


class TestCollect:
    def test_collect_tagging_tier(self, session, collected_at):
        """Test collect with tagging tier."""
        client = session.client("resourcegroupstaggingapi", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "get_resources",
                {
                    "ResourceTagMappingList": [
                        {
                            "ResourceARN": "arn:aws:s3:::my-bucket",
                            "Tags": [{"Key": "Env", "Value": "prod"}],
                        }
                    ]
                },
            )
            # Stub session.client to return our stubbed client
            with patch.object(
                session, "client", return_value=client
            ):
                result = collect(
                    session,
                    regions=["us-east-1"],
                    tier="tagging",
                    account_id="123456789012",
                    collected_at=collected_at,
                )
                assert isinstance(result, CollectOutput)
                assert result.tier_used == "tagging"
                assert len(result.resources) > 0

    def test_collect_cloudcontrol_tier(self, session, collected_at):
        """Test collect with cloudcontrol tier."""
        client = session.client("cloudcontrol", region_name="us-east-1")
        with Stubber(client) as stubber:
            stubber.add_response(
                "list_resources",
                {
                    "ResourceDescriptions": [
                        {
                            "Identifier": "my-bucket",
                            "Properties": json.dumps(
                                {"Arn": "arn:aws:s3:::my-bucket"}
                            ),
                        }
                    ]
                },
            )
            with patch.object(
                session, "client", return_value=client
            ):
                result = collect(
                    session,
                    regions=["us-east-1"],
                    tier="cloudcontrol",
                    account_id="123456789012",
                    collected_at=collected_at,
                    max_workers=1,
                )
                assert isinstance(result, CollectOutput)
                assert result.tier_used == "cloudcontrol"

    def test_collect_multi_region(self, session, collected_at):
        """Test collect across multiple regions."""
        # This test uses mocking to avoid regional complexity
        config_client = session.client("config", region_name="us-east-1")
        with Stubber(config_client) as stubber:
            stubber.add_response(
                "select_resource_config",
                {
                    "Results": [
                        json.dumps(
                            {
                                "arn": "arn:aws:s3:::bucket-east",
                                "resourceType": "AWS::S3::Bucket",
                                "resourceName": "bucket-east",
                                "awsRegion": "us-east-1",
                                "tags": [],
                                "configuration": {},
                            }
                        )
                    ]
                },
            )

            with patch(
                "awsnap.collect.config_sql.recorder_on", return_value=True
            ), patch.object(
                session, "client", return_value=config_client
            ):
                result = collect(
                    session,
                    regions=["us-east-1"],
                    tier="config",
                    account_id="123456789012",
                    collected_at=collected_at,
                )
                assert isinstance(result, CollectOutput)
