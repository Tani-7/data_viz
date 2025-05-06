import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import folium_static
import altair as alt
import geopandas as gpd
from shapely.geometry import Point, Polygon
from folium.plugins import MarkerCluster, HeatMap
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
import requests
from io import StringIO


# LOADING THE DATA

@st.cache_data
def load_data():
    url = "https://raw.githubusercontent.com/plotly/datasets/master/airbnb-data.csv"
    df = pd.read_csv(url)

    # Data on the  NYC borough boundaries
    nyc_geo = requests.get(
        "https://data.cityofnewyork.us/api/geospatial/tqmj-j8zm?method=export&format=GeoJSON").json()

    # Get subway routes (sample data)
    subway_url = "https://raw.githubusercontent.com/jupyter-widgets/ipyleaflet/master/examples/subway_lines.geojson"
    subway_routes = requests.get(subway_url).json()

    return df, nyc_geo, subway_routes


df, nyc_geo, subway_routes = load_data()

# Streamlit App Configuration
st.set_page_config(layout="wide")
st.title("NYC Airbnb Analytics: Urban Insights Dashboard")

# Sidebar Controls
st.sidebar.header("Filters")
price_range = st.sidebar.slider(
    "Price Range (USD)",
    int(df.price.min()),
    int(df.price.max()),
    (50, 300)
)

borough_filter = st.sidebar.multiselect(
    "Select Boroughs",
    options=df.neighbourhood_group.unique(),
    default=df.neighbourhood_group.unique()
)

# Data Filtering
filtered_df = df[
    (df.price.between(price_range[0], price_range[1])) &
    (df.neighbourhood_group.isin(borough_filter))
]

# Main Dashboard Layout
tab1, tab2, tab3, tab4 = st.tabs([
    "Interactive Map",
    "Neighborhood Analysis",
    "Landmark Impact",
    "Transit Correlation"
])

# Tab 1: Interactive Map with Folium
with tab1:
    col1, col2 = st.columns([3, 1])

    with col1:
        # Create Folium Cluster Map
        m = folium.Map(location=[40.7128, -74.0060], zoom_start=11)
        marker_cluster = MarkerCluster().add_to(m)

        # Add price gradient circles
        for idx, row in filtered_df.iterrows():
            folium.CircleMarker(
                location=[row.latitude, row.longitude],
                radius=3,
                color='#3186cc' if row.price < 100 else '#cc3131',
                fill=True,
                fill_opacity=0.7,
                tooltip=f"${row.price} | {row.neighbourhood}"
            ).add_to(marker_cluster)

        # Add Heatmap
        HeatMap(
            data=filtered_df[['latitude', 'longitude', 'price']].values,
            radius=20,
            blur=15
        ).add_to(m)

        folium_static(m, width=1000, height=600)

    with col2:
        st.subheader("Price Distribution")
        hist = alt.Chart(filtered_df).mark_bar().encode(
            alt.X("price:Q", bin=True, title="Price"),
            alt.Y("count()", title="Number of Listings"),
            tooltip=['count()']
        ).interactive()
        st.altair_chart(hist, use_container_width=True)

# Tab 2: Linked Charts with Altair
with tab2:
    # Linked Selection
    brush = alt.selection_interval(encodings=['x'])

    # Scatter Plot
    scatter = alt.Chart(filtered_df).mark_circle().encode(
        x='longitude:Q',
        y='latitude:Q',
        color='neighbourhood_group:N',
        size='price:Q',
        tooltip=['neighbourhood:N', 'price:Q']
    ).add_selection(brush).properties(width=800, height=400)

    # Bar Chart
    bars = alt.Chart(filtered_df).mark_bar().encode(
        y='neighbourhood:N',
        x='average(price):Q',
        color='neighbourhood_group:N',
        tooltip=['neighbourhood:N', 'average(price):Q']
    ).transform_filter(brush).properties(width=800, height=200)

    st.altair_chart(scatter & bars)

# Tab 3: Landmark Buffer Analysis
with tab3:
    # Create GeoDataFrame
    geometry = [Point(xy) for xy in zip(
        filtered_df.longitude, filtered_df.latitude)]
    gdf = gpd.GeoDataFrame(filtered_df, geometry=geometry, crs="EPSG:4326")

    # Define Landmarks
    landmarks = {
        "Central Park": Polygon([[-73.9730, 40.7642],
                                [-73.9587, 40.8005],
                                [-73.9814, 40.7969],
                                [-73.9492, 40.7642]]),
        "Statue of Liberty": Point(-74.0445, 40.6892)
    }

    # Create Buffer Zones
    buffers = {
        name: geom.buffer(0.02)  # ~1.5km radius
        for name, geom in landmarks.items()
    }

    # Spatial Queries
    central_park_listings = gdf[gdf.within(buffers["Central Park"])]
    sol_listings = gdf[gdf.within(buffers["Statue of Liberty"])]

    # Visualization
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Central Park Buffer Zone")
        st.metric("Listings in Area", len(central_park_listings))
        st.dataframe(central_park_listings[['name', 'price', 'neighbourhood']])

    with col2:
        st.subheader("Statue of Liberty Buffer Zone")
        st.metric("Listings in Area", len(sol_listings))
        st.dataframe(sol_listings[['name', 'price', 'neighbourhood']])

# Tab 4: Transit Correlation with Bokeh
with tab4:
    # Prepare Subway Data
    subway_lines = []
    for feature in subway_routes['features']:
        if feature['geometry']['type'] == 'LineString':
            coords = feature['geometry']['coordinates']
            subway_lines.append({
                'xs': [c[0] for c in coords],
                'ys': [c[1] for c in coords]
            })

    # Create Bokeh Plot
    p = figure(title="Subway Routes & Airbnb Density",
               x_range=(-74.1, -73.7), y_range=(40.5, 40.9),
               width=1000, height=600)

    # Plot Subway Lines
    for line in subway_lines:
        p.line(x=line['xs'], y=line['ys'], line_width=2, color='blue')

    # Plot Airbnb Listings
    source = ColumnDataSource(filtered_df)
    p.circle(x='longitude', y='latitude', size=5,
             fill_alpha=0.6, fill_color='red',
             line_color=None, source=source)

    st.bokeh_chart(p)

# Best Value Heatmap
st.header("Best Value Neighborhoods")
col1, col2 = st.columns([2, 1])

with col1:
    # Calculate value score
    filtered_df['value_score'] = filtered_df['number_of_reviews'] * \
        filtered_df['review_scores_rating'] / filtered_df['price']

    # Create HeatMap
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=11)
    HeatMap(
        data=filtered_df[['latitude', 'longitude', 'value_score']].values,
        radius=20,
        blur=15,
        gradient={0.4: 'blue', 0.6: 'lime', 1: 'red'}
    ).add_to(m)

    folium_static(m, width=1000, height=400)

with col2:
    st.subheader("Value Score Formula")
    st.latex(
        r'''\text{Value Score} = \frac{\text{Number of Reviews} \times \text{Rating}}{\text{Price}}''')
    st.write("Higher scores indicate better value listings")
