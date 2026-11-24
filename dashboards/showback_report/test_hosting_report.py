"""Tests for hosting_report.py, using sample_hosting.csv. Run from showback_report/: python -m pytest"""

from pathlib import Path

import pandas as pd
import pytest

from hosting_data import read_hosting_csv
from hosting_report import (
    ALL_BUSINESS_UNITS,
    ALL_SERVICE_AREAS,
    filter_history,
    filter_view,
    financial_year_spend,
    largest_with_remainder,
    latest_month,
    monthly_spend,
    service_type,
    spend_by_account,
    spend_by_account_aws_service,
    spend_by_account_service_type,
    spend_by_business_unit,
    spend_by_namespace,
    spend_by_namespace_service_type,
    spend_by_service_type,
    tagging_coverage,
    top_with_remainder,
)

SAMPLE = Path(__file__).parent / "sample_hosting.csv"


@pytest.fixture
def df():
    return read_hosting_csv(SAMPLE)


def test_latest_month(df):
    assert latest_month(df) == "2026-09"


def test_filter_view(df):
    assert len(filter_view(df, "2026-09", ALL_BUSINESS_UNITS)) == 3
    assert filter_view(df, "2026-09", "HMPPS")["spend_usd"].sum() == pytest.approx(340.0)


def test_spend_by_business_unit(df):
    out = spend_by_business_unit(filter_view(df, "2026-09", ALL_BUSINESS_UNITS))
    assert out["business_unit"].tolist() == ["OCTO", "HMPPS", "untagged"]
    assert out["spend_usd"].tolist() == pytest.approx([1200.0, 340.0, 10.0])
    assert out["pct_of_total"].sum() == pytest.approx(100.0)


def test_tagging_coverage_september(df):
    out = tagging_coverage(filter_view(df, "2026-09", ALL_BUSINESS_UNITS)).set_index("tag")
    assert out.loc["service_area", "taggable_usage_cost_usd"] == pytest.approx(2015.0)
    assert out.loc["service_area", "pct_tagged"] == pytest.approx(100 * 2002 / 2015)
    assert out.loc["application", "pct_tagged"] == pytest.approx(100 * 442 / 2015)


@pytest.mark.parametrize("costs,expected", [
    ([1, 1, 1], [33.4, 33.3, 33.3]),
    ([1, 1, 1, 1, 1, 1], [16.7, 16.7, 16.7, 16.7, 16.6, 16.6]),
    ([3331, 3333, 3336], [33.3, 33.3, 33.4]),
    ([0, 1, 1, 1], [0, 33.4, 33.3, 33.3]),
    ([0.163577808], [100.0]),
])
def test_spend_shares_use_largest_remainders(costs, expected):
    source = pd.DataFrame({
        "business_unit": [f"unit-{index}" for index in range(len(costs))],
        "spend_usd": costs,
    })
    out = spend_by_business_unit(source).sort_values("business_unit")
    assert out.pct_of_total.tolist() == pytest.approx(expected)
    assert (out.pct_of_total * 10).round().sum() == 1000
    assert out.pct_of_total.between(0, 100).all()
    assert out.spend_usd.tolist() == costs
    shuffled = spend_by_business_unit(source.iloc[::-1]).sort_values("business_unit")
    assert shuffled.pct_of_total.tolist() == out.pct_of_total.tolist()


@pytest.mark.parametrize("costs", [[0, 0], [125, -25], [-1, -1, -1], [1, -1], [float("inf"), 1]])
def test_spend_shares_preserve_negative_and_undefined_cases(costs):
    source = pd.DataFrame({
        "business_unit": [f"unit-{index}" for index in range(len(costs))],
        "spend_usd": costs,
    })
    out = spend_by_business_unit(source).sort_values("business_unit").reset_index(drop=True)
    expected = 100 * source.spend_usd / source.spend_usd.sum()
    pd.testing.assert_series_equal(out.pct_of_total, expected, check_names=False)


@pytest.mark.parametrize("report,group_column,percentage", [
    (spend_by_account_service_type, "account_name", "pct_of_account"),
    (spend_by_account_aws_service, "account_name", "pct_of_account"),
    (spend_by_namespace_service_type, "tag_namespace", "pct_of_namespace"),
])
def test_largest_remainders_are_independent_per_group(report, group_column, percentage):
    source = pd.DataFrame({
        group_column: ["equal", "equal", "equal", "credit", "credit", "zero"],
        "product_name": [
            "Amazon Elastic Compute Cloud", "Amazon Relational Database Service", "Amazon Simple Storage Service",
            "Amazon Elastic Compute Cloud", "Amazon Simple Storage Service", "Amazon Elastic Compute Cloud",
        ],
        "spend_usd": [1, 1, 1, 125, -25, 0],
    })
    out = report(source)
    equal = out[out[group_column] == "equal"].sort_values("service_type")
    assert equal[percentage].tolist() == pytest.approx([33.4, 33.3, 33.3])
    assert out.loc[out[group_column] == "credit", percentage].tolist() == [125, -25]
    assert out.loc[out[group_column] == "zero", percentage].isna().all()
    assert out.spend_usd.sum() == source.spend_usd.sum()


def test_tagging_coverage_leaves_out_untaggable_products(df):
    # July has an AWS Support row (65 usage) flagged as never taggable
    out = tagging_coverage(filter_view(df, "2026-07", ALL_BUSINESS_UNITS)).set_index("tag")
    assert out.loc["service_area", "taggable_usage_cost_usd"] == pytest.approx(1950.0)
    assert out.loc["service_area", "pct_tagged"] == pytest.approx(100 * 1690 / 1950)


def test_spend_by_account_and_namespace(df):
    view = filter_view(df, "2026-09", ALL_BUSINESS_UNITS)
    acc = spend_by_account(view)
    assert acc["account_name"].tolist()[0] == "example-platform-prod"
    assert acc["spend_usd"].sum() == pytest.approx(1550.0)
    ns = spend_by_namespace(view).set_index("tag_namespace")
    assert ns.loc["untagged", "spend_usd"] == pytest.approx(1210.0)
    assert ns.loc["probation-dev", "spend_usd"] == pytest.approx(340.0)


def test_service_type_mapping():
    assert service_type("Amazon Elastic Compute Cloud") == "Compute"
    assert service_type("Amazon Relational Database Service") == "Database"
    assert service_type("Citrix NetScaler VPX") == "Networking"
    assert service_type("AWS Support (Business)") == "Support"
    assert service_type("Something New") == "Other"
    assert service_type("") == "Other"


def test_monthly_spend_preserves_missing_months_and_zero():
    source = pd.DataFrame({
        "billing_period": ["2025-09", "2026-07", "2026-09", "2026-09", "2026-10"],
        "spend_usd": [500, 0, 100, -10, 900],
    })
    out = monthly_spend(source, "2026-09").set_index("billing_period")
    assert len(out) == 12
    assert out.index[0] == "2025-10"
    assert out.index[-1] == "2026-09"
    assert out.loc["2026-07", "spend_usd"] == 0
    assert out.loc["2026-07", "availability"] == "Available"
    assert pd.isna(out.loc["2026-08", "spend_usd"])
    assert out.loc["2026-08", "availability"] == "Not available"
    assert out.loc["2026-09", "spend_usd"] == 90


@pytest.mark.parametrize("month,start,count", [
    ("2026-03", "2025-04", 12),
    ("2026-04", "2026-04", 1),
    ("2026-09", "2026-04", 6),
    ("2027-01", "2026-04", 10),
])
def test_financial_year_boundaries(df, month, start, count):
    out = financial_year_spend(df, month)
    assert len(out) == count
    assert out.iloc[0].billing_period == start
    assert out.iloc[-1].billing_period == month


def test_financial_year_spend_uses_available_history(df):
    out = financial_year_spend(df, "2026-09")
    assert out.spend_usd.sum() == pytest.approx(4515)
    assert out.spend_usd.isna().sum() == 3
    scoped = df[df.business_unit == "HMPPS"]
    assert financial_year_spend(scoped, "2026-09").spend_usd.sum() == pytest.approx(1005)
    assert monthly_spend(df.iloc[:0], "2026-09").spend_usd.isna().all()


def test_namespace_service_type_shares():
    source = pd.DataFrame({
        "tag_namespace": ["team-a", "team-a", "team-b"],
        "product_name": ["Amazon Elastic Compute Cloud", "Amazon Simple Storage Service", "New product"],
        "spend_usd": [75, 25, 50],
    })
    out = spend_by_namespace_service_type(source)
    assert out.spend_usd.sum() == 150
    assert out.pct_of_namespace.tolist() == pytest.approx([75, 25, 100])
    assert out.service_type.tolist() == ["Compute", "Storage", "Other"]


def test_account_aws_service_rows_grouped_by_account_then_category():
    source = pd.DataFrame({
        "account_name": ["b", "a", "a", "a", "a"],
        "product_name": [
            "Amazon Simple Storage Service", "Amazon Relational Database Service",
            "AWS Lambda", "Amazon Elastic Compute Cloud", "Amazon Elastic Compute Cloud",
        ],
        "spend_usd": [50, 30, 10, 40, 20],
    })
    out = spend_by_account_aws_service(source)
    assert out.columns.tolist() == ["account_name", "service_type", "product_name", "spend_usd", "pct_of_account"]
    assert out.account_name.tolist() == ["a", "a", "a", "b"]
    assert out.service_type.tolist() == ["Compute", "Compute", "Database", "Storage"]
    assert out.product_name.tolist() == [
        "Amazon Elastic Compute Cloud", "AWS Lambda", "Amazon Relational Database Service",
        "Amazon Simple Storage Service",
    ]
    assert out.spend_usd.tolist() == [60, 10, 30, 50]
    assert out.pct_of_account.tolist() == pytest.approx([60, 10, 30, 100])


def test_largest_with_remainder_groups_small_categories():
    data = pd.DataFrame({
        "service_type": list("ABCDEFGH"),
        "spend_usd": [40.0, 20, 10, 10, 8, 6, 6, 0],
        "pct_of_total": [40.0, 20, 10, 10, 8, 6, 6, 0],
    })
    out = largest_with_remainder(data, "service_type", 6, "Remaining")
    assert out.service_type.tolist() == ["A", "B", "C", "D", "E", "Remaining (2)"]
    assert out.spend_usd.tolist() == [40, 20, 10, 10, 8, 12]
    assert out.pct_of_total.sum() == pytest.approx(100)
    assert largest_with_remainder(data.head(6), "service_type", 6, "Remaining").service_type.tolist() == list("ABCDEF")


def test_top_with_remainder_keeps_credits():
    data = pd.DataFrame({"account_name": list("ABCDE"), "spend_usd": [-5.0, 30, 0, 20, 10]})
    out = top_with_remainder(data, "account_name", 3, "Other accounts")
    assert out.account_name.tolist() == ["B", "D", "Other accounts (3)"]
    assert out.spend_usd.tolist() == [30, 20, 5]
    assert top_with_remainder(data, "account_name", 5, "Other").account_name.tolist() == list("BDECA")


def test_spend_by_service_type(df):
    view = filter_view(df, "2026-09", ALL_BUSINESS_UNITS)
    out = spend_by_service_type(view).set_index("service_type")["spend_usd"].to_dict()
    assert out == pytest.approx({"Compute": 1200.0, "Database": 340.0, "Networking": 10.0})
    per_acc = spend_by_account_service_type(view)
    assert per_acc.groupby("account_name")["pct_of_account"].sum().tolist() == pytest.approx([100.0] * 3)


def test_service_area_filter_combines_with_other_filters():
    rows = pd.DataFrame({
        "billing_period": ["2026-08", "2026-09", "2026-09", "2026-09", "2026-09"],
        "cost_category_service_area": ["Hosting", "Hosting", "Hosting", "Data", "Hosting"],
        "business_unit": ["HMPPS", "HMPPS", "OCTO", "HMPPS", "HMPPS"],
        "account_name": ["a", "a", "b", "a", "c"],
        "tag_namespace": ["ns1", "ns1", "ns1", "ns1", "ns2"],
        "spend_usd": [1.0, 2.0, 4.0, 8.0, 16.0],
    })
    assert filter_history(rows)["spend_usd"].sum() == 31
    assert filter_history(rows, "Data")["spend_usd"].tolist() == [8]
    assert filter_history(rows, "Hosting", "HMPPS", ["a"], ["ns1"])["spend_usd"].tolist() == [1, 2]
    assert filter_view(rows, "2026-09", ALL_BUSINESS_UNITS, "Hosting")["spend_usd"].tolist() == [2, 4, 16]
    assert filter_view(rows, "2026-09", "HMPPS")["spend_usd"].tolist() == [2, 8, 16]
    assert filter_view(rows, "2026-09", "HMPPS", ALL_SERVICE_AREAS).equals(filter_view(rows, "2026-09", "HMPPS"))
