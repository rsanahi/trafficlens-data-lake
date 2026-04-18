import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="TrafficLens Data Lake", layout="wide", page_icon="🚦")

# --- Custom Styling: Glassmorphism & Premium UI ---
st.markdown("""
<style>
    /* Main Background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    
    /* Metrics Container (Glassmorphism) */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        color: #f8fafc !important;
    }
    
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease-in-out;
    }
    
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        border: 1px solid rgba(14, 165, 233, 0.5);
    }

    /* DataFrame custom borders */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    h1, h2, h3 {
        color: #38bdf8 !important;
        font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)


st.title("🚦 TrafficLens Data Lake Explorer")
st.markdown("Welcome to the **Curated Layer** of your Data Lake. Analyze your trip summaries and deep-learning object detections.")

# --- Sidebar ---
st.sidebar.markdown("### 🌐 Architecture")
st.sidebar.info("This dashboard executes Serverless SQL across Parquet files residing in the **Curated Layer** (`datalake/curated/`).")
DATA_PATH = "datalake/curated"

@st.cache_data
def load_data(table_name):
    query = f"SELECT * FROM read_parquet('{DATA_PATH}/{table_name}.parquet')"
    try:
        con = duckdb.connect(database=':memory:')
        df = con.execute(query).df()
        return df
    except Exception as e:
        st.error(f"Error loading {table_name}: {e}")
        return pd.DataFrame()

# --- Data Loading ---
df_trips = load_data("dim_trips")
df_counts = load_data("fct_vehicle_counts")

if df_trips.empty and df_counts.empty:
    st.warning("⚠️ No Data found in the Curated Layer. Please run the `batch_ingest.py` and `dbt run` first.")
    st.stop()

# --- Main Page: KPIs ---
st.markdown("### 📊 High-Level Metrics")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

total_distance = df_trips['estimated_distance_km'].sum() if not df_trips.empty else 0
total_duration = df_trips['duration_seconds'].sum() / 3600.0 if not df_trips.empty else 0
# Compute aggregate detections
total_cars = int(df_counts['car_count'].sum()) if not df_counts.empty and 'car_count' in df_counts.columns else 0
total_motorcycles = int(df_counts['motorcycle_count'].sum()) if not df_counts.empty and 'motorcycle_count' in df_counts.columns else 0

kpi1.metric("🛣️ Total Distance", f"{total_distance:.2f} km")
kpi2.metric("⏱️ Total Hours", f"{total_duration:.2f} h")
kpi3.metric("🚗 Cars Detected", f"{total_cars:,}")
kpi4.metric("🏍️ M-Cycles Detected", f"{total_motorcycles:,}")

st.markdown("---")

# --- Visualizations ---
if not df_counts.empty:
    st.markdown("### 📈 Detection Trends")
    
    # Aggregate counts by Trip (source_file)
    df_agg = df_counts.groupby('source_file')[['car_count', 'motorcycle_count']].sum().reset_index()
    # Sort for better display 
    df_agg = df_agg.sort_values(by='car_count', ascending=False)
    
    # Plotly Stacked Bar
    fig = px.bar(
        df_agg, 
        x="source_file", 
        y=["car_count", "motorcycle_count"], 
        title="Vehicle Detections per Trip",
        labels={"value": "Count", "source_file": "Video Source", "variable": "Vehicle Type"},
        color_discrete_sequence=["#38bdf8", "#fbbf24"],
        template="plotly_dark"
    )
    
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_title="",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
# --- DataTables ---
st.markdown("### 🚗 Recent Trips Summary (`dim_trips`)")
if not df_trips.empty:
    st.dataframe(df_trips.sort_values("start_time", ascending=False).head(15), use_container_width=True)
