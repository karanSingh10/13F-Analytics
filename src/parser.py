"""
Module 2 -- XML parser.

Parses SEC 13F information-table XML into a tidy DataFrame, one row per
<infoTable> entry, with every field the schema defines:

    issuer, title, cusip, value, shares, share_type, put_call,
    investment_discretion, other_manager, sole, shared, none

Fixes vs. the earlier pipeline
------------------------------
* Namespace-safe parsing. SEC info tables use an XML namespace
  (http://www.sec.gov/edgar/document/thirteenf/informationtable) and the
  prefix varies between filings (ns1:, n1:, none at all). Searching for
  literal tag names like "infoTable" silently returns zero rows on
  namespaced files -- another source of the old "empty holdings" bug.
  We match on the *local* tag name, ignoring prefixes entirely.

* Value units are normalized. Before Q4 2022 (technical amendment effective
  Jan 2023), `value` was reported in THOUSANDS of dollars; after, in whole
  dollars. Mixing them makes old portfolios look 1000x smaller. We detect
  the regime from the report period and emit a consistent `value_usd`.

* No silent failures: malformed rows are counted and logged, not swallowed.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pandas as pd

from . import config
from .utils import log, load_parquet, save_parquet

# Report periods up to and including this date reported value in $ thousands.
VALUE_IN_THOUSANDS_UNTIL = pd.Timestamp("2022-12-31")


def _local(tag: str) -> str:
    """Strip namespace: '{http://...}infoTable' -> 'infotable'."""
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(elem: ET.Element, name: str) -> str | None:
    name = name.lower()
    for child in elem.iter():
        if _local(child.tag) == name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _to_float(x: str | None) -> float | None:
    if x is None:
        return None
    try:
        return float(x.replace(",", ""))
    except ValueError:
        return None


def parse_info_table(xml_text: str) -> pd.DataFrame:
    """Parse one information-table XML into a DataFrame (raw units)."""
    root = ET.fromstring(xml_text)

    rows, bad = [], 0
    for node in root.iter():
        if _local(node.tag) != "infotable":
            continue
        try:
            rows.append({
                "issuer": _child_text(node, "nameOfIssuer"),
                "title": _child_text(node, "titleOfClass"),
                "cusip": _child_text(node, "cusip"),
                "value": _to_float(_child_text(node, "value")),
                "shares": _to_float(_child_text(node, "sshPrnamt")),
                "share_type": _child_text(node, "sshPrnamtType"),
                "put_call": _child_text(node, "putCall"),
                "investment_discretion": _child_text(node, "investmentDiscretion"),
                "other_manager": _child_text(node, "otherManager"),
                "sole": _to_float(_child_text(node, "Sole")),
                "shared": _to_float(_child_text(node, "Shared")),
                "none": _to_float(_child_text(node, "None")),
            })
        except Exception as exc:  # keep parsing; report at the end
            bad += 1
            log.warning("bad infoTable row skipped: %s", exc)

    if bad:
        log.warning("%d malformed rows skipped", bad)
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(
            "Parsed 0 holdings. This XML is probably the cover page "
            "(primary_doc.xml), not the information table."
        )
    return df


def normalize_value_units(df: pd.DataFrame, report_date: pd.Timestamp) -> pd.DataFrame:
    """Add value_usd, consistent across the 2023 units change."""
    df = df.copy()
    multiplier = 1_000 if report_date <= VALUE_IN_THOUSANDS_UNTIL else 1
    df["value_usd"] = df["value"] * multiplier
    return df


def build_raw_holdings() -> pd.DataFrame:
    """Notebook 03 entry point: parse every cached XML -> holdings_raw.parquet."""
    filings = load_parquet(config.FILINGS_PARQUET)

    frames = []
    for _, f in filings.iterrows():
        if not f["local_xml_path"]:
            log.warning("skipping %s -- no XML cached", f["quarter"])
            continue
        xml_text = open(f["local_xml_path"], encoding="utf-8").read()
        df = parse_info_table(xml_text)
        df = normalize_value_units(df, pd.Timestamp(f["reportDate"]))
        df["quarter"] = f["quarter"]
        df["report_date"] = pd.Timestamp(f["reportDate"])
        df["accession_number"] = f["accessionNumber"]
        frames.append(df)
        log.info("%s: %d raw positions", f["quarter"], len(df))

    if not frames:
        raise ValueError("No holdings parsed from any filing.")
    holdings = pd.concat(frames, ignore_index=True)
    save_parquet(holdings, config.HOLDINGS_RAW_PARQUET)
    return holdings
