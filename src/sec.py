"""
Module 1 -- SEC downloader.

Pipeline:  CIK -> submissions API -> 13F-HR filings -> filing index ->
           *content-verified* information-table XML -> local cache.

Fixes vs. the earlier broken pipeline
-------------------------------------
1. XML discovery is verified by CONTENT, not filename guessing.
   Every 13F filing contains at least two XMLs:
     - primary_doc.xml      (the cover page  -> has NO holdings)
     - <something>.xml      (the information table -> has <infoTable> rows)
   The old keyword list put "primary_doc" *ahead* of the real table, which is
   exactly why holdings came back empty. Here we download each candidate and
   keep the one that actually contains an <informationTable>.

2. Quarter comes from `reportDate` (the period the holdings describe),
   not `filingDate`. 13Fs are filed ~45 days late, so deriving the quarter
   from the filing date shifts everything one quarter forward.

3. Amendments (13F-HR/A) are handled: for each report period we keep the
   most recently filed document, so a restatement supersedes the original.

4. URLs use the un-padded CIK from config, so switching managers means
   editing one line in config.py -- nothing is hardcoded to Berkshire.
"""
from __future__ import annotations

import pandas as pd
import requests

from . import config
from .utils import log, polite_get, save_parquet

ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


# ---------------------------------------------------------------------------
# Step 1: submissions -> table of 13F filings
# ---------------------------------------------------------------------------
def get_submissions(session: requests.Session) -> dict:
    url = SUBMISSIONS_URL.format(cik=config.CIK)
    log.info("fetching submissions: %s", url)
    return polite_get(session, url).json()


def get_13f_filings(session: requests.Session, n_quarters: int | None = None) -> pd.DataFrame:
    """Return one row per report period: the latest 13F-HR / 13F-HR/A for it."""
    data = get_submissions(session)
    recent = pd.DataFrame(data["filings"]["recent"])

    f = recent[recent["form"].isin(["13F-HR", "13F-HR/A"])].copy()
    if f.empty:
        raise ValueError(f"No 13F filings found for CIK {config.CIK}")

    f["filingDate"] = pd.to_datetime(f["filingDate"])
    f["reportDate"] = pd.to_datetime(f["reportDate"])
    # Quarter of the HOLDINGS period (reportDate), not of the filing date.
    f["quarter"] = f["reportDate"].dt.to_period("Q").astype(str)

    # Amendments supersede originals: keep latest filing per report period.
    f = (
        f.sort_values(["reportDate", "filingDate"])
         .groupby("quarter", as_index=False)
         .tail(1)
         .sort_values("reportDate", ascending=False)
         .reset_index(drop=True)
    )

    n = n_quarters or config.N_QUARTERS
    f = f.head(n)
    log.info("found %d report periods: %s ... %s",
             len(f), f["quarter"].iloc[-1], f["quarter"].iloc[0])
    return f[["accessionNumber", "form", "filingDate", "reportDate", "quarter",
              "primaryDocument"]]


# ---------------------------------------------------------------------------
# Step 2: filing directory -> the *real* information-table XML
# ---------------------------------------------------------------------------
def filing_folder(accession_number: str) -> str:
    return accession_number.replace("-", "")


def filing_index_url(accession_number: str) -> str:
    return f"{ARCHIVES_BASE}/{config.cik_no_zeros()}/{filing_folder(accession_number)}/index.json"


def list_filing_xmls(session: requests.Session, accession_number: str) -> list[str]:
    idx = polite_get(session, filing_index_url(accession_number)).json()
    items = idx.get("directory", {}).get("item", [])
    return [it["name"] for it in items if it["name"].lower().endswith(".xml")]


def looks_like_info_table(xml_text: str) -> bool:
    """True if this XML actually contains 13F holdings rows."""
    lowered = xml_text[:200_000].lower()
    return "<infotable" in lowered or "informationtable" in lowered


def find_info_table_xml(session: requests.Session, accession_number: str) -> tuple[str | None, str | None]:
    """Return (filename, xml_text) of the verified information table.

    Strategy: skip the cover page (primary_doc), try likely names first,
    but ALWAYS verify by content before accepting a file.
    """
    xml_files = list_filing_xmls(session, accession_number)
    if not xml_files:
        log.warning("no XML files in %s", accession_number)
        return None, None

    # Order candidates: obvious info-table names first, cover page last.
    def rank(name: str) -> int:
        n = name.lower()
        if "infotable" in n or "informationtable" in n or "form13f" in n:
            return 0
        if "primary_doc" in n or "primarydoc" in n:
            return 2   # cover page -- last resort only
        return 1

    folder = filing_folder(accession_number)
    base = f"{ARCHIVES_BASE}/{config.cik_no_zeros()}/{folder}"

    for name in sorted(xml_files, key=rank):
        url = f"{base}/{name}"
        try:
            text = polite_get(session, url).text
        except requests.RequestException as exc:
            log.warning("failed %s: %s", url, exc)
            continue
        if looks_like_info_table(text):
            return name, text
        log.info("skipping %s (no <infoTable> -- probably the cover page)", name)

    log.warning("no information-table XML verified in %s", accession_number)
    return None, None


# ---------------------------------------------------------------------------
# Step 3: orchestration used by notebooks 01 + 02
# ---------------------------------------------------------------------------
def build_filings_dataset(session: requests.Session,
                          n_quarters: int | None = None) -> pd.DataFrame:
    """Notebook 01 entry point: filings table with verified XML, cached to disk."""
    filings = get_13f_filings(session, n_quarters)

    records = []
    for _, row in filings.iterrows():
        acc = row["accessionNumber"]
        xml_name, xml_text = find_info_table_xml(session, acc)

        local_path = None
        if xml_text is not None:
            local_path = config.RAW_XML_DIR / f"{row['quarter']}_{filing_folder(acc)}.xml"
            local_path.write_text(xml_text, encoding="utf-8")

        records.append({
            **row.to_dict(),
            "xml_file": xml_name,
            "xml_url": (f"{ARCHIVES_BASE}/{config.cik_no_zeros()}/"
                        f"{filing_folder(acc)}/{xml_name}") if xml_name else None,
            "local_xml_path": str(local_path) if local_path else None,
        })

    out = pd.DataFrame(records)
    missing = out["local_xml_path"].isna().sum()
    if missing:
        log.warning("%d filings have no verified holdings XML", missing)
    save_parquet(out, config.FILINGS_PARQUET)
    return out
