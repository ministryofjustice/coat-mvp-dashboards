import base64
import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from hosting_data import read_hosting_csv
from hosting_report import tagging_coverage


ROOT = Path(__file__).parent
SAMPLE = ROOT / "sample_hosting.csv"


def chart_traces(app):
    return [json.loads(chart.proto.spec)["data"][0] for chart in app.get("plotly_chart")]


def decoded(values):
    if isinstance(values, dict):
        return np.frombuffer(base64.b64decode(values["bdata"]), dtype=values["dtype"]).tolist()
    return values


@pytest.fixture
def app_factory():
    def create(transform=""):
        script = f"""
import io
import runpy
from unittest.mock import patch
import streamlit as st
from hosting_data import read_hosting_csv

st.cache_data.clear()
source = read_hosting_csv({str(SAMPLE)!r})
{transform}
uploaded_file = io.BytesIO(source.to_csv(index=False).encode('utf-8'))
uploaded_file.name = 'sample_hosting.csv'
st.session_state['tested_downloads'] = []
with patch('config.APP_ENV', None), patch('local_data_input.manual_file_upload', return_value=uploaded_file), patch('streamlit.download_button', wraps=st.download_button) as downloads:
    runpy.run_path({str(ROOT / 'app.py')!r}, run_name='__main__')
    st.session_state['tested_downloads'] = [call.kwargs for call in downloads.call_args_list]
"""
        app = AppTest.from_string(script).run(timeout=30)
        assert not app.exception, app.exception
        return app

    return create


def test_month_selection_without_data_details(app_factory):
    app = app_factory()
    source = read_hosting_csv(SAMPLE)
    assert app.selectbox(key="billing_month").value == "2026-09"
    assert not any(item.label == "Data details" for item in app.expander)
    assert not any("Source file:" in item.value for item in app.markdown)
    for month in app.selectbox(key="billing_month").options:
        app.selectbox(key="billing_month").select(month).run()
        assert not app.exception, app.exception
        expected = source.loc[source.billing_period == month, "spend_usd"].sum()
        assert app.metric[0].value == f"${expected:,.2f}"


def test_account_namespace_filters_and_recovery(app_factory):
    app = app_factory()
    source = read_hosting_csv(SAMPLE)
    view = source[source.billing_period == "2026-09"]
    account = view.iloc[0].account_name
    app.multiselect(key="account_filter").set_value([account]).run()
    assert not app.exception, app.exception
    assert app.metric[1].value == "1"
    expected = view.loc[view.account_name == account, "spend_usd"].sum()
    assert app.metric[0].value == f"${expected:,.2f}"
    namespace = next(
        value for value in view.tag_namespace.unique()
        if value not in set(view.loc[view.account_name == account, "tag_namespace"])
    )
    app.multiselect(key="namespace_filter").set_value([namespace]).run()
    assert not app.exception, app.exception
    assert any("No rows match" in item.value for item in app.info)
    assert len(app.dataframe) == 0
    assert len(app.get("download_button")) == 0
    app.multiselect(key="account_filter").set_value([]).run()
    assert not app.exception, app.exception
    expected = view.loc[view.tag_namespace == namespace, "spend_usd"].sum()
    assert app.metric[0].value == f"${expected:,.2f}"
    app.selectbox(key="business_unit").select("OCTO").run()
    assert not app.exception, app.exception
    selected = app.multiselect(key="namespace_filter")
    assert all(value in selected.options for value in selected.value)


def test_tables_render_without_download_buttons(app_factory):
    app = app_factory()
    assert len(app.dataframe) == 7
    assert len(app.get("download_button")) == 0
    assert app.session_state["tested_downloads"] == []
    app.selectbox(key="business_unit").select("HMPPS").run()
    account = app.multiselect(key="account_filter").options[0]
    app.multiselect(key="account_filter").set_value([account]).run()
    assert not app.exception, app.exception
    assert len(app.dataframe) == 7
    assert len(app.get("download_button")) == 0
    assert app.session_state["tested_downloads"] == []
    for table in app.dataframe:
        assert table.proto.alt


def test_progress_columns_and_negative_share_fallback(app_factory):
    app = app_factory()
    table = next(table for table in app.dataframe if "pct_of_total" in table.value)
    columns = json.loads(table.proto.columns)
    assert columns["pct_of_total"]["type_config"]["type"] == "progress"
    assert columns["pct_of_total"]["type_config"]["max_value"] == 100
    app = app_factory("source.loc[source.business_unit == 'HMPPS', 'spend_usd'] = -100")
    table = next(table for table in app.dataframe if "pct_of_total" in table.value)
    columns = json.loads(table.proto.columns)
    assert columns["pct_of_total"]["type_config"]["type"] == "number"
    assert (table.value.pct_of_total < 0).any()
    assert any("outside 0-100%" in item.value for item in app.info)


def test_zero_cost_and_unavailable_tagging(app_factory):
    app = app_factory("source['spend_usd'] = 0\nsource['is_taggable_product'] = False")
    assert next(table.value for table in app.dataframe if "pct_of_total" in table.value).pct_of_total.isna().all()
    coverage = next(table.value for table in app.dataframe if "pct_tagged" in table.value)
    assert coverage.pct_tagged.isna().all()
    assert [trace["type"] for trace in chart_traces(app)] == ["scatter", "bar", "bar"]
    assert sum("can't be shown as parts of a whole" in item.value for item in app.info) == 1
    assert any("Tagging coverage is unavailable" in item.value for item in app.info)
    assert any("shown as blank" in item.value for item in app.info)


def test_namespace_progress_bars_after_rounding(app_factory):
    app = app_factory("source['spend_usd'] = 0.163577808")
    table = next(table for table in app.dataframe if "pct_of_namespace" in table.value)
    column = json.loads(table.proto.columns)["pct_of_namespace"]
    assert column["type_config"]["type"] == "progress"
    assert table.value.pct_of_namespace.between(0, 100).all()
    assert table.value.pct_of_namespace.max() == 100
    assert table.value.groupby("tag_namespace").pct_of_namespace.sum().tolist() == pytest.approx([100, 100])
    assert not any("outside 0-100%" in item.value for item in app.info)


def test_namespace_genuine_outliers_remain_numbers(app_factory):
    app = app_factory(
        "source = source[source.billing_period == '2026-09'].copy()\n"
        "source['tag_namespace'] = 'same-namespace'\n"
        "source['spend_usd'] = [125, -25, 0]"
    )
    table = next(table for table in app.dataframe if "pct_of_namespace" in table.value)
    column = json.loads(table.proto.columns)["pct_of_namespace"]
    assert column["type_config"]["type"] == "number"
    assert table.value.pct_of_namespace.min() == -25
    assert table.value.pct_of_namespace.max() == 125
    assert any("outside 0-100%" in item.value for item in app.info)


@pytest.mark.parametrize("percentage,expected_type,expected_value", [
    (100.00000000000001, "progress", 100),
    (-0.00000000000001, "progress", 0),
    (100.001, "number", 100.001),
    (-0.001, "number", -0.001),
])
def test_percentage_boundary_tolerance(app_factory, percentage, expected_type, expected_value):
    app = app_factory(
        "source['usage_cost_usd'] = 100.0\n"
        "source['is_taggable_product'] = True\n"
        "for column in source.filter(like='tagged_').columns:\n"
        f"    source[column] = {percentage!r}"
    )
    table = next(table for table in app.dataframe if "pct_tagged" in table.value)
    column = json.loads(table.proto.columns)["pct_tagged"]
    assert column["type_config"]["type"] == expected_type
    assert table.value.pct_tagged.tolist() == pytest.approx([expected_value] * 5)
    assert any("outside 0-100%" in item.value for item in app.info) == (expected_type == "number")


def test_single_month_and_unavailable_month_reset(app_factory):
    app = app_factory(
        "if st.session_state.get('replacement_csv'):\n"
        "    source = source[(source.billing_period == '2026-09') & (source.business_unit == 'OCTO')]"
    )
    app.selectbox(key="billing_month").select("2026-07").run()
    app.selectbox(key="business_unit").select("HMPPS").run()
    app.multiselect(key="account_filter").set_value(
        [app.multiselect(key="account_filter").options[0]]
    ).run()
    app.multiselect(key="namespace_filter").set_value(
        [app.multiselect(key="namespace_filter").options[0]]
    ).run()
    app.session_state["replacement_csv"] = True
    app.run()
    assert not app.exception, app.exception
    assert app.selectbox(key="billing_month").options == ["2026-09"]
    assert app.selectbox(key="billing_month").value == "2026-09"
    assert app.selectbox(key="business_unit").value == "All Business Units"
    assert app.multiselect(key="account_filter").value == []
    assert app.multiselect(key="namespace_filter").value == []


def test_history_availability_and_forecast_placeholder(app_factory):
    app = app_factory()
    assert [tab.label for tab in app.tabs] == [
        "Year-to-date", "Spend trend", "Forecast",
        "Tagging coverage", "By account / namespace", "By service type",
    ]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["YTD spend (USD)"] == "Not available"
    assert metrics["Available-month subtotal (USD, partial)"] == "$4,515.00"
    assert metrics["Next 3 months forecast (USD)"] == "Not available"
    assert any("Resource-count tagging compliance is not available" in item.value for item in app.info)
    assert any("2026-04, 2026-05, 2026-06" in item.value for item in app.info)
    trend = next(table.value for table in app.dataframe if "billing_period" in table.value and len(table.value) == 12)
    assert trend.spend_usd.isna().sum() == 9
    assert trend.iloc[-1].spend_usd == 1550


def test_history_applies_all_filters_and_month_cutoff(app_factory):
    app = app_factory()
    app.selectbox(key="business_unit").select("HMPPS").run()
    app.multiselect(key="account_filter").set_value(["example-probation-dev"]).run()
    app.multiselect(key="namespace_filter").set_value(["probation-dev"]).run()
    app.selectbox(key="billing_month").select("2026-08").run()
    assert not app.exception, app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Total spend (USD)"] == "$320.00"
    assert metrics["Available-month subtotal (USD, partial)"] == "$620.00"
    trend = next(table.value for table in app.dataframe if "billing_period" in table.value and len(table.value) == 12)
    assert trend.iloc[-1].billing_period == "2026-08"
    assert trend.spend_usd.sum() == 620


def test_ytd_populates_when_missing_months_arrive(app_factory):
    app = app_factory(
        "import pandas as pd\n"
        "if st.session_state.get('full_history'):\n"
        "    source = pd.concat([source] + [source.iloc[[0]].assign(billing_period=month, spend_usd=100) "
        "for month in ['2026-04', '2026-05', '2026-06']], ignore_index=True)"
    )
    assert next(metric.value for metric in app.metric if metric.label == "YTD spend (USD)") == "Not available"
    app.session_state["full_history"] = True
    app.run()
    assert not app.exception, app.exception
    assert next(metric.value for metric in app.metric if metric.label == "YTD spend (USD)") == "$4,815.00"
    assert not any("Full YTD spend is not available" in item.value for item in app.info)


def test_single_month_trend_and_april_ytd(app_factory):
    app = app_factory("source = source[source.billing_period == '2026-09'].assign(billing_period='2026-04')")
    assert any("A spend trend is not yet available" in item.value for item in app.info)
    assert next(metric.value for metric in app.metric if metric.label == "YTD spend (USD)") == "$1,550.00"
    assert [trace["type"] for trace in chart_traces(app)] == ["indicator"] * 5 + ["bar", "pie"]


def test_chart_types_are_diversified(app_factory):
    app = app_factory()
    traces = chart_traces(app)
    assert [trace["type"] for trace in traces] == ["scatter"] + ["indicator"] * 5 + ["bar", "pie"]
    source = read_hosting_csv(SAMPLE)
    coverage = tagging_coverage(source[source.billing_period == "2026-09"])
    dials = traces[1:6]
    assert [dial["title"]["text"] for dial in dials] == coverage.tag.tolist()
    assert [dial["value"] for dial in dials] == pytest.approx(coverage.pct_tagged.tolist())
    assert all(dial["gauge"]["axis"]["range"] == [0, 100] for dial in dials)
    accounts, donut = traces[6:]
    assert accounts["y"][::-1] == ["example-platform-prod", "example-probation-dev", "example-unassigned"]
    assert sum(decoded(accounts["x"])) == pytest.approx(1550)
    assert "example-platform-prod $1,200; example-probation-dev $340" in app.get("plotly_chart")[6].proto.alt
    service_table = next(table.value for table in app.dataframe if {"service_type", "pct_of_total"} <= set(table.value))
    assert donut["labels"] == service_table.service_type.tolist()
    assert donut["text"] == [f"{value:.1f}%" for value in service_table.pct_of_total]
    assert donut["hole"] == 0.55


def test_donut_groups_small_service_types(app_factory):
    app = app_factory(
        "import pandas as pd\n"
        "products = ['Amazon Elastic Compute Cloud', 'Amazon Relational Database Service', "
        "'Amazon Simple Storage Service', 'Amazon Virtual Private Cloud', 'AWS CloudTrail', "
        "'AmazonCloudWatch', 'AWS Glue', 'Amazon SageMaker']\n"
        "row = source[source.billing_period == '2026-09'].iloc[[0]]\n"
        "source = pd.concat([row.assign(product_name=name, spend_usd=80.0 - 10 * index) "
        "for index, name in enumerate(products)], ignore_index=True)"
    )
    donut = next(trace for trace in chart_traces(app) if trace["type"] == "pie")
    assert donut["labels"] == [
        "Compute", "Database", "Storage", "Networking", "Security & governance", "Remaining service types (3)",
    ]
    assert donut["text"] == ["22.2%", "19.4%", "16.7%", "13.9%", "11.1%", "16.7%"]
    assert decoded(donut["values"]) == pytest.approx([80, 70, 60, 50, 40, 60])
    assert len(set(donut["marker"]["colors"][:len(donut["labels"])])) == 6


def test_part_to_whole_charts_fall_back_for_credits(app_factory):
    app = app_factory("source.loc[source.business_unit == 'HMPPS', 'spend_usd'] = -100")
    traces = chart_traces(app)
    assert [trace["type"] for trace in traces] == ["scatter"] + ["indicator"] * 7 + ["bar", "bar"]
    assert sum("can't be shown as parts of a whole" in item.value for item in app.info) == 1
    assert dict(zip(traces[8]["y"], decoded(traces[8]["x"])))["example-probation-dev"] == -100


def test_service_breakdown_shows_all_namespaces_without_local_filters(app_factory):
    app = app_factory()
    assert not any(item.key == "service_breakdown_account" for item in app.selectbox)
    assert not any(item.key == "service_breakdown_namespace" for item in app.selectbox)
    assert not any(item.value == "Per account" for item in app.subheader)
    assert not any("pct_of_account" in table.value for table in app.dataframe)
    app.selectbox(key="billing_month").select("2026-07").run()
    assert not app.exception, app.exception
    table = next(table.value for table in app.dataframe if "pct_of_namespace" in table.value)
    assert table.groupby("tag_namespace").spend_usd.sum().to_dict() == pytest.approx({
        "untagged": 1250, "probation-dev": 300,
    })
    assert table.groupby("tag_namespace").pct_of_namespace.sum().to_dict() == pytest.approx({
        "untagged": 100, "probation-dev": 100,
    })
    assert table.spend_usd.sum() == 1550
    app.multiselect(key="account_filter").set_value(["example-platform-prod"]).run()
    assert not app.exception, app.exception
    table = next(table.value for table in app.dataframe if "pct_of_namespace" in table.value)
    assert table.tag_namespace.unique().tolist() == ["untagged"]
    assert table.spend_usd.sum() == 1200