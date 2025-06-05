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

# ────────────────────────────────────────────────────────────────────────────────
# 0) STREAMLIT CONFIGURATION
#────────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FM Birthplace Map Generator",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ────────────────────────────────────────────────────────────────────────────────
# 1) CUSTOM CSS FOR STYLING
#────────────────────────────────────────────────────────────────────────────────
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

    /* ===== Removed Download Button CSS ===== */
    /* The .mega-download-btn styles were removed so that we can use a plain Markdown link instead. */
    </style>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────────
# 2) SESSION STATE INITIALIZATION
#────────────────────────────────────────────────────────────────────────────────
if "geocode_cache" not in st.session_state:
    st.session_state.geocode_cache = {}
if "players_data" not in st.session_state:
    st.session_state.players_data = None

# ────────────────────────────────────────────────────────────────────────────────
# 3) GEOCODING + CACHING UTILITIES
#────────────────────────────────────────────────────────────────────────────────
def load_cache():
    """Load geocoding cache from local JSON (if it exists)."""
    cache_file = "geocode_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_cache(cache):
    """Save updated geocoding cache to JSON."""
    cache_file = "geocode_cache.json"
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except:
        pass


def geocode_city(city_name, cache):
    """
    Geocode a single city via Nominatim (with polite rate-limiting),
    caching the result so we don't repeat lookups.
    """
    if city_name in cache:
        return cache[city_name]

    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": city_name,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": "FM-Birthplace-Map/1.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                addr = data[0].get("address", {})
                country = addr.get("country", "Unknown")
                result = {
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"]),
                    "country": country,
                }
                cache[city_name] = result
                return result
    except Exception as e:
        st.warning(f"Geocoding failed for {city_name}: {str(e)}")

    cache[city_name] = None
    return None

# ────────────────────────────────────────────────────────────────────────────────
# 4) DATA CLEANING HELPERS
#────────────────────────────────────────────────────────────────────────────────
def clean_city_name(city):
    """Remove parentheses (and their contents) + extra whitespace from city name."""
    if not isinstance(city, str):
        return city
    return re.sub(r"\s*\([^)]*\)", "", city).strip()


def parse_file_data(uploaded_file):
    """Read CSV or HTML export into a pandas DataFrame."""
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
    """
    Normalize column names, ensure PlayerName & BirthCity exist,
    and create a cleaned BirthCity_clean column.
    """
    col_map = {
        "Nom": "PlayerName",
        "Name": "PlayerName",
        "Player Name": "PlayerName",
        "Ville de naissance": "BirthCity",
        "Birth City": "BirthCity",
        "Birthplace": "BirthCity",
    }
    for old, new in col_map.items():
        if old in df.columns:
            df = df.rename(columns={old: new})

    if "PlayerName" not in df.columns or "BirthCity" not in df.columns:
        avail = ", ".join(df.columns)
        st.error(f"Required columns not found. Available: {avail}")
        st.info("Expected: 'Nom'/'Name' and 'Ville de naissance'/'Birth City'")
        return None

    df["BirthCity_clean"] = df["BirthCity"].apply(clean_city_name)
    df = df.dropna(subset=["PlayerName", "BirthCity_clean"])
    return df


def geocode_players(df):
    """
    Geocode every unique BirthCity_clean in df (with caching).
    Returns df with new columns: lat, lon, country.
    """
    cache = load_cache()
    unique_cities = df["BirthCity_clean"].unique()
    to_geocode = [c for c in unique_cities if c not in cache]

    if to_geocode:
        st.info(f"Geocoding {len(to_geocode)} new cities…")
        prog = st.progress(0)
        for i, city in enumerate(to_geocode):
            geocode_city(city, cache)
            prog.progress((i + 1) / len(to_geocode))
            time.sleep(0.5)  # polite rate-limit
        save_cache(cache)
        prog.empty()

    coords = df["BirthCity_clean"].map(lambda c: cache.get(c, None))
    df["lat"] = coords.apply(lambda x: x["lat"] if isinstance(x, dict) and "lat" in x else None)
    df["lon"] = coords.apply(lambda x: x["lon"] if isinstance(x, dict) and "lon" in x else None)
    df["country"] = coords.apply(lambda x: x.get("country", "Unknown") if isinstance(x, dict) else None)
    return df

# ────────────────────────────────────────────────────────────────────────────────
# 5) BUILD FULL-WIDTH FOLIUM MAP HTML
#────────────────────────────────────────────────────────────────────────────────
def create_map_html(df):
    """
    Return a single HTML string containing a Folium map
    that fits all player markers. We will embed this at 100% width.
    """
    valid = df.dropna(subset=["lat", "lon"])
    if valid.empty:
        st.warning("No valid coordinates found to plot.")
        return None

    center_lat = valid["lat"].mean()
    center_lon = valid["lon"].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=2, tiles="OpenStreetMap")

    for _, row in valid.iterrows():
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
            "><strong>🏳️ Country:</strong> {row['country']}</p>
        </div>"""
        folium.Marker(
            location=[row["lat"], row["lon"]],
            tooltip=folium.Tooltip(tooltip_html, max_width=300),
            icon=folium.Icon(color="blue", icon="user", prefix="fa"),
        ).add_to(m)

    if len(valid) > 1:
        sw = valid[["lat", "lon"]].min().values.tolist()
        ne = valid[["lat", "lon"]].max().values.tolist()
        m.fit_bounds([sw, ne], padding=(20, 20))

    return m.get_root().render()

# ────────────────────────────────────────────────────────────────────────────────
# 6) APPLICATION HEADER (NO ⚽)
#────────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="main-header">
        <h1>FM Birthplace Map Generator</h1>
        <p>Upload your Football Manager export and see a full-width world map of your players' birthplaces</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────────
# 7) MAIN LOGIC: UPLOAD OR DISPLAY MAP
#────────────────────────────────────────────────────────────────────────────────
if st.session_state.players_data is None:
    # ---- Upload Section ----
    st.markdown(
        """
        <div class="upload-section">
            <h3>📁 Upload Your FM Export</h3>
            <p>Supported formats: HTML (direct from FM) or CSV</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- How to export the birthplace view from FM? with Info Tooltip ----
    instruction_text_upload = '''
How to export the birthplace view from FM? <span class='info-icon' title='1. Navigate to the squad page in Football Manager.\n2. Load the birthplace_view so the Birthplace column is visible.\n3. Click the first player row to highlight it.\n4. Select all players: Ctrl+A (Windows) or ⌘+A (macOS).\n5. Open the print/export dialog: Ctrl+P (Windows) or ⌘+P (macOS).\n6. Choose "Web Page" (or "Save as Web Page") and save.'>&#9432;</span>
'''  
    st.markdown(instruction_text_upload, unsafe_allow_html=True)
    
    # ---- Simple clickable link (no gap) ----
    st.markdown(
        "<div style='margin-top: -15px;'><a href='https://mega.nz/file/QUs3TSrA#7DYuBGehr7FXfYbzxlcsXKtHjrilFnlSXJ4h9bd4d_A'>Download birthplace_view.fmf</a></div>",
        unsafe_allow_html=True,
    )

    # ---- Add separation before file uploader ----
    st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)
    
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
                        # Set session state and force rerun
                        st.session_state.players_data = df_geo
                        st.rerun()

else:
    # ---- Stats Cards on top ----
    df = st.session_state.players_data
    valid = df.dropna(subset=["lat", "lon"])  
    unique_cities = df["BirthCity_clean"].nunique()
    unique_ctrs = df["country"].dropna().nunique()

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

    # ---- Full-Width Map ----
    map_html = create_map_html(df)
    if map_html is not None:
        st.markdown("## World Map", unsafe_allow_html=True)
        components.html(map_html, height=800, width=0)

    # ---- Clear Data Button (centered) ----
    st.markdown("<div class='clear-container'>", unsafe_allow_html=True)
    if st.button("Clear Data"):
        del st.session_state["players_data"]
        if "upload_file" in st.session_state:
            st.session_state["upload_file"] = None
        if "geocode_cache" in st.session_state:
            del st.session_state["geocode_cache"]
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Show Failed Geocoding if needed ----
    failed = df[df["lat"].isna()]
    if not failed.empty:
        with st.expander(f"⚠️ Failed to geocode {len(failed)} players"):
            st.dataframe(failed[["PlayerName", "BirthCity", "BirthCity_clean"]], use_container_width=True)
            st.info("Try adding country names to improve accuracy.")

# ────────────────────────────────────────────────────────────────────────────────
# 8) FOOTER
#────────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; padding: 1rem;">
        <p>🔧 Built with Streamlit | 🗺️ Maps by OpenStreetMap | 📍 Geocoding by Nominatim</p>
    </div>
    """,
    unsafe_allow_html=True,
)