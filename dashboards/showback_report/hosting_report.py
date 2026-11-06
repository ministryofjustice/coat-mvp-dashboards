"""Monthly and historical figures for the Hosting showback page.

Input is the DataFrame from hosting_data.read_hosting_csv. No Streamlit here,
so the tests run with plain pytest.
"""

from math import isfinite

import pandas as pd

ALL_BUSINESS_UNITS = "All Business Units"

# (label shown on the page, column in the CSV)
TAG_COLUMNS = [
    ("service_area", "tagged_service_area_usage_cost_usd"),
    ("business_unit", "tagged_business_unit_usage_cost_usd"),
    ("application", "tagged_application_usage_cost_usd"),
    ("owner", "tagged_owner_usage_cost_usd"),
    ("is_production", "tagged_is_production_usage_cost_usd"),
    ("environment_name", "tagged_environment_name_usage_cost_usd"),
    ("namespace", "tagged_namespace_usage_cost_usd"),
]

# Same product-to-category list as showback_scope.html section 7.
_EXACT = {
    "Compute": [
        "Amazon Elastic Compute Cloud", "Amazon Elastic Container Service",
        "Amazon Elastic Container Service for Kubernetes", "AWS Lambda",
        "Amazon EC2 Container Registry (ECR)",
    ],
    "End-user computing": ["Amazon WorkSpaces", "Amazon WorkSpaces Web", "Amazon WorkSpaces Applications"],
    "Storage": [
        "Amazon Simple Storage Service", "AWS Backup", "Amazon Elastic File System",
        "Amazon FSx", "AWS Transfer Family",
    ],
    "Database": [
        "Amazon Relational Database Service", "Amazon OpenSearch Service", "Amazon ElastiCache",
        "Amazon Redshift", "Amazon DynamoDB", "AWS Database Migration Service",
        "Elastic Cloud (Elasticsearch Service)",
    ],
    "Networking": [
        "Amazon Virtual Private Cloud", "AWS Network Firewall", "Elastic Load Balancing",
        "Amazon Route 53", "AWS Direct Connect", "Amazon CloudFront",
    ],
    "Security & governance": [
        "AWS CloudTrail", "Amazon GuardDuty", "AWS Config", "AWS Key Management Service",
        "Amazon Inspector", "Amazon Detective", "AWS Security Hub", "AWS Shield", "AWS WAF",
        "AWS Secrets Manager", "AWS Certificate Manager", "AWS Directory Service", "Amazon Cognito",
    ],
    "Monitoring & management": [
        "AmazonCloudWatch", "Amazon Managed Service for Prometheus", "AWS X-Ray", "AWS Systems Manager",
    ],
    "Analytics & data": [
        "AWS Glue", "Amazon Athena", "Amazon QuickSight",
        "Amazon Managed Workflows for Apache Airflow", "Amazon Kinesis",
    ],
    "AI & ML": ["Amazon SageMaker", "Amazon Kendra"],
    "Integration & messaging": ["Amazon MQ", "Amazon Simple Queue Service", "Amazon Simple Notification Service"],
}
_EXACT_LOOKUP = {name: category for category, names in _EXACT.items() for name in names}

# Same order as the CASE in section 7: the first match wins.
_CATEGORY_ORDER = [
    "Compute", "End-user computing", "Storage", "Database", "Networking", "Security & governance",
    "Monitoring & management", "Analytics & data", "AI & ML", "Support", "Integration & messaging",
]
_CONTAINS = {"Networking": "NetScaler", "Monitoring & management": "Grafana", "AI & ML": "Bedrock"}


def service_type(product_name: str) -> str:
    name = "" if pd.isna(product_name) else product_name
    for category in _CATEGORY_ORDER:
        if _EXACT_LOOKUP.get(name) == category:
            return category
        if category in _CONTAINS and _CONTAINS[category] in name:
            return category
        if category == "Support" and name.startswith("AWS Support"):
            return category
    return "Other"


def latest_month(df: pd.DataFrame) -> str:
    return max(df["billing_period"])


def filter_view(df: pd.DataFrame, month: str, business_unit: str) -> pd.DataFrame:
    view = df[df["billing_period"] == month]
    if business_unit != ALL_BUSINESS_UNITS:
        view = view[view["business_unit"] == business_unit]
    return view


def monthly_spend(view: pd.DataFrame, month: str, periods: int = 12) -> pd.DataFrame:
    months = pd.period_range(end=month, periods=periods, freq="M").astype(str)
    totals = view.groupby("billing_period")["spend_usd"].sum(min_count=1)
    out = totals.reindex(months).rename_axis("billing_period").reset_index()
    out["availability"] = out["spend_usd"].notna().map({True: "Available", False: "Not available"})
    return out


def financial_year_spend(view: pd.DataFrame, month: str) -> pd.DataFrame:
    reporting_month = pd.Period(month, freq="M")
    periods = (reporting_month.month - 4) % 12 + 1
    return monthly_spend(view, month, periods)


def _spend_percentages(spend: pd.Series) -> pd.Series:
    """Allocate tenths of a percent by largest remainder for nonnegative spend."""
    total = spend.sum()
    if spend.empty or not spend.map(isfinite).all() or not isfinite(total) or total <= 0 or (spend < 0).any():
        return 100 * spend / total
    scaled = spend / total * 1000
    units = scaled.astype("int64")
    remaining = 1000 - int(units.sum())
    ranked = (scaled - units).sort_values(ascending=False, kind="stable").index
    units.loc[ranked[:remaining]] += 1
    return units / 10


def _with_pct(out: pd.DataFrame, column: str, by: str | None = None) -> pd.DataFrame:
    out[column] = (
        out.groupby(by)["spend_usd"].transform(_spend_percentages)
        if by else _spend_percentages(out["spend_usd"])
    )
    return out


def _spend_by(view: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = view.groupby(columns, as_index=False)["spend_usd"].sum()
    return _with_pct(out, "pct_of_total").sort_values("spend_usd", ascending=False, ignore_index=True)


def spend_by_business_unit(view: pd.DataFrame) -> pd.DataFrame:
    return _spend_by(view, ["business_unit"])


def spend_by_account(view: pd.DataFrame) -> pd.DataFrame:
    return _spend_by(view, ["account_name", "business_unit"])


def spend_by_namespace(view: pd.DataFrame) -> pd.DataFrame:
    return _spend_by(view, ["tag_namespace"])


def spend_by_service_type(view: pd.DataFrame) -> pd.DataFrame:
    return _spend_by(view.assign(service_type=view["product_name"].map(service_type)), ["service_type"])


def largest_with_remainder(data: pd.DataFrame, category: str, limit: int, remainder_label: str) -> pd.DataFrame:
    positive = data[data["spend_usd"] > 0].sort_values("spend_usd", ascending=False, kind="stable")
    if len(positive) <= limit:
        return positive.reset_index(drop=True)
    rest = positive.iloc[limit - 1:]
    remainder = pd.DataFrame({
        category: [f"{remainder_label} ({len(rest)})"],
        "spend_usd": [rest["spend_usd"].sum()],
        "pct_of_total": [round(rest["pct_of_total"].sum(), 1)],
    })
    return pd.concat([positive.iloc[:limit - 1], remainder], ignore_index=True)


def top_with_remainder(data: pd.DataFrame, category: str, limit: int, remainder_label: str) -> pd.DataFrame:
    """Like largest_with_remainder, but keeps zero and negative spend so bar charts can show credits."""
    ranked = data.sort_values("spend_usd", ascending=False, kind="stable", ignore_index=True)
    if len(ranked) <= limit:
        return ranked
    rest = ranked.iloc[limit - 1:]
    remainder = pd.DataFrame({
        category: [f"{remainder_label} ({len(rest)})"],
        "spend_usd": [rest["spend_usd"].sum()],
    })
    return pd.concat([ranked.iloc[:limit - 1], remainder], ignore_index=True)


def spend_by_account_service_type(view: pd.DataFrame) -> pd.DataFrame:
    typed = view.assign(service_type=view["product_name"].map(service_type))
    out = typed.groupby(["account_name", "service_type"], as_index=False)["spend_usd"].sum()
    out = _with_pct(out, "pct_of_account", by="account_name")
    return out.sort_values(["account_name", "spend_usd"], ascending=[True, False], ignore_index=True)


def spend_by_namespace_service_type(view: pd.DataFrame) -> pd.DataFrame:
    typed = view.assign(service_type=view["product_name"].map(service_type))
    out = typed.groupby(["tag_namespace", "service_type"], as_index=False)["spend_usd"].sum()
    out = _with_pct(out, "pct_of_namespace", by="tag_namespace")
    return out.sort_values(["tag_namespace", "spend_usd"], ascending=[True, False], ignore_index=True)


def tagging_coverage(view: pd.DataFrame) -> pd.DataFrame:
    """Share of taggable Usage cost carrying each tag. Products that never carry tags are left out."""
    taggable = view[view["is_taggable_product"]]
    base = taggable["usage_cost_usd"].sum()
    rows = [
        {
            "tag": label,
            "tagged_usage_cost_usd": taggable[column].sum(),
            "taggable_usage_cost_usd": base,
            "pct_tagged": 100 * taggable[column].sum() / base if base else float("nan"),
        }
        for label, column in TAG_COLUMNS
    ]
    return pd.DataFrame(rows)
