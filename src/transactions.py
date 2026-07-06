# transaction engine - figures out what changed between two quarters
# basically doing a full outer join between current and previous quarter holdings
# then labeling each row as buy/sell/new position/full exit/hold
#
# one important thing - we classify on SHARES not dollar value
# because price moves every quarter anyway so value change doesnt tell you
# whether the manager actually did anything

from __future__ import annotations
import numpy as np
import pandas as pd
from . import config
from .utils import load_parquet, log, save_parquet

KEY = ["cusip", "put_call"]
SHARE_TOLERANCE = 0.005  # less than 0.5% share change = probably just rounding


def _quarter_pairs(quarters):
    qs = sorted(quarters)
    return list(zip(qs[:-1], qs[1:]))


def classify_pair(prev_df, curr_df):
    cols = KEY + ["issuer", "title", "asset_class", "shares", "value_usd", "portfolio_weight"]
    merged = prev_df[cols].merge(
        curr_df[cols], on=KEY, how="outer",
        suffixes=("_prev", "_curr"), indicator=True,
    )

    for c in ("issuer", "title", "asset_class"):
        merged[c] = merged[f"{c}_curr"].fillna(merged[f"{c}_prev"])

    sh_prev = merged["shares_prev"].fillna(0.0)
    sh_curr = merged["shares_curr"].fillna(0.0)
    merged["share_change"]     = sh_curr - sh_prev
    merged["value_change_usd"] = merged["value_usd_curr"].fillna(0.0) - merged["value_usd_prev"].fillna(0.0)

    rel = np.where(sh_prev > 0, np.abs(merged["share_change"]) / sh_prev, np.inf)

    conditions = [
        merged["_merge"] == "right_only",
        merged["_merge"] == "left_only",
        (merged["share_change"] > 0) & (rel > SHARE_TOLERANCE),
        (merged["share_change"] < 0) & (rel > SHARE_TOLERANCE),
    ]
    merged["action"] = np.select(conditions, ["NEW POSITION", "FULL EXIT", "BUY", "SELL"], default="HOLD")

    keep = KEY + ["issuer", "title", "asset_class",
                  "shares_prev", "shares_curr", "share_change",
                  "value_usd_prev", "value_usd_curr", "value_change_usd",
                  "portfolio_weight_prev", "portfolio_weight_curr", "action"]
    return merged[keep]


def build_transactions():
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
        log.info("%s vs %s: %s", curr_q, prev_q, tx["action"].value_counts().to_dict())

    transactions = pd.concat(frames, ignore_index=True)
    save_parquet(transactions, config.TRANSACTIONS_PARQUET)
    return transactions
