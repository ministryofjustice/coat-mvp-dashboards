import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Car Color Dashboard",
    page_icon="🚗",
    layout="wide",
)

st.title("🚗 Car Color Dashboard")
st.caption("Explore the distribution of car colors.")

COLOR_MAP = {
    "White": "#E5E7EB",
    "Black": "#222222",
    "Gray": "#808080",
    "Silver": "#C0C0C0",
    "Blue": "#2563EB",
    "Red": "#DC2626",
    "Brown": "#92400E",
    "Green": "#16A34A",
    "Yellow": "#EAB308",
    "Orange": "#F97316",
}

sample = pd.DataFrame({
    "color": list(COLOR_MAP),
    "count": [320, 240, 180, 120, 90, 75, 30, 25, 12, 8],
})

st.sidebar.header("Dashboard settings")
uploaded_file = st.sidebar.file_uploader(
    "Upload car color data",
    type=["csv"],
    help="Required columns: color, count. Counts must be non-negative integers.",
)

if uploaded_file is None:
    data = sample.copy()
    st.info("Showing illustrative sample data—not actual market statistics.")
else:
    try:
        data = pd.read_csv(uploaded_file)
        if not {"color", "count"}.issubset(data.columns):
            raise ValueError("Your CSV must contain 'color' and 'count' columns.")

        data = data[["color", "count"]].copy()
        if data.empty:
            raise ValueError("Your CSV contains no rows.")

        if data["color"].isna().any():
            raise ValueError("Every row must have a color.")

        data["color"] = data["color"].astype(str).str.strip().str.title()
        if data["color"].eq("").any():
            raise ValueError("Color names cannot be blank.")

        data["count"] = pd.to_numeric(data["count"], errors="raise")
        counts = data["count"]
        if (
            counts.isna().any()
            or counts.isin([float("inf"), float("-inf")]).any()
            or (counts < 0).any()
            or (counts % 1 != 0).any()
        ):
            raise ValueError("Counts must be finite, non-negative whole numbers.")

        data = data.groupby("color", as_index=False)["count"].sum()
    except Exception as exc:
        st.error(f"Unable to load data: {exc}")
        st.stop()

selected_colors = st.sidebar.multiselect(
    "Colors to include",
    options=sorted(data["color"].unique()),
    default=sorted(data["color"].unique()),
)

filtered = (
    data[data["color"].isin(selected_colors)]
    .sort_values("count", ascending=False)
    .reset_index(drop=True)
)

if filtered.empty or filtered["count"].sum() == 0:
    st.warning("Select at least one color with a positive count.")
    st.stop()

total = filtered["count"].sum()
filtered["share_percent"] = filtered["count"] / total * 100
leader = filtered.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Total cars", f"{total:,.0f}")
col2.metric("Colors with cars", int((filtered["count"] > 0).sum()))
col3.metric(
    "Most common color",
    leader["color"],
    f"{leader['share_percent']:.1f}% of selected cars",
    delta_color="off",
)

left, right = st.columns([3, 2])

with left:
    st.subheader("Cars by color")
    bar = px.bar(
        filtered,
        x="color",
        y="count",
        color="color",
        color_discrete_map=COLOR_MAP,
        text="count",
        labels={"color": "Car color", "count": "Number of cars"},
    )
    bar.update_traces(marker_line_color="#64748B", marker_line_width=1)
    bar.update_layout(showlegend=False, xaxis_tickangle=-30)
    st.plotly_chart(bar, use_container_width=True)

with right:
    st.subheader("Color distribution")
    donut = px.pie(
        filtered,
        names="color",
        values="count",
        color="color",
        color_discrete_map=COLOR_MAP,
        hole=0.5,
    )
    donut.update_traces(
        textinfo="percent+label",
        marker_line_color="#64748B",
        marker_line_width=1,
    )
    donut.update_layout(showlegend=False)
    st.plotly_chart(donut, use_container_width=True)

st.subheader("Data breakdown")
st.caption("Percentages are calculated from the selected colors.")
st.dataframe(
    filtered,
    column_config={
        "color": "Color",
        "count": st.column_config.NumberColumn("Cars", format="%d"),
        "share_percent": st.column_config.NumberColumn(
            "Share (%)", format="%.2f"
        ),
    },
    hide_index=True,
    use_container_width=True,
)

st.download_button(
    label="📥 Download filtered data",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="car_color_data.csv",
    mime="text/csv",
)