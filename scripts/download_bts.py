"""
BTS On-Time Flight Performance Downloader
Downloads 2018-2025 data from transtats.bts.gov
Stores as partitioned Parquet files, cleans up ZIPs year by year.

Usage:
    python download.py

Output:
    ./data/lake/year=YYYY/month=MM/*.parquet
"""

import urllib.request
import os
import zipfile
import glob
import shutil
import uuid
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
TEMP_DIR  = "./data/temp_zips"
LAKE_DIR  = "./data/lake"

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(LAKE_DIR, exist_ok=True)

# All columns kept — no filtering applied

# ── URL patterns ─────────────────────────────────────────────────────────────
# 2018+ uses the Marketing Carrier dataset (different filename prefix)
BASE_URL = "https://transtats.bts.gov/PREZIP"

def build_url(year: int, month: int) -> str:
    fname = (
        f"On_Time_Marketing_Carrier_On_Time_Performance_"
        f"Beginning_January_2018_{year}_{month}.zip"
    )
    return f"{BASE_URL}/{fname}", fname


# ── Download one month ────────────────────────────────────────────────────────
def download_month(year: int, month: int) -> str | None:
    url, fname = build_url(year, month)
    dest = os.path.join(TEMP_DIR, f"{year}_{month:02d}.zip")

    if os.path.exists(dest):
        print(f"  ↳ {year}-{month:02d} already downloaded, skipping.")
        return dest

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            f.write(r.read())
        size_mb = os.path.getsize(dest) / 1_000_000
        print(f"  ✓ {year}-{month:02d}  ({size_mb:.1f} MB)")
        return dest
    except Exception as e:
        print(f"  ✗ {year}-{month:02d}  skipped — {e}")
        return None


# ── Convert one ZIP → Parquet ─────────────────────────────────────────────────
def zip_to_parquet(zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_files = [f for f in z.namelist() if f.endswith(".csv")]
        if not csv_files:
            print(f"    ! No CSV found in {zip_path}")
            return

        with z.open(csv_files[0]) as f:
            for chunk in pd.read_csv(f, chunksize=200_000, low_memory=False, encoding="latin-1"):
                # Normalize column names
                chunk.columns = [c.lower().strip() for c in chunk.columns]

                # Drop unnamed index columns BTS sometimes appends
                chunk = chunk.loc[:, ~chunk.columns.str.startswith("unnamed")]

                # Ensure year/month exist for partitioning
                if "year" not in chunk.columns or "month" not in chunk.columns:
                    print("    ! year/month columns missing — skipping chunk")
                    continue

                chunk["year"]  = chunk["year"].astype(int)
                chunk["month"] = chunk["month"].astype(int)

                chunk.to_parquet(
                    LAKE_DIR,
                    partition_cols=["year", "month"],
                    engine="pyarrow",
                    index=False,
                    basename_template=f"part-{{i}}-{uuid.uuid4()}.parquet",
                    existing_data_behavior="overwrite_or_ignore",
                )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    years  = range(2019, 2026)   # 2018 through 2025 inclusive
    months = range(1, 13)

    total_months = len(years) * len(months)
    done = 0

    for year in years:
        print(f"\n{'─'*50}")
        print(f"  Year {year}")
        print(f"{'─'*50}")

        # 1. Download all months for this year
        for month in months:
            download_month(year, month)
            done += 1
            print(f"  Progress: {done}/{total_months} months")

        # 2. Convert this year's ZIPs to Parquet
        print(f"\n  Converting {year} ZIPs → Parquet...")
        for zip_path in sorted(glob.glob(os.path.join(TEMP_DIR, "*.zip"))):
            print(f"    {os.path.basename(zip_path)}")
            zip_to_parquet(zip_path)

        # 3. Delete ZIPs to reclaim disk space before next year
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)
        print(f"  🧹 Cleaned up {year} ZIPs.")

    # Final cleanup
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

    print("\n✅ Done. Parquet lake written to ./data/lake/")
    print("   Query with: duckdb.query(\"SELECT * FROM './data/lake/**/*.parquet'\")")


if __name__ == "__main__":
    main()