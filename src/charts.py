
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
from src import config

PALETTE = {
    "primary":  "#1f3b57",
    "positive": "#2e7d5b",
    "negative": "#a63a3a",
    "accent":   "#c8a45d",
    "grid":     "#d9d9d9",
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

def _finish(fig, ax, title, save_as):
    ax.set_title(title, fontsize=12, loc="left", pad=10)
    fig.text(0.01, 0.01, f"source: SEC EDGAR 13F | {config.MANAGER_NAME}", fontsize=7, color="gray")
    fig.tight_layout()
    if save_as:
        fig.savefig(config.FIGURES_DIR / save_as, bbox_inches="tight")
    plt.show()
    plt.close(fig)

def plot_portfolio_value(summary, save_as="portfolio_value.png"):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(summary["quarter"], summary["portfolio_value_usd"], marker="o", color=PALETTE["primary"], linewidth=2)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_billions))
    ax.set_xlabel("quarter")
    _finish(fig, ax, "portfolio value over time", save_as)

def plot_top_holdings(holdings_table, quarter, save_as="top_holdings.png"):
    df = holdings_table.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(df["issuer"], df["portfolio_weight"] * 100, color=PALETTE["primary"])
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    for y, v in enumerate(df["portfolio_weight"] * 100):
        ax.text(v + 0.3, y, f"{v:.1f}%", va="center", fontsize=8)
    _finish(fig, ax, f"top holdings - {quarter}", save_as)

def plot_buys_sells(tx, quarter, n=8, save_as="buys_sells.png"):
    q = tx[tx["quarter"] == quarter]
    moves = (q[q["action"] != "HOLD"]
             .assign(mag=lambda d: d["value_change_usd"].abs())
             .sort_values("mag", ascending=False).head(n)
             .sort_values("value_change_usd"))
    colors = [PALETTE["positive"] if v > 0 else PALETTE["negative"] for v in moves["value_change_usd"]]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(moves["issuer"], moves["value_change_usd"] / 1e9, color=colors)
    ax.set_xlabel("change in position value ($B)")
    ax.axvline(0, color="black", linewidth=0.8)
    _finish(fig, ax, f"biggest position changes - {quarter}", save_as)

def plot_concentration(summary, save_as="concentration.png"):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(summary["quarter"], summary["top5_weight"] * 100, marker="o", label="top 5", color=PALETTE["primary"])
    ax.plot(summary["quarter"], summary["top10_weight"] * 100, marker="s", label="top 10", color=PALETTE["accent"])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlabel("quarter")
    ax.legend(frameon=False)
    _finish(fig, ax, "portfolio concentration over time", save_as)

def plot_asset_allocation(alloc, quarter, save_as="asset_allocation.png"):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(alloc["asset_class"][::-1], alloc["weight"][::-1] * 100, color=PALETTE["primary"])
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    _finish(fig, ax, f"asset allocation - {quarter}", save_as)

def plot_turnover(summary, save_as="turnover.png"):
    df = summary.dropna(subset=["turnover"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(df["quarter"], df["turnover"] * 100, color=PALETTE["accent"])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlabel("quarter")
    _finish(fig, ax, "quarterly portfolio turnover", save_as)
