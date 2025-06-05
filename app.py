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

# FIFA 3-letter codes to full country names
FIFA_TO_COUNTRY = {
    "WAL": "Wales",
    "ENG": "England",
    "SCO": "Scotland",
    "NIR": "Northern Ireland",
    "ALG": "Algeria",
    "CIV": "Ivory Coast",
    "CGO": "Congo",
    "COD": "DR Congo",
    "GER": "Germany",
    "POR": "Portugal",
    "CRO": "Croatia",
    "SUI": "Switzerland",
    "DEN": "Denmark",
    "SWE": "Sweden",
    "NED": "Netherlands",
    "IRN": "Iran",
    "KSA": "Saudi Arabia",
    "CHN": "China",
    "KOR": "South Korea",
    "JPN": "Japan",
    "RSA": "South Africa",
    "AUS": "Australia",
    "NZL": "New Zealand",
    "ARG": "Argentina",
    "BRA": "Brazil",
    "CHI": "Chile",
    "COL": "Colombia",
    "ECU": "Ecuador",
    "PAR": "Paraguay",
    "PER": "Peru",
    "URU": "Uruguay",
    "VEN": "Venezuela",
    "MEX": "Mexico",
    "USA": "United States",
    "CAN": "Canada",
    "CRC": "Costa Rica",
    "HON": "Honduras",
    "JAM": "Jamaica",
    "PAN": "Panama",
    "TRI": "Trinidad and Tobago",
    "SKN": "Saint Kitts and Nevis",
    "LCA": "Saint Lucia",
    "VIN": "Saint Vincent and the Grenadines",
    "SAM": "Samoa",
    "SMR": "San Marino",
    "STP": "São Tomé and Príncipe",
    "SEN": "Senegal",
    "SRB": "Serbia",
    "SEY": "Seychelles",
    "SLE": "Sierra Leone",
    "SGP": "Singapore",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "SOL": "Solomon Islands",
    "SOM": "Somalia",
    "SSD": "South Sudan",
    "ESP": "Spain",
    "SRI": "Sri Lanka",
    "SDN": "Sudan",
    "SUR": "Suriname",
    "SYR": "Syria",
    "TAH": "Tahiti",
    "TJK": "Tajikistan",
    "TAN": "Tanzania",
    "THA": "Thailand",
    "TOG": "Togo",
    "TGA": "Tonga",
    "TUN": "Tunisia",
    "TUR": "Turkey",
    "TKM": "Turkmenistan",
    "TCA": "Turks and Caicos Islands",
    "UGA": "Uganda",
    "UKR": "Ukraine",
    "UAE": "United Arab Emirates",
    "VIR": "U.S. Virgin Islands",
    "UZB": "Uzbekistan",
    "VAN": "Vanuatu",
    "VIE": "Vietnam",
    "YEM": "Yemen",
    "ZAM": "Zambia",
    "ZIM": "Zimbabwe",
    "BES": "Bonaire",
    "BOE": "Bonaire",
    "GUF": "French Guiana",
    "GLP": "Guadeloupe",
    "KIR": "Kiribati",
    "MTQ": "Martinique",
    "NIU": "Niue",
    "MNP": "Northern Mariana Islands",
    "NMI": "Northern Mariana Islands",
    "REU": "Réunion",
    "MAF": "Saint Martin",
    "SMN": "Saint Martin",
    "SXM": "Sint Maarten",
    "SMA": "Sint Maarten",
    "TUV": "Tuvalu",
    "ZAN": "Zanzibar",
    "ALA": "Åland",
    "BSQ": "Basque Country",
    "CAT": "Catalonia",
    "FLK": "Falkland Islands",
    "FIS": "Falkland Islands",
    "GBR": "Great Britain",
    "GOZ": "Gozo",
    "GRL": "Greenland",
    "GGY": "Guernsey",
    "JER": "Jersey",
    "IOM": "Isle of Man",
    "MHL": "Marshall Islands",
    "FSM": "Micronesia",
    "MON": "Monaco",
    "MCO": "Monaco",
    "NRU": "Nauru",
    "NCY": "Northern Cyprus",
    "TRNC": "Northern Cyprus",
    "PLW": "Palau",
    "BLM": "Saint Barthélemy",
    "SPM": "Saint Pierre and Miquelon",
    "SHN": "Saint Helena",
    "SRD": "Sardinia",
    "SAR": "Sardinia",
    "PMR": "Transnistria",
    "TOK": "Tokelau",
    "VAT": "Vatican City",
    "WLF": "Wallis and Futuna",
    "WAF": "Wallis and Futuna",
    "ESH": "Western Sahara",
    "SADR": "Western Sahara",
    "AFG": "Afghanistan",
    "AIA": "Anguilla",
    "ALB": "Albania",
    "AND": "Andorra",
    "ANG": "Angola",
    "ARM": "Armenia",
    "ARU": "Aruba",
    "ASA": "American Samoa",
    "ATG": "Antigua and Barbuda",
    "AUT": "Austria",
    "AZE": "Azerbaijan",
    "BAH": "Bahamas",
    "BAN": "Bangladesh",
    "BDI": "Burundi",
    "BEL": "Belgium",
    "BEN": "Benin",
    "BER": "Bermuda",
    "BHU": "Bhutan",
    "BOL": "Bolivia",
    "BIH": "Bosnia and Herzegovina",
    "BOT": "Botswana",
    "BRA": "Brazil",
    "BRU": "Brunei",
    "BUL": "Bulgaria",
    "BFA": "Burkina Faso",
    "CAM": "Cambodia",
    "CMR": "Cameroon",
    "CPV": "Cape Verde",
    "CAY": "Cayman Islands",
    "CTA": "Central African Republic",
    "CHA": "Chad",
    "CHN": "China",
    "COL": "Colombia",
    "COM": "Comoros",
    "COK": "Cook Islands",
    "CUB": "Cuba",
    "CUW": "Curaçao",
    "CYP": "Cyprus",
    "CZE": "Czech Republic",
    "DJI": "Djibouti",
    "DMA": "Dominica",
    "DOM": "Dominican Republic",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ESP": "Spain",
    "EST": "Estonia",
    "ETH": "Ethiopia",
    "FRO": "Faroe Islands",
    "FIJ": "Fiji",
    "FIN": "Finland",
    "FRA": "France",
    "GAB": "Gabon",
    "GAM": "Gambia",
    "GEO": "Georgia",
    "GHA": "Ghana",
    "GIB": "Gibraltar",
    "GRE": "Greece",
    "GRN": "Grenada",
    "GUM": "Guam",
    "GUA": "Guatemala",
    "GUI": "Guinea",
    "GNB": "Guinea-Bissau",
    "GUY": "Guyana",
    "HAI": "Haiti",
    "HKG": "Hong Kong",
    "HUN": "Hungary",
    "ISL": "Iceland",
    "IND": "India",
    "IDN": "Indonesia",
    "IRQ": "Iraq",
    "ISR": "Israel",
    "ITA": "Italy",
    "JOR": "Jordan",
    "KAZ": "Kazakhstan",
    "KEN": "Kenya",
    "KOS": "Kosovo",
    "KUW": "Kuwait",
    "KGZ": "Kyrgyzstan",
    "LAO": "Laos",
    "LVA": "Latvia",
    "LBN": "Lebanon",
    "LES": "Lesotho",
    "LBR": "Liberia",
    "LBY": "Libya",
    "LIE": "Liechtenstein",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "MAC": "Macau",
    "MAD": "Madagascar",
    "MWI": "Malawi",
    "MAS": "Malaysia",
    "MDV": "Maldives",
    "MLI": "Mali",
    "MLT": "Malta",
    "MTN": "Mauritania",
    "MRI": "Mauritius",
    "MDA": "Moldova",
    "MNG": "Mongolia",
    "MNE": "Montenegro",
    "MSR": "Montserrat",
    "MAR": "Morocco",
    "MOZ": "Mozambique",
    "MYA": "Myanmar",
    "NAM": "Namibia",
    "NEP": "Nepal",
    "NCL": "New Caledonia",
    "NCA": "Nicaragua",
    "NIG": "Niger",
    "NGA": "Nigeria",
    "PRK": "North Korea",
    "MKD": "North Macedonia",
    "NOR": "Norway",
    "OMA": "Oman",
    "PAK": "Pakistan",
    "PLE": "Palestine",
    "PAN": "Panama",
    "PHI": "Philippines",
    "POL": "Poland",
    "PUR": "Puerto Rico",
    "QAT": "Qatar",
    "IRL": "Republic of Ireland",
    "ROU": "Romania",
    "RUS": "Russia",
    "RWA": "Rwanda",
    "SLV": "El Salvador",
    "SWZ": "Eswatini",
    "TLS": "Timor-Leste",
    "TPE": "Chinese Taipei",
    "VGB": "British Virgin Islands",
    "BHR": "Bahrain",
    "BLR": "Belarus",
    "BLZ": "Belize",
    "BRB": "Barbados",
    "EQG": "Equatorial Guinea",
    "ERI": "Eritrea",
    "PNG": "Papua New Guinea"
}

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


def _alpha3_to_country_name(alpha3: str) -> str:
    """
    If alpha3 is in FIFA_TO_COUNTRY, return that "full name".
    Otherwise, return alpha3 unchanged.
    """
    key = alpha3.strip().upper()
    if key in FIFA_TO_COUNTRY:
        return FIFA_TO_COUNTRY[key]
    return alpha3


def geocode_city(city_name: str, country_value: str = None, cache: dict = None) -> dict:
    """
    Geocode a single city via Nominatim, disambiguated by:
      • A FIFA 3-letter code (e.g. 'WAL') → full name (e.g. 'Wales'), or
      • No country (fallback).  
    Uses `q="CityName, CountryName"` so Nominatim picks the right city.
    """
    # Convert any 3-letter code to a full name
    country_name = None
    if country_value and len(country_value.strip()) == 3:
        country_name = _alpha3_to_country_name(country_value.strip())
    elif country_value:
        country_name = country_value.strip()

    # Build query key exactly as we'll ask Nominatim
    if country_name:
        query_key = f"{city_name.strip()}, {country_name}"
    else:
        query_key = city_name.strip()

    # Return cached result if available
    if cache is not None and query_key in cache:
        return cache[query_key]

    # Otherwise, ask Nominatim with q="City, Country" or "City"
    query = query_key
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": "FM-Birthplace-Map/1.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                address = data[0].get("address", {})
                # Use the country name from FIFA codes if available
                found_country = country_name or address.get("country", "Unknown")
                result = {
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"]),
                    "country": found_country,
                }
                if cache is not None:
                    cache[query_key] = result
                return result
    except Exception as e:
        st.warning(f"Geocoding exception for '{query}': {e}")

    # On failure, cache None so we don't retry forever
    if cache is not None:
        cache[query_key] = None
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
    Normalize column names so we have:
      - df['PlayerName']
      - df['BirthCity']
      - df['NoB']   (FIFA 3-letter code, e.g. 'WAL', 'ENG', 'FRA', etc.)
    Then create df['BirthCity_clean'].
    """
    col_map = {
        "Nom": "PlayerName",
        "Name": "PlayerName",
        "Player Name": "PlayerName",
        "Ville de naissance": "BirthCity",
        "Birth City": "BirthCity",
        "Birthplace": "BirthCity",
        "Nation of Birth": "NoB",
        "NoB": "NoB",  # Ensure we capture NoB directly if it's already named that way
        "Nationality": "Nat",
        "2nd Nat": "2nd Nat"
    }
    
    # Normalize column names (case-insensitive)
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

    df["BirthCity_clean"] = df["BirthCity"].apply(clean_city_name)
    df = df.dropna(subset=["PlayerName", "BirthCity_clean"])
    
    return df


def geocode_players(df: pd.DataFrame) -> pd.DataFrame:
    cache = load_cache()
    has_nob = "NoB" in df.columns

    # 1) Gather unique (city, NoB) pairs
    unique_pairs = []
    for _, row in df.iterrows():
        city = row["BirthCity_clean"].strip()
        country_value = None
        if has_nob and pd.notna(row["NoB"]):
            country_value = str(row["NoB"]).strip()
        pair = (city, country_value)
        if pair not in unique_pairs:
            unique_pairs.append(pair)

    # 2) Determine which pairs need geocoding
    to_geocode = []
    for city, country_value in unique_pairs:
        if country_value and len(country_value.strip()) == 3:
            country_name = _alpha3_to_country_name(country_value.strip())
            cache_key = f"{city}, {country_name}"
        elif country_value:
            cache_key = f"{city}, {country_value.strip()}"
        else:
            cache_key = city

        if cache_key not in cache:
            to_geocode.append((city, country_value))

    # 3) Geocode each missing pair
    if to_geocode:
        st.info(f"Geocoding {len(to_geocode)} city-country combos…")
        prog = st.progress(0)
        for i, (city, country_value) in enumerate(to_geocode):
            result = geocode_city(city, country_value, cache)
            prog.progress((i + 1) / len(to_geocode))
            time.sleep(0.5)
        save_cache(cache)
        prog.empty()

    # ————————————
    # 4) **Fix**: Attach coords back onto each row using the **same** cache key
    def get_coords(row):
        city = row["BirthCity_clean"]
        if "NoB" in row and pd.notna(row["NoB"]):
            nob = str(row["NoB"]).strip()
            country_name = _alpha3_to_country_name(nob)
            cache_key = f"{city}, {country_name}"
        else:
            cache_key = city
        return cache.get(cache_key)

    coords = df.apply(get_coords, axis=1)
    df["lat"] = coords.apply(lambda x: x["lat"] if isinstance(x, dict) else None)
    df["lon"] = coords.apply(lambda x: x["lon"] if isinstance(x, dict) else None)
    
    # Use FIFA country names for birth country when NoB is available
    def get_country(row, coords_dict):
        if isinstance(coords_dict, dict):
            if "NoB" in row and pd.notna(row["NoB"]) and len(str(row["NoB"]).strip()) == 3:
                return _alpha3_to_country_name(str(row["NoB"]).strip())
            return coords_dict.get("country", "Unknown")
        return None
    
    df["country"] = df.apply(lambda row: get_country(row, coords.loc[row.name]), axis=1)

    return df
# ────────────────────────────────────────────────────────────────────────────────
# 5) BUILD FULL-WIDTH FOLIUM MAP HTML
#────────────────────────────────────────────────────────────────────────────────
def create_map_html(df):
    """
    Return a single HTML string containing a Folium map
    that fits all player markers. We will embed this at 100% width.
    Now includes Nationality and 2nd Nationality in the tooltip.
    """
    valid = df.dropna(subset=["lat", "lon"])
    if valid.empty:
        st.warning("No valid coordinates found to plot.")
        return None

    center_lat = valid["lat"].mean()
    center_lon = valid["lon"].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=2, tiles="OpenStreetMap")

    for _, row in valid.iterrows():
        # Prepare nationality information
        nationality_code = row.get("Nat", "Unknown") if pd.notna(row.get("Nat", None)) else "Unknown"
        nationality = _alpha3_to_country_name(nationality_code) if len(str(nationality_code).strip()) == 3 else nationality_code
        
        second_nat_code = row.get("2nd Nat", None)
        has_second_nat = pd.notna(second_nat_code) and second_nat_code != "None"
        second_nat = _alpha3_to_country_name(second_nat_code) if has_second_nat and len(str(second_nat_code).strip()) == 3 else second_nat_code
        
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
            "><strong>🏳️ Birth Country:</strong> {row['country']}</p>
            <p style="
                margin: 4px 0;
                color: #374151;
                font-size: 13px;
                line-height: 1.4;
            "><strong>🌍 Nationality:</strong> {nationality}</p>"""
        
        # Only add 2nd nationality if it exists
        if has_second_nat:
            tooltip_html += f"""
            <p style="
                margin: 4px 0;
                color: #374151;
                font-size: 13px;
                line-height: 1.4;
            "><strong>🌍 2nd Nationality:</strong> {second_nat}</p>"""
            
        tooltip_html += """
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
        <div class="upload-section" style="
            background-color: var(--background-color, #1E1E1E); 
            color: var(--text-color, #E0E0E0); 
            padding: 20px; 
            border-radius: 8px;
        ">
            <h3 style="color: var(--accent-color, #4DA6FF);">📁 Upload Your FM Export</h3>
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

    # ---- How to export the birthplace view from FM? with Info Tooltip ----
    instruction_text_upload = '''
<span style="color: var(--text-color, #333333);">How to export the birthplace view from FM? <span class='info-icon' style="color: var(--accent-color, #1E88E5); cursor: pointer;" title='1. Navigate to the squad page in Football Manager.\n2. Load the birthplace_view so the Birthplace column is visible.\n3. Click the first player row to highlight it.\n4. Select all players: Ctrl+A (Windows) or ⌘+A (macOS).\n5. Open the print/export dialog: Ctrl+P (Windows) or ⌘+P (macOS).\n6. Choose "Web Page" (or "Save as Web Page") and save.'>&#9432;</span></span>
'''  
    st.markdown(instruction_text_upload, unsafe_allow_html=True)
    
    # ---- Simple clickable link (no gap) ----
    st.markdown(
        "<div style='margin-top: -15px;'><a href='https://mega.nz/file/BQEGBDSK#KaAzX5MRC5RvJE0onqHC7naalwKqTlph5bOfdtnXVA4' style='color: var(--accent-color, #1E88E5); text-decoration: underline;'>Download birthplace_view.fmf</a></div>",
        unsafe_allow_html=True,
    )

    # ---- Add separation before file uploader ----
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
        <p>© Created by Ryoshiin, 2025</p>
    </div>
    """,
    unsafe_allow_html=True,
)