"""
Module 7 -- Professional charts.

A small matplotlib chart library with a consistent, research-report look:
muted palette, no chartjunk, dollar formatting, source footnote. Every
function returns the Figure and optionally saves a PNG to reports/figures.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

from . import config

PALETTE = {
    "primary": "#1f3b57",   # deep navy
    "positive": "#2e7d5b",  # green
    "negative": "#a63a3a",  # red
    "accent": "#c8a45d",    # gold
    "grid": "#d9d9d9",
}

plt.rcParams.update({
    "figure.dpi": 110,
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": PALETTE["grid"],
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
})


def _billions(x, _pos=None):
    return f"${x/1e9:,.0f}B"


def _finish(fig, ax, title: str, subtitle: str, save_as: str | None):
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=14)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color="gray")
    fig.text(0.01, 0.01, f"Source: SEC EDGAR 13F filings | {config.MANAGER_NAME}",
             fontsize=7, color="gray")
    fig.tight_layout()
    if save_as:
        path = config.FIGURES_DIR / save_as
        fig.savefig(path, bbox_inches="tight")
    return fig


def plot_portfolio_value(summary: pd.DataFrame, save_as="portfolio_value.png"):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(summary["quarter"], summary["portfolio_value_usd"],
            marker="o", color=PALETTE["primary"], linewidth=2)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_billions))
    return _finish(fig, ax, "Reported 13F Portfolio Value",
                   "Long U.S.-listed equity positions, quarterly", save_as)


def plot_top_holdings(holdings_table: pd.DataFrame, quarter: str,
                      save_as="top_holdings.png"):
    df = holdings_table.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(df["issuer"], df["portfolio_weight"] * 100, color=PALETTE["primary"])
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    for y, v in enumerate(df["portfolio_weight"] * 100):
        ax.text(v + 0.3, y, f"{v:.1f}%", va="center", fontsize=8)
    return _finish(fig, ax, f"Largest Holdings — {quarter}",
                   "Percent of reported 13F assets", save_as)


def plot_buys_sells(tx: pd.DataFrame, quarter: str, n: int = 8,
                    save_as="buys_sells.png"):
    q = tx[tx["quarter"] == quarter]
    moves = (q[q["action"] != "HOLD"]
             .assign(mag=lambda d: d["value_change_usd"].abs())
             .sort_values("mag", ascending=False).head(n)
             .sort_values("value_change_usd"))
    colors = [PALETTE["positive"] if v > 0 else PALETTE["negative"]
              for v in moves["value_change_usd"]]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(moves["issuer"], moves["value_change_usd"] / 1e9, color=colors)
    ax.set_xlabel("Change in position value ($B)")
    ax.axvline(0, color="black", linewidth=0.8)
    return _finish(fig, ax, f"Largest Position Changes — {quarter}",
                   "Quarter-over-quarter change in reported value", save_as)


def plot_concentration(summary: pd.DataFrame, save_as="concentration.png"):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(summary["quarter"], summary["top5_weight"] * 100,
            marker="o", label="Top 5", color=PALETTE["primary"])
    ax.plot(summary["quarter"], summary["top10_weight"] * 100,
            marker="s", label="Top 10", color=PALETTE["accent"])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.legend(frameon=False)
    return _finish(fig, ax, "Portfolio Concentration",
                   "Share of assets in largest positions", save_as)


def plot_asset_allocation(alloc: pd.DataFrame, quarter: str,
                          save_as="asset_allocation.png"):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(alloc["asset_class"][::-1], alloc["weight"][::-1] * 100,
            color=PALETTE["primary"])
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    return _finish(fig, ax, f"Asset Allocation — {quarter}",
                   "By reported security type", save_as)


def plot_turnover(summary: pd.DataFrame, save_as="turnover.png"):
    df = summary.dropna(subset=["turnover"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(df["quarter"], df["turnover"] * 100, color=PALETTE["accent"])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    return _finish(fig, ax, "Quarterly Portfolio Turnover",
                   "min(buys, sells) / average portfolio value", save_as)
