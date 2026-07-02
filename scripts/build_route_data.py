"""
Route aggregation builder for search.html
==========================================
Produces one JSON file per route: data/aggregations/routes/{ORIG}-{DEST}.json

Run:
    python3 scripts/build_route_data.py          # top 300 routes
    python3 scripts/build_route_data.py JFK LAX  # single route

Each JSON has exactly the shape search.html expects:
  route      — metadata (flight count, year range, carriers operating)
  accuracy   — dep & arr breakdown into perfect / standard / disruptive
  heatmap    — 7 rows (Mon–Sun) × 4 cols (Morning/Midday/Afternoon/Night)
               values are % of flights delayed ≥15 min
  carriers   — ranked list with vol, avg dep/arr delay, cancel rate
  annual     — year-by-year arr_delay baseline + per-carrier tracks
"""

import os, sys, json, time
import duckdb

LAKE   = os.path.join(os.path.dirname(__file__), "..", "data", "lake")
OUTDIR = os.path.join(os.path.dirname(__file__), "..", "data", "aggregations", "routes")
GLOB   = f"'{LAKE}/**/*.parquet'"

os.makedirs(OUTDIR, exist_ok=True)
con = duckdb.connect()

CARRIER_NAMES = {
    "AA": "American Airlines", "DL": "Delta Air Lines",
    "UA": "United Airlines",   "WN": "Southwest Airlines",
    "B6": "JetBlue Airways",   "AS": "Alaska Airlines",
    "NK": "Spirit Airlines",   "F9": "Frontier Airlines",
    "G4": "Allegiant Air",     "HA": "Hawaiian Airlines",
    "MQ": "Envoy Air",         "OO": "SkyWest Airlines",
    "YX": "Republic Airways",  "9E": "Endeavor Air",
    "EV": "ExpressJet",        "VX": "Virgin America",
    "FL": "AirTran Airways",
}

TIME_BLOCKS = [
    ("Morning",   600, 1000),
    ("Midday",   1000, 1500),
    ("Afternoon",1500, 1900),
    ("Night",    1900, 2300),
]

DAYS = [1, 2, 3, 4, 5, 6, 7]  # BTS: 1=Mon … 7=Sun


def write(path, data):
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"), allow_nan=False)
    kb = os.path.getsize(path) / 1024
    print(f"  ✓ {os.path.basename(path)}  ({kb:.1f} KB)")


def build_route(orig, dest):
    slug = f"{orig}-{dest}"
    out_path = os.path.join(OUTDIR, f"{slug}.json")

    # ── Route metadata ──────────────────────────────────────
    meta = con.execute(f"""
        SELECT
            COUNT(*) AS total_flights,
            MIN(year) AS year_min, MAX(year) AS year_max,
            COUNT(DISTINCT year) AS year_count
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND cancelled=0
    """).df().iloc[0]

    total = int(meta["total_flights"])
    if total == 0:
        return False
    year_min = int(meta["year_min"])
    year_max = int(meta["year_max"])

    # ── Accuracy: dep & arr breakdown ───────────────────────
    acc = con.execute(f"""
        SELECT
            -- Departure
            ROUND(100.0 * SUM(CASE WHEN depdelay <= 5  THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_perfect,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 5 AND depdelay <= 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_standard,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_disruptive,
            -- Arrival
            ROUND(100.0 * SUM(CASE WHEN arrdelay <= 5  THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_perfect,
            ROUND(100.0 * SUM(CASE WHEN arrdelay > 5 AND arrdelay <= 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_standard,
            ROUND(100.0 * SUM(CASE WHEN arrdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_disruptive,
            ROUND(AVG(depdelay), 1) AS mean_dep_delay,
            ROUND(AVG(arrdelay), 1) AS mean_arr_delay
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND arrdelay IS NOT NULL AND cancelled=0
    """).df().iloc[0]

    accuracy = {
        "dep": {
            "perfect":    float(acc["dep_perfect"]),
            "standard":   float(acc["dep_standard"]),
            "disruptive": float(acc["dep_disruptive"]),
        },
        "arr": {
            "perfect":    float(acc["arr_perfect"]),
            "standard":   float(acc["arr_standard"]),
            "disruptive": float(acc["arr_disruptive"]),
        },
        "mean_dep_delay": float(acc["mean_dep_delay"]),
        "mean_arr_delay": float(acc["mean_arr_delay"]),
    }

    # ── Per-year accuracy breakdown ──────────────────────────────
    acc_yr_df = con.execute(f"""
        SELECT year,
            ROUND(100.0 * SUM(CASE WHEN depdelay <= 5  THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_perfect,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 5 AND depdelay <= 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_standard,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_disruptive,
            ROUND(100.0 * SUM(CASE WHEN arrdelay <= 5  THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_perfect,
            ROUND(100.0 * SUM(CASE WHEN arrdelay > 5 AND arrdelay <= 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_standard,
            ROUND(100.0 * SUM(CASE WHEN arrdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_disruptive
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND arrdelay IS NOT NULL AND cancelled=0
        GROUP BY year HAVING COUNT(*) >= 50
        ORDER BY year
    """).df()
    accuracy_by_year = {
        str(int(r["year"])): {
            "dep": {"perfect": float(r["dep_perfect"]), "standard": float(r["dep_standard"]), "disruptive": float(r["dep_disruptive"])},
            "arr": {"perfect": float(r["arr_perfect"]), "standard": float(r["arr_standard"]), "disruptive": float(r["arr_disruptive"])},
        }
        for _, r in acc_yr_df.iterrows()
    }

    # ── Heatmap: 7 days × 4 time blocks (dep + arr), also 12 months × 7 × 4 ──
    heatmap_raw = con.execute(f"""
        SELECT month, dayofweek,
               crsdeptime,
               CASE WHEN depdelay > 15 THEN 1 ELSE 0 END AS dep_late,
               CASE WHEN arrdelay > 15 THEN 1 ELSE 0 END AS arr_late
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND arrdelay IS NOT NULL AND cancelled=0
          AND crsdeptime IS NOT NULL
    """).df()

    heatmap = []
    arr_heatmap = []
    for dow in DAYS:
        row_df = heatmap_raw[heatmap_raw["dayofweek"] == dow]
        dep_row = []
        arr_row = []
        for _, lo, hi in TIME_BLOCKS:
            slot = row_df[(row_df["crsdeptime"] >= lo) & (row_df["crsdeptime"] < hi)]
            if len(slot) >= 10:
                dep_row.append(round(float(slot["dep_late"].mean() * 100), 1))
                arr_row.append(round(float(slot["arr_late"].mean() * 100), 1))
            else:
                dep_row.append(None)
                arr_row.append(None)
        heatmap.append(dep_row)
        arr_heatmap.append(arr_row)

    # 12 × 7 × 4  (month → DOW → time slot)
    monthly_heatmap = []
    arr_monthly_heatmap = []
    for mo in range(1, 13):
        mo_df = heatmap_raw[heatmap_raw["month"] == mo]
        dep_month = []
        arr_month = []
        for dow in DAYS:
            dow_df = mo_df[mo_df["dayofweek"] == dow]
            dep_row = []
            arr_row = []
            for _, lo, hi in TIME_BLOCKS:
                slot = dow_df[(dow_df["crsdeptime"] >= lo) & (dow_df["crsdeptime"] < hi)]
                if len(slot) >= 10:
                    dep_row.append(round(float(slot["dep_late"].mean() * 100), 1))
                    arr_row.append(round(float(slot["arr_late"].mean() * 100), 1))
                else:
                    dep_row.append(None)
                    arr_row.append(None)
            dep_month.append(dep_row)
            arr_month.append(arr_row)
        monthly_heatmap.append(dep_month)
        arr_monthly_heatmap.append(arr_month)

    # ── Carriers ────────────────────────────────────────────
    carriers_df = con.execute(f"""
        SELECT
            iata_code_marketing_airline AS code,
            COUNT(*) AS vol,
            ROUND(AVG(depdelay), 1) AS dep_delay,
            ROUND(AVG(arrdelay), 1) AS arr_delay,
            ROUND(100.0 * SUM(cancelled) / (COUNT(*) + SUM(cancelled)), 2) AS cancel_pct,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN carrierdelay    ELSE NULL END), 1) AS carrier_cause,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN weatherdelay    ELSE NULL END), 1) AS weather_cause,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN nasdelay        ELSE NULL END), 1) AS nas_cause,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN lateaircraftdelay ELSE NULL END), 1) AS late_aircraft_cause
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL
        GROUP BY iata_code_marketing_airline
        HAVING COUNT(*) >= 50
        ORDER BY vol DESC
        LIMIT 10
    """).df()

    carriers = []
    for _, r in carriers_df.iterrows():
        code = str(r["code"])
        carriers.append({
            "code":    code,
            "name":    CARRIER_NAMES.get(code, code),
            "vol":     int(r["vol"]),
            "dep_delay": float(r["dep_delay"]) if r["dep_delay"] is not None else None,
            "arr_delay": float(r["arr_delay"]) if r["arr_delay"] is not None else None,
            "cancel_pct": float(r["cancel_pct"]) if r["cancel_pct"] is not None else None,
            "causes": {
                "carrier":      float(r["carrier_cause"])      if r["carrier_cause"]      is not None else 0,
                "weather":      float(r["weather_cause"])      if r["weather_cause"]      is not None else 0,
                "nas":          float(r["nas_cause"])          if r["nas_cause"]          is not None else 0,
                "late_aircraft":float(r["late_aircraft_cause"]) if r["late_aircraft_cause"] is not None else 0,
            }
        })

    # ── Annual timeline ─────────────────────────────────────
    annual_df = con.execute(f"""
        SELECT year,
               ROUND(AVG(arrdelay), 1)  AS arr_delay,
               ROUND(AVG(depdelay), 1)  AS dep_delay,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND arrdelay IS NOT NULL AND cancelled=0
        GROUP BY year ORDER BY year
    """).df()

    baseline = [
        {"year": int(r["year"]), "arr_delay": float(r["arr_delay"]), "dep_delay": float(r["dep_delay"]), "flights": int(r["flights"])}
        for _, r in annual_df.iterrows()
    ]

    # Per-carrier annual (only carriers with ≥30 flights in a year)
    top_carrier_codes = [c["code"] for c in carriers]
    by_carrier = {}
    for code in top_carrier_codes:
        cdf = con.execute(f"""
            SELECT year,
                   ROUND(AVG(arrdelay), 1) AS arr_delay,
                   ROUND(AVG(depdelay), 1) AS dep_delay,
                   COUNT(*) AS flights
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND iata_code_marketing_airline='{code}'
              AND arrdelay IS NOT NULL AND depdelay IS NOT NULL AND cancelled=0
            GROUP BY year HAVING COUNT(*) >= 30
            ORDER BY year
        """).df()
        if not cdf.empty:
            by_carrier[code] = [
                {"year": int(r["year"]), "arr_delay": float(r["arr_delay"]), "dep_delay": float(r["dep_delay"]), "flights": int(r["flights"])}
                for _, r in cdf.iterrows()
            ]

    # ── Monthly delay rate (Jan–Dec) all-years + per-year ───
    monthly_df = con.execute(f"""
        SELECT year, month,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delay_pct
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND cancelled=0
        GROUP BY year, month
        HAVING COUNT(*) >= 10
        ORDER BY year, month
    """).df()

    all_month = {}
    year_month = {}
    for _, r in monthly_df.iterrows():
        yr, mo, pct = int(r["year"]), int(r["month"]), round(float(r["delay_pct"]), 1)
        all_month.setdefault(mo, []).append(pct)
        year_month.setdefault(yr, {})[mo] = pct

    monthly = [round(sum(all_month[m])/len(all_month[m]), 1) if m in all_month else None
               for m in range(1, 13)]
    monthly_by_year = {yr: [year_month[yr].get(m) for m in range(1, 13)]
                       for yr in sorted(year_month)}

    # ── Arrival monthly delay rate ─────────────────────────────
    arr_monthly_df = con.execute(f"""
        SELECT month,
               ROUND(100.0 * SUM(CASE WHEN arrdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delay_pct
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND arrdelay IS NOT NULL AND cancelled=0
        GROUP BY month HAVING COUNT(*) >= 10
        ORDER BY month
    """).df()
    arr_month_map = {int(r["month"]): round(float(r["delay_pct"]), 1) for _, r in arr_monthly_df.iterrows()}
    arr_monthly = [arr_month_map.get(m) for m in range(1, 13)]

    # ── Insight blurb ────────────────────────────────────────
    dep_dis = accuracy["dep"]["disruptive"]
    arr_dis = accuracy["arr"]["disruptive"]
    diff = round(dep_dis - arr_dis, 1)
    if diff > 1:
        insight = (f"Airlines make up time in the air on {abs(diff):.0f}% of delayed departures, "
                   f"resulting in better arrival accuracy than departure accuracy.")
    elif diff < -1:
        insight = (f"Arrival delays run {abs(diff):.0f}% higher than departure delays — "
                   f"congestion at {dest} worsens on-time performance after landing.")
    else:
        insight = ("Departure and arrival accuracy track closely on this route — "
                   "what leaves late tends to arrive late.")

    # ── Monthly flight counts (for variable-width polar wedges) ─
    mc_df = con.execute(f"""
        SELECT month, COUNT(*) AS flights
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND cancelled=0
        GROUP BY month ORDER BY month
    """).df()
    mc_map = {int(r["month"]): int(r["flights"]) for _, r in mc_df.iterrows()}
    monthly_counts = [mc_map.get(m, 0) for m in range(1, 13)]

    write(out_path, {
        "route":    {"from": orig, "to": dest, "total_flights": total, "year_min": year_min, "year_max": year_max},
        "accuracy": accuracy,
        "accuracy_by_year": accuracy_by_year,
        "insight":  insight,
        "heatmap":              heatmap,
        "arr_heatmap":          arr_heatmap,
        "monthly_heatmap":      monthly_heatmap,
        "arr_monthly_heatmap":  arr_monthly_heatmap,
        "monthly":         monthly,
        "arr_monthly":     arr_monthly,
        "monthly_by_year": monthly_by_year,
        "monthly_counts":  monthly_counts,
        "carriers":        carriers,
        "annual":   {"baseline": baseline, "by_carrier": by_carrier},
    })
    return True


# ── Main ──────────────────────────────────────────────────────
if len(sys.argv) == 3:
    routes = [(sys.argv[1].upper(), sys.argv[2].upper())]
else:
    print("Discovering all routes …")
    routes_df = con.execute(f"""
        SELECT origin, dest, COUNT(*) AS n
        FROM {GLOB}
        WHERE depdelay IS NOT NULL AND cancelled=0
        GROUP BY origin, dest
        ORDER BY n DESC
    """).df()
    routes = [(str(r["origin"]), str(r["dest"])) for _, r in routes_df.iterrows()]
    print(f"  → {len(routes)} routes to build")

t0 = time.time()
ok = 0
skipped = 0
for orig, dest in routes:
    slug = f"{orig}-{dest}"
    out_path = os.path.join(OUTDIR, f"{slug}.json")
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                existing = json.load(f)
            if "heatmap" in existing and "annual" in existing:
                skipped += 1
                continue
        except Exception:
            pass
    try:
        if build_route(orig, dest):
            ok += 1
    except Exception as e:
        print(f"  ✗ {orig}-{dest}: {e}")
if skipped:
    print(f"  (skipped {skipped} already-built routes)")

elapsed = time.time() - t0
print(f"\n✅  Built {ok}/{len(routes)} route files in {elapsed:.0f}s → {OUTDIR}/")
