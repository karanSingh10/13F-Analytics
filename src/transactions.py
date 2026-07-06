"""
Module 5 -- Transaction engine.

Reproduces the SQL FULL OUTER JOIN logic in pandas: for every pair of
consecutive quarters, join current holdings to previous holdings on
(cusip, put_call) with how="outer" and classify each row:

    prev NaN,  curr value  -> NEW POSITION
    prev value, curr NaN   -> FULL EXIT
    shares up              -> BUY
    shares down            -> SELL
    shares unchanged       -> HOLD

Classification is done on SHARES, not value: a position's dollar value
moves every quarter just from price changes, so value deltas alone would
flag every single holding as a "trade". Shares only change when the
manager actually transacts. (Share splits are the known caveat; see
README.) Dollar deltas are still reported for sizing the trades.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .utils import load_parquet, log, save_parquet

KEY = ["cusip", "put_call"]
SHARE_TOLERANCE = 0.005  # <0.5% share change counts as HOLD (rounding noise)


def _quarter_pairs(quarters: list[str]) -> list[tuple[str, str]]:
    """[(prev, curr), ...] over chronologically sorted quarters."""
    qs = sorted(quarters)
    return list(zip(qs[:-1], qs[1:]))


def classify_pair(prev_df: pd.DataFrame, curr_df: pd.DataFrame) -> pd.DataFrame:
    """FULL OUTER JOIN of two quarters -> classified transactions."""
    cols = KEY + ["issuer", "title", "asset_class", "shares", "value_usd",
                  "portfolio_weight"]
    merged = prev_df[cols].merge(
        curr_df[cols], on=KEY, how="outer",
        suffixes=("_prev", "_curr"), indicator=True,
    )

    # Descriptive fields: prefer current quarter's, fall back to previous.
    for c in ("issuer", "title", "asset_class"):
        merged[c] = merged[f"{c}_curr"].fillna(merged[f"{c}_prev"])

    sh_prev = merged["shares_prev"].fillna(0.0)
    sh_curr = merged["shares_curr"].fillna(0.0)
    merged["share_change"] = sh_curr - sh_prev
    merged["value_change_usd"] = (
        merged["value_usd_curr"].fillna(0.0) - merged["value_usd_prev"].fillna(0.0)
    )

    rel = np.where(sh_prev > 0, np.abs(merged["share_change"]) / sh_prev, np.inf)

    conditions = [
        merged["_merge"] == "right_only",                       # NEW POSITION
        merged["_merge"] == "left_only",                        # FULL EXIT
        (merged["share_change"] > 0) & (rel > SHARE_TOLERANCE),  # BUY
        (merged["share_change"] < 0) & (rel > SHARE_TOLERANCE),  # SELL
    ]
    labels = ["NEW POSITION", "FULL EXIT", "BUY", "SELL"]
    merged["action"] = np.select(conditions, labels, default="HOLD")

    keep = KEY + ["issuer", "title", "asset_class",
                  "shares_prev", "shares_curr", "share_change",
                  "value_usd_prev", "value_usd_curr", "value_change_usd",
                  "portfolio_weight_prev", "portfolio_weight_curr", "action"]
    return merged[keep]


def build_transactions() -> pd.DataFrame:
    """Notebook 05 entry point: transactions for every consecutive quarter pair."""
    holdings = load_parquet(config.HOLDINGS_PARQUET)

    frames = []
    for prev_q, curr_q in _quarter_pairs(holdings["quarter"].unique().tolist()):
        tx = classify_pair(
            holdings[holdings["quarter"] == prev_q],
            holdings[holdings["quarter"] == curr_q],
        )
        tx.insert(0, "quarter", curr_q)
        tx.insert(1, "prev_quarter", prev_q)
        frames.append(tx)
        log.info("%s vs %s: %s", curr_q, prev_q,
                 tx["action"].value_counts().to_dict())

    transactions = pd.concat(frames, ignore_index=True)
    save_parquet(transactions, config.TRANSACTIONS_PARQUET)
    return transactions
