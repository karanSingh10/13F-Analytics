"""Generate the 8 project notebooks. Notebooks are thin: markdown + calls into src/."""
import nbformat as nbf
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "notebooks"
OUT.mkdir(exist_ok=True)

SETUP = '''# --- setup: make src/ importable from notebooks/ ---
import sys, pathlib
PROJECT_ROOT = pathlib.Path.cwd().parent if pathlib.Path.cwd().name == "notebooks" else pathlib.Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

# On Google Colab, uncomment:
# !pip install -q pyarrow requests pandas matplotlib
# then upload/clone the repo so that src/ sits next to notebooks/

import pandas as pd
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")'''


def nb(cells):
    n = nbf.v4.new_notebook()
    out = []
    for kind, src in cells:
        out.append(nbf.v4.new_markdown_cell(src) if kind == "md"
                   else nbf.v4.new_code_cell(src))
    n.cells = out
    n.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python",
                                 "name": "python3"},
                  "language_info": {"name": "python", "version": "3.12"}}
    return n


NOTEBOOKS = {

"01_download_filings.ipynb": [
("md", """# 01 — SEC Filings Downloader

**Job:** CIK → SEC submissions API → 13F-HR filings → *content-verified* information-table XML → `data/filings.parquet` + cached XML.

**Lessons baked into `src/sec.py` (from earlier failed attempts):**
1. **403 errors** — the SEC requires a descriptive `User-Agent` with contact info. Set yours in `src/config.py`.
2. **Never hardcode a `Host` header** — the old code sent `Host: data.sec.gov` to `www.sec.gov`, silently breaking Archives requests.
3. **`primary_doc.xml` is the cover page, not the holdings** — the old keyword search picked it first, which is why holdings came back empty. We now *download and verify* that a candidate XML actually contains `<infoTable>` rows before accepting it.
4. **Quarter = `reportDate`, not `filingDate`** — 13Fs are filed ~45 days after quarter end, so filing-date quarters are shifted by one.
5. **Amendments (13F-HR/A) supersede originals** — we keep the latest filing per report period.
6. **Rate limiting + retries** — SEC allows ≤10 req/s; we sleep between requests and retry 403/429/5xx with backoff instead of hiding errors in a bare `except`."""),
("code", SETUP),
("code", '''from src import config
from src.utils import make_session
from src.sec import build_filings_dataset

print("Manager:", config.MANAGER_NAME, "| CIK:", config.CIK)
print("User-Agent:", config.USER_AGENT)
assert "your_email" not in config.USER_AGENT, (
    "Edit USER_AGENT in src/config.py with your real name/email first — "
    "the SEC rejects anonymous requests with 403."
)'''),
("code", '''session = make_session()
filings = build_filings_dataset(session, n_quarters=config.N_QUARTERS)
filings'''),
("code", '''# Sanity checks: every quarter should have a verified holdings XML
assert filings["local_xml_path"].notna().all(), "Some filings have no verified infoTable XML"
assert filings["quarter"].is_unique
filings[["quarter", "form", "filingDate", "reportDate", "xml_file"]]'''),
("md", "**Output:** `data/processed/filings.parquet` + one cached XML per quarter in `data/raw_xml/`. Next: `02_download_xml.ipynb`."),
],

"02_download_xml.ipynb": [
("md", """# 02 — XML Cache Verification

Notebook 01 already downloads and caches the verified XML (one network pass, not two).
This notebook **audits the cache**: every file exists, is well-formed XML, and contains `<infoTable>` rows — so notebook 03 never parses a cover page or an HTML error page again.

> Rule from the design discussion: notebooks never call each other — they pass data through `data/`."""),
("code", SETUP),
("code", '''from pathlib import Path
from xml.etree import ElementTree as ET
from src import config
from src.utils import load_parquet
from src.sec import looks_like_info_table

filings = load_parquet(config.FILINGS_PARQUET)
filings[["quarter", "xml_file", "local_xml_path"]]'''),
("code", '''report = []
for _, f in filings.iterrows():
    p = Path(f["local_xml_path"])
    txt = p.read_text(encoding="utf-8")
    ok_xml = True
    try:
        ET.fromstring(txt)
    except ET.ParseError:
        ok_xml = False
    report.append({
        "quarter": f["quarter"],
        "file": p.name,
        "size_kb": round(p.stat().st_size / 1024, 1),
        "well_formed": ok_xml,
        "has_infoTable": looks_like_info_table(txt),
        "looks_like_html": txt.lstrip()[:6].lower().startswith("<html"),  # the old 403 symptom
    })
audit = pd.DataFrame(report)
audit'''),
("code", '''assert audit["well_formed"].all(), "Malformed XML in cache — re-run notebook 01"
assert audit["has_infoTable"].all(), "A cover page slipped through — re-run notebook 01"
assert not audit["looks_like_html"].any(), "HTML error page cached (bad User-Agent?)"
print("cache verified: ", len(audit), "quarters ready for parsing")'''),
],

"03_parse_xml.ipynb": [
("md", """# 03 — Parse XML → Raw Holdings

Parses every cached information table into one tidy DataFrame (`holdings_raw.parquet`), one row per `<infoTable>` entry, with **all** fields: issuer, title, cusip, value, shares, share_type, put_call, investment_discretion, sole/shared/none.

**Key fixes in `src/parser.py`:**
- **Namespace-safe** parsing — SEC info tables use namespaces with varying prefixes (`ns1:`, `n1:`, none). Matching literal tag names returns 0 rows on namespaced files: the other cause of the old "empty holdings" bug. We match on local tag names.
- **Value-units regime** — before the Jan-2023 technical amendment, `value` was in **thousands of dollars**; after, in whole dollars. We normalize both into `value_usd` so history is comparable.
- Malformed rows are **logged and counted**, never silently swallowed."""),
("code", SETUP),
("code", '''from src.parser import build_raw_holdings

holdings_raw = build_raw_holdings()
holdings_raw.head(10)'''),
("code", '''# Per-quarter row counts — Berkshire typically reports ~40–130 rows/quarter
holdings_raw.groupby("quarter").agg(
    rows=("cusip", "size"),
    issuers=("issuer", "nunique"),
    total_value_usd=("value_usd", "sum"),
)'''),
("code", '''# Field completeness audit
holdings_raw.isna().mean().round(3).sort_values(ascending=False).to_frame("share_missing")'''),
],

"04_build_holdings.ipynb": [
("md", """# 04 — Clean Holdings: Dedupe + Asset Classification

**The "Apple duplicate" fix:** one security appears in *multiple* infoTable rows when voting authority / investment discretion is split across subsidiaries. Those rows are the **same position** — we aggregate on `(quarter, cusip, put_call)`, summing value/shares and keeping an `n_rows` audit column.

`put_call` stays in the key so a stock and a put on the same CUSIP remain **separate positions** (they are economically opposite).

Then every position gets an `asset_class` (Common Stock, Preferred, ADR/ADS, ETF, Corporate/Convertible Bond, Note, Call/Put Option, Right, Warrant) and a `portfolio_weight`."""),
("code", SETUP),
("code", '''from src.assets import clean_holdings

holdings = clean_holdings()
holdings.head(10)'''),
("code", '''# Proof the dedupe worked: positions merged from >1 raw row
holdings[holdings["n_rows"] > 1][["quarter", "issuer", "n_rows", "shares", "value_usd"]].head(10)'''),
("code", '''# Weights must sum to 1 within each quarter
holdings.groupby("quarter")["portfolio_weight"].sum().round(6)'''),
("code", '''# Asset class mix, latest quarter
latest = holdings["quarter"].max()
holdings[holdings["quarter"] == latest].groupby("asset_class")["value_usd"].sum().sort_values(ascending=False)'''),
],

"05_transaction_engine.ipynb": [
("md", """# 05 — Transaction Engine (FULL OUTER JOIN)

Reproduces the SQL logic in pandas. For each consecutive quarter pair, `merge(how="outer")` on `(cusip, put_call)`:

| prev | curr | action |
|---|---|---|
| ∅ | ✓ | **NEW POSITION** |
| ✓ | ∅ | **FULL EXIT** |
| shares ↑ | | **BUY** |
| shares ↓ | | **SELL** |
| shares = | | HOLD |

**Why shares, not value:** market prices move every position's value every quarter — classifying on value would label *everything* a trade. Shares only change when the manager transacts. (Caveat: stock splits look like share changes; cross-check big anomalies.)"""),
("code", SETUP),
("code", '''from src.transactions import build_transactions

tx = build_transactions()
tx.head(10)'''),
("code", '''# Action counts per quarter
tx.pivot_table(index="quarter", columns="action", values="cusip",
               aggfunc="count", fill_value=0)'''),
("code", '''# Biggest trades in the latest quarter
latest = tx["quarter"].max()
(tx[(tx["quarter"] == latest) & (tx["action"] != "HOLD")]
   .reindex(tx[tx["quarter"] == latest]["value_change_usd"].abs().sort_values(ascending=False).index)
   .dropna(subset=["action"])
   [["issuer", "action", "share_change", "value_change_usd"]]
   .head(15))'''),
],

"06_portfolio_analysis.ipynb": [
("md", """# 06 — Institutional Analytics

Quarterly portfolio summary (value, position count, top-5/top-10 concentration, **HHI**, average/median position, turnover) plus the league tables: largest holdings / buys / sells / new positions / full exits.

Turnover convention: `min(gross buys, gross sells) / average portfolio value` — counts round-trip trading only, so pure in/outflows don't inflate it."""),
("code", SETUP),
("code", '''from src import analytics
from src.utils import load_parquet
from src import config

holdings = load_parquet(config.HOLDINGS_PARQUET)
tx = load_parquet(config.TRANSACTIONS_PARQUET)

summary = analytics.portfolio_summary(holdings, tx)
summary'''),
("code", '''latest = summary["quarter"].iloc[-1]
print(f"=== {latest} ===")
analytics.largest_holdings(holdings, latest, n=10)'''),
("code", '''analytics.largest_buys(tx, latest, n=10)'''),
("code", '''analytics.largest_sells(tx, latest, n=10)'''),
("code", '''analytics.new_positions(tx, latest, n=10)'''),
("code", '''analytics.full_exits(tx, latest, n=10)'''),
("code", '''analytics.asset_allocation(holdings, latest)'''),
],

"07_visualizations.ipynb": [
("md", """# 07 — Publication-Quality Visualizations

Institutional-research styling from `src/charts.py`: muted navy/gold palette, no chartjunk, `$B` axis formatting, source footnote. Every chart is also saved to `reports/figures/` for the README / a report."""),
("code", SETUP),
("code", '''from src import analytics, charts, config
from src.utils import load_parquet

holdings = load_parquet(config.HOLDINGS_PARQUET)
tx = load_parquet(config.TRANSACTIONS_PARQUET)
summary = load_parquet(config.PORTFOLIO_PARQUET)
latest = summary["quarter"].iloc[-1]'''),
("code", '''charts.plot_portfolio_value(summary);'''),
("code", '''charts.plot_top_holdings(analytics.largest_holdings(holdings, latest), latest);'''),
("code", '''charts.plot_buys_sells(tx, latest);'''),
("code", '''charts.plot_concentration(summary);'''),
("code", '''charts.plot_asset_allocation(analytics.asset_allocation(holdings, latest), latest);'''),
("code", '''charts.plot_turnover(summary);'''),
("code", '''sorted(p.name for p in config.FIGURES_DIR.glob("*.png"))'''),
],

"08_storytelling.ipynb": [
("md", """# 08 — Automated Commentary & Report

Turns the metrics into research-note prose, e.g. *"Berkshire increased exposure to Chevron while trimming Occidental. Apple remained the largest holding, representing 24.8% of assets. Portfolio turnover declined compared with the previous quarter."*

Every sentence is generated from the data — swap the CIK in `config.py` and the same code narrates any manager. The full markdown report is written to `reports/`."""),
("code", SETUP),
("code", '''from src import commentary, config
from src.utils import load_parquet

holdings = load_parquet(config.HOLDINGS_PARQUET)
tx = load_parquet(config.TRANSACTIONS_PARQUET)
summary = load_parquet(config.PORTFOLIO_PARQUET)

latest = summary["quarter"].iloc[-1]
print(commentary.quarterly_commentary(latest, holdings, tx, summary))'''),
("code", '''report_md = commentary.full_report(holdings, tx, summary)
out = config.PROJECT_ROOT / "reports" / "portfolio_review.md"
out.write_text(report_md, encoding="utf-8")
print("wrote", out)
print()
print(report_md[:1500])'''),
("md", """### Optional next step — Parquet → Supabase
The `data/processed/*.parquet` files are the project's "database". To productionize, replace the parquet layer with Supabase/BigQuery tables: each notebook writes to a table instead of a file, everything else stays identical — that's the payoff of the *notebooks depend on data + functions, never on each other* rule."""),
],
}

for name, cells in NOTEBOOKS.items():
    nbf.write(nb(cells), OUT / name)
    print("wrote", name)
