"""
Central config. Two fixed accounts (internal tool, no self-signup) --
credentials are bcrypt hashes supplied via environment, never plaintext
in source. See .env.example for how to generate ADMIN_PASSWORD_HASH /
USER_PASSWORD_HASH.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
EXPORT_TMP_DIR = BASE_DIR / "tmp_exports"
EXPORT_TMP_DIR.mkdir(exist_ok=True)

# --- Auth: two roles, admin + viewer. Passwords are bcrypt hashes read
# from the environment -- never committed in plaintext. Generate one with:
#   python -c "import bcrypt;print(bcrypt.hashpw(b'yourpw', bcrypt.gensalt()).decode())"
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
USER_PASSWORD_HASH = os.getenv("USER_PASSWORD_HASH", "")

if not ADMIN_PASSWORD_HASH or not USER_PASSWORD_HASH:
    sys.exit(
        "FATAL: ADMIN_PASSWORD_HASH and USER_PASSWORD_HASH must be set in .env "
        "(bcrypt hashes -- see .env.example). Refusing to start with no/blank credentials."
    )

USERS = {
    "admin": {"password_hash": ADMIN_PASSWORD_HASH, "role": "admin"},
    "user": {"password_hash": USER_PASSWORD_HASH, "role": "viewer"},
}

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
if not SESSION_SECRET:
    sys.exit("FATAL: SESSION_SECRET must be set in .env (long random string).")
SESSION_TTL_HOURS = 12

# --- Encryption at rest for admin-entered secrets (Gmail app password).
# Fernet key -- generate with:
#   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
if not ENCRYPTION_KEY:
    sys.exit("FATAL: ENCRYPTION_KEY must be set in .env (Fernet key -- see .env.example).")

# --- CORS: internal tool served as a monolith in prod, so same-origin is
# the norm. Only widen this if the frontend is genuinely hosted separately.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# --- Server port (uvicorn). Single source of truth -- run.py reads this
# instead of hardcoding a port; scripts/set_port.sh updates this default.
PORT = int(os.getenv("PORT", "8585"))

# --- Database (MySQL) ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "knpc_dashboard")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4",
)

# --- Scraping ---
DEFAULT_SCRAPE_FREQUENCY_MINUTES = int(os.getenv("SCRAPE_FREQUENCY_MINUTES", 30))
SCRAPE_REQUEST_TIMEOUT = 15
SCRAPE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# --- AI facility ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_API_URL = os.getenv("CLAUDE_API_URL", "https://api.anthropic.com/v1/messages")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

# --- EIA (U.S. Energy Information Administration) Open Data API ---
# Free key: https://www.eia.gov/opendata/register.php
# Used for the "Products" catalog (see EIA_PRODUCT_SERIES below). Never
# written into a Source.url -- injected onto the request in eia_client.py
# so it doesn't show up in the admin sources table or scrape logs.
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
EIA_API_BASE_URL = os.getenv("EIA_API_BASE_URL", "https://api.eia.gov/v2")
EIA_SCRAPE_REQUEST_TIMEOUT = 15

# --- Email (Gmail SMTP) ---
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# --- Item catalog (top-level nav: category -> items) ---
# Seeded into the DB on first boot; admins can add/disable further items
# and sources from the admin panel afterwards.
SEED_CATALOG = {
    "Crude": [
        {"code": "BRENT", "name": "Brent", "unit": "USD/bbl"},
        {"code": "WTI", "name": "WTI", "unit": "USD/bbl"},
        {"code": "OMAN", "name": "Oman", "unit": "USD/bbl"},
        {"code": "DUBAI", "name": "Dubai", "unit": "USD/bbl"},
        {"code": "KEC", "name": "Kuwait Export Crude", "unit": "USD/bbl"},
    ],
    # Replaced (see docs/archive or git history for the old Singapore/regional
    # proxy lineup) with the EIA U.S. daily spot-price product set from the
    # uploaded Energy_Product_Spot_Prices.xlsx, sourced live from the EIA
    # Open Data API (petroleum/pri/spt) -- see EIA_PRODUCT_SERIES below.
    "Products": [
        {"code": "GASOLINE_CONV_GC", "name": "Conventional Gasoline (US Gulf Coast, Regular)", "unit": "$/gal"},
        {"code": "ULSD_GC", "name": "Ultra-Low-Sulfur No. 2 Diesel Fuel (US Gulf Coast)", "unit": "$/gal"},
        {"code": "JETKERO_GC", "name": "Kerosene-Type Jet Fuel (US Gulf Coast)", "unit": "$/gal"},
        {"code": "PROPANE_MB", "name": "Propane (Mont Belvieu, Texas)", "unit": "$/gal"},
    ],
}

# Retired product codes from the old catalog -- kept only so a one-time
# migration (backend/tools/replace_products_catalog.py) knows what to
# deactivate. Not used by seed.py.
RETIRED_PRODUCT_CODES = [
    "NAPHTHA", "GASOLINE92", "GASOLINE95", "JETKERO",
    "GASOIL10", "FUELOIL180", "FUELOIL380", "LPG",
]

# --- Seed source data, carried over from github.com/BT-Rajan/knpc-dashboard
# (main branch) config.py SOURCES / YAHOO_BENCHMARKS / PRODUCT_PROXY_MAP /
# DUBAI_KEYWORDS. Same underlying websites, re-expressed as rows for this
# app's Source table (url + source_type + value_selector) instead of
# in-code collector functions. Pure data — consumed by app/seed.py, no
# scraper logic changes.
SOURCE_URLS = {
    "kpc_oil_prices": "https://eapp.kpc.com.kw/oilprices/oilprices.aspx",
    "oilprice_charts": "https://oilprice.com/oil-price-charts/",
    "oilprice_news": "https://oilprice.com/Latest-Energy-News/World-News/",
    "investing_commodities": "https://www.investing.com/commodities/",
    "tradingeconomics_energy": "https://tradingeconomics.com/commodities",
    "yahoo_chart": "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d",
}

# Multi-ticker fallback per crude benchmark (Yahoo Finance), tried in order.
YAHOO_TICKERS = {
    "BRENT": ["BZ=F"],
    "WTI": ["CL=F"],
    "OMAN": ["O6=F", "QM=F", "O9=F"],
}

# Keyword-anchored fallback sources (used when a benchmark/product has no
# clean futures ticker, or as a secondary check behind Yahoo) — same
# public pages and keyword lists the old app scanned for a nearby price.
DUBAI_KEYWORDS = ["dubai crude", "dubai", "oman/dubai", "platts dubai"]
KEC_KEYWORDS = ["kec", "kuwait export crude"]
BRENT_KEYWORDS = ["brent"]
WTI_KEYWORDS = ["wti", "west texas intermediate"]
OMAN_KEYWORDS = ["oman crude", "oman"]

# --- Products: EIA Open Data API (petroleum/pri/spt), daily spot prices ---
# series = EIA's published series ID for this exact product/location pair
# (same style of code as RWTC for WTI). query = (product keyword, location
# keyword) used by eia_client.resolve_series_id() as a self-healing fallback
# if the hardcoded series ID above ever stops returning data -- see
# app/eia_client.py for why. Product/location names below are the "Category"
# / "Product / Location" columns from the source spreadsheet.
EIA_PRODUCT_SERIES = {
    "GASOLINE_CONV_GC": {
        "series": "EER_EPMRU_PF4_RGC_DPG",
        "query": ("conventional gasoline", "gulf coast"),
    },
    "ULSD_GC": {
        "series": "EER_EPD2DXL0_PF4_RGC_DPG",
        "query": ("ultra-low sulfur", "gulf coast"),
    },
    "JETKERO_GC": {
        "series": "EER_EPJK_PF4_RGC_DPG",
        "query": ("kerosene-type jet fuel", "gulf coast"),
    },
    "PROPANE_MB": {
        "series": "EER_EPLLPA_PF4_Y44MB_DPG",
        "query": ("propane", "mont belvieu"),
    },
}

# --- Report Generation ---
QUARTER_MONTHS = {
    "Q1": (1, 3),
    "Q2": (4, 6),
    "Q3": (7, 9),
    "Q4": (10, 12),
}
REPORTS_DIR = BASE_DIR / "exports" / "quarterly_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

MOG_DIVISION_NAME = "Marketing Operations Group (MOG)"

# Product metadata -- U.S. Gulf Coast / Mont Belvieu spot markets, sourced
# live from the EIA Open Data API (see EIA_PRODUCT_SERIES above).
PRODUCT_PROXY_MAP = {
    "GASOLINE_CONV_GC": {
        "market": "U.S. Gulf Coast",
        "proxy_type": "Direct spot price (not a proxy)",
        "benchmark_basis": "EIA daily spot price, Conventional Gasoline, Regular",
        "notes": "EIA petroleum/pri/spt series EER_EPMRU_PF4_RGC_DPG.",
    },
    "ULSD_GC": {
        "market": "U.S. Gulf Coast",
        "proxy_type": "Direct spot price (not a proxy)",
        "benchmark_basis": "EIA daily spot price, Ultra-Low-Sulfur No. 2 Diesel Fuel",
        "notes": "EIA petroleum/pri/spt series EER_EPD2DXL0_PF4_RGC_DPG.",
    },
    "JETKERO_GC": {
        "market": "U.S. Gulf Coast",
        "proxy_type": "Direct spot price (not a proxy)",
        "benchmark_basis": "EIA daily spot price, Kerosene-Type Jet Fuel",
        "notes": "EIA petroleum/pri/spt series EER_EPJK_PF4_RGC_DPG.",
    },
    "PROPANE_MB": {
        "market": "Mont Belvieu, Texas",
        "proxy_type": "Direct spot price (not a proxy)",
        "benchmark_basis": "EIA daily spot price, Propane",
        "notes": "EIA petroleum/pri/spt series EER_EPLLPA_PF4_Y44MB_DPG.",
    },
}
