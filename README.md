# 13F-Analytics

An institutional-grade pipeline that downloads SEC 13F filings, parses holdings, detects quarter-over-quarter transactions, computes portfolio analytics, renders research-report charts, and writes automated commentary. Built for Berkshire Hathaway by default, but changing one line in `src/config.py` points it at **any** 13F filer.

## Architecture

Notebooks are orchestration and storytelling. `src/` is the reusable engine. `data/` is the database. **Notebooks never call each other — they pass data through parquet files.**

```
13F-Analytics/
├── notebooks/
│   ├── 01_download_filings.ipynb    SEC API → filings.parquet + cached XML
│   ├── 02_download_xml.ipynb        audit the XML cache (well-formed, has infoTable)
│   ├── 03_parse_xml.ipynb           XML → holdings_raw.parquet
│   ├── 04_build_holdings.ipynb      dedupe + classify → holdings.parquet
│   ├── 05_transaction_engine.ipynb  FULL OUTER JOIN → transactions.parquet
│   ├── 06_portfolio_analysis.ipynb  summary metrics, league tables
│   ├── 07_visualizations.ipynb      publication-quality charts → reports/figures
│   └── 08_storytelling.ipynb        automated commentary → reports/portfolio_review.md
├── src/
│   ├── config.py        CIK, N_QUARTERS, User-Agent, all paths (edit here only)
│   ├── utils.py         retrying session, SEC rate limiting, parquet I/O
│   ├── sec.py           submissions API, content-verified XML discovery
│   ├── parser.py        namespace-safe infoTable parser, value-unit normalization
│   ├── assets.py        dedupe (the "Apple problem") + asset classification
│   ├── transactions.py  BUY / SELL / NEW POSITION / FULL EXIT / HOLD engine
│   ├── analytics.py     portfolio value, weights, HHI, turnover, league tables
│   ├── charts.py        institutional-style matplotlib chart library
│   └── commentary.py    data-driven narrative generation
├── data/
│   ├── raw_xml/         cached information-table XML, one per quarter
│   └── processed/       filings, holdings_raw, holdings, transactions, portfolio_summary (parquet)
├── reports/figures/     saved PNG charts
├── tests/test_pipeline.py   end-to-end test on synthetic 13F XML (no network needed)
└── README.md
```

Data flow: `filings.parquet → raw_xml/ → holdings_raw.parquet → holdings.parquet → transactions.parquet → portfolio_summary.parquet → charts + report`.

## Quick start

### Option A: Google Colab (recommended, no local setup needed)

Open a new Colab notebook at colab.research.google.com and run these cells in order:

**1. Get the code**
```python
!git clone https://github.com/YOUR_USERNAME/13F-Analytics.git
```

**2. Navigate into the project**
```python
import os, sys
os.chdir('/content/13F-Analytics')
sys.path.insert(0, '/content/13F-Analytics')
```

**3. Install dependencies**
```python
!pip install pyarrow requests pandas matplotlib numpy -q
```

**4. Set your User-Agent (required -- the SEC rejects anonymous requests)**
```python
!sed -i 's/13F-Analytics research your_email@example.com/Your Name your_email@email.com/' src/config.py
!grep "USER_AGENT" src/config.py
```

**5. Verify the engine works (no network needed)**
```python
!python tests/test_pipeline.py
```

**6. Run the full pipeline**
```python
!python run_all.py
```

This downloads 8 quarters of Berkshire Hathaway 13F data from SEC EDGAR, parses holdings, detects transactions, computes portfolio metrics, renders charts, and writes research commentary. Takes about 3 minutes.

To persist data across Colab sessions, mount Google Drive before step 1:
```python
from google.colab import drive
drive.mount('/content/drive')
!git clone https://github.com/YOUR_USERNAME/13F-Analytics.git /content/drive/MyDrive/13F-Analytics
import os, sys
os.chdir('/content/drive/MyDrive/13F-Analytics')
sys.path.insert(0, '/content/drive/MyDrive/13F-Analytics')
```

### Option B: Local machine

```bash
git clone https://github.com/YOUR_USERNAME/13F-Analytics.git
cd 13F-Analytics
pip install -r requirements.txt
```

Edit `src/config.py` and set `USER_AGENT` to your real name and email. Then:

```bash
python tests/test_pipeline.py   # verify engine works without network
python run_all.py               # run all 8 notebooks in sequence
```

### To analyze a different fund manager

Find any manager's CIK at sec.gov/cgi-bin/browse-edgar, then edit two lines in `src/config.py`:

```python
CIK = "0001067983"          # replace with any manager's 10-digit CIK
MANAGER_NAME = "Berkshire Hathaway"  # update the display name
```

Delete `data/processed/` and `data/raw_xml/` contents and re-run.

## Hard-won lessons encoded in this codebase

These are the failure modes from earlier attempts, and where each fix lives:

| Symptom | Root cause | Fix |
|---|---|---|
| 403 / HTML instead of JSON | Missing descriptive `User-Agent`; hardcoded `Host: data.sec.gov` header sent to `www.sec.gov` | `config.HEADERS` requires contact info; no `Host` header; retries with backoff (`utils.make_session`) |
| Empty holdings DataFrames | `primary_doc.xml` (the cover page) mistaken for the information table by filename guessing | `sec.find_info_table_xml` downloads candidates and **verifies content** contains `<infoTable>` before accepting |
| Still empty after finding the right file | XML namespaces (`ns1:` etc.) break literal tag-name searches | `parser.py` matches on local tag names, prefix-agnostic |
| Quarters shifted by one | Quarter derived from `filingDate` (13Fs are filed ~45 days late) | Quarter comes from `reportDate` |
| Apple appears 2–3 times per quarter | Voting authority split across subsidiaries produces multiple infoTable rows for one position | `assets.clean_holdings` aggregates on `(quarter, cusip, put_call)` with an `n_rows` audit column |
| Old quarters look 1000× smaller | Value reported in $ thousands before Jan 2023, dollars after | `parser.normalize_value_units` emits a consistent `value_usd` |
| Every holding flagged as a "trade" | Classifying trades on dollar value, which moves with prices | Transaction engine classifies on **share** changes |
| Restated filings double-counted | 13F-HR/A amendments treated as extra quarters | Latest filing per report period wins |
| Silent, undebuggable failures | Bare `except: return None` everywhere | Errors raise or log with counts; each pipeline stage is auditable |

## Known limitations

13F data covers long U.S.-listed positions only: no shorts, no cash, no most non-U.S. holdings, and it arrives with a ~45-day lag. Stock splits appear as share changes to the transaction engine — sanity-check outsized "trades" against corporate actions. Sector allocation requires an external CUSIP→sector mapping (e.g., OpenFIGI) and is left as an extension point in `analytics.py`.

## Scaling up

Because logic lives in `src/` and state lives in `data/`, the upgrade path is mechanical: swap the parquet layer for Supabase/BigQuery tables, loop `build_filings_dataset` over a list of CIKs, and schedule notebook 01 quarterly. Nothing else changes.
