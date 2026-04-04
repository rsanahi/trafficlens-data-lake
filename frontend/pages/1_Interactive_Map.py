import streamlit as st
import duckdb
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="Interactive Map | TrafficLens", layout="wide", page_icon="🗺️")

# Custom CSS for dark modern theme matching app.py
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #38bdf8 !important;
        font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🗺️ Interactive Route Map")
st.markdown("Visualize trips and object detections simultaneously using **PyDeck** against the `fct_vehicle_counts` Curated Data Mart.")

@st.cache_data
def load_telemetry_detects():
    """Load Curated Fact table containing both telemetry + YOLO detections"""
    query = """
        SELECT 
            event_time, 
            latitude, 
            longitude, 
            speed_kmh,
            source_file,
            car_count,
            motorcycle_count,
            total_vehicles
        FROM read_parquet('datalake/curated/fct_vehicle_counts.parquet')
        ORDER BY event_time
    """
    try:
        con = duckdb.connect(database=':memory:')
        df = con.execute(query).df()
        return df
    except Exception as e:
        st.sidebar.error(f"Error loading curated fact table: {e}")
        return pd.DataFrame()

@st.cache_data
def load_trips():
    """Load trip metadata from Curated Layer"""
    try:
        con = duckdb.connect(database=':memory:')
        df = con.execute("SELECT * FROM read_parquet('datalake/curated/dim_trips.parquet')").df()
        return df
    except Exception as e:
        return pd.DataFrame()

# --- Load Data Phase ---
df = load_telemetry_detects()
trips_df = load_trips()

if df.empty or trips_df.empty:
    st.warning("⚠️ No data found. Please run the `batch_ingest.py` and `dbt run` first.")
    st.stop()

# --- View Filters ---
st.sidebar.markdown("### 🔍 Filters")

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

# Date Filter Logic
if isinstance(selected_date, tuple) and len(selected_date) == 2:
    start_d, end_d = selected_date
    filtered_df = filtered_df[(filtered_df['event_time'].dt.date >= start_d) & (filtered_df['event_time'].dt.date <= end_d)]
    filtered_trips_df = filtered_trips_df[(filtered_trips_df['start_time'].dt.date >= start_d) & (filtered_trips_df['start_time'].dt.date <= end_d)]
elif isinstance(selected_date, tuple) and len(selected_date) == 1:
    s_d = selected_date[0]
    filtered_df = filtered_df[filtered_df['event_time'].dt.date == s_d]
    filtered_trips_df = filtered_trips_df[filtered_trips_df['start_time'].dt.date == s_d]

# Trip Selection filter
st.sidebar.markdown("### 🚗 Trip Breakdown")
selected_trips = []
if not filtered_trips_df.empty:
    filtered_trips_df['label'] = filtered_trips_df.apply(
        lambda x: f"{x['start_time'].strftime('%Y-%m-%d %H:%M')} ({x['duration_seconds']//60} min)", axis=1
    )
    
    if not filtered_df.empty and 'source_file' in filtered_df.columns:
        valid_trips = filtered_df['source_file'].unique()
        filtered_trips_df = filtered_trips_df[filtered_trips_df['trip_id'].isin(valid_trips)]
    
    filtered_trips_df = filtered_trips_df.sort_values('start_time', ascending=False)
    trip_options = dict(zip(filtered_trips_df['trip_id'], filtered_trips_df['label']))
    
    selected_trips = st.sidebar.multiselect(
        "Focus Trip",
        options=trip_options.keys(),
        format_func=lambda x: trip_options[x]
    )

if selected_trips:
    filtered_df = filtered_df[filtered_df['source_file'].isin(selected_trips)]

st.sidebar.markdown("---")
st.sidebar.caption(f"Raw Points Plotted: {len(filtered_df)}")

# --- Color Scheme & Map Setup ---
color_mode = st.columns(2)[1].radio("🎨 Color Points By", ["Traffic Congestion", "Individual Trips"], horizontal=True)

if color_mode == "Traffic Congestion":
    # Custom color function mapping [R, G, B, A] output
    def congestion_color(val):
        if val == 0:
            return [56, 189, 248, 180] # Light Blue (sky-400) - Clear Road
        elif val <= 2:
            return [250, 204, 21, 200]  # Yellow (yellow-400) - Minor Traffic
        elif val <= 5:
            return [249, 115, 22, 220]  # Orange (orange-500) - Moderate
        else:
            return [239, 68, 68, 220]   # Red (red-500) - Heavy Traffic
            
    filtered_df['color'] = filtered_df['total_vehicles'].apply(congestion_color)
else:
    # Color by Trip 
    unique_trips = filtered_df['source_file'].unique()
    import random
    trip_colors = {t: [random.randint(80, 255), random.randint(80, 255), random.randint(80, 255), 180] for t in unique_trips}
    filtered_df['color'] = filtered_df['source_file'].map(trip_colors)

# --- Rendering the PyDeck Map ---
if not filtered_df.empty:
    layer = pdk.Layer(
        "ScatterplotLayer",
        filtered_df,
        id="scatter_layer",
        get_position=["longitude", "latitude"],
        get_color="color", 
        get_radius=5, # Scale point up slightly
        pickable=True,
        auto_highlight=True,
        opacity=0.8,
        filled=True,
        radius_min_pixels=3,
        radius_max_pixels=10,
    )
    
    tooltip = {
        "html": (
            "<div style='font-family: Inter;'>"
            "<b>Trip:</b> {source_file}<br/>"
            "<b>Time:</b> {event_time}<br/>"
            "<b>Speed:</b> {speed_kmh} km/h<hr style='margin:4px 0;'/>"
            "<b>🚗 Cars:</b> {car_count}&nbsp;&nbsp;&nbsp;<b>🏍 M-Cycles:</b> {motorcycle_count}"
            "</div>"
        ),
        "style": {
            "backgroundColor": "rgba(30, 41, 59, 0.9)",
            "color": "white",
            "border": "1px solid #38bdf8",
            "borderRadius": "8px"
        }
    }

    # Center Map on viewport
    current_filters = f"{selected_date}_{selected_trips}"
    if "map_filters" not in st.session_state or st.session_state.map_filters != current_filters:
        st.session_state.view_state = pdk.ViewState(
            latitude=filtered_df["latitude"].mean(),
            longitude=filtered_df["longitude"].mean(),
            zoom=14,
            pitch=35, # Slight angle for modern feel
        )
        st.session_state.map_filters = current_filters

    view_state = st.session_state.view_state

    # Map Style selector
    style_opts = {"Dark (Premium)": "mapbox://styles/mapbox/dark-v10", "Streets": "mapbox://styles/mapbox/streets-v11"}
    selected_style = st.columns(2)[0].selectbox("Map Style (Requires Mapbox Token in Streamlit Env)", list(style_opts.keys()), index=0)
    
    try:
        r = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style=style_opts[selected_style]
        )
        st.pydeck_chart(r)
    except Exception as e:
        st.error(f"Error rendering map: {e}.")
        
    with st.expander("📉 View Raw Data Table"):
        st.dataframe(filtered_df, use_container_width=True)
else:
    st.warning("No tracking data available for the chosen parameters.")
