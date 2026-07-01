"""
Flight aggregation builder for search.html flight-number mode
=============================================================
Produces: data/aggregations/flights/{CARRIER}-{NUM}.json

A "flight" here is a (carrier, flight_number) pair. Because the same
number can serve multiple legs (e.g. AA100 JFK-LAX and AA100 LAX-ORD on
different days), the JSON includes a `legs` array — one entry per
origin–dest pair that operated ≥100 times.

Run:
    python3 scripts/build_flight_data.py            # top 600 flights
    python3 scripts/build_flight_data.py AA 100     # single flight
"""

import os, sys, json, time
import duckdb

LAKE   = os.path.join(os.path.dirname(__file__), "..", "data", "lake")
OUTDIR = os.path.join(os.path.dirname(__file__), "..", "data", "aggregations", "flights")
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
    "EV": "ExpressJet Airlines",
}

DOW_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]


def write(path, data):
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    kb = os.path.getsize(path) / 1024
    print(f"  ✓ {os.path.basename(path)}  ({kb:.1f} KB)")


def build_flight(carrier, flight_num):
    slug = f"{carrier}-{int(flight_num)}"
    out_path = os.path.join(OUTDIR, f"{slug}.json")

    # ── Find all legs for this flight ───────────────────────
    legs_df = con.execute(f"""
        SELECT origin, dest, origincityname AS origin_city, destcityname AS dest_city,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_dep,
               ROUND(AVG(arrdelay), 1) AS mean_arr,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_dep_del,
               ROUND(100.0 * SUM(CASE WHEN arrdelay  > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_arr_del,
               ROUND(100.0 * SUM(cancelled) / (COUNT(*) + SUM(cancelled)), 2) AS cancel_pct,
               MIN(year) AS year_min, MAX(year) AS year_max
        FROM {GLOB}
        WHERE iata_code_marketing_airline = '{carrier}'
          AND flight_number_marketing_airline = {int(flight_num)}
          AND depdelay IS NOT NULL
        GROUP BY origin, dest, origincityname, destcityname
        HAVING COUNT(*) >= 50
        ORDER BY flights DESC
        LIMIT 8
    """).df()

    if legs_df.empty:
        return False

    # Primary leg = most-operated origin-dest pair
    primary = legs_df.iloc[0]
    orig, dest = str(primary["origin"]), str(primary["dest"])
    total_flights = int(legs_df["flights"].sum())

    legs = []
    for _, r in legs_df.iterrows():
        legs.append({
            "origin":      str(r["origin"]),
            "dest":        str(r["dest"]),
            "origin_city": str(r["origin_city"]),
            "dest_city":   str(r["dest_city"]),
            "flights":     int(r["flights"]),
            "mean_dep":    float(r["mean_dep"]) if r["mean_dep"] is not None else None,
            "mean_arr":    float(r["mean_arr"]) if r["mean_arr"] is not None else None,
            "pct_dep_del": float(r["pct_dep_del"]),
            "pct_arr_del": float(r["pct_arr_del"]),
            "cancel_pct":  float(r["cancel_pct"]),
        })

    # ── Accuracy (primary leg) ───────────────────────────────
    acc = con.execute(f"""
        SELECT
            ROUND(100.0 * SUM(CASE WHEN depdelay <= 5  THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_perfect,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 5 AND depdelay <= 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_standard,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS dep_disruptive,
            ROUND(100.0 * SUM(CASE WHEN arrdelay <= 5  THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_perfect,
            ROUND(100.0 * SUM(CASE WHEN arrdelay > 5 AND arrdelay <= 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_standard,
            ROUND(100.0 * SUM(CASE WHEN arrdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS arr_disruptive,
            ROUND(AVG(depdelay), 1) AS mean_dep_delay,
            ROUND(AVG(arrdelay), 1) AS mean_arr_delay
        FROM {GLOB}
        WHERE iata_code_marketing_airline = '{carrier}'
          AND flight_number_marketing_airline = {int(flight_num)}
          AND origin = '{orig}' AND dest = '{dest}'
          AND depdelay IS NOT NULL AND arrdelay IS NOT NULL AND cancelled = 0
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
        "mean_dep_delay": float(acc["mean_dep_delay"]) if acc["mean_dep_delay"] is not None else None,
        "mean_arr_delay": float(acc["mean_arr_delay"]) if acc["mean_arr_delay"] is not None else None,
    }

    # ── Heatmap: day × time block (primary leg) ─────────────
    TIME_BLOCKS = [(600, 1000), (1000, 1500), (1500, 1900), (1900, 2300)]
    hm_raw = con.execute(f"""
        SELECT dayofweek, crsdeptime,
               CASE WHEN depdelay > 15 THEN 1 ELSE 0 END AS del15
        FROM {GLOB}
        WHERE iata_code_marketing_airline = '{carrier}'
          AND flight_number_marketing_airline = {int(flight_num)}
          AND origin = '{orig}' AND dest = '{dest}'
          AND depdelay IS NOT NULL AND cancelled = 0
    """).df()

    heatmap = []
    for dow in range(1, 8):
        row_df = hm_raw[hm_raw["dayofweek"] == dow]
        row = []
        for lo, hi in TIME_BLOCKS:
            slot = row_df[(row_df["crsdeptime"] >= lo) & (row_df["crsdeptime"] < hi)]
            row.append(round(float(slot["del15"].mean() * 100), 1) if len(slot) >= 5 else None)
        heatmap.append(row)

    # ── Annual timeline ──────────────────────────────────────
    annual_df = con.execute(f"""
        SELECT year,
               ROUND(AVG(arrdelay), 1)  AS arr_delay,
               ROUND(AVG(depdelay), 1)  AS dep_delay,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE iata_code_marketing_airline = '{carrier}'
          AND flight_number_marketing_airline = {int(flight_num)}
          AND origin = '{orig}' AND dest = '{dest}'
          AND arrdelay IS NOT NULL AND cancelled = 0
        GROUP BY year ORDER BY year
    """).df()

    annual = [
        {"year": int(r["year"]), "arr_delay": float(r["arr_delay"]),
         "dep_delay": float(r["dep_delay"]), "flights": int(r["flights"])}
        for _, r in annual_df.iterrows()
    ]

    # ── Route-average comparison ─────────────────────────────
    route_avg = con.execute(f"""
        SELECT
            ROUND(AVG(depdelay), 1) AS route_dep,
            ROUND(AVG(arrdelay), 1) AS route_arr,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS route_pct_del,
            COUNT(*) AS route_flights
        FROM {GLOB}
        WHERE origin = '{orig}' AND dest = '{dest}'
          AND depdelay IS NOT NULL AND arrdelay IS NOT NULL AND cancelled = 0
    """).df().iloc[0]

    vs_route = {
        "route_dep_delay": float(route_avg["route_dep"]) if route_avg["route_dep"] is not None else None,
        "route_arr_delay": float(route_avg["route_arr"]) if route_avg["route_arr"] is not None else None,
        "route_pct_delayed": float(route_avg["route_pct_del"]),
        "route_flights": int(route_avg["route_flights"]),
        "dep_vs_route": round(float(acc["mean_dep_delay"] or 0) - float(route_avg["route_dep"] or 0), 1),
        "arr_vs_route": round(float(acc["mean_arr_delay"] or 0) - float(route_avg["route_arr"] or 0), 1),
    }

    # ── Day of week breakdown ────────────────────────────────
    dow_df = con.execute(f"""
        SELECT dayofweek,
               ROUND(AVG(depdelay), 1) AS dep_delay,
               ROUND(AVG(arrdelay), 1) AS arr_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE iata_code_marketing_airline = '{carrier}'
          AND flight_number_marketing_airline = {int(flight_num)}
          AND origin = '{orig}' AND dest = '{dest}'
          AND depdelay IS NOT NULL AND cancelled = 0
        GROUP BY dayofweek ORDER BY dayofweek
    """).df()

    by_dow = [
        {"dow": int(r["dayofweek"]), "day": DOW_NAMES[int(r["dayofweek"])-1],
         "dep_delay": float(r["dep_delay"]), "arr_delay": float(r["arr_delay"]),
         "pct_delayed": float(r["pct_delayed"]), "flights": int(r["flights"])}
        for _, r in dow_df.iterrows()
    ]

    # ── Delay causes (primary leg, delayed flights only) ─────
    causes_df = con.execute(f"""
        SELECT
            ROUND(AVG(carrierdelay), 1)      AS carrier,
            ROUND(AVG(weatherdelay), 1)      AS weather,
            ROUND(AVG(nasdelay), 1)          AS nas,
            ROUND(AVG(lateaircraftdelay), 1) AS late_aircraft,
            ROUND(AVG(securitydelay), 1)     AS security
        FROM {GLOB}
        WHERE iata_code_marketing_airline = '{carrier}'
          AND flight_number_marketing_airline = {int(flight_num)}
          AND origin = '{orig}' AND dest = '{dest}'
          AND depdelay > 15 AND cancelled = 0
          AND carrierdelay IS NOT NULL
    """).df().iloc[0]

    causes = {k: float(v) if v is not None else 0 for k, v in causes_df.items()}

    # ── Insight ──────────────────────────────────────────────
    dep_d = accuracy["dep"]["disruptive"]
    arr_d = accuracy["arr"]["disruptive"]
    vs_r  = vs_route["arr_vs_route"]
    if vs_r < -2:
        insight = f"{carrier}{int(flight_num)} runs {abs(vs_r):.1f} min better than the {orig}–{dest} route average — one of the more reliable options on this corridor."
    elif vs_r > 3:
        insight = f"{carrier}{int(flight_num)} averages {vs_r:.1f} min worse than the {orig}–{dest} route average. Consider other departure times or carriers."
    else:
        insight = f"{carrier}{int(flight_num)} tracks close to the {orig}–{dest} route average arrival delay."

    write(out_path, {
        "flight":   {"carrier": carrier, "number": int(flight_num),
                     "carrier_name": CARRIER_NAMES.get(carrier, carrier),
                     "primary_origin": orig, "primary_dest": dest,
                     "total_flights": total_flights},
        "legs":     legs,
        "accuracy": accuracy,
        "heatmap":  heatmap,
        "by_dow":   by_dow,
        "causes":   causes,
        "annual":   annual,
        "vs_route": vs_route,
        "insight":  insight,
    })
    return True


# ── Main ──────────────────────────────────────────────────────
if len(sys.argv) == 3:
    flights = [(sys.argv[1].upper(), int(sys.argv[2]))]
else:
    print("Discovering top flights …")
    flights_df = con.execute(f"""
        SELECT iata_code_marketing_airline AS carrier,
               flight_number_marketing_airline AS flight_num,
               COUNT(*) AS n
        FROM {GLOB}
        WHERE depdelay IS NOT NULL AND cancelled = 0
        GROUP BY carrier, flight_number_marketing_airline
        HAVING COUNT(*) >= 200
        ORDER BY n DESC
        LIMIT 600
    """).df()
    flights = [(str(r["carrier"]), int(r["flight_num"])) for _, r in flights_df.iterrows()]
    print(f"  → {len(flights)} flights to build")

t0 = time.time()
ok = 0
for carrier, num in flights:
    try:
        if build_flight(carrier, num):
            ok += 1
    except Exception as e:
        print(f"  ✗ {carrier}{num}: {e}")

elapsed = time.time() - t0
print(f"\n✅  Built {ok}/{len(flights)} flight files in {elapsed:.0f}s → {OUTDIR}/")
