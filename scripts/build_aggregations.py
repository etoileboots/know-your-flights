"""
Dashboard Aggregation Builder
===============================
Pre-computes all JSON files the dashboard will consume.
Run once (or when data updates) — not at request time.

Usage:
    python scripts/build_aggregations.py

Output: docs/aggregations/
  landing/
    hero_stats.json          — overall numbers for landing page
    annual_trend.json        — year-by-year trend for timeline
    time_of_day_risk.json    — hour-of-day delay risk (global)

  airport/{CODE}.json        — per-airport profile
  route/{ORIG}_{DEST}.json   — per-route profile + all flights ranked
  flight/{CARRIER}{NUM}.json — per-flight profile
  
  indexes/
    airports.json            — list of all airports (for search autocomplete)
    routes.json              — list of all routes
    flights.json             — list of all flight numbers
"""

import os
import json
import duckdb
import pandas as pd

LAKE   = "./data/lake"
OUTDIR = "./docs/aggregations"
GLOB   = f"'{LAKE}/**/*.parquet'"

os.makedirs(OUTDIR, exist_ok=True)

con = duckdb.connect()

def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✓ {path}")

def df_to_records(df):
    return json.loads(df.to_json(orient="records"))

# ── Derived field expressions (reused across queries) ─────────────────────────
DELAY_CATEGORY = """
    CASE
        WHEN depdelay <= 0   THEN 'on_time'
        WHEN depdelay <= 15  THEN 'minor'
        WHEN depdelay <= 60  THEN 'moderate'
        WHEN depdelay <= 180 THEN 'severe'
        ELSE 'extreme'
    END
"""

TIME_OF_DAY = """
    CASE
        WHEN FLOOR(crsdeptime/100) BETWEEN 5  AND 8  THEN 'early_morning'
        WHEN FLOOR(crsdeptime/100) BETWEEN 9  AND 12 THEN 'morning'
        WHEN FLOOR(crsdeptime/100) BETWEEN 13 AND 17 THEN 'afternoon'
        WHEN FLOOR(crsdeptime/100) BETWEEN 18 AND 21 THEN 'evening'
        ELSE 'night'
    END
"""

SEASON = """
    CASE
        WHEN month IN (12,1,2) THEN 'winter'
        WHEN month IN (3,4,5)  THEN 'spring'
        WHEN month IN (6,7,8)  THEN 'summer'
        ELSE 'fall'
    END
"""

CASCADE_FLAG = "CASE WHEN lateaircraftdelay > 0 THEN 1 ELSE 0 END"

print("\n" + "═"*55)
print("  Building dashboard aggregations")
print("═"*55)


# ════════════════════════════════════════════════════════════
# LANDING PAGE
# ════════════════════════════════════════════════════════════
print("\n── Landing page ──")

hero = con.execute(f"""
    SELECT
        COUNT(*)                                                              AS total_flights,
        ROUND(AVG(depdelay), 1)                                               AS mean_dep_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                                   AS pct_delayed,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2)                           AS cancel_pct,
        ROUND(AVG(arrdelay), 1)                                               AS mean_arr_delay
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
""").df().iloc[0].to_dict()

# Story 1: system getting worse
annual_trend = con.execute(f"""
    SELECT year,
           COUNT(*) AS flights,
           ROUND(AVG(depdelay), 1) AS mean_delay,
           ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
           ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct,
           ROUND(AVG(CASE WHEN depdelay > 15 THEN carrierdelay END), 1) AS carrier_cause,
           ROUND(AVG(CASE WHEN depdelay > 15 THEN weatherdelay END), 1) AS weather_cause,
           ROUND(AVG(CASE WHEN depdelay > 15 THEN lateaircraftdelay END), 1) AS late_aircraft_cause
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY year ORDER BY year
""").df()

# Story 2: time of day risk (global)
time_risk = con.execute(f"""
    SELECT
        FLOOR(crsdeptime/100) AS hour,
        {TIME_OF_DAY} AS time_of_day,
        COUNT(*) AS flights,
        ROUND(AVG(depdelay), 1) AS mean_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 30 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed_30,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 60 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed_60
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled=0
      AND crsdeptime BETWEEN 0 AND 2359
    GROUP BY hour, time_of_day ORDER BY hour
""").df()

# Story 3: cascade (global)
cascade_stats = con.execute(f"""
    SELECT
        FLOOR(crsdeptime/100) AS hour,
        ROUND(AVG(lateaircraftdelay), 1) AS avg_late_aircraft,
        ROUND(AVG(depdelay), 1) AS avg_total_delay,
        ROUND(100.0 * SUM({CASCADE_FLAG}) / COUNT(*), 1) AS pct_cascade
    FROM {GLOB}
    WHERE depdelay > 15 AND lateaircraftdelay IS NOT NULL
      AND crsdeptime BETWEEN 0 AND 2359
    GROUP BY hour ORDER BY hour
""").df()

# Story 5: COVID annotation points
covid_monthly = con.execute(f"""
    SELECT year, month,
           COUNT(*) AS flights,
           ROUND(AVG(depdelay), 1) AS mean_delay,
           ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY year, month ORDER BY year, month
""").df()

write(f"{OUTDIR}/landing/hero_stats.json", hero)
write(f"{OUTDIR}/landing/annual_trend.json", df_to_records(annual_trend))
write(f"{OUTDIR}/landing/time_of_day_risk.json", df_to_records(time_risk))
write(f"{OUTDIR}/landing/cascade_by_hour.json", df_to_records(cascade_stats))
write(f"{OUTDIR}/landing/covid_monthly.json", df_to_records(covid_monthly))


# ════════════════════════════════════════════════════════════
# INDEXES (for search autocomplete)
# ════════════════════════════════════════════════════════════
print("\n── Indexes ──")

airports_index = con.execute(f"""
    SELECT origin AS code, origincityname AS city, originstate AS state,
           COUNT(*) AS flights,
           ROUND(AVG(depdelay), 1) AS mean_delay
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY origin, origincityname, originstate
    HAVING COUNT(*) > 1000
    ORDER BY flights DESC
""").df()

routes_index = con.execute(f"""
    SELECT origin, dest, origincityname AS origin_city, destcityname AS dest_city,
           COUNT(*) AS flights,
           ROUND(AVG(depdelay), 1) AS mean_delay
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY origin, dest, origincityname, destcityname
    HAVING COUNT(*) > 500
    ORDER BY flights DESC
""").df()

flights_index = con.execute(f"""
    SELECT iata_code_marketing_airline AS carrier,
           flight_number_marketing_airline AS flight_num,
           origin, dest,
           COUNT(*) AS operated,
           ROUND(AVG(depdelay), 1) AS mean_delay
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY carrier, flight_number_marketing_airline, origin, dest
    HAVING COUNT(*) > 100
    ORDER BY operated DESC
""").df()

write(f"{OUTDIR}/indexes/airports.json", df_to_records(airports_index))
write(f"{OUTDIR}/indexes/routes.json", df_to_records(routes_index))
write(f"{OUTDIR}/indexes/flights.json", df_to_records(flights_index))


# ════════════════════════════════════════════════════════════
# AIRPORT PROFILES (top 50 busiest)
# ════════════════════════════════════════════════════════════
print("\n── Airport profiles ──")

top_airports = airports_index.head(50)["code"].tolist()

for code in top_airports:
    # Summary
    summary = con.execute(f"""
        SELECT
            COUNT(*) AS total_flights,
            ROUND(AVG(depdelay), 1) AS mean_delay,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_delay,
            ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
            ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN carrierdelay END), 1) AS carrier_cause,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN weatherdelay END), 1) AS weather_cause,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN nasdelay END), 1) AS nas_cause,
            ROUND(AVG(CASE WHEN depdelay > 15 THEN lateaircraftdelay END), 1) AS late_aircraft_cause
        FROM {GLOB}
        WHERE origin='{code}' AND depdelay IS NOT NULL
    """).df().iloc[0].to_dict()

    # By hour
    by_hour = con.execute(f"""
        SELECT FLOOR(crsdeptime/100) AS hour,
               {TIME_OF_DAY} AS time_of_day,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB}
        WHERE origin='{code}' AND depdelay IS NOT NULL
          AND crsdeptime BETWEEN 0 AND 2359 AND cancelled=0
        GROUP BY hour, time_of_day ORDER BY hour
    """).df()

    # By day of week
    by_dow = con.execute(f"""
        SELECT dayofweek,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB}
        WHERE origin='{code}' AND depdelay IS NOT NULL AND cancelled=0
        GROUP BY dayofweek ORDER BY dayofweek
    """).df()

    # By carrier at this airport
    by_carrier = con.execute(f"""
        SELECT iata_code_marketing_airline AS carrier,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
        FROM {GLOB}
        WHERE origin='{code}' AND depdelay IS NOT NULL
        GROUP BY carrier HAVING COUNT(*) > 200
        ORDER BY mean_delay DESC
    """).df()

    # Top destinations by delay
    top_dests = con.execute(f"""
        SELECT dest, destcityname AS city,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB}
        WHERE origin='{code}' AND depdelay IS NOT NULL
        GROUP BY dest, destcityname HAVING COUNT(*) > 100
        ORDER BY flights DESC LIMIT 20
    """).df()

    # Annual trend
    by_year = con.execute(f"""
        SELECT year,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE origin='{code}' AND depdelay IS NOT NULL
        GROUP BY year ORDER BY year
    """).df()

    # Verdict components
    best_hour = by_hour.loc[by_hour["pct_delayed"].idxmin()]
    worst_hour = by_hour.loc[by_hour["pct_delayed"].idxmax()]
    best_dow = by_dow.loc[by_dow["pct_delayed"].idxmin()]
    worst_dow = by_dow.loc[by_dow["pct_delayed"].idxmax()]
    dow_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    verdict = {
        "best_hour": int(best_hour["hour"]),
        "best_hour_pct": float(best_hour["pct_delayed"]),
        "worst_hour": int(worst_hour["hour"]),
        "worst_hour_pct": float(worst_hour["pct_delayed"]),
        "best_dow": dow_names[int(best_dow["dayofweek"]) - 1],
        "worst_dow": dow_names[int(worst_dow["dayofweek"]) - 1],
    }

    write(f"{OUTDIR}/airport/{code}.json", {
        "code": code,
        "summary": summary,
        "by_hour": df_to_records(by_hour),
        "by_dow": df_to_records(by_dow),
        "by_carrier": df_to_records(by_carrier),
        "top_destinations": df_to_records(top_dests),
        "by_year": df_to_records(by_year),
        "verdict": verdict,
    })


# ════════════════════════════════════════════════════════════
# ROUTE PROFILES (top 200 routes)
# ════════════════════════════════════════════════════════════
print("\n── Route profiles ──")

top_routes = routes_index.head(200)[["origin","dest"]].values.tolist()

for orig, dest in top_routes:
    slug = f"{orig}_{dest}"

    # Route summary + personality score
    summary = con.execute(f"""
        SELECT COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(STDDEV(depdelay), 1) AS std_delay,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_delay,
               ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY depdelay), 1) AS p90_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL
    """).df().iloc[0].to_dict()

    # Route personality (4 quadrants based on mean + std vs global medians)
    global_mean_median = 11.0
    global_std_median  = 30.0
    mean_d = summary["mean_delay"] or 0
    std_d  = summary["std_delay"]  or 0

    if mean_d <= global_mean_median and std_d <= global_std_median:
        personality = "reliably_good"
        personality_label = "Reliably good"
    elif mean_d <= global_mean_median and std_d > global_std_median:
        personality = "unpredictably_good"
        personality_label = "Usually good, occasionally bad"
    elif mean_d > global_mean_median and std_d <= global_std_median:
        personality = "reliably_bad"
        personality_label = "Reliably late"
    else:
        personality = "unpredictably_bad"
        personality_label = "High delay, high variance — avoid"

    # All flights on this route ranked
    all_flights = con.execute(f"""
        SELECT iata_code_marketing_airline AS carrier,
               flight_number_marketing_airline AS flight_num,
               COUNT(*) AS operated,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_delay,
               ROUND(STDDEV(depdelay), 1) AS std_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY depdelay), 1) AS p90_delay,
               ROUND(AVG(FLOOR(crsdeptime/100)), 0) AS avg_dep_hour,
               ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL
        GROUP BY carrier, flight_number_marketing_airline
        HAVING COUNT(*) > 50
        ORDER BY mean_delay ASC
    """).df()

    # Day of week
    by_dow = con.execute(f"""
        SELECT dayofweek,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL AND cancelled=0
        GROUP BY dayofweek ORDER BY dayofweek
    """).df()

    # By hour
    by_hour = con.execute(f"""
        SELECT FLOOR(crsdeptime/100) AS hour,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL AND cancelled=0
          AND crsdeptime BETWEEN 0 AND 2359
        GROUP BY hour ORDER BY hour
    """).df()

    # Monthly trend
    monthly = con.execute(f"""
        SELECT year, month,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL AND cancelled=0
        GROUP BY year, month ORDER BY year, month
    """).df()

    # Verdict
    dow_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    best_dow  = by_dow.loc[by_dow["pct_delayed"].idxmin()]
    worst_dow = by_dow.loc[by_dow["pct_delayed"].idxmax()]
    best_flight = all_flights.iloc[-1] if len(all_flights) else None

    verdict = {
        "personality": personality,
        "personality_label": personality_label,
        "best_dow": dow_names[int(best_dow["dayofweek"]) - 1],
        "best_dow_pct": float(best_dow["pct_delayed"]),
        "worst_dow": dow_names[int(worst_dow["dayofweek"]) - 1],
        "worst_dow_pct": float(worst_dow["pct_delayed"]),
        "best_flight": f"{best_flight['carrier']}{int(best_flight['flight_num'])}" if best_flight is not None else None,
        "best_flight_pct": float(best_flight["pct_delayed"]) if best_flight is not None else None,
    }

    write(f"{OUTDIR}/route/{slug}.json", {
        "origin": orig,
        "dest": dest,
        "summary": summary,
        "personality": personality,
        "personality_label": personality_label,
        "all_flights": df_to_records(all_flights),
        "by_dow": df_to_records(by_dow),
        "by_hour": df_to_records(by_hour),
        "monthly_trend": df_to_records(monthly),
        "verdict": verdict,
    })


# ════════════════════════════════════════════════════════════
# FLIGHT PROFILES (top 500 most-operated flights)
# ════════════════════════════════════════════════════════════
print("\n── Flight profiles ──")

top_flights = flights_index.head(500)[["carrier","flight_num","origin","dest"]].values.tolist()

for carrier, flight_num, orig, dest in top_flights:
    flight_num = int(flight_num)
    slug = f"{carrier}{flight_num}"

    history = con.execute(f"""
        SELECT year, month, dayofweek,
               depdelay, arrdelay,
               carrierdelay, weatherdelay, nasdelay, lateaircraftdelay,
               {CASCADE_FLAG} AS is_cascade,
               {DELAY_CATEGORY} AS delay_category
        FROM {GLOB}
        WHERE iata_code_marketing_airline='{carrier}'
          AND flight_number_marketing_airline={flight_num}
          AND origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL
    """).df()

    if history.empty:
        continue

    # Summary
    summary = {
        "carrier": carrier,
        "flight_num": flight_num,
        "origin": orig,
        "dest": dest,
        "total_flights": int(len(history)),
        "mean_delay": round(float(history["depdelay"].mean()), 1),
        "median_delay": round(float(history["depdelay"].median()), 1),
        "std_delay": round(float(history["depdelay"].std()), 1),
        "p90_delay": round(float(history["depdelay"].quantile(0.9)), 1),
        "pct_delayed": round(float((history["depdelay"] > 15).mean() * 100), 1),
        "cascade_pct": round(float(history["is_cascade"].mean() * 100), 1),
    }

    # Delay category distribution
    cat_dist = history["delay_category"].value_counts(normalize=True).mul(100).round(1).to_dict()

    # By day of week
    dow_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    by_dow = history.groupby("dayofweek").agg(
        mean_delay=("depdelay","mean"),
        pct_delayed=("depdelay", lambda x: (x > 15).mean() * 100),
        flights=("depdelay","count"),
        cascade_pct=("is_cascade","mean")
    ).reset_index()
    by_dow["mean_delay"]  = by_dow["mean_delay"].round(1)
    by_dow["pct_delayed"] = by_dow["pct_delayed"].round(1)
    by_dow["cascade_pct"] = (by_dow["cascade_pct"] * 100).round(1)
    by_dow["day_name"] = by_dow["dayofweek"].apply(lambda d: dow_names[int(d)-1])

    # By month
    by_month = history.groupby("month").agg(
        mean_delay=("depdelay","mean"),
        pct_delayed=("depdelay", lambda x: (x > 15).mean() * 100),
    ).reset_index().round(1)

    # Cause breakdown (delayed only)
    delayed = history[history["depdelay"] > 15]
    causes = {}
    for col in ["carrierdelay","weatherdelay","nasdelay","lateaircraftdelay"]:
        causes[col] = round(float(delayed[col].mean()), 1) if not delayed.empty else 0

    # Compare against route average
    route_stats = con.execute(f"""
        SELECT COUNT(*) AS route_flights,
               ROUND(AVG(depdelay), 1) AS route_mean,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS route_pct_delayed,
               ROUND(AVG(CASE WHEN depdelay > 15 THEN carrierdelay END), 1) AS route_carrier_cause,
               ROUND(AVG(CASE WHEN depdelay > 15 THEN lateaircraftdelay END), 1) AS route_late_aircraft
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL
    """).df().iloc[0].to_dict()

    # Rank on route
    rank_df = con.execute(f"""
        SELECT iata_code_marketing_airline AS carrier,
               flight_number_marketing_airline AS flight_num,
               ROUND(AVG(depdelay), 1) AS mean_delay
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL
        GROUP BY carrier, flight_number_marketing_airline
        HAVING COUNT(*) > 50
        ORDER BY mean_delay ASC
    """).df()
    rank_df["rank"] = range(1, len(rank_df) + 1)
    match = rank_df[(rank_df["carrier"] == carrier) & (rank_df["flight_num"] == flight_num)]
    rank = int(match["rank"].iloc[0]) if not match.empty else None
    total_on_route = len(rank_df)

    # Verdict
    best_dow_row  = by_dow.loc[by_dow["pct_delayed"].idxmin()]
    worst_dow_row = by_dow.loc[by_dow["pct_delayed"].idxmax()]
    verdict = {
        "rank_on_route": rank,
        "total_on_route": total_on_route,
        "best_dow": str(best_dow_row["day_name"]),
        "best_dow_pct": float(best_dow_row["pct_delayed"]),
        "worst_dow": str(worst_dow_row["day_name"]),
        "worst_dow_pct": float(worst_dow_row["pct_delayed"]),
        "vs_route_mean": round(float(summary["mean_delay"]) - float(route_stats["route_mean"] or 0), 1),
        "cascade_risk": "high" if summary["cascade_pct"] > 40 else "medium" if summary["cascade_pct"] > 20 else "low",
    }

    write(f"{OUTDIR}/flight/{slug}.json", {
        "summary": summary,
        "delay_category_dist": cat_dist,
        "by_dow": df_to_records(by_dow),
        "by_month": df_to_records(by_month),
        "causes": causes,
        "route_comparison": route_stats,
        "verdict": verdict,
    })


print(f"\n✅ All aggregations built → {OUTDIR}/")
print(f"   These JSON files are what the dashboard reads — serve them as static files.")