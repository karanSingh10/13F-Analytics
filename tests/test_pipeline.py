"""End-to-end pipeline test on synthetic (but realistic) 13F XML.

Covers the historical failure modes:
- namespaced XML with ns1: prefix
- duplicate CUSIP rows (split voting authority) -> must aggregate
- put/call options -> must classify + key separately from the stock
- value-units regime (pre-2023 thousands vs post-2023 dollars)
- new position / full exit / buy / sell classification
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import analytics, assets, charts, commentary, config, parser, transactions

NS = 'xmlns:ns1="http://www.sec.gov/edgar/document/thirteenf/informationtable"'


def info_table_xml(rows):
    body = ""
    for r in rows:
        pc = f"<ns1:putCall>{r['pc']}</ns1:putCall>" if r.get("pc") else ""
        body += f"""
  <ns1:infoTable>
    <ns1:nameOfIssuer>{r['issuer']}</ns1:nameOfIssuer>
    <ns1:titleOfClass>{r['title']}</ns1:titleOfClass>
    <ns1:cusip>{r['cusip']}</ns1:cusip>
    <ns1:value>{r['value']}</ns1:value>
    <ns1:shrsOrPrnAmt>
      <ns1:sshPrnamt>{r['shares']}</ns1:sshPrnamt>
      <ns1:sshPrnamtType>SH</ns1:sshPrnamtType>
    </ns1:shrsOrPrnAmt>
    {pc}
    <ns1:investmentDiscretion>DFND</ns1:investmentDiscretion>
    <ns1:otherManager>{r.get('mgr', 4)}</ns1:otherManager>
    <ns1:votingAuthority>
      <ns1:Sole>{r['shares']}</ns1:Sole>
      <ns1:Shared>0</ns1:Shared>
      <ns1:None>0</ns1:None>
    </ns1:votingAuthority>
  </ns1:infoTable>"""
    return f'<ns1:informationTable {NS}>{body}\n</ns1:informationTable>'


# Q1 (values in whole dollars, post-2023 regime)
q1 = info_table_xml([
    # Apple split across two managers -> the classic duplicate
    dict(issuer="APPLE INC", title="COM", cusip="037833100", value=100_000_000_000, shares=500_000_000, mgr=4),
    dict(issuer="APPLE INC", title="COM", cusip="037833100", value=50_000_000_000, shares=250_000_000, mgr=8),
    dict(issuer="CHEVRON CORP", title="COM", cusip="166764100", value=20_000_000_000, shares=120_000_000),
    dict(issuer="OCCIDENTAL PETE", title="COM", cusip="674599105", value=15_000_000_000, shares=240_000_000),
    dict(issuer="KRAFT HEINZ CO", title="COM", cusip="500754106", value=11_000_000_000, shares=325_000_000),
    dict(issuer="BANK AMER CORP", title="COM", cusip="060505104", value=30_000_000_000, shares=1_000_000_000),
])

# Q2: buy CVX, trim OXY, exit KHC, new position AMZN, Apple unchanged, add a put
q2 = info_table_xml([
    dict(issuer="APPLE INC", title="COM", cusip="037833100", value=160_000_000_000, shares=750_000_000),
    dict(issuer="CHEVRON CORP", title="COM", cusip="166764100", value=26_000_000_000, shares=150_000_000),
    dict(issuer="OCCIDENTAL PETE", title="COM", cusip="674599105", value=10_000_000_000, shares=160_000_000),
    dict(issuer="BANK AMER CORP", title="COM", cusip="060505104", value=31_000_000_000, shares=1_000_000_000),
    dict(issuer="AMAZON COM INC", title="COM", cusip="023135106", value=5_000_000_000, shares=28_000_000),
    dict(issuer="SPDR S&amp;amp;P 500", title="ETF TRUST UNIT", cusip="78462F103", value=1_000_000_000, shares=2_000_000, pc="Put"),
])

# ---------------------------------------------------------------------------
# 1. parser: namespace handling + row counts
df1 = parser.parse_info_table(q1)
assert len(df1) == 6, f"expected 6 raw rows, got {len(df1)}"
assert df1["cusip"].notna().all()

# value regime: pre-2023 report must be multiplied by 1000
old = parser.normalize_value_units(df1, pd.Timestamp("2022-09-30"))
new = parser.normalize_value_units(df1, pd.Timestamp("2026-03-31"))
assert (old["value_usd"] == new["value_usd"] * 1000).all()
print("parser OK (namespaces, units regime)")

# ---------------------------------------------------------------------------
# 2. build fake filings + raw holdings on disk, then clean
(config.RAW_XML_DIR / "2026Q1_test.xml").write_text(q1)
(config.RAW_XML_DIR / "2026Q2_test.xml").write_text(q2)
filings = pd.DataFrame([
    dict(accessionNumber="0000000000-26-000001", form="13F-HR",
         filingDate=pd.Timestamp("2026-05-15"), reportDate=pd.Timestamp("2026-03-31"),
         quarter="2026Q1", primaryDocument="primary_doc.xml",
         xml_file="infotable.xml", xml_url="test",
         local_xml_path=str(config.RAW_XML_DIR / "2026Q1_test.xml")),
    dict(accessionNumber="0000000000-26-000002", form="13F-HR",
         filingDate=pd.Timestamp("2026-08-14"), reportDate=pd.Timestamp("2026-06-30"),
         quarter="2026Q2", primaryDocument="primary_doc.xml",
         xml_file="infotable.xml", xml_url="test",
         local_xml_path=str(config.RAW_XML_DIR / "2026Q2_test.xml")),
])
filings.to_parquet(config.FILINGS_PARQUET, index=False)

raw = parser.build_raw_holdings()
clean = assets.clean_holdings()

q1c = clean[clean["quarter"] == "2026Q1"]
apple = q1c[q1c["cusip"] == "037833100"]
assert len(apple) == 1, "Apple duplicate rows not aggregated!"
assert apple["shares"].iloc[0] == 750_000_000
assert apple["n_rows"].iloc[0] == 2
assert abs(q1c["portfolio_weight"].sum() - 1) < 1e-9

put = clean[clean["put_call"] == "Put"]
assert put["asset_class"].iloc[0] == "Put Option"
etf_free = clean[clean["issuer"] == "AMAZON COM INC"]["asset_class"].iloc[0]
assert etf_free == "Common Stock"
print("cleaning OK (dedupe, weights, classification)")

# ---------------------------------------------------------------------------
# 3. transaction engine
tx = transactions.build_transactions()
q2tx = tx[tx["quarter"] == "2026Q2"].set_index("issuer")
assert q2tx.loc["CHEVRON CORP", "action"] == "BUY"
assert q2tx.loc["OCCIDENTAL PETE", "action"] == "SELL"
assert q2tx.loc["KRAFT HEINZ CO", "action"] == "FULL EXIT"
assert q2tx.loc["AMAZON COM INC", "action"] == "NEW POSITION"
assert q2tx.loc["BANK AMER CORP", "action"] == "HOLD"      # value moved, shares didn't
assert q2tx.loc["APPLE INC", "action"] == "HOLD"
print("transaction engine OK (buy/sell/new/exit/hold)")

# ---------------------------------------------------------------------------
# 4. analytics + commentary + charts
summary = analytics.portfolio_summary(clean, tx)
assert summary["hhi"].between(0, 1).all()
assert analytics.largest_holdings(clean, "2026Q2").iloc[0]["issuer"] == "APPLE INC"

text = commentary.quarterly_commentary("2026Q2", clean, tx, summary)
assert "APPLE INC" in text and "CHEVRON" in text.upper()
print("\n--- sample commentary ---\n" + text + "\n-------------------------\n")

import matplotlib
matplotlib.use("Agg")
charts.plot_portfolio_value(summary)
charts.plot_top_holdings(analytics.largest_holdings(clean, "2026Q2"), "2026Q2")
charts.plot_buys_sells(tx, "2026Q2")
charts.plot_concentration(summary)
charts.plot_asset_allocation(analytics.asset_allocation(clean, "2026Q2"), "2026Q2")
charts.plot_turnover(summary)
print("charts OK ->", sorted(p.name for p in config.FIGURES_DIR.glob('*.png')))

print("\nALL PIPELINE TESTS PASSED")
