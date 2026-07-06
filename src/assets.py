"""
Module 3 -- Asset classification + holdings cleaning.

Two jobs:

1. classify_asset(): map (titleOfClass, putCall) -> a clean asset_class:
   Common Stock, Preferred Stock, ADR/ADS, ETF, Corporate Bond,
   Convertible Bond, Note, Call Option, Put Option, Right, Warrant, Other.

2. clean_holdings(): fix the "Apple duplicate" problem. A single security
   appears in MULTIPLE infoTable rows when voting authority or investment
   discretion is split across Berkshire subsidiaries (sole vs shared,
   different otherManager codes). Those are the SAME position and must be
   aggregated -- summing naively without grouping double-counts nothing, but
   treating each row as a distinct holding breaks quarter-over-quarter
   transaction matching. We aggregate on (quarter, cusip, put_call).
"""
from __future__ import annotations

import pandas as pd

from . import config
from .utils import load_parquet, log, save_parquet

_CLASS_RULES = [  # (keywords in titleOfClass, asset_class) -- order matters
    (("ADR",), "ADR"),
    (("ADS",), "ADS"),
    (("ETF", "TRUST UNIT", "INDEX FD", "FUND"), "ETF"),
    (("CONV",), "Convertible Bond"),
    (("BOND", "DEB",), "Corporate Bond"),
    (("NOTE",), "Note"),
    (("PFD", "PREF",), "Preferred Stock"),
    (("RIGHT", "RT",), "Right"),
    (("WARRANT", "WT",), "Warrant"),
    (("COM", "CL A", "CL B", "CL C", "ORD", "SHS", "STOCK"), "Common Stock"),
]


def classify_asset(title: str | None, put_call: str | None) -> str:
    """Return a clean asset class label for one holding."""
    if put_call:
        pc = put_call.strip().lower()
        if pc == "call":
            return "Call Option"
        if pc == "put":
            return "Put Option"

    t = (title or "").upper()
    for keywords, label in _CLASS_RULES:
        if any(k in t for k in keywords):
            return label
    return "Other"


def clean_holdings() -> pd.DataFrame:
    """Notebook 04 entry point: dedupe + classify -> holdings.parquet."""
    raw = load_parquet(config.HOLDINGS_RAW_PARQUET)

    raw = raw.dropna(subset=["cusip"]).copy()
    raw["cusip"] = raw["cusip"].str.strip().str.upper()
    raw["put_call"] = raw["put_call"].fillna("")

    before = len(raw)
    grouped = (
        raw.groupby(["quarter", "report_date", "cusip", "put_call"], as_index=False)
        .agg(
            issuer=("issuer", "first"),
            title=("title", "first"),
            value_usd=("value_usd", "sum"),
            shares=("shares", "sum"),
            share_type=("share_type", "first"),
            sole=("sole", "sum"),
            shared=("shared", "sum"),
            none=("none", "sum"),
            n_rows=("cusip", "size"),   # audit trail: how many raw rows merged
        )
    )
    log.info("deduplicated %d raw rows -> %d positions", before, len(grouped))

    grouped["asset_class"] = [
        classify_asset(t, pc) for t, pc in zip(grouped["title"], grouped["put_call"])
    ]

    # Portfolio weight within each quarter
    grouped["portfolio_weight"] = grouped["value_usd"] / grouped.groupby("quarter")[
        "value_usd"
    ].transform("sum")

    grouped = grouped.sort_values(
        ["report_date", "value_usd"], ascending=[False, False]
    ).reset_index(drop=True)

    save_parquet(grouped, config.HOLDINGS_PARQUET)
    return grouped
