# 13F Analytics - Tracking What Smart Money is Doing

## why i built this

about a year back i got really into stocks. not just reading about it but actually investing, pretty aggressively. at one point i was almost 50% down on my portfolio which was a painful way to learn that enthusiasm is not the same as a strategy.

so i decided to approach it differently. instead of guessing, i wanted to understand where the smartest investors in the world were putting their money. while researching i came across SEC Form 13F - a document that every institutional investor managing more than $100 million in US equities has to file every quarter disclosing all their holdings.

this felt like exactly what i needed. if i could see what warren buffett or ray dalio is holding and how that changes quarter over quarter, i could at least understand how serious investors think about building a portfolio.

the problem is there are thousands of these documents and reading them one by one would take months. so i decided to build something to automate it.

i started with berkshire hathaway because i am personally a big fan of warren buffett, but then realized there is no reason to hardcode it to one manager. i made it modular so you just change the CIK (the fund managers unique ID on SEC EDGAR) and the whole pipeline runs for any manager.

along the way i learned a lot of things i had no idea about before - what CIK and CUSIP and accession numbers are, how 13F XML is structured, how to parse XML with namespaces, how to do API calls from google colab, the 45 day filing delay and why it matters, what portfolio turnover and HHI mean. more than i expected honestly.

i am also working on a follow up project that aggregates across multiple fund managers at the same time to see consensus positions and divergences. that one needs more compute than colab can handle so its a separate thing.

---

## what this does

picks any 13F filer, downloads their last 8 quarters of filings from SEC EDGAR, parses the holdings XML, detects what changed quarter over quarter, computes portfolio metrics, draws charts, and writes a research commentary paragraph for each quarter.

all automated. change one line to switch managers.

---

## view the results (already rendered)

the notebooks below already have outputs from running on berkshire hathaway data. click any link to open in colab and see the results without running anything:

| notebook | what it shows |
|---|---|
| [Portfolio Analysis](https://colab.research.google.com/github/karanSingh10/13F-Analytics/blob/main/notebooks/06_portfolio_analysis.ipynb) | holdings tables, buys, sells, new positions, exits |
| [Visualizations](https://colab.research.google.com/github/karanSingh10/13F-Analytics/blob/main/notebooks/07_visualizations.ipynb) | all six charts |
| [Research Commentary](https://colab.research.google.com/github/karanSingh10/13F-Analytics/blob/main/notebooks/08_storytelling.ipynb) | automated narrative for each quarter |

---

## project structure

```
13F-Analytics/
├── notebooks/
│   ├── 01_download_filings.ipynb    hits SEC API, finds and downloads XML
│   ├── 02_download_xml.ipynb        verifies the downloaded XML cache
│   ├── 03_parse_xml.ipynb           parses XML into a holdings table
│   ├── 04_build_holdings.ipynb      deduplicates and classifies positions
│   ├── 05_transaction_engine.ipynb  detects buys/sells/new positions/exits
│   ├── 06_portfolio_analysis.ipynb  metrics and league tables
│   ├── 07_visualizations.ipynb      charts
│   └── 08_storytelling.ipynb        automated commentary
├── src/
│   ├── config.py       all settings in one place - CIK, User-Agent, paths
│   ├── utils.py        HTTP session with retries, parquet helpers
│   ├── sec.py          SEC API calls and XML discovery
│   ├── parser.py       XML parser, handles namespaces and unit changes
│   ├── assets.py       deduplication and asset classification
│   ├── transactions.py buy/sell/new/exit detection via full outer join
│   ├── analytics.py    portfolio metrics and league tables
│   ├── charts.py       matplotlib chart library
│   └── commentary.py   automated narrative generation
├── data/
│   ├── raw_xml/        cached XML files, one per quarter
│   └── processed/      parquet files passed between notebooks
├── reports/figures/    saved PNG charts
├── tests/
│   └── test_pipeline.py    runs full pipeline on fake data, never touches real data/
└── run_all.py          runs all 8 notebooks in sequence
```

notebooks never call each other directly. each one writes a parquet file to data/processed/ and the next one reads it. this way any notebook can be rerun on its own without redoing everything.

---

## run it yourself

### on google colab (easiest)

open a new colab notebook and run these cells:

**1. clone the repo**
```python
!git clone https://github.com/karanSingh10/13F-Analytics.git
import os, sys
os.chdir('/content/13F-Analytics')
sys.path.insert(0, '/content/13F-Analytics')
```

**2. install dependencies**
```python
!pip install pyarrow requests pandas matplotlib numpy -q
```

**3. set your name and email (required - SEC rejects anonymous requests)**
```python
!sed -i 's/Your Name your_email@example.com/Your Name youremail@email.com/' src/config.py
!grep "USER_AGENT" src/config.py
```

**4. verify engine works (no internet needed)**
```python
!python tests/test_pipeline.py
```

**5. run the full pipeline**
```python
!python run_all.py
```

takes about 3 minutes. after that open any notebook from the notebooks/ folder in the colab sidebar to see results.

to keep data between sessions mount google drive before step 1:
```python
from google.colab import drive
drive.mount('/content/drive')
!git clone https://github.com/karanSingh10/13F-Analytics.git /content/drive/MyDrive/13F-Analytics
import os, sys
os.chdir('/content/drive/MyDrive/13F-Analytics')
sys.path.insert(0, '/content/drive/MyDrive/13F-Analytics')
```

### on your local machine

```bash
git clone https://github.com/karanSingh10/13F-Analytics.git
cd 13F-Analytics
pip install -r requirements.txt
python tests/test_pipeline.py
python run_all.py
```

---

## to analyze a different fund manager

this is the whole point of making it modular. open src/config.py and change these two lines:

```python
CIK = "0001067983"              # put the managers CIK here
MANAGER_NAME = "Berkshire Hathaway"  # update the display name
```

to find any managers CIK go to sec.gov/cgi-bin/browse-edgar, search by fund name, the CIK is the 10 digit number next to their name.

then delete data/processed/ and data/raw_xml/ contents and run run_all.py again.

some examples:
- Bridgewater Associates: 1350694
- Pershing Square: 1336528  
- Renaissance Technologies: 1037389
- Citadel: 1423053

---

## things i learned building this that werent obvious

**the SEC requires you to identify yourself** - every request needs a User-Agent with your name and email otherwise you get 403 errors and nothing works

**there are two XML files per filing and only one has the holdings** - the other is a cover page. you have to verify by reading the content not guessing from the filename

**XML namespaces were confusing** - the tag might be ns1:infoTable or n1:infoTable or just infoTable depending on the filer, you cant just search for a literal tag name

**13F data is delayed by 45 days** - the quarter end is March 31 but the filing comes in May. use the reportDate not the filingDate when assigning quarters

**berkshire reports apple in multiple rows** - because they have subsidiaries with different voting authority. same position, multiple rows, need to add them up

**value field changed units in 2023** - before that quarter it was in thousands of dollars, after it was in actual dollars. mix them up and old portfolios look 1000x smaller

**classify trades on shares not dollar value** - prices move every quarter so dollar values change even when the manager did nothing. shares only change on actual transactions

---

## what 13F data does and doesnt cover

covers: long positions in US listed equities and some options

does not cover: short positions, cash, most bonds, international holdings, positions under certain thresholds

also the 45 day delay means by the time you see the data the manager may have already changed their positions. useful for understanding how serious investors think, not for real time signals.
