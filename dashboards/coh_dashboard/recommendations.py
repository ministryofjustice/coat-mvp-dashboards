import json

import pandas as pd

EFFORT_FACTOR_MAP = {
    "Low": 1,
    "Medium": 2,
    "High": 6,
    "VeryHigh": 10,
}


def get_effort_factor(effort):
    """Get effort factor from implementation effort string"""
    if pd.isna(effort):
        return 1
    effort_str = str(effort).strip()
    return EFFORT_FACTOR_MAP.get(effort_str, 1)


def classify_savings(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "Unknown"

    if v >= 1000:
        return ">=$1000/month"
    elif v >= 500:
        return ">=$500/month and <$1000/month"
    elif v >= 100:
        return ">=$100/month and <$500/month"
    elif v >= 1:
        return ">=$1/month and <$100/month"
    else:
        return "<$1/month"


def coerce_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    mapping = {
        "true": True,
        "false": False,
        "True": True,
        "False": False,
        True: True,
        False: False,
        1: True,
        0: False,
    }
    return series.map(lambda x: mapping.get(x, x)).fillna(False).astype(bool)


def parse_tags(value):
    if pd.isna(value):
        return {}
    if isinstance(value, list):
        return {
            item.get("key"): item.get("value")
            for item in value
            if isinstance(item, dict) and "key" in item
        }
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return {
                    item.get("key"): item.get("value")
                    for item in parsed
                    if isinstance(item, dict) and "key" in item
                }
        except Exception:
            return {}
    return {}


def load_data(source):
    """Normalise a recommendations CSV or dataframe for the dashboard."""
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)

    numeric_columns = [
        "estimatedMonthlySavings",
        "estimatedMonthlyCost",
        "estimatedSavingsPercentage",
        "recommendationLookbackPeriodInDays",
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "lastRefreshTimestamp" in df.columns:
        df["lastRefreshTimestamp"] = pd.to_datetime(
            df["lastRefreshTimestamp"], errors="coerce", utc=True
        )

    for col in ["restartNeeded", "rollbackPossible"]:
        if col in df.columns:
            df[col] = coerce_bool_series(df[col])

    df["savingsValueCategory"] = df["estimatedMonthlySavings"].apply(classify_savings)
    df["estimatedAnnualSavings"] = df["estimatedMonthlySavings"].fillna(0) * 12

    df["effortFactor"] = df["implementationEffort"].apply(get_effort_factor)

    if "tags" in df.columns:
        df["parsedTags"] = df["tags"].apply(parse_tags)
        df["tag_owner"] = df["parsedTags"].apply(lambda d: d.get("owner"))
        df["tag_environment_name"] = df["parsedTags"].apply(lambda d: d.get("environment-name"))
        df["tag_is_production"] = df["parsedTags"].apply(lambda d: d.get("is-production"))
        df["tag_application"] = df["parsedTags"].apply(lambda d: d.get("application"))
        df["tag_business_unit"] = df["parsedTags"].apply(lambda d: d.get("business-unit"))
        df["tag_source_code"] = df["parsedTags"].apply(lambda d: d.get("source-code"))

    return df
