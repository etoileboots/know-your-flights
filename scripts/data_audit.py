"""
BTS Flight Data — Dataset Audit
Produces a structured profile of the Parquet lake.

Usage:
    python scripts/audit.py

Output:
    Prints audit report to terminal
    Saves docs/data_profile.md
"""

import os
import duckdb
import pandas as pd

LAKE_DIR    = "./data/lake"
OUTPUT_PATH = "./docs/data_profile.md"
GLOB        = f"'{LAKE_DIR}/**/*.parquet'"

os.makedirs("./docs", exist_ok=True)

con = duckdb.connect()

lines = []

def log(text=""):
    print(text)
    lines.append(str(text))


# ── 1. Overview ───────────────────────────────────────────────────────────────
log("# Data profile — BTS On-Time Performance 2018–2025")
log()

total_rows = con.execute(f"SELECT COUNT(*) FROM {GLOB}").fetchone()[0]
log(f"## Overview")
log(f"- Total rows: {total_rows:,}")
log(f"- Total columns: 119")


# ── 2. Coverage ───────────────────────────────────────────────────────────────
log()
log("## Coverage (rows per year/month)")
log()

coverage = con.execute(f"""
    SELECT year, month, COUNT(*) AS rows
    FROM {GLOB}
    GROUP BY year, month
    ORDER BY year, month
""").df()

pivot = coverage.pivot(index="year", columns="month", values="rows").fillna(0).astype(int)
pivot.columns = [f"M{c:02d}" for c in pivot.columns]
log(pivot.to_string())

missing = []
for year in range(2018, 2026):
    for month in range(1, 13):
        if coverage[(coverage.year == year) & (coverage.month == month)].empty:
            missing.append(f"{year}-{month:02d}")

log()
if missing:
    log(f"⚠️  Missing months: {', '.join(missing)}")
else:
    log("✓ All months present for 2018–2025")


# ── 3. Null rates (sampled) ───────────────────────────────────────────────────
log()
log("## Null rates (sampled from 1% of rows)")
log()

schema = con.execute(f"DESCRIBE SELECT * FROM {GLOB} LIMIT 1").df()
col_names = schema["column_name"].tolist()

null_exprs = ", ".join(
    [f"ROUND(100.0 * SUM(CASE WHEN \"{c}\" IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS \"{c}\""
     for c in col_names]
)

null_rates = con.execute(f"""
    SELECT {null_exprs}
    FROM (SELECT * FROM {GLOB} USING SAMPLE 1%)
""").df().T.rename(columns={0: "null_%"}).sort_values("null_%", ascending=False)

high_null = null_rates[null_rates["null_%"] > 50]
low_null  = null_rates[null_rates["null_%"] <= 50]

log("### Columns >50% null (likely drop candidates)")
log(high_null.to_string())
log()
log("### Columns ≤50% null (likely useful)")
log(low_null.to_string())


# ── 4. Key distributions ──────────────────────────────────────────────────────
log()
log("## Key distributions")

log()
log("### Top 15 carriers by flight count")
carriers = con.execute(f"""
    SELECT iata_code_marketing_airline AS carrier, COUNT(*) AS flights
    FROM {GLOB}
    GROUP BY iata_code_marketing_airline
    ORDER BY flights DESC
    LIMIT 15
""").df()
log(carriers.to_string(index=False))

log()
log("### Top 20 origin airports")
airports = con.execute(f"""
    SELECT origin, origincityname AS city, COUNT(*) AS flights
    FROM {GLOB}
    GROUP BY origin, origincityname
    ORDER BY flights DESC
    LIMIT 20
""").df()
log(airports.to_string(index=False))

log()
log("### Departure delay distribution (minutes)")
delay_stats = con.execute(f"""
    SELECT
        ROUND(MIN(depdelay), 1)                                          AS min,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY depdelay), 1) AS p25,
        ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY depdelay), 1) AS median,
        ROUND(AVG(depdelay), 1)                                          AS mean,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY depdelay), 1) AS p75,
        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY depdelay), 1) AS p95,
        ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY depdelay), 1) AS p99,
        ROUND(MAX(depdelay), 1)                                          AS max
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
""").df()
log(delay_stats.to_string(index=False))

log()
log("### Arrival delay distribution (minutes)")
arr_stats = con.execute(f"""
    SELECT
        ROUND(MIN(arrdelay), 1)                                          AS min,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY arrdelay), 1) AS p25,
        ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY arrdelay), 1) AS median,
        ROUND(AVG(arrdelay), 1)                                          AS mean,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY arrdelay), 1) AS p75,
        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY arrdelay), 1) AS p95,
        ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY arrdelay), 1) AS p99,
        ROUND(MAX(arrdelay), 1)                                          AS max
    FROM {GLOB}
    WHERE arrdelay IS NOT NULL
""").df()
log(arr_stats.to_string(index=False))

log()
log("### Cancellation & diversion rates")
cancel = con.execute(f"""
    SELECT
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancelled_pct,
        ROUND(100.0 * SUM(diverted)  / COUNT(*), 2) AS diverted_pct
    FROM {GLOB}
""").df()
log(cancel.to_string(index=False))

log()
log("### Cancellation reasons (code breakdown)")
cancel_codes = con.execute(f"""
    SELECT
        cancellationcode,
        COUNT(*) AS count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM {GLOB}
    WHERE cancelled = 1 AND cancellationcode IS NOT NULL
    GROUP BY cancellationcode
    ORDER BY count DESC
""").df()
log(cancel_codes.to_string(index=False))

log()
log("### Delay cause breakdown (avg minutes, delayed flights only)")
causes = con.execute(f"""
    SELECT
        ROUND(AVG(carrierdelay),      1) AS carrier,
        ROUND(AVG(weatherdelay),      1) AS weather,
        ROUND(AVG(nasdelay),          1) AS nas,
        ROUND(AVG(securitydelay),     1) AS security,
        ROUND(AVG(lateaircraftdelay), 1) AS late_aircraft
    FROM {GLOB}
    WHERE depdelay > 0
""").df()
log(causes.to_string(index=False))

log()
log("### Delay cause — % of delayed flights where each cause is non-zero")
cause_pct = con.execute(f"""
    SELECT
        ROUND(100.0 * SUM(CASE WHEN carrierdelay      > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS carrier_pct,
        ROUND(100.0 * SUM(CASE WHEN weatherdelay      > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS weather_pct,
        ROUND(100.0 * SUM(CASE WHEN nasdelay          > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS nas_pct,
        ROUND(100.0 * SUM(CASE WHEN securitydelay     > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS security_pct,
        ROUND(100.0 * SUM(CASE WHEN lateaircraftdelay > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_aircraft_pct
    FROM {GLOB}
    WHERE depdelay > 0
""").df()
log(cause_pct.to_string(index=False))

log()
log("### Flights by day of week (1=Mon, 7=Sun)")
dow = con.execute(f"""
    SELECT dayofweek, COUNT(*) AS flights,
           ROUND(AVG(depdelay), 2) AS avg_dep_delay
    FROM {GLOB}
    GROUP BY dayofweek
    ORDER BY dayofweek
""").df()
log(dow.to_string(index=False))

log()
log("### Flights by quarter")
quarter = con.execute(f"""
    SELECT quarter, COUNT(*) AS flights,
           ROUND(AVG(depdelay), 2) AS avg_dep_delay
    FROM {GLOB}
    GROUP BY quarter
    ORDER BY quarter
""").df()
log(quarter.to_string(index=False))


# ── 5. Anomaly checks ─────────────────────────────────────────────────────────
log()
log("## Anomaly checks")

neg = con.execute(f"""
    SELECT COUNT(*) FROM {GLOB} WHERE depdelay < -30
""").fetchone()[0]
log(f"- Flights departing >30 min early: {neg:,}")

extreme = con.execute(f"""
    SELECT COUNT(*) FROM {GLOB} WHERE depdelay > 500
""").fetchone()[0]
log(f"- Flights with departure delay >500 min: {extreme:,}")

log()
log("### Top 10 most extreme delays")
worst = con.execute(f"""
    SELECT flightdate, iata_code_marketing_airline AS carrier,
           origin, dest, depdelay, arrdelay, cancellationcode
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    ORDER BY depdelay DESC
    LIMIT 10
""").df()
log(worst.to_string(index=False))

log()
log("### Duplicate check (same date, carrier, origin, dest, flight number)")
dupes = con.execute(f"""
    SELECT year, month, dayofmonth,
           iata_code_marketing_airline,
           flight_number_marketing_airline,
           origin, dest,
           COUNT(*) AS n
    FROM {GLOB}
    GROUP BY ALL
    HAVING COUNT(*) > 1
    LIMIT 5
""").df()
if dupes.empty:
    log("✓ No duplicates found")
else:
    log(f"⚠️  Potential duplicates:")
    log(dupes.to_string(index=False))


# ── 6. Save markdown ──────────────────────────────────────────────────────────
with open(OUTPUT_PATH, "w") as f:
    f.write("\n".join(lines))

print()
print(f"✅ Audit complete — report saved to {OUTPUT_PATH}")