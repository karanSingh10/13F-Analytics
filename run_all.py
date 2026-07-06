"""
Run all 8 notebooks in sequence from a single Colab cell.

Usage (in Colab, after mounting Drive and cd-ing to project root):

    !python run_all.py

Or to run only specific notebooks:

    !python run_all.py 03 04 05
"""
import subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

requested = sys.argv[1:]  # e.g. ['03', '04']

ALL = [
    "01_download_filings",
    "02_download_xml",
    "03_parse_xml",
    "04_build_holdings",
    "05_transaction_engine",
    "06_portfolio_analysis",
    "07_visualizations",
    "08_storytelling",
]

to_run = [n for n in ALL if (not requested or any(n.startswith(r) for r in requested))]

print(f"Running {len(to_run)} notebook(s) from {BASE}\n")

for nb in to_run:
    nb_path = BASE / "notebooks" / f"{nb}.ipynb"
    print(f"  {nb} ...", end=" ", flush=True)
    result = subprocess.run(
        ["jupyter", "nbconvert", "--to", "notebook", "--execute",
         str(nb_path),
         "--output", str(nb_path),
         "--ExecutePreprocessor.timeout=600"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("done")
    else:
        print("FAILED")
        print(result.stderr[-2000:])
        sys.exit(1)

print("\nAll done. Open any notebook in notebooks/ to see results.")
