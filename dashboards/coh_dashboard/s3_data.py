import io
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import boto3
import pandas as pd
import streamlit as st

# BCM data exports write one directory per delivery. Cost Optimization Hub
# refreshes daily, and each delivery is a directory whose name includes that
# day's date, containing one or more *.snappy.parquet chunks.
_DASHED_TIMESTAMP = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?:T(?P<hour>\d{2}):?(?P<minute>\d{2}):?(?P<second>\d{2}))?"
)

_COLUMN_RENAMES = {
    "account_id": "accountId",
    "account_name": "accountName",
    "action_type": "actionType",
    "currency_code": "currencyCode",
    "current_resource_summary": "currentResourceSummary",
    "current_resource_type": "currentResourceType",
    "implementation_effort": "implementationEffort",
    "last_refresh_timestamp": "lastRefreshTimestamp",
    "recommendation_id": "recommendationId",
    "recommendation_ID": "recommendationId",
    "recommendation_lookback_period_in_days": "recommendationLookbackPeriodInDays",
    "recommendation_source": "source",
    "recommended_resource_summary": "recommendedResourceSummary",
    "recommended_resource_type": "recommendedResourceType",
    "region": "region",
    "resource_arn": "resourceArn",
    "resource_id": "resourceId",
    "restart_needed": "restartNeeded",
    "rollback_possible": "rollbackPossible",
    "tags": "tags",
}

_METRIC_COLUMNS = {
    "estimatedMonthlySavings": (
        "estimated_monthly_savings_after_discount",
        "estimated_monthly_savings_before_discount",
    ),
    "estimatedMonthlyCost": (
        "estimated_monthly_cost_after_discount",
        "estimated_monthly_cost_before_discount",
    ),
    "estimatedSavingsPercentage": (
        "estimated_savings_percentage_after_discount",
        "estimated_savings_percentage_before_discount",
    ),
}


def get_coh_s3_uri() -> str:
    """Return the configured S3 URI for the Cost Optimization Hub export."""
    return os.getenv("COH_REPORT_S3_URI")


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Parse an s3://bucket/key URI into its bucket and object key."""
    parsed_uri = urlparse(s3_uri)

    if parsed_uri.scheme != "s3" or not parsed_uri.netloc or not parsed_uri.path:
        raise ValueError(
            f"Invalid S3 URI: {s3_uri!r}. "
            "Expected a URI in the form s3://bucket/key."
        )

    return parsed_uri.netloc, parsed_uri.path.lstrip("/")


def _listing_prefix(key: str) -> str:
    if key.endswith("/") or key.endswith(".parquet") or key.endswith(".csv"):
        return key
    return f"{key}/"


def _timestamp_from_match(match: re.Match) -> datetime | None:
    try:
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour") or 0),
            int(match.group("minute") or 0),
            int(match.group("second") or 0),
        )
    except ValueError:
        return None


def partition_timestamp(key: str) -> datetime:
    """Return the latest date embedded in an export object key."""
    stamps = [
        stamp
        for match in _DASHED_TIMESTAMP.finditer(key)
        if (stamp := _timestamp_from_match(match)) is not None
    ]
    return max(stamps) if stamps else datetime.min


def list_object_keys(s3_client, bucket: str, prefix: str) -> list[str]:
    """List every object key under an S3 prefix."""
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def select_latest_parquet_keys(keys: list[str]) -> list[str]:
    """Choose the snappy parquet chunks in the latest dated partition.

    A partition is the directory that holds the parquet chunks. When a day has
    more than one delivery, the directory whose path contains the latest
    timestamp is used, and every chunk in that directory is returned.
    """
    parquet_keys = [key for key in keys if key.endswith(".parquet")]
    if not parquet_keys:
        raise FileNotFoundError(
            "No parquet files were found under the Cost Optimization Hub export prefix."
        )

    ranked = [
        (partition_timestamp(key), key.rsplit("/", 1)[0], key)
        for key in parquet_keys
    ]
    latest_directory = max(ranked, key=lambda item: (item[0], item[1]))[1]
    return sorted(key for _, directory, key in ranked if directory == latest_directory)


def read_snappy_parquet(payload: bytes) -> pd.DataFrame:
    """Parse one snappy.parquet object into a dataframe."""
    return pd.read_parquet(io.BytesIO(payload), engine="pyarrow")


def _coalesce(frame: pd.DataFrame, target: str, candidates: tuple[str, ...]) -> None:
    series = None
    for name in candidates:
        if name not in frame.columns:
            continue
        values = frame[name]
        series = values if series is None else series.where(series.notna(), values)
    if series is not None:
        frame[target] = series


def normalise_export_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Map data-export column names onto the dashboard's column names.

    Discounted figures are preferred. A missing discounted value falls back to
    the before-discount figure for that row.
    """
    normalised = frame.copy()
    for target, candidates in _METRIC_COLUMNS.items():
        _coalesce(normalised, target, candidates)
    drop_columns = [
        column
        for candidates in _METRIC_COLUMNS.values()
        for column in candidates
        if column in normalised.columns
    ]
    normalised = normalised.drop(columns=drop_columns)
    return normalised.rename(columns=_COLUMN_RENAMES)


def read_coh_export(s3_uri: str | None = None, s3_client=None) -> pd.DataFrame:
    """Download the latest partition and return it as one dataframe."""
    uri = s3_uri or get_coh_s3_uri()
    bucket, key = parse_s3_uri(uri)
    client = s3_client or boto3.client("s3")
    keys = select_latest_parquet_keys(
        list_object_keys(client, bucket, _listing_prefix(key))
    )

    frames = []
    for object_key in keys:
        response = client.get_object(Bucket=bucket, Key=object_key)
        frames.append(read_snappy_parquet(response["Body"].read()))

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    return normalise_export_columns(combined)


@st.cache_data(ttl=300)
def load_coh_dataframe(s3_uri: str | None = None) -> pd.DataFrame:
    """Load the latest Cost Optimization Hub export from S3.

    boto3 uses the pod's AWS credential chain. In EKS this should normally be
    provided through the IAM role associated with the Kubernetes service account.
    """
    return read_coh_export(s3_uri)
