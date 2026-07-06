"""
Central configuration for the 13F-Analytics pipeline.

Every notebook and module imports from here so the whole project stays
consistent (one CIK, one data folder, one User-Agent).
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Target manager
# ---------------------------------------------------------------------------
CIK = "0001067983"          # Berkshire Hathaway Inc (zero-padded to 10 digits)
MANAGER_NAME = "Berkshire Hathaway"
N_QUARTERS = 8              # how many recent quarters to analyze

# ---------------------------------------------------------------------------
# SEC etiquette
# ---------------------------------------------------------------------------
# The SEC *requires* a descriptive User-Agent with contact info.
# Requests without it get 403'd.  <-- this was the original "403 problem".
#
# NOTE: do NOT hardcode a "Host" header. The old code sent
# Host: data.sec.gov on every request, which silently breaks calls to
# www.sec.gov (the Archives server). requests sets Host correctly on its own.
USER_AGENT = "13F-Analytics research your_email@example.com"  # <-- EDIT ME

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

# SEC fair-access policy: max 10 requests/second. We stay well under it.
REQUEST_DELAY_SECONDS = 0.25
MAX_RETRIES = 4

# ---------------------------------------------------------------------------
# Paths (single shared /data layer -- notebooks talk through these files)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_XML_DIR = DATA_DIR / "raw_xml"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

FILINGS_PARQUET = PROCESSED_DIR / "filings.parquet"
HOLDINGS_RAW_PARQUET = PROCESSED_DIR / "holdings_raw.parquet"
HOLDINGS_PARQUET = PROCESSED_DIR / "holdings.parquet"
TRANSACTIONS_PARQUET = PROCESSED_DIR / "transactions.parquet"
PORTFOLIO_PARQUET = PROCESSED_DIR / "portfolio_summary.parquet"

for _d in (RAW_XML_DIR, PROCESSED_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def cik_no_zeros() -> str:
    """CIK without leading zeros (EDGAR Archives paths use this form)."""
    return str(int(CIK))
