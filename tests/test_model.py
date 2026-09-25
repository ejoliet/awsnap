from __future__ import annotations

from datetime import datetime, timezone

import pytest

from awsnap.model import (
    COLUMNS,
    Coverage,
    Resource,
    RunMetadata,
    canonical_json,
    dedup,
    make_resource,
    parse_arn,
    summarize_coverage,
)


class TestParseArn:
    def test_s3_bucket_no_region_account(self):
        """S3 bucket ARN has empty region and account."""
        arn = "arn:aws:s3:::my-bucket"
        parts = parse_arn(arn)
        assert parts.partition == "aws"
        assert parts.service == "s3"
        assert parts.region == ""
        assert parts.account == ""
        assert parts.resource == "my-bucket"

    def test_ec2_with_path(self):
        """EC2 instance ARN with path segments."""
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        parts = parse_arn(arn)
        assert parts.partition == "aws"
        assert parts.service == "ec2"
        assert parts.region == "us-east-1"
        assert parts.account == "123456789012"
        assert parts.resource == "instance/i-1234567890abcdef0"

    def test_lambda_with_colon(self):
        """Lambda ARN with colon in resource."""
        arn = "arn:aws:lambda:us-west-2:123456789012:function:my-function:1"
        parts = parse_arn(arn)
        assert parts.partition == "aws"
        assert parts.service == "lambda"
        assert parts.region == "us-west-2"
        assert parts.account == "123456789012"
        assert parts.resource == "function:my-function:1"

    def test_invalid_arn_not_starting_with_arn(self):
        """Invalid ARN not starting with 'arn'."""
        with pytest.raises(ValueError, match="Invalid ARN"):
            parse_arn("aws:s3:::bucket")

    def test_invalid_arn_too_few_parts(self):
        """Invalid ARN with too few colon-separated parts."""
        with pytest.raises(ValueError, match="Invalid ARN"):
            parse_arn("arn:aws:s3")

    def test_invalid_arn_empty_string(self):
        """Invalid ARN empty string."""
        with pytest.raises(ValueError, match="Invalid ARN"):
            parse_arn("")


class TestCanonicalJson:
    def test_sorted_keys(self):
        """JSON keys are sorted."""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_compact_separators(self):
        """JSON uses compact separators."""
        obj = {"key": "value"}
        result = canonical_json(obj)
        assert result == '{"key":"value"}'
        assert ", " not in result  # no space after comma

    def test_nested_objects(self):
        """Nested objects also sorted."""
        obj = {"b": {"z": 1, "a": 2}, "a": 3}
        result = canonical_json(obj)
        expected = '{"a":3,"b":{"a":2,"z":1}}'
        assert result == expected

    def test_default_str_conversion(self):
        """Non-serializable objects converted via str()."""
        dt = datetime(2024, 1, 15, 12, 0, 0)
        obj = {"time": dt}
        result = canonical_json(obj)
        assert "2024-01-15" in result


class TestMakeResource:
    def test_basic_resource(self):
        """Create resource with all fields."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        res = make_resource(
            arn="arn:aws:s3:::my-bucket",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="my-bucket",
            tags={"env": "prod"},
            raw={"BucketName": "my-bucket", "CreationDate": "2024-01-15"},
            source="config",
            collected_at=now,
        )

        assert res.arn == "arn:aws:s3:::my-bucket"
        assert res.service == "s3"
        assert res.resource_type == "AWS::S3::Bucket"
        assert res.region == "us-east-1"
        assert res.name == "my-bucket"
        assert res.tags == canonical_json({"env": "prod"})
        assert res.source == "config"
        assert res.collected_at == now

    def test_region_fallback_from_arn(self):
        """Empty region falls back to ARN region."""
        now = datetime.now(timezone.utc)
        res = make_resource(
            arn="arn:aws:ec2:eu-west-1:123456789012:instance/i-123",
            resource_type="AWS::EC2::Instance",
            region="",
            name="my-instance",
            tags={},
            raw={},
            source="cloudcontrol",
            collected_at=now,
        )
        assert res.region == "eu-west-1"

    def test_name_fallback_from_arn_last_segment(self):
        """Empty name falls back to last segment of ARN resource."""
        now = datetime.now(timezone.utc)
        res = make_resource(
            arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="AWS::EC2::Instance",
            region="us-east-1",
            name="",
            tags={},
            raw={},
            source="cloudcontrol",
            collected_at=now,
        )
        assert res.name == "i-1234567890abcdef0"

    def test_service_parsed_from_arn(self):
        """Service extracted from ARN."""
        now = datetime.now(timezone.utc)
        res = make_resource(
            arn="arn:aws:lambda:us-east-1:123456789012:function:my-func",
            resource_type="AWS::Lambda::Function",
            region="us-east-1",
            name="my-func",
            tags={},
            raw={},
            source="cloudcontrol",
            collected_at=now,
        )
        assert res.service == "lambda"


class TestResourceAsRow:
    def test_as_row_order_matches_columns(self):
        """as_row() returns values in COLUMNS order."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        res = Resource(
            arn="arn:aws:s3:::bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="bucket",
            tags="{}",
            raw="{}",
            source="config",
            collected_at=now,
        )
        row = res.as_row()
        assert len(row) == len(COLUMNS)
        assert row[0] == "arn:aws:s3:::bucket"  # arn
        assert row[1] == "s3"  # service
        assert row[2] == "AWS::S3::Bucket"  # resource_type
        assert row[3] == "us-east-1"  # region
        assert row[4] == "bucket"  # name
        assert row[5] == "{}"  # tags
        assert row[6] == "{}"  # raw
        assert row[7] == "config"  # source
        assert row[8] == now  # collected_at


class TestDedup:
    def test_dedup_by_arn_single_source(self):
        """Dedup with single source per ARN returns winner."""
        now = datetime.now(timezone.utc)
        res1 = Resource(
            arn="arn:aws:s3:::bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="bucket",
            tags="{}",
            raw="{}",
            source="config",
            collected_at=now,
        )
        result = dedup([res1])
        assert len(result) == 1
        assert result[0].arn == "arn:aws:s3:::bucket"

    def test_dedup_prefers_lower_precedence(self):
        """Prefers source with lower SOURCE_PRECEDENCE."""
        now = datetime.now(timezone.utc)
        config_res = Resource(
            arn="arn:aws:s3:::bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="bucket",
            tags="{}",
            raw="{}",
            source="config",
            collected_at=now,
        )
        tagging_res = Resource(
            arn="arn:aws:s3:::bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="bucket",
            tags="{}",
            raw="{}",
            source="tagging",
            collected_at=now,
        )
        result = dedup([tagging_res, config_res])
        assert len(result) == 1
        assert result[0].source == "config"

    def test_dedup_tag_enrichment(self):
        """If winner has empty tags, takes non-empty tags from loser."""
        now = datetime.now(timezone.utc)
        config_res = Resource(
            arn="arn:aws:s3:::bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="bucket",
            tags="{}",
            raw="{}",
            source="config",
            collected_at=now,
        )
        tagging_res = Resource(
            arn="arn:aws:s3:::bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="bucket",
            tags='{"env":"prod"}',
            raw="{}",
            source="tagging",
            collected_at=now,
        )
        result = dedup([config_res, tagging_res])
        assert len(result) == 1
        assert result[0].tags == '{"env":"prod"}'
        assert result[0].source == "config"  # still config, but enriched tags

    def test_dedup_sorted_by_arn(self):
        """Output sorted by ARN for stable/diffable results."""
        now = datetime.now(timezone.utc)
        res_z = Resource(
            arn="arn:aws:s3:::z-bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="z-bucket",
            tags="{}",
            raw="{}",
            source="config",
            collected_at=now,
        )
        res_a = Resource(
            arn="arn:aws:s3:::a-bucket",
            service="s3",
            resource_type="AWS::S3::Bucket",
            region="us-east-1",
            name="a-bucket",
            tags="{}",
            raw="{}",
            source="config",
            collected_at=now,
        )
        result = dedup([res_z, res_a])
        assert len(result) == 2
        assert result[0].arn == "arn:aws:s3:::a-bucket"
        assert result[1].arn == "arn:aws:s3:::z-bucket"


class TestRunMetadata:
    def test_as_dict(self):
        """as_dict converts to dict with proper conversions."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        meta = RunMetadata(
            account_id="123456789012",
            run_id="abc123def456",
            awsnap_version="0.1.0",
            tier_used="config",
            regions=["us-east-1", "eu-west-1"],
            resource_count=1234,
            coverage_note="All good",
            collected_at=now,
        )
        result = meta.as_dict()
        assert result["account_id"] == "123456789012"
        assert result["run_id"] == "abc123def456"
        assert result["awsnap_version"] == "0.1.0"
        assert result["tier_used"] == "config"
        assert result["regions"] == "us-east-1,eu-west-1"
        assert result["resource_count"] == 1234
        assert result["coverage_note"] == "All good"
        assert result["collected_at"] == "2024-01-15T12:00:00+00:00"


class TestSummarizeCoverage:
    def test_all_ok(self):
        """Summary when all collectors succeed."""
        coverage = [
            Coverage(
                tier="config",
                collector="config",
                region="us-east-1",
                ok=True,
                count=100,
                seconds=1.5,
            ),
            Coverage(
                tier="tagging",
                collector="tagging",
                region="us-east-1",
                ok=True,
                count=50,
                seconds=0.5,
            ),
        ]
        result = summarize_coverage(coverage)
        assert "config:1 ok/0 fail" in result
        assert "tagging:1 ok/0 fail" in result

    def test_with_failures(self):
        """Summary includes failures."""
        coverage = [
            Coverage(
                tier="cloudcontrol",
                collector="cloudcontrol",
                region="us-east-1",
                ok=True,
                count=58,
                seconds=2.0,
            ),
            Coverage(
                tier="cloudcontrol",
                collector="cloudcontrol",
                region="us-east-1",
                ok=False,
                count=0,
                seconds=0.5,
                note="AccessDenied",
            ),
            Coverage(
                tier="cloudcontrol",
                collector="cloudcontrol",
                region="us-east-1",
                ok=False,
                count=0,
                seconds=0.3,
                note="TypeNotFound",
            ),
        ]
        result = summarize_coverage(coverage)
        assert "cloudcontrol:1 ok/2 fail" in result
        assert "AccessDenied x1" in result
        assert "TypeNotFound x1" in result

    def test_grouped_notes(self):
        """Failure notes are grouped by text with counts."""
        coverage = [
            Coverage(
                tier="cloudcontrol",
                collector="cc",
                region="r1",
                ok=False,
                count=0,
                seconds=0.1,
                note="AccessDenied",
            ),
            Coverage(
                tier="cloudcontrol",
                collector="cc",
                region="r2",
                ok=False,
                count=0,
                seconds=0.1,
                note="AccessDenied",
            ),
            Coverage(
                tier="cloudcontrol",
                collector="cc",
                region="r3",
                ok=False,
                count=0,
                seconds=0.1,
                note="TypeNotFound",
            ),
        ]
        result = summarize_coverage(coverage)
        assert "cloudcontrol:0 ok/3 fail" in result
        assert "AccessDenied x2" in result
        assert "TypeNotFound x1" in result

    def test_empty_coverage(self):
        """Empty coverage list."""
        result = summarize_coverage([])
        assert result == ""

    def test_multiple_tiers(self):
        """Multiple tiers in output."""
        coverage = [
            Coverage(
                tier="config",
                collector="config",
                region="us-east-1",
                ok=True,
                count=100,
                seconds=1.0,
            ),
            Coverage(
                tier="cloudcontrol",
                collector="cc",
                region="us-east-1",
                ok=True,
                count=50,
                seconds=2.0,
            ),
            Coverage(
                tier="tagging",
                collector="tagging",
                region="us-east-1",
                ok=True,
                count=40,
                seconds=0.5,
            ),
        ]
        result = summarize_coverage(coverage)
        parts = result.split("; ")
        assert len(parts) == 3
        assert any("config:" in p for p in parts)
        assert any("cloudcontrol:" in p for p in parts)
        assert any("tagging:" in p for p in parts)
