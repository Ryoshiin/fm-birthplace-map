import os
import re
import pandas as pd
from io import StringIO
import requests
import time
import folium
import streamlit as st
import streamlit.components.v1 as components
import json
from folium.plugins import MarkerCluster
from constants import FIFA_TO_COUNTRY, PROVINCE_LOOKUP

LOCATIONIQ_SEARCH_URL = "https://eu1.locationiq.com/v1/search"

# Setup page config
st.set_page_config(
    page_title="FM Birthplace Map Generator",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS styling
st.markdown(
    """
    <style>
    /* ===== Page Header ===== */
    .main-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }

    /* ===== Upload Section ===== */
    .upload-section {
        background: #f8fafc;
        padding: 2rem;
        border-radius: 10px;
        border: 2px dashed #cbd5e0;
        text-align: center;
        margin: 2rem 0;
    }
    .upload-section h3 {
        margin-bottom: 0.5rem;
    }
    .upload-section p {
        margin-top: 0;
        color: #374151;
    }

    /* ===== Stats Cards ===== */
    .stats-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
        margin-bottom: 1rem;
    }
    .stats-card h3 {
        margin: 0;
        font-size: 2rem;
        color: #2563EB;
    }
    .stats-card p {
        margin: 0;
        color: #374151;
    }

    /* ===== Progress Bar Color ===== */
    .stProgress > div > div > div > div {
        background-color: #667eea !important;
    }

    /* ===== Clear Data Button ===== */
    .clear-container {
        text-align: center;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
    .clear-container .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 10px;
        font-weight: 600;
        font-size: 14px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        transition: all 0.3s ease;
        min-width: 200px;
    }
    .clear-container .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.3);
    }
    
    /* ===== Info Icon Tooltip ===== */
    .info-icon {
        display: inline-block;
        color: #667eea;
        margin-left: 8px;
        cursor: pointer;
        font-size: 20px;
        vertical-align: middle;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Init session state
if "geocode_cache" not in st.session_state:
    st.session_state.geocode_cache = {}
if "players_data" not in st.session_state:
    st.session_state.players_data = None

def load_cache():
    """Load geocoding cache from disk if available"""
    cache_file = "geocode_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    """Save geocoding cache to disk"""
    cache_file = "geocode_cache.json"
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except:
        pass

def _alpha3_to_country_name(alpha3: str) -> str:
    """Convert FIFA code to country name"""
    key = alpha3.strip().upper()
    return FIFA_TO_COUNTRY.get(key, alpha3)

def build_query_key(row):
    """Create geocoding query from city and country info"""
    base = row["BirthCity_base"]
    paren = row.get("BirthCity_paren", None)
    nob = row.get("NoB", None)

    parts = [base]
    used_country = False

    if isinstance(paren, str) and paren.strip():
        uc = paren.strip().upper()
        if len(uc) == 3 and uc in FIFA_TO_COUNTRY:
            parts.append(_alpha3_to_country_name(uc))
            used_country = True
        elif len(uc) == 2 and uc in PROVINCE_LOOKUP:
            parts.append(PROVINCE_LOOKUP[uc])
        else:
            parts.append(paren.strip())

    if not used_country and isinstance(nob, str) and nob.strip():
        if len(nob.strip()) == 3 and nob.strip().upper() in FIFA_TO_COUNTRY:
            parts.append(_alpha3_to_country_name(nob.strip().upper()))
        else:
            parts.append(nob.strip())

    return ", ".join(parts)

def geocode_city(full_query: str, cache: dict = None) -> dict:
    if cache is not None and full_query in cache:
        return cache[full_query]

    # reject garbage queries early
    if not isinstance(full_query, str):
        if cache is not None:
            cache[full_query] = None
        return None
    q = full_query.strip()
    if not q or q == "-" or q.startswith("-,"):
        if cache is not None:
            cache[full_query] = None
        return None

    try:
        params = {
            "key": st.secrets["LOCATIONIQ_KEY"],
            "q": q,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }

        resp = requests.get(LOCATIONIQ_SEARCH_URL, params=params, timeout=10)

        if resp.status_code == 429:
            st.error("LocationIQ rate-limited (HTTP 429).")
            if cache is not None:
                cache[full_query] = None
            return None

        if resp.status_code in (401, 403):
            st.error(f"LocationIQ auth denied (HTTP {resp.status_code}).")
            if cache is not None:
                cache[full_query] = None
            return None

        if resp.status_code != 200:
            st.warning(f"LocationIQ HTTP {resp.status_code} for '{q}'")
            if cache is not None:
                cache[full_query] = None
            return None

        data = resp.json()

        if isinstance(data, dict) and data.get("error"):
            st.warning(f"LocationIQ error for '{q}': {data.get('error')}")
            if cache is not None:
                cache[full_query] = None
            return None

        if isinstance(data, list) and data:
            address = data[0].get("address", {}) or {}
            result = {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "country": address.get("country", "Unknown"),
            }
            if cache is not None:
                cache[full_query] = result
            return result

    except Exception as e:
        st.warning(f"Geocoding exception for '{q}': {e}")

    if cache is not None:
        cache[full_query] = None
    return None


def clean_city_name(city):
    """Split city name into base and parenthetical parts"""
    if not isinstance(city, str):
        return city, None

    m = re.search(r"^(.*?)\s*\(([^)]+)\)\s*$", city.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return city.strip(), None

def parse_file_data(uploaded_file):
    """Parse CSV or HTML file into DataFrame"""
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        else:
            html = uploaded_file.read().decode("utf-8", errors="ignore")
            tables = pd.read_html(StringIO(html))
            if not tables:
                raise ValueError("No tables found in HTML.")
            return tables[0]
    except Exception as e:
        st.error(f"Error parsing file: {str(e)}")
        return None

def process_players_data(df):
    """Normalize columns and process birth city data"""
    col_map = {
        "Nom": "PlayerName",
        "Name": "PlayerName",
        "Player Name": "PlayerName",
        "Ville de naissance": "BirthCity",
        "Birth City": "BirthCity",
        "Birthplace": "BirthCity",
        "Nation of Birth": "NoB",
        "NoB": "NoB",
        "Nationality": "Nat",
        "2nd Nat": "2nd Nat"
    }
    
    for col in df.columns:
        for pattern, new_name in col_map.items():
            if col.lower() == pattern.lower():
                df = df.rename(columns={col: new_name})
                break
    
    if "PlayerName" not in df.columns or "BirthCity" not in df.columns:
        avail = ", ".join(df.columns)
        st.error(f"Required columns not found. Available: {avail}")
        st.info("Expected: 'Nom'/'Name' and 'Ville de naissance'/'Birth City'")
        return None

    df[["BirthCity_base", "BirthCity_paren"]] = (
        df["BirthCity"].apply(lambda x: pd.Series(clean_city_name(x)))
    )
    
    df = df.dropna(subset=["PlayerName", "BirthCity_base"])
    df = df[df["BirthCity_base"].astype(str).str.strip().ne("-")]
    df = df[df["BirthCity_base"].astype(str).str.strip().ne("")]

    return df

def geocode_players(df: pd.DataFrame) -> pd.DataFrame:
    """Geocode all player birthplaces with progress tracking"""
    cache = load_cache()

    unique_queries = []
    for _, row in df.iterrows():
        q = build_query_key(row)
        if q not in unique_queries:
            unique_queries.append(q)

    to_geocode = [q for q in unique_queries if q not in cache]

    if to_geocode:
        st.info(f"Geocoding {len(to_geocode)} locations…")
        prog = st.progress(0)
        
        for i, query_string in enumerate(to_geocode):
            result = geocode_city(query_string, cache)

            if result is None:
                parts = [p.strip() for p in query_string.split(",")]
                if len(parts) >= 2:
                    fallback_query = f"{parts[0]}, {parts[-1]}"
                    result = geocode_city(fallback_query, cache)

            cache[query_string] = result
            prog.progress((i + 1) / len(to_geocode))
            time.sleep(1.1)

        save_cache(cache)
        prog.empty()

    def lookup_coords(row):
        key = build_query_key(row)
        return cache.get(key)

    coords_series = df.apply(lookup_coords, axis=1)
    df["lat"] = coords_series.apply(lambda x: x["lat"] if isinstance(x, dict) else None)
    df["lon"] = coords_series.apply(lambda x: x["lon"] if isinstance(x, dict) else None)
    df["country"] = coords_series.apply(lambda x: x["country"] if isinstance(x, dict) else None)

    return df

def create_map_html(df, map_style="OpenStreetMap"):
    """Create Folium map with player markers"""
    valid = df.dropna(subset=["lat", "lon"])
    if valid.empty:
        st.warning("No valid coordinates found to plot.")
        return None

    center_lat = valid["lat"].mean()
    center_lon = valid["lon"].mean()
    
    if map_style == "Satellite":
        tiles = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attr = 'Esri, Maxar, Earthstar Geographics, and the GIS User Community'
        m = folium.Map(location=[center_lat, center_lon], zoom_start=2, tiles=None, max_bounds=True)
        
        folium.TileLayer(
            tiles=tiles,
            attr=attr,
            name="Satellite",
            no_wrap=True
        ).add_to(m)

        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
            attr="Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS user community",
            overlay=True,
            name="Labels",
            no_wrap=True
        ).add_to(m)
    else:
        m = folium.Map(location=[center_lat, center_lon], zoom_start=2, tiles=None, max_bounds=True)

        folium.TileLayer(
            tiles="OpenStreetMap",
            name="OpenStreetMap",
            no_wrap=True
        ).add_to(m)


    cluster = MarkerCluster(
        icon_create_function="""
        function(cluster) {
          const count = cluster.getChildCount();
          return L.divIcon({
            html: `
              <div style="
                background-color: #38a7da;
                color: white;
                width: 30px;
                height: 30px;
                line-height: 30px;
                border-radius: 15px;
                text-align: center;
                font-weight: bold;
                font-size: 14px;
              ">
                ${count}
              </div>`,
            className: 'custom-cluster',
            iconSize: [30, 30]
          });
        }
        """,
        options={
            "maxClusterRadius": 1,
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": True
        }
    ).add_to(m)
    
    for _, row in valid.iterrows():
        nationality_code = row.get("Nat", "Unknown")
        if pd.notna(nationality_code) and len(str(nationality_code).strip()) == 3:
            nationality = _alpha3_to_country_name(str(nationality_code).strip())
        else:
            nationality = nationality_code if pd.notna(nationality_code) else "Unknown"

        second_nat_code = row.get("2nd Nat", None)
        has_second_nat = pd.notna(second_nat_code) and second_nat_code != "None"
        if has_second_nat and len(str(second_nat_code).strip()) == 3:
            second_nat = _alpha3_to_country_name(str(second_nat_code).strip())
        else:
            second_nat = second_nat_code

        # Convert birth country code to full name if it's a FIFA code
        birth_country = row['country']
        nob_code = row.get("NoB", None)
        if pd.notna(nob_code) and len(str(nob_code).strip()) == 3:
            birth_country_display = _alpha3_to_country_name(str(nob_code).strip())
        else:
            birth_country_display = birth_country

        tooltip_html = f"""
        <div style="
            font-family: Arial, sans-serif;
            min-width: 200px;
            background: white;
            padding: 12px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border: 1px solid #e2e8f0;
        ">
            <h4 style="
                margin: 0 0 8px 0;
                color: #2563EB;
                font-size: 16px;
                font-weight: 600;
            ">{row['PlayerName']}</h4>
            <p style="
                margin: 4px 0;
                color: #374151;
                font-size: 13px;
                line-height: 1.4;
            "><strong>📍 Birth City:</strong> {row['BirthCity']}</p>
            <p style="
                margin: 4px 0;
                color: #374151;
                font-size: 13px;
                line-height: 1.4;
            "><strong>🏳️ Birth Country:</strong> {birth_country_display}</p>
            <p style="
                margin: 4px 0;
                color: #374151;
                font-size: 13px;
                line-height: 1.4;
            "><strong>🌍 Nationality:</strong> {nationality}</p>"""
            
        if has_second_nat:
            tooltip_html += f"""
            <p style="
                margin: 4px 0;
                color: #374151;
                font-size: 13px;
                line-height: 1.4;
            "><strong>🌍 2nd Nationality:</strong> {second_nat}</p>"""
        tooltip_html += "</div>"

        folium.Marker(
            location=[row["lat"], row["lon"]],
            tooltip=folium.Tooltip(tooltip_html, max_width=300),
            icon=folium.Icon(color="blue", icon="user", prefix="fa"),
        ).add_to(cluster)

    # Fit map to show all markers
    if len(valid) > 1:
        sw = valid[["lat", "lon"]].min().values.tolist()
        ne = valid[["lat", "lon"]].max().values.tolist()
        m.fit_bounds([sw, ne], padding=(20, 20))

    map_name = m.get_name()
    m.get_root().html.add_child(folium.Element(
        f"<script>setTimeout(function(){{ {map_name}.invalidateSize(); }}, 300);</script>"
    ))

    return m.get_root().render()


# Header
st.markdown(
    """
    <div class="main-header">
        <h1>FM Birthplace Map Generator</h1>
        <p>Upload your Football Manager data to visualize your players' birthplaces on an interactive world map</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Upload or display map
if st.session_state.players_data is None:
    # Upload section
    st.markdown(
        """
        <div class="upload-section" style="
            background-color: var(--background-color, #1E1E1E); 
            color: var(--text-color, #E0E0E0); 
            padding: 20px; 
            border-radius: 8px;
        ">
            <h3 style="color: var(--accent-color, #4DA6FF);">📁 Upload Player Birthplace Data</h3>
            <p style="color: var(--secondary-text-color, #CCCCCC);">Supported formats: HTML (direct from FM) or CSV</p>
        </div>
        <style>
            :root {
                --background-color: #FFFFFF;
                --text-color: #333333;
                --accent-color: #1E88E5;
                --secondary-text-color: #666666;
            }
            
            @media (prefers-color-scheme: dark) {
                :root {
                    --background-color: #1E1E1E;
                    --text-color: #E0E0E0;
                    --accent-color: #4DA6FF;
                    --secondary-text-color: #CCCCCC;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # Export instructions
    st.markdown(
        """
        <div class="instructions-card" style="
            background-color: var(--background-color, #1E1E1E); 
            color: var(--text-color, #E0E0E0);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid var(--accent-color, #4DA6FF);
        ">
            <h4 style="color: var(--accent-color, #4DA6FF); margin-top: 0;">📋 How to export player data from FM:</h4>
            <ol style="margin-left: 20px; padding-left: 0;">
                <li>Navigate to the squad page in Football Manager (your game has to be set to English)</li>
                <li>Import the <strong>birthplace_view</strong> view (download link below) to display birthplace and other required columns</li>
                <li>Click the first player row to highlight it</li>
                <li>Select all players: <kbd>Ctrl+A</kbd> (Windows) or <kbd>⌘+A</kbd> (macOS)</li>
                <li>Open the print/export dialog: <kbd>Ctrl+P</kbd> (Windows) or <kbd>⌘+P</kbd> (macOS)</li>
                <li>Choose "Web Page" (or "Save as Web Page") and save</li>
            </ol>
            <div style="margin-top: 10px;">
                <a href="https://mega.nz/file/BQEGBDSK#KaAzX5MRC5RvJE0onqHC7naalwKqTlph5bOfdtnXVA4" 
                   style="color: var(--accent-color, #4DA6FF); text-decoration: underline; font-weight: bold;">
                   📥 Download birthplace_view.fmf
                </a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    st.markdown("<hr style='margin: 20px 0; border-color: var(--secondary-text-color, #666666); opacity: 0.3;'>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose your Football Manager export file",
        type=["html", "csv"],
        key="upload_file",
        help="Must contain at least 'Name' and 'Birth City' columns",
    )
    if uploaded_file is not None:
        with st.spinner("Processing and geocoding…"):
            df_raw = parse_file_data(uploaded_file)
            if df_raw is not None:
                df_proc = process_players_data(df_raw)
                if df_proc is not None:
                    st.success(f"✅ Loaded {len(df_proc)} players.")
                    with st.spinner("Geocoding…"):
                        df_geo = geocode_players(df_proc)
                        # Store data and refresh
                        st.session_state.players_data = df_geo
                        st.rerun()
else:
    # Stats display
    df = st.session_state.players_data
    valid = df.dropna(subset=["lat", "lon"])  
    unique_cities = df["BirthCity_base"].nunique()
    unique_ctrs   = df["country"].dropna().nunique()

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        st.markdown(
            f"""<div class="stats-card">
                    <h3>{len(df)}</h3>
                    <p>Total Players</p>
                </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="stats-card">
                    <h3>{len(valid)}</h3>
                    <p>Geocoded Players</p>
                </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="stats-card">
                    <h3>{unique_cities}</h3>
                    <p>Unique Cities</p>
                </div>""",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""<div class="stats-card">
                    <h3>{unique_ctrs}</h3>
                    <p>Unique Countries</p>
                </div>""",
            unsafe_allow_html=True,
        )

    # Map style options
    map_style = st.radio(
        "Map Style:",
        ["OpenStreetMap", "Satellite"],
        horizontal=True
    )

    # Display map
    map_html = create_map_html(df, map_style)
    if map_html is not None:
        st.markdown("## World Map", unsafe_allow_html=True)
        components.html(map_html, height=800, scrolling=False)
    # Reset button
    st.markdown("<div class='clear-container'>", unsafe_allow_html=True)
    if st.button("Clear Data"):
        del st.session_state["players_data"]
        if "upload_file" in st.session_state:
            st.session_state["upload_file"] = None
        if "geocode_cache" in st.session_state:
            del st.session_state["geocode_cache"]
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # Show geocoding failures
    failed = df[df["lat"].isna()]
    if not failed.empty:
        with st.expander(f"⚠️ Failed to geocode {len(failed)} players"):
            st.dataframe(failed[["PlayerName", "BirthCity", "BirthCity_base", "BirthCity_paren"]], use_container_width=True)
            st.info("Try adding country names or parentheses to improve accuracy.")


# Footer
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; padding: 1rem;">
        <p>🔧 Built with Streamlit | 🗺️ Maps by OpenStreetMap | 📍 Geocoding by LocationIQ</p>
        <p>© Created by Ryoshiin, 2025</p>
    </div>
    """,
    unsafe_allow_html=True,
)