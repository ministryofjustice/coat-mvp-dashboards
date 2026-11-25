"""Tests for the Cost Optimization Hub S3 export loader.

Run from dashboards/coh_dashboard/: python -m pytest
"""

import io
from datetime import datetime

import pandas as pd
import pytest

from recommendations import load_data
from s3_data import (
    parse_s3_uri,
    partition_timestamp,
    read_coh_export,
    select_latest_parquet_keys,
)


PREFIX = "coh-reports-auto-root-account/COH-No-RI-SP-PARQUET-Export"
EXPORT_URI = f"s3://coh-export/{PREFIX}/"


def parquet_bytes(frame):
    buffer = io.BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
    return buffer.getvalue()


def recommendation(**overrides):
    row = {
        "action_type": "Rightsize",
        "currency_code": "USD",
        "current_resource_type": "Ec2Instance",
        "estimated_monthly_cost_after_discount": 80.0,
        "estimated_monthly_cost_before_discount": 100.0,
        "estimated_monthly_savings_after_discount": 1200.5,
        "estimated_monthly_savings_before_discount": 1500.0,
        "estimated_savings_percentage_after_discount": 40.0,
        "estimated_savings_percentage_before_discount": 50.0,
        "implementation_effort": "Low",
        "last_refresh_timestamp": "2026-11-22T00:00:00Z",
        "recommendation_id": "rec-new",
        "recommendation_lookback_period_in_days": 14,
        "recommendation_source": "ComputeOptimizer",
        "recommended_resource_summary": "t3.small",
        "recommended_resource_type": "Ec2Instance",
        "region": "eu-west-2",
        "restart_needed": True,
        "rollback_possible": False,
    }
    row.update(overrides)
    return row


class FakeBody:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload


class FakePaginator:
    def __init__(self, objects):
        self.objects = objects

    def paginate(self, Bucket, Prefix):
        del Bucket
        keys = [key for key in self.objects if key.startswith(Prefix)]
        return [{"Contents": [{"Key": key} for key in keys]}]


class FakeS3:
    def __init__(self, objects):
        self.objects = objects

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.objects)

    def get_object(self, Bucket, Key):
        del Bucket
        return {"Body": FakeBody(self.objects[Key])}


def export_objects():
    latest = f"{PREFIX}/data/2026-11-22/2026-11-22T010203Z-new"
    older_execution = f"{PREFIX}/data/2026-11-22/2026-11-22T000000Z-old"
    previous_day = f"{PREFIX}/data/2026-11-21/2026-11-21T010203Z-old"
    return {
        f"{previous_day}/COH-No-RI-SP-PARQUET-Export-00001.snappy.parquet": parquet_bytes(
            pd.DataFrame([recommendation(recommendation_id="rec-old", estimated_monthly_savings_after_discount=1.0)])
        ),
        f"{older_execution}/COH-No-RI-SP-PARQUET-Export-00001.snappy.parquet": parquet_bytes(
            pd.DataFrame([recommendation(recommendation_id="rec-earlier", estimated_monthly_savings_after_discount=2.0)])
        ),
        f"{latest}/COH-No-RI-SP-PARQUET-Export-00001.snappy.parquet": parquet_bytes(
            pd.DataFrame([recommendation()])
        ),
        f"{latest}/COH-No-RI-SP-PARQUET-Export-00002.snappy.parquet": parquet_bytes(
            pd.DataFrame([recommendation(recommendation_id="rec-chunk", estimated_monthly_savings_after_discount=10.0)])
        ),
        f"{PREFIX}/metadata/2026-11-22/Manifest.json": b"{}",
    }


def test_parse_s3_uri():
    assert parse_s3_uri(EXPORT_URI) == ("coh-export", f"{PREFIX}/")


def test_parse_s3_uri_rejects_a_bare_bucket():
    with pytest.raises(ValueError, match="s3://bucket/key"):
        parse_s3_uri("s3://coh-export")


def test_partition_timestamp_reads_the_delivery_date():
    key = f"{PREFIX}/data/2026-11-22/2026-11-22T010203Z-new/export-00001.snappy.parquet"
    assert partition_timestamp(key) == datetime(2026, 11, 22, 1, 2, 3)


def test_latest_partition_includes_every_chunk_and_ignores_older_deliveries():
    selected = select_latest_parquet_keys(export_objects())

    assert selected == [
        f"{PREFIX}/data/2026-11-22/2026-11-22T010203Z-new/COH-No-RI-SP-PARQUET-Export-00001.snappy.parquet",
        f"{PREFIX}/data/2026-11-22/2026-11-22T010203Z-new/COH-No-RI-SP-PARQUET-Export-00002.snappy.parquet",
    ]


def test_missing_parquet_is_reported():
    with pytest.raises(FileNotFoundError, match="No parquet files"):
        select_latest_parquet_keys([f"{PREFIX}/metadata/Manifest.json"])


def test_snappy_export_loads_the_latest_partition_into_a_dashboard_frame():
    frame = read_coh_export(EXPORT_URI, s3_client=FakeS3(export_objects()))

    assert list(frame["recommendationId"]) == ["rec-new", "rec-chunk"]
    assert frame["estimatedMonthlySavings"].tolist() == [1200.5, 10.0]
    assert frame["estimatedMonthlyCost"].tolist() == [80.0, 80.0]
    assert frame["estimatedSavingsPercentage"].tolist() == [40.0, 40.0]
    assert frame["actionType"].tolist() == ["Rightsize", "Rightsize"]
    assert frame["source"].tolist() == ["ComputeOptimizer", "ComputeOptimizer"]
    assert "estimated_monthly_savings_after_discount" not in frame.columns


def test_discounted_metric_falls_back_when_it_is_missing():
    key = f"{PREFIX}/data/2026-11-22/export-00001.snappy.parquet"
    row = recommendation()
    row.pop("estimated_monthly_savings_after_discount")
    objects = {key: parquet_bytes(pd.DataFrame([row]))}

    frame = read_coh_export(EXPORT_URI, s3_client=FakeS3(objects))

    assert frame.loc[0, "estimatedMonthlySavings"] == 1500.0


def test_application_integration_prepares_the_parquet_export():
    frame = read_coh_export(EXPORT_URI, s3_client=FakeS3(export_objects()))
    prepared = load_data(frame)

    assert prepared["estimatedMonthlySavings"].sum() == pytest.approx(1210.5)
    assert prepared["estimatedAnnualSavings"].tolist() == pytest.approx([14406.0, 120.0])
    assert prepared.loc[0, "savingsValueCategory"] == ">=$1000/month"
    assert prepared.loc[1, "savingsValueCategory"] == ">=$1/month and <$100/month"
    assert prepared["effortFactor"].tolist() == [1, 1]
    assert bool(prepared.loc[0, "restartNeeded"])
    assert not bool(prepared.loc[0, "rollbackPossible"])
    assert prepared.loc[0, "currencyCode"] == "USD"
    assert prepared.loc[0, "lastRefreshTimestamp"] == pd.Timestamp("2026-11-22T00:00:00Z")
