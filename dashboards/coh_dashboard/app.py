from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import numpy as np

from auth import require_entra_login
from recommendations import load_data
from s3_data import load_coh_dataframe
from render_html import render_footer, render_header
from config import APP_ENV, DASHBOARD_NAME
from local_data_input import manual_file_upload

st.set_page_config(
    page_title=DASHBOARD_NAME,
    page_icon="💰",
    layout="wide",
)

render_header()

require_entra_login()

st.title(DASHBOARD_NAME)
st.caption("AWS Cost Optimization Hub recommendations")

# Constants

SAVINGS_CATEGORY_ORDER = [
    ">=$1000/month",
    ">=$500/month and <$1000/month",
    ">=$100/month and <$500/month",
    ">=$1/month and <$100/month",
    "<$1/month",
    "Unknown",
]

SAVINGS_CATEGORY_COLORS = {
    ">=$1000/month": "#1E8449",
    ">=$500/month and <$1000/month": "#27AE60",
    ">=$100/month and <$500/month": "#F1C40F",
    ">=$1/month and <$100/month": "#E67E22",
    "<$1/month": "#C0392B",
    "Unknown": "#95A5A6",
}

def get_recommendation_count_factor(count):
    """Map recommendation count to factor"""
    if count <= 100:
        return 1.0
    elif count <= 500:
        return 1.5
    elif count <= 1500:
        return 2.0
    else:
        return 3.0


def calculate_priority_score(row):
    """Calculate priority score based on formula:
    Priority Score = (TotalEstimatedMonthlySavings^1.2) / ((effortFactor × recommendationCountFactor)^2)
    """
    savings = row.get('totalEstimatedMonthlySavings', 0)
    effort_factor = row.get('effortFactor', 1)
    count_factor = row.get('recommendationCountFactor', 1.0)
    
    if savings <= 0 or effort_factor == 0 or count_factor == 0:
        return 0
    
    numerator = savings ** 1.2
    denominator = (effort_factor * count_factor) ** 2
    
    return numerator / denominator if denominator > 0 else 0


# -----------------------------
# Helpers
# -----------------------------
def format_currency(value: float, currency: str = "USD") -> str:
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{value:,.2f}"


@st.cache_data
def load_report(source):
    return load_data(source)


def make_bar_chart(data, x, y, title, color=None, orientation="v"):
    if data.empty:
        return None
    fig = px.bar(
        data,
        x=x if orientation == "v" else y,
        y=y if orientation == "v" else x,
        color=color,
        orientation=orientation,
        title=title,
        text_auto=".2s",
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=420)
    return fig


def make_treemap(data, path, values, title):
    if data.empty:
        return None
    fig = px.treemap(data, path=path, values=values, title=title)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=450)
    return fig


# -----------------------------
# Data input
# -----------------------------

if APP_ENV:
    try:
        report = load_coh_dataframe()
    except Exception as exc:
        st.error("Unable to load the Cost Optimization Hub report from S3.")
        st.exception(exc)
        st.stop()
else:
    report = manual_file_upload()

df = load_report(report)

if df.empty:
    st.warning("The report contains no rows.")
    st.stop()

currency = (
    df["currencyCode"].dropna().iloc[0]
    if "currencyCode" in df.columns and df["currencyCode"].dropna().any()
    else "USD"
)

# -----------------------------
# Sidebar filters
# -----------------------------
st.sidebar.header("Filters")

def multiselect_filter(column_name, label=None):
    if column_name not in df.columns:
        return None
    options = sorted([x for x in df[column_name].dropna().unique().tolist()])
    return st.sidebar.multiselect(label or column_name, options, default=options)


selected_accounts = multiselect_filter("accountName", "Account")
selected_regions = multiselect_filter("region", "Region")
selected_resource_types = multiselect_filter("currentResourceType", "Current resource type")
selected_action_types = multiselect_filter("actionType", "Action type")
selected_efforts = multiselect_filter("implementationEffort", "Implementation effort")
selected_sources = multiselect_filter("source", "Source")
selected_savings_bands = multiselect_filter("savingsValueCategory", "Savings value category")

filtered_df = df.copy()

filter_map = {
    "accountName": selected_accounts,
    "region": selected_regions,
    "currentResourceType": selected_resource_types,
    "actionType": selected_action_types,
    "implementationEffort": selected_efforts,
    "source": selected_sources,
    "savingsValueCategory": selected_savings_bands,
}

for column, selected in filter_map.items():
    if selected is not None and len(selected) > 0:
        filtered_df = filtered_df[filtered_df[column].isin(selected)]

# -----------------------------
# KPI row
# -----------------------------
total_recommendations = len(filtered_df)
total_monthly_savings = filtered_df["estimatedMonthlySavings"].fillna(0).sum()
total_annual_savings = filtered_df["estimatedAnnualSavings"].fillna(0).sum()
avg_savings = filtered_df["estimatedMonthlySavings"].fillna(0).mean() if total_recommendations else 0
total_monthly_cost = filtered_df["estimatedMonthlyCost"].fillna(0).sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Recommendations", f"{total_recommendations:,}")
c2.metric("Est. Monthly Savings", format_currency(total_monthly_savings, currency))
c3.metric("Est. Annual Savings", format_currency(total_annual_savings, currency))
c4.metric("Avg Savings / Recommendation", format_currency(avg_savings, currency))
c5.metric("Est. Monthly Cost", format_currency(total_monthly_cost, currency))

st.divider()

# -----------------------------
# Summary tables for charts
# -----------------------------
if "accountName" in filtered_df.columns:
    savings_by_account = (
        filtered_df.groupby("accountName", dropna=False, as_index=False)["estimatedMonthlySavings"]
        .sum()
        .sort_values("estimatedMonthlySavings", ascending=False)
    )
else:
    savings_by_account = pd.DataFrame(columns=["accountName", "estimatedMonthlySavings"])

savings_by_region = (
    filtered_df.groupby("region", dropna=False, as_index=False)["estimatedMonthlySavings"]
    .sum()
    .sort_values("estimatedMonthlySavings", ascending=False)
)

savings_by_resource_type = (
    filtered_df.groupby("currentResourceType", dropna=False, as_index=False)["estimatedMonthlySavings"]
    .sum()
    .sort_values("estimatedMonthlySavings", ascending=False)
)

savings_by_action = (
    filtered_df.groupby("actionType", dropna=False, as_index=False)["estimatedMonthlySavings"]
    .sum()
    .sort_values("estimatedMonthlySavings", ascending=False)
)

recommendations_by_effort = (
    filtered_df.groupby("implementationEffort", dropna=False, as_index=False)["recommendationId"]
    .count()
    .rename(columns={"recommendationId": "recommendationCount"})
    .sort_values("recommendationCount", ascending=False)
)

recommendations_by_source = (
    filtered_df.groupby("source", dropna=False, as_index=False)["recommendationId"]
    .count()
    .rename(columns={"recommendationId": "recommendationCount"})
    .sort_values("recommendationCount", ascending=False)
)

recommendations_by_savings_band = (
    filtered_df.groupby("savingsValueCategory", dropna=False, as_index=False)["recommendationId"]
    .count()
    .rename(columns={"recommendationId": "recommendationCount"})
)

triple_agg = (
    filtered_df.groupby(
        ["currentResourceType", "actionType", "savingsValueCategory"],
        dropna=False,
        as_index=False,
    )["recommendationId"]
    .count()
    .rename(columns={"recommendationId": "recommendationCount"})
    .sort_values("recommendationCount", ascending=False)
)

triple_savings_agg = (
    filtered_df.groupby(
        ["currentResourceType", "actionType", "savingsValueCategory"],
        dropna=False,
        as_index=False,
    )["estimatedMonthlySavings"]
    .sum()
    .rename(columns={"estimatedMonthlySavings": "totalEstimatedMonthlySavings"})
    .sort_values("totalEstimatedMonthlySavings", ascending=False)
)

monthly_savings_by_savings_band = (
    filtered_df.groupby("savingsValueCategory", dropna=False, as_index=False)["estimatedMonthlySavings"]
    .sum()
    .rename(columns={"estimatedMonthlySavings": "totalEstimatedMonthlySavings"})
)

savings_by_category_and_effort = (
    filtered_df.groupby(
        ["savingsValueCategory", "implementationEffort"],
        dropna=False,
        as_index=False,
    )["estimatedMonthlySavings"]
    .sum()
    .rename(columns={"estimatedMonthlySavings": "totalEstimatedMonthlySavings"})
)

# Create priority score aggregation - CORRECT: Average effort factors properly grouped
priority_agg = (
    filtered_df.groupby(
        ["currentResourceType", "actionType", "savingsValueCategory"],
        dropna=False,
        as_index=False,
    ).agg({
        "estimatedMonthlySavings": "sum",
        "recommendationId": "count",
        "effortFactor": "mean",  # Average effort factor for this specific combination
    })
    .rename(columns={
        "estimatedMonthlySavings": "totalEstimatedMonthlySavings",
        "recommendationId": "recommendationCount",
        "effortFactor": "effortFactor",
    })
)

# Calculate recommendation count factor for each group
priority_agg["recommendationCountFactor"] = priority_agg["recommendationCount"].apply(
    get_recommendation_count_factor
)

# Calculate priority score
priority_agg["priorityScore"] = priority_agg.apply(calculate_priority_score, axis=1)

# Sort by priority score
priority_agg = priority_agg.sort_values("priorityScore", ascending=False)

# Charts: CORA-style overview
row1_col1, row1_col2 = st.columns(2)
with row1_col1:
    fig = make_bar_chart(
        savings_by_account.head(15),
        x="accountName",
        y="estimatedMonthlySavings",
        title="Estimated Monthly Savings by Account",
    )
    if fig:
        st.plotly_chart(fig, use_container_width=True)

with row1_col2:
    fig = make_bar_chart(
        savings_by_resource_type,
        x="currentResourceType",
        y="estimatedMonthlySavings",
        title="Estimated Monthly Savings by Current Resource Type",
    )
    if fig:
        st.plotly_chart(fig, use_container_width=True)

row2_col1, row2_col2 = st.columns(2)
with row2_col1:
    fig = make_bar_chart(
        savings_by_action,
        x="actionType",
        y="estimatedMonthlySavings",
        title="Estimated Monthly Savings by Action Type",
    )
    if fig:
        st.plotly_chart(fig, use_container_width=True)

with row2_col2:
    fig = make_bar_chart(
        recommendations_by_effort,
        x="implementationEffort",
        y="recommendationCount",
        title="Recommendation Count by Implementation Effort",
    )
    if fig:
        st.plotly_chart(fig, use_container_width=True)

# Recommendation count by Savings Value Category

st.subheader("Recommendation count by Savings Value Category")

pie_df = recommendations_by_savings_band.copy()

if not pie_df.empty:
    savings_category_order = [
        ">=$1000/month",
        ">=$500/month and <$1000/month",
        ">=$100/month and <$500/month",
        ">=$1/month and <$100/month",
        "<$1/month",
        "Unknown",
    ]

    pie_df["savingsValueCategory"] = pd.Categorical(
        pie_df["savingsValueCategory"],
        categories=savings_category_order,
        ordered=True,
    )
    pie_df = pie_df.sort_values("savingsValueCategory")

    fig = px.pie(
        pie_df,
        names="savingsValueCategory",
        values="recommendationCount",
        title="Recommendation Count by Savings Value Category",
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label+value")
    fig.update_layout(
        height=450,
        margin=dict(l=20, r=20, t=60, b=20),
        legend_title="Savings Value Category",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data available for the selected filters.")

# Recommendation count by Resource Type + Action Type across Savings Value Categories

st.subheader("Recommendation count by Resource Type + Action Type across Savings Value Categories")

triple_panel_df = triple_agg.copy()

if not triple_panel_df.empty:
    savings_category_order = [
        ">=$1000/month",
        ">=$500/month and <$1000/month",
        ">=$100/month and <$500/month",
        ">=$1/month and <$100/month",
        "<$1/month",
        "Unknown",
    ]

    triple_panel_df["resourceAction"] = (
        triple_panel_df["currentResourceType"].fillna("Unknown").astype(str)
        + " | "
        + triple_panel_df["actionType"].fillna("Unknown").astype(str)
    )

    available_categories = [
        cat for cat in savings_category_order
        if cat in triple_panel_df["savingsValueCategory"].astype(str).unique()
    ]

    selected_panel_categories = st.multiselect(
        "Filter this panel by savings value category",
        options=available_categories,
        default=available_categories,
        key="triple_panel_savings_category_filter",
    )

    if selected_panel_categories:
        triple_panel_df = triple_panel_df[
            triple_panel_df["savingsValueCategory"].astype(str).isin(selected_panel_categories)
        ]

    if not triple_panel_df.empty:
        triple_panel_df["savingsValueCategory"] = pd.Categorical(
            triple_panel_df["savingsValueCategory"],
            categories=savings_category_order,
            ordered=True,
        )

        combo_order = (
            triple_panel_df.groupby("resourceAction", as_index=False)["recommendationCount"]
            .sum()
            .sort_values("recommendationCount", ascending=False)["resourceAction"]
            .tolist()
        )

        chart_df = triple_panel_df.sort_values(
            ["resourceAction", "savingsValueCategory"]
        )

        fig = px.bar(
            chart_df,
            x="resourceAction",
            y="recommendationCount",
            color="savingsValueCategory",
            category_orders={
                "resourceAction": combo_order,
                "savingsValueCategory": savings_category_order,
            },
            title="Recommendation Count for Each Resource Type / Action Type Combination by Savings Value Category",
            barmode="stack",
            text_auto=True,
        )
        fig.update_layout(
            xaxis_title="Current Resource Type | Action Type",
            yaxis_title="Recommendation Count",
            legend_title="Savings Value Category",
            height=550,
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        pivot_df = (
            triple_panel_df.pivot_table(
                index=["currentResourceType", "actionType"],
                columns="savingsValueCategory",
                values="recommendationCount",
                aggfunc="sum",
                fill_value=0,
            )
            .reindex(columns=selected_panel_categories, fill_value=0)
            .reset_index()
        )

        st.dataframe(
            pivot_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No data available for the selected savings value categories.")
else:
    st.info("No data available for the selected filters.")

# Total Estimated Monthly Savings by Savings Value Category

st.subheader("Total Estimated Monthly Savings by Savings Value Category")

savings_pie_df = monthly_savings_by_savings_band.copy()

if not savings_pie_df.empty:
    savings_category_order = [
        ">=$1000/month",
        ">=$500/month and <$1000/month",
        ">=$100/month and <$500/month",
        ">=$1/month and <$100/month",
        "<$1/month",
        "Unknown",
    ]

    savings_pie_df["savingsValueCategory"] = pd.Categorical(
        savings_pie_df["savingsValueCategory"],
        categories=savings_category_order,
        ordered=True,
    )
    savings_pie_df = savings_pie_df.sort_values("savingsValueCategory")

    fig = px.pie(
        savings_pie_df,
        names="savingsValueCategory",
        values="totalEstimatedMonthlySavings",
        title="Pie Chart of Total Estimated Monthly Savings by Savings Value Category",
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label+value")
    fig.update_layout(
        height=450,
        margin=dict(l=20, r=20, t=60, b=20),
        legend_title="Savings Value Category",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No savings data available for the selected filters.")

# Total Estimated Monthly Savings by Resource Type + Action Type across Savings Value Categories

st.subheader("Total Estimated Monthly Savings by Resource Type + Action Type across Savings Value Categories")

triple_savings_panel_df = triple_savings_agg.copy()

if not triple_savings_panel_df.empty:
    savings_category_order = [
        ">=$1000/month",
        ">=$500/month and <$1000/month",
        ">=$100/month and <$500/month",
        ">=$1/month and <$100/month",
        "<$1/month",
        "Unknown",
    ]

    triple_savings_panel_df["resourceAction"] = (
        triple_savings_panel_df["currentResourceType"].fillna("Unknown").astype(str)
        + " | "
        + triple_savings_panel_df["actionType"].fillna("Unknown").astype(str)
    )

    available_savings_categories = [
        cat for cat in savings_category_order
        if cat in triple_savings_panel_df["savingsValueCategory"].astype(str).unique()
    ]

    selected_savings_panel_categories = st.multiselect(
        "Filter savings panel by savings value category",
        options=available_savings_categories,
        default=available_savings_categories,
        key="triple_savings_panel_savings_category_filter",
    )

    if selected_savings_panel_categories:
        triple_savings_panel_df = triple_savings_panel_df[
            triple_savings_panel_df["savingsValueCategory"].astype(str).isin(
                selected_savings_panel_categories
            )
        ]

    if not triple_savings_panel_df.empty:
        triple_savings_panel_df["savingsValueCategory"] = pd.Categorical(
            triple_savings_panel_df["savingsValueCategory"],
            categories=savings_category_order,
            ordered=True,
        )

        combo_order = (
            triple_savings_panel_df.groupby("resourceAction", as_index=False)[
                "totalEstimatedMonthlySavings"
            ]
            .sum()
            .sort_values("totalEstimatedMonthlySavings", ascending=False)["resourceAction"]
            .tolist()
        )

        chart_df = triple_savings_panel_df.sort_values(
            ["resourceAction", "savingsValueCategory"]
        )

        fig = px.bar(
            chart_df,
            x="resourceAction",
            y="totalEstimatedMonthlySavings",
            color="savingsValueCategory",
            category_orders={
                "resourceAction": combo_order,
                "savingsValueCategory": savings_category_order,
            },
            title="Total Estimated Monthly Savings for Each Resource Type / Action Type Combination by Savings Value Category",
            barmode="stack",
            text_auto=".2s",
        )
        fig.update_layout(
            xaxis_title="Current Resource Type | Action Type",
            yaxis_title="Total Estimated Monthly Savings",
            legend_title="Savings Value Category",
            height=550,
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        pivot_df = (
            triple_savings_panel_df.pivot_table(
                index=["currentResourceType", "actionType"],
                columns="savingsValueCategory",
                values="totalEstimatedMonthlySavings",
                aggfunc="sum",
                fill_value=0,
            )
            .reindex(columns=selected_savings_panel_categories, fill_value=0)
            .reset_index()
        )

        st.dataframe(
            pivot_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No data available for the selected savings value categories.")
else:
    st.info("No savings data available for the selected filters.")

# Total Savings by Savings Value Category and Implementation Effort

st.subheader("Total Savings by Savings Value Category and Implementation Effort")

savings_effort_df = savings_by_category_and_effort.copy()

if not savings_effort_df.empty:
    savings_effort_df["implementationEffort"] = (
        savings_effort_df["implementationEffort"]
        .fillna("Unknown")
        .astype(str)
        .str.strip()
    )

    savings_effort_df = savings_effort_df.sort_values(
        ["savingsValueCategory", "implementationEffort"]
    )

    fig = px.bar(
        savings_effort_df,
        x="savingsValueCategory",
        y="totalEstimatedMonthlySavings",
        color="implementationEffort",
        title="Total Savings by Savings Value Category and Implementation Effort",
        barmode="stack",
        text_auto=".2s",
        category_orders={"savingsValueCategory": SAVINGS_CATEGORY_ORDER},
    )
    fig.update_layout(
        xaxis_title="Savings Value Category",
        yaxis_title="Total Estimated Monthly Savings",
        legend_title="Implementation Effort",
        height=500,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)

    pivot_df = (
        savings_effort_df.pivot_table(
            index="savingsValueCategory",
            columns="implementationEffort",
            values="totalEstimatedMonthlySavings",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(
            [
                c
                for c in SAVINGS_CATEGORY_ORDER
                if c in savings_effort_df["savingsValueCategory"].astype(str).unique()
            ],
            fill_value=0,
        )
        .reset_index()
        .round(2)
    )

    st.dataframe(
        pivot_df,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Drill-down: action type and resource type breakdown")

    drilldown_source_df = filtered_df.copy()
    drilldown_source_df["implementationEffort"] = (
        drilldown_source_df["implementationEffort"]
        .fillna("Unknown")
        .astype(str)
        .str.strip()
    )

    available_savings_categories = [
        c
        for c in SAVINGS_CATEGORY_ORDER
        if c in drilldown_source_df["savingsValueCategory"].astype(str).unique()
    ]

    available_efforts = sorted(
        drilldown_source_df["implementationEffort"].dropna().astype(str).unique().tolist()
    )

    drilldown_col1, drilldown_col2 = st.columns(2)

    with drilldown_col1:
        selected_drilldown_savings_category = st.selectbox(
            "Select savings value category",
            options=available_savings_categories,
            key="savings_effort_drilldown_category",
        )

    with drilldown_col2:
        selected_drilldown_effort = st.selectbox(
            "Select implementation effort",
            options=available_efforts,
            key="savings_effort_drilldown_effort",
        )

    drilldown_df = drilldown_source_df[
        (drilldown_source_df["savingsValueCategory"].astype(str) == selected_drilldown_savings_category)
        & (drilldown_source_df["implementationEffort"] == selected_drilldown_effort)
    ].copy()

    if not drilldown_df.empty:
        breakdown_df = (
            drilldown_df.groupby(
                ["actionType", "currentResourceType"],
                dropna=False,
                as_index=False,
            )["estimatedMonthlySavings"]
            .sum()
            .rename(columns={"estimatedMonthlySavings": "totalEstimatedMonthlySavings"})
            .sort_values("totalEstimatedMonthlySavings", ascending=False)
        )

        breakdown_df["actionResource"] = (
            breakdown_df["actionType"].fillna("Unknown").astype(str)
            + " | "
            + breakdown_df["currentResourceType"].fillna("Unknown").astype(str)
        )

        fig = px.bar(
            breakdown_df,
            x="actionResource",
            y="totalEstimatedMonthlySavings",
            title=(
                "Breakdown of Total Savings by Action Type / Resource Type "
                f"for {selected_drilldown_effort} effort in {selected_drilldown_savings_category}"
            ),
            text_auto=".2s",
        )
        fig.update_layout(
            xaxis_title="Action Type | Current Resource Type",
            yaxis_title="Total Estimated Monthly Savings",
            height=500,
            margin=dict(l=20, r=20, t=60, b=20),
        )
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            breakdown_df[["actionType", "currentResourceType", "totalEstimatedMonthlySavings"]].round(2),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No drill-down data available for the selected savings category and implementation effort.")
else:
    st.info("No data available for the selected filters.")

# NEW PANELS: Priority Score Analysis

st.divider()
st.header("Priority Score Analysis")

st.markdown("""
This section uses the following formula to calculate Priority Scores:

**Priority Score = (TotalEstimatedMonthlySavings^1.2) / ((effortFactor × recommendationCountFactor)^2)**

Where:
- **Effort Factor**: Average of effort factors for recommendations in the group (Low=1, Medium=2, High=6, Very High=10)
- **Recommendation Count Factor**: Based on total recommendations in the group (1-100 recs=1.0, 100-500=1.5, 500-1500=2.0, 1500+=3.0)

Higher priority scores indicate better opportunities (high savings, lower effort, fewer recommendations to process).
""")

# Panel 1: Priority Score Summary Table
st.subheader("Priority Score by Action Type / Resource Type / Savings Category")

if not priority_agg.empty:
    # Create display dataframe
    display_df = priority_agg[[
        "currentResourceType",
        "actionType",
        "savingsValueCategory",
        "recommendationCount",
        "totalEstimatedMonthlySavings",
        "effortFactor",
        "recommendationCountFactor",
        "priorityScore",
    ]].copy()
    
    # Rename columns for display
    display_df.columns = [
        "Resource Type",
        "Action Type",
        "Savings Category",
        "# Recommendations",
        "Total Monthly Savings",
        "Avg Effort Factor",
        "Count Factor",
        "Priority Score",
    ]
    
    # Format numeric columns
    display_df["Total Monthly Savings"] = display_df["Total Monthly Savings"].apply(
        lambda x: format_currency(x, currency)
    )
    display_df["Priority Score"] = display_df["Priority Score"].round(2)
    display_df["Avg Effort Factor"] = display_df["Avg Effort Factor"].round(2)
    display_df["Count Factor"] = display_df["Count Factor"].round(2)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No data available for priority score analysis.")

st.divider()

# Panel 2: Drill-down table for individual recommendations
st.subheader("Individual Recommendations Drill-Down")

st.markdown("Filter individual recommendations by Action Type, Resource Type, and Savings Category.")

drill_df = filtered_df.copy()

# Create filter columns
filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    available_actions = sorted([x for x in drill_df["actionType"].dropna().unique().tolist()])
    selected_action = st.selectbox(
        "Filter by Action Type",
        options=["All"] + available_actions,
        key="drill_action_type",
    )

with filter_col2:
    available_resources = sorted([x for x in drill_df["currentResourceType"].dropna().unique().tolist()])
    selected_resource = st.selectbox(
        "Filter by Resource Type",
        options=["All"] + available_resources,
        key="drill_resource_type",
    )

with filter_col3:
    available_categories = sorted([x for x in drill_df["savingsValueCategory"].dropna().unique().tolist()])
    selected_category = st.selectbox(
        "Filter by Savings Category",
        options=["All"] + available_categories,
        key="drill_savings_category",
    )

# Apply filters
drill_display_df = drill_df.copy()

if selected_action != "All":
    drill_display_df = drill_display_df[drill_display_df["actionType"] == selected_action]

if selected_resource != "All":
    drill_display_df = drill_display_df[drill_display_df["currentResourceType"] == selected_resource]

if selected_category != "All":
    drill_display_df = drill_display_df[drill_display_df["savingsValueCategory"] == selected_category]

# Sort by estimated monthly savings
drill_display_df = drill_display_df.sort_values("estimatedMonthlySavings", ascending=False)

if not drill_display_df.empty:
    preferred_columns = [
        "estimatedMonthlySavings",
        "estimatedAnnualSavings",
        "savingsValueCategory",
        "accountId",
        "accountName",
        "region",
        "currentResourceType",
        "recommendedResourceType",
        "actionType",
        "implementationEffort",
        "effortFactor",
        "estimatedMonthlyCost",
        "estimatedSavingsPercentage",
        "resourceId",
        "currentResourceSummary",
        "recommendedResourceSummary",
        "restartNeeded",
        "rollbackPossible",
        "source",
        "lastRefreshTimestamp",
        "recommendationId",
        "resourceArn",
    ]
    
    display_columns = [c for c in preferred_columns if c in drill_display_df.columns]
    
    st.dataframe(
        drill_display_df[display_columns],
        use_container_width=True,
        hide_index=True,
    )
    
    st.markdown(f"**Showing {len(drill_display_df)} recommendations**")
else:
    st.info("No recommendations match the selected filters.")

st.divider()

# Detailed recommendations table (original)
st.subheader("Detailed recommendations")

preferred_columns = [
    "estimatedMonthlySavings",
    "estimatedAnnualSavings",
    "savingsValueCategory",
    "accountId",
    "accountName",
    "region",
    "currentResourceType",
    "recommendedResourceType",
    "resourceId",
    "actionType",
    "currentResourceSummary",
    "recommendedResourceSummary",
    "estimatedMonthlyCost",
    "estimatedSavingsPercentage",
    "implementationEffort",
    "effortFactor",
    "restartNeeded",
    "rollbackPossible",
    "source",
    "lastRefreshTimestamp",
    "recommendationId",
    "resourceArn",
    "tag_owner",
    "tag_environment_name",
    "tag_is_production",
    "tag_application",
    "tag_business_unit",
    "tag_source_code",
]

display_columns = [c for c in preferred_columns if c in filtered_df.columns]
st.dataframe(
    filtered_df[display_columns].sort_values(
        by="estimatedMonthlySavings", ascending=False
    ),
    use_container_width=True,
    hide_index=True,
)

# Download enriched data
st.subheader("Download enriched dataset")
csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download filtered/enriched CSV",
    data=csv_bytes,
    file_name="aws_cost_optimization_hub_enriched.csv",
    mime="text/csv",
)

render_footer()

