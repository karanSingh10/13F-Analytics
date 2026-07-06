"""
Module 8 -- Automated commentary.

Turns the metrics into a short, research-note-style narrative, e.g.:

    Berkshire Hathaway reported $312B of U.S.-listed holdings for 2026Q1,
    up 3.4% from the prior quarter. Apple Inc remained the largest holding
    at 24.8% of assets. The firm added to Chevron Corp (+$1.2B) and opened
    a new position in ...

Every sentence is generated from the data -- nothing is hardcoded.
"""
from __future__ import annotations

import pandas as pd

from . import analytics, config


def _fmt_usd(x: float) -> str:
    if abs(x) >= 1e9:
        return f"${x/1e9:,.1f}B"
    if abs(x) >= 1e6:
        return f"${x/1e6:,.0f}M"
    return f"${x:,.0f}"


def quarterly_commentary(quarter: str,
                         holdings: pd.DataFrame,
                         transactions: pd.DataFrame,
                         summary: pd.DataFrame) -> str:
    parts: list[str] = []
    s = summary.set_index("quarter")
    if quarter not in s.index:
        raise ValueError(f"{quarter} not in summary")
    row = s.loc[quarter]

    # 1. Headline: portfolio value and QoQ change
    qs = list(s.index)
    idx = qs.index(quarter)
    if idx > 0:
        prev = s.iloc[idx - 1]
        chg = row["portfolio_value_usd"] / prev["portfolio_value_usd"] - 1
        direction = "up" if chg >= 0 else "down"
        parts.append(
            f"{config.MANAGER_NAME} reported {_fmt_usd(row['portfolio_value_usd'])} "
            f"of U.S.-listed holdings for {quarter}, {direction} {abs(chg):.1%} "
            f"from the prior quarter across {int(row['n_positions'])} positions."
        )
    else:
        parts.append(
            f"{config.MANAGER_NAME} reported {_fmt_usd(row['portfolio_value_usd'])} "
            f"of U.S.-listed holdings for {quarter} across "
            f"{int(row['n_positions'])} positions."
        )

    # 2. Largest holding
    parts.append(
        f"{row['largest_holding']} remained the largest holding, representing "
        f"{row['largest_holding_weight']:.1%} of reported assets; the top five "
        f"positions accounted for {row['top5_weight']:.1%}."
    )

    # 3. Biggest buy / sell
    buys = analytics.largest_buys(transactions, quarter, n=1)
    if not buys.empty and buys.loc[0, "value_change_usd"] > 0:
        b = buys.loc[0]
        verb = ("initiated a new position in" if b["action"] == "NEW POSITION"
                else "added to")
        parts.append(f"The firm {verb} {b['issuer']} "
                     f"({_fmt_usd(b['value_change_usd'])}).")

    sells = analytics.largest_sells(transactions, quarter, n=1)
    if not sells.empty and sells.loc[0, "value_change_usd"] < 0:
        srow = sells.loc[0]
        verb = ("fully exited" if srow["action"] == "FULL EXIT" else "trimmed")
        parts.append(f"It {verb} {srow['issuer']} "
                     f"({_fmt_usd(srow['value_change_usd'])}).")

    # 4. Turnover trend
    if pd.notna(row.get("turnover")) and idx > 0 and pd.notna(s.iloc[idx - 1].get("turnover")):
        t_now, t_prev = row["turnover"], s.iloc[idx - 1]["turnover"]
        trend = ("declined" if t_now < t_prev
                 else "increased" if t_now > t_prev else "was unchanged")
        parts.append(f"Portfolio turnover {trend} compared with the previous "
                     f"quarter ({t_now:.1%} vs {t_prev:.1%}).")

    return " ".join(parts)


def full_report(holdings, transactions, summary) -> str:
    """Markdown report covering every quarter with transactions."""
    lines = [f"# {config.MANAGER_NAME} — 13F Portfolio Review", ""]
    for q in summary["quarter"].tolist()[1:]:  # first quarter has no prior
        lines += [f"## {q}", "", quarterly_commentary(
            q, holdings, transactions, summary), ""]
    lines += ["---",
              "*Generated automatically from SEC EDGAR 13F filings. 13F data "
              "covers long U.S.-listed positions only and is reported with a "
              "~45-day lag; it excludes shorts, cash, and most non-U.S. "
              "holdings.*"]
    return "\n".join(lines)
