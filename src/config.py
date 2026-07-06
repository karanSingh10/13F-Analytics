# this is the main config file, every notebook reads from here
# if you want to analyze a different fund manager just change CIK and MANAGER_NAME
# thats literally the only thing you need to change

from pathlib import Path

# ---- which fund manager to analyze ----
CIK = "0001067983"       # berkshire hathaway - change this to any manager's CIK
MANAGER_NAME = "Berkshire Hathaway"   # just for display purposes in charts/reports
N_QUARTERS = 8           # how many quarters back you want to look

# ---- SEC requires you to identify yourself ----
# if you dont set this the SEC will return 403 errors and nothing will work
# put your real name and email here, doesnt need to be anything special
USER_AGENT = "Your Name your_email@example.com"   # <-- change this before running

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    # do NOT add Host header here, it breaks requests to the archives server
}

# SEC allows max 10 requests per second, keeping it slow to be safe
REQUEST_DELAY_SECONDS = 0.25
MAX_RETRIES = 4

# ---- folder structure ----
# all notebooks read and write through these paths
# notebooks never call each other, they just read/write files here
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_XML_DIR = DATA_DIR / "raw_xml"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

FILINGS_PARQUET      = PROCESSED_DIR / "filings.parquet"
HOLDINGS_RAW_PARQUET = PROCESSED_DIR / "holdings_raw.parquet"
HOLDINGS_PARQUET     = PROCESSED_DIR / "holdings.parquet"
TRANSACTIONS_PARQUET = PROCESSED_DIR / "transactions.parquet"
PORTFOLIO_PARQUET    = PROCESSED_DIR / "portfolio_summary.parquet"

for _d in (RAW_XML_DIR, PROCESSED_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def cik_no_zeros():
    # EDGAR archive URLs use CIK without leading zeros
    return str(int(CIK))
