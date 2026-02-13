import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="TrafficLens Data Lake", layout="wide")

st.title("🚦 TrafficLens Data Lake Explorer")

# --- Sidebar ---
st.sidebar.header("Data Lake Connection")
# In AWS, this would point to 's3://trafficlens-gold/'
DATA_PATH = "datalake/gold"

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

# --- Main Page: KPIs ---
if "dim_trips" not in st.session_state:
    st.session_state["trips_df"] = load_data("dim_trips")

df_trips = st.session_state["trips_df"]

if not df_trips.empty:
    col1, col2, col3 = st.columns(3)
    
    total_distance = df_trips['estimated_distance_km'].sum()
    total_duration = df_trips['duration_seconds'].sum() / 3600.0 # Hours
    max_speed = df_trips['max_speed_kmh'].max()
    
    col1.metric("Total Distance", f"{total_distance:.2f} km")
    col2.metric("Total Hours", f"{total_duration:.2f} h")
    col3.metric("Max Speed Ever", f"{max_speed:.1f} km/h")
    
    st.subheader("Recent Trips")
    st.dataframe(df_trips.sort_values("start_time", ascending=False).head(10))
else:
    st.warning("No Trip Data found in Gold Layer. Run 'dbt run' first.")

st.markdown("---")
st.info("💡 **Architecture Note:** This dashboard reads pre-aggregated Parquet files from the Gold Layer (Serverless).")
