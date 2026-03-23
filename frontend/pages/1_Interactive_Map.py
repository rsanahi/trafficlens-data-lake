import streamlit as st
import duckdb
import pandas as pd
import pydeck as pdk
from datetime import datetime, time

st.set_page_config(page_title="Interactive Map | TrafficLens", layout="wide")

st.title("🗺️ Interactive Route Map")

# Path to Silver Telemetry (Partitioned data)
import glob
DATA_DIR = "datalake/silver/telemetry"

@st.cache_data
def load_telemetry():
    """Laws full telemetry data from Silver Layer"""
    # Find all parquet files recursively
    files = glob.glob(f"{DATA_DIR}/**/*.parquet", recursive=True)
    
    if not files:
        st.error(f"No parquet files found in {DATA_DIR}")
        return pd.DataFrame()
        
    st.sidebar.info(f"Loaded {len(files)} partition files.")
    
    # Read directly with glob pattern which debug script proved works
    query = f"""
        SELECT 
            event_time, 
            latitude, 
            longitude, 
            speed_kmh,
            frame_filename,
            source_file
        FROM read_parquet('{DATA_DIR}/**/*.parquet')
        ORDER BY event_time
    """
    try:
        con = duckdb.connect(database=':memory:')
        df = con.execute(query).df()
        return df
    except Exception as e:
        st.error(f"Error loading telemetry: {e}")
        return pd.DataFrame()

@st.cache_data
def load_trips():
    """Laws trip metadata from Gold Layer"""
    try:
        con = duckdb.connect(database=':memory:')
        # Read the single Gold parquet file
        df = con.execute("SELECT * FROM read_parquet('datalake/gold/dim_trips.parquet')").df()
        return df
    except Exception as e:
        # If gold layer not ready, return empty
        return pd.DataFrame()

# Load Data
trips_df = load_trips()
df = load_telemetry()

# Check if data exists
if df.empty or trips_df.empty:
    st.warning("No telemetry or trip data found. Please process videos first.")
    st.stop()

# --- Filters ---
st.sidebar.markdown("### 🔍 Filters")

# 1. Date Filter (Top level)
min_date = df['event_time'].min().date()
max_date = df['event_time'].max().date()

selected_date = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

filtered_df = df.copy()
filtered_trips_df = trips_df.copy()

# Apply Date Filter
if isinstance(selected_date, tuple) and len(selected_date) == 2:
    start_d, end_d = selected_date
    filtered_df = filtered_df[(filtered_df['event_time'].dt.date >= start_d) & (filtered_df['event_time'].dt.date <= end_d)]
    filtered_trips_df = filtered_trips_df[(filtered_trips_df['start_time'].dt.date >= start_d) & (filtered_trips_df['start_time'].dt.date <= end_d)]
elif isinstance(selected_date, tuple) and len(selected_date) == 1:
    s_d = selected_date[0]
    filtered_df = filtered_df[filtered_df['event_time'].dt.date == s_d]
    filtered_trips_df = filtered_trips_df[filtered_trips_df['start_time'].dt.date == s_d]

# 2. Trip Filter (Dependent on Date)
st.sidebar.markdown("### 🚗 Trips")

selected_trips = []
if not filtered_trips_df.empty:
    # Create readable labels: "YYYY-MM-DD HH:MM (15 min)"
    filtered_trips_df['label'] = filtered_trips_df.apply(
        lambda x: f"{x['start_time'].strftime('%Y-%m-%d %H:%M')} ({x['duration_seconds']//60} min)", axis=1
    )
    
    # Filter trips to only those that have points in the loaded Silver data
    if not filtered_df.empty and 'source_file' in filtered_df.columns:
        valid_trips = filtered_df['source_file'].unique()
        filtered_trips_df = filtered_trips_df[filtered_trips_df['trip_id'].isin(valid_trips)]
    
    # Sort by recent
    filtered_trips_df = filtered_trips_df.sort_values('start_time', ascending=False)
    trip_options = dict(zip(filtered_trips_df['trip_id'], filtered_trips_df['label']))
    
    selected_trips = st.sidebar.multiselect(
        "Filter by Trip",
        options=trip_options.keys(),
        default=None,  # Do not select by default if user just wants all trips on that date
        format_func=lambda x: trip_options[x]
    )

# Apply Trip Filter if selected
if selected_trips:
    filtered_df = filtered_df[filtered_df['source_file'].isin(selected_trips)]

# Sidebar: Debug Info
st.sidebar.markdown("---")
st.sidebar.text(f"Raw Points: {len(df)}")
st.sidebar.text(f"Total Trips: {len(trips_df)}")

st.write(f"Showing **{len(filtered_df)}** points.")

# Map Style Selector
map_style_options = {
    "Simple (No Token)": "simple",
    "Streets (Requires Token)": "mapbox://styles/mapbox/streets-v11",
    "Satellite (Requires Token)": "mapbox://styles/mapbox/satellite-streets-v11",
}
selected_style_name = st.sidebar.selectbox("Map Style", list(map_style_options.keys()), index=0)

# Color Logic
color_mode = st.sidebar.radio("Color By", ["Speed", "Trip"])

if color_mode == "Trip":
    # Let's map unique trips to colors in a new column list [R, G, B, A]
    unique_trips = filtered_df['source_file'].unique()
    import random
    trip_colors = {t: [random.randint(50, 255), random.randint(50, 255), random.randint(50, 255), 180] for t in unique_trips}
    
    filtered_df['color'] = filtered_df['source_file'].map(trip_colors)
    get_color_logic = "color"
else:
    # PyDeck implementation needed for dynamic speed color, for now static Red
    get_color_logic = "[200, 30, 0, 160]"

if not filtered_df.empty:
    layer = pdk.Layer(
        "ScatterplotLayer",
        filtered_df,
        id="trip_scatter",
        get_position=["longitude", "latitude"],
        get_color=get_color_logic, 
        get_radius=3, # Smaller radius (3 meters)
        pickable=True,
        auto_highlight=True,
        opacity=0.8,
        filled=True,
        radius_min_pixels=2,
        radius_max_pixels=6,
    )
    
    tooltip = {
        "html": "<b>Trip:</b> {source_file}<br/><b>Time:</b> {event_time}<br/><b>Speed:</b> {speed_kmh} km/h",
        "style": {"backgroundColor": "steelblue", "color": "white"}
    }

    view_state = pdk.ViewState(
        latitude=filtered_df["latitude"].mean(),
        longitude=filtered_df["longitude"].mean(),
        zoom=13,
        pitch=0,
    )

    try:
        # Determine map style
        style_uri = map_style_options[selected_style_name]
        if style_uri == "simple":
            style_uri = None # Let Streamlit pick default
            
        r = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style=style_uri
        )
        
        event = st.pydeck_chart(r, on_select="rerun", selection_mode="single-object")
        
        # Extract selection from our named layer
        selected_points = event.selection.objects.get("trip_scatter", []) if hasattr(event, "selection") else []
        if selected_points:
            trip_path = selected_points[0].get("source_file")
            if trip_path:
                st.success("🎯 You selected a Trip! Click the copy icon below to copy its path:")
                st.code(trip_path, language="text")
                
    except Exception as e:
        st.error(f"Error rendering map: {e}.")
        
    # Show data table below
    with st.expander("See Raw Data"):
        st.dataframe(filtered_df)
        
else:
    st.warning("No data found for the selected time range.")
