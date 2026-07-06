"""
Module 6 -- Institutional analytics.

Per-quarter portfolio metrics plus the "league tables" institutional
research desks publish: largest holdings / buys / sells / new positions /
exits, turnover, concentration (top-5/top-10, HHI), position-size stats.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .utils import load_parquet, save_parquet


# ---------------------------------------------------------------------------
# Portfolio-level summary (one row per quarter)
# ---------------------------------------------------------------------------
def portfolio_summary(holdings: pd.DataFrame | None = None,
                      transactions: pd.DataFrame | None = None) -> pd.DataFrame:
    if holdings is None:
        holdings = load_parquet(config.HOLDINGS_PARQUET)
    if transactions is None:
        transactions = load_parquet(config.TRANSACTIONS_PARQUET)

    rows = []
    for q, grp in holdings.groupby("quarter"):
        w = grp.sort_values("value_usd", ascending=False)["portfolio_weight"]
        rows.append({
            "quarter": q,
            "report_date": grp["report_date"].iloc[0],
            "portfolio_value_usd": grp["value_usd"].sum(),
            "n_positions": len(grp),
            "top5_weight": w.head(5).sum(),
            "top10_weight": w.head(10).sum(),
            "hhi": (w ** 2).sum(),                     # Herfindahl-Hirschman
            "avg_position_usd": grp["value_usd"].mean(),
            "median_position_usd": grp["value_usd"].median(),
            "largest_holding": grp.loc[grp["value_usd"].idxmax(), "issuer"],
            "largest_holding_weight": w.iloc[0],
        })
    summary = pd.DataFrame(rows).sort_values("report_date").reset_index(drop=True)

    summary = summary.merge(quarterly_turnover(transactions), on="quarter", how="left")
    save_parquet(summary, config.PORTFOLIO_PARQUET)
    return summary


def quarterly_turnover(transactions: pd.DataFrame) -> pd.DataFrame:
    """Turnover = min(buys, sells) / average portfolio value, per quarter.

    The min() convention counts round-trip trading only, so pure inflows or
    outflows don't inflate turnover.
    """
    rows = []
    for q, grp in transactions.groupby("quarter"):
        buys = grp.loc[grp["action"].isin(["BUY", "NEW POSITION"]),
                       "value_change_usd"].clip(lower=0).sum()
        sells = -grp.loc[grp["action"].isin(["SELL", "FULL EXIT"]),
                         "value_change_usd"].clip(upper=0).sum()
        avg_value = (grp["value_usd_prev"].fillna(0).sum()
                     + grp["value_usd_curr"].fillna(0).sum()) / 2
        rows.append({
            "quarter": q,
            "gross_buys_usd": buys,
            "gross_sells_usd": sells,
            "turnover": min(buys, sells) / avg_value if avg_value else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# League tables for one quarter
# ---------------------------------------------------------------------------
def largest_holdings(holdings: pd.DataFrame, quarter: str, n: int = 10) -> pd.DataFrame:
    q = holdings[holdings["quarter"] == quarter]
    return (q.sort_values("value_usd", ascending=False)
             .head(n)[["issuer", "asset_class", "value_usd", "portfolio_weight"]]
             .reset_index(drop=True))


def _tx_table(transactions: pd.DataFrame, quarter: str, actions: list[str],
              ascending: bool, n: int) -> pd.DataFrame:
    q = transactions[(transactions["quarter"] == quarter)
                     & (transactions["action"].isin(actions))]
    cols = ["issuer", "action", "share_change", "value_change_usd",
            "value_usd_prev", "value_usd_curr"]
    return (q.sort_values("value_change_usd", ascending=ascending)
             .head(n)[cols].reset_index(drop=True))


def largest_buys(tx, quarter, n=10):
    return _tx_table(tx, quarter, ["BUY", "NEW POSITION"], ascending=False, n=n)


def largest_sells(tx, quarter, n=10):
    return _tx_table(tx, quarter, ["SELL", "FULL EXIT"], ascending=True, n=n)


def new_positions(tx, quarter, n=10):
    return _tx_table(tx, quarter, ["NEW POSITION"], ascending=False, n=n)


def full_exits(tx, quarter, n=10):
    return _tx_table(tx, quarter, ["FULL EXIT"], ascending=True, n=n)


def asset_allocation(holdings: pd.DataFrame, quarter: str) -> pd.DataFrame:
    q = holdings[holdings["quarter"] == quarter]
    alloc = (q.groupby("asset_class")["value_usd"].sum()
              .sort_values(ascending=False).reset_index())
    alloc["weight"] = alloc["value_usd"] / alloc["value_usd"].sum()
    return alloc
