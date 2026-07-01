"""
Map Data Builder
================
Fetches airport coordinates and builds GeoJSON files for the Mapbox map.

Run from your project root:
    python scripts/build_map_data.py

Outputs:
    data/aggregations/map/airports.geojson   — airport points with delay stats
    data/aggregations/map/routes.geojson     — route lines with delay stats
"""

import os
import json
import duckdb
import urllib.request
import pandas as pd

LAKE   = "./data/lake"
OUTDIR = "./data/aggregations/map"
GLOB   = f"'{LAKE}/**/*.parquet'"

os.makedirs(OUTDIR, exist_ok=True)
con = duckdb.connect()

print("\n" + "═"*55)
print("  Building map data")
print("═"*55)


# ── Step 1: Pull airport stats from lake ──────────────────
print("\n── Airport stats from lake ──")

airport_stats = con.execute(f"""
    SELECT
        origin                  AS code,
        origincityname          AS city,
        originstate             AS state,
        COUNT(*)                AS flights,
        ROUND(AVG(depdelay), 1) AS mean_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)    AS pct_delayed,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY origin, origincityname, originstate
    ORDER BY flights DESC
""").df()

print(f"  {len(airport_stats)} airports found")


# ── Step 2: Fetch airport coordinates ────────────────────
# Using OurAirports public dataset — free, no API key needed
print("\n── Fetching airport coordinates (OurAirports) ──")

AIRPORTS_CSV_URL = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"

try:
    req = urllib.request.Request(AIRPORTS_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        coords_df = pd.read_csv(r, low_memory=False)
    print(f"  Downloaded {len(coords_df)} airports from OurAirports")
except Exception as e:
    print(f"  ✗ Failed to fetch coordinates: {e}")
    print("  Falling back to hardcoded top-50 airport coordinates")
    coords_df = None

# Build code → lat/lng lookup
coord_lookup = {}

if coords_df is not None:
    # OurAirports uses iata_code column
    iata = coords_df[coords_df["iata_code"].notna() & (coords_df["iata_code"] != "")]
    for _, row in iata.iterrows():
        code = str(row["iata_code"]).strip().upper()
        try:
            coord_lookup[code] = {
                "lat": float(row["latitude_deg"]),
                "lng": float(row["longitude_deg"]),
                "name": str(row["name"]),
                "type": str(row.get("type",""))
            }
        except Exception:
            pass
    print(f"  {len(coord_lookup)} IATA codes with coordinates")

# Hardcoded fallback for top US airports
HARDCODED = {
    "ATL": (33.6367,-84.4281,"Hartsfield-Jackson Atlanta"),
    "LAX": (33.9425,-118.4081,"Los Angeles International"),
    "ORD": (41.9742,-87.9073,"Chicago O'Hare"),
    "DFW": (32.8998,-97.0403,"Dallas/Fort Worth"),
    "DEN": (39.8561,-104.6737,"Denver International"),
    "JFK": (40.6413,-73.7781,"John F. Kennedy"),
    "SFO": (37.6213,-122.3790,"San Francisco International"),
    "SEA": (47.4502,-122.3088,"Seattle-Tacoma"),
    "LAS": (36.0840,-115.1537,"Harry Reid International"),
    "MCO": (28.4312,-81.3081,"Orlando International"),
    "EWR": (40.6895,-74.1745,"Newark Liberty"),
    "PHX": (33.4373,-112.0078,"Phoenix Sky Harbor"),
    "IAH": (29.9902,-95.3368,"George Bush Intercontinental"),
    "MIA": (25.7959,-80.2870,"Miami International"),
    "BOS": (42.3656,-71.0096,"Boston Logan"),
    "MSP": (44.8848,-93.2223,"Minneapolis-Saint Paul"),
    "DTW": (42.2162,-83.3554,"Detroit Metro Wayne County"),
    "PHL": (39.8729,-75.2437,"Philadelphia International"),
    "LGA": (40.7772,-73.8726,"LaGuardia"),
    "FLL": (26.0726,-80.1527,"Fort Lauderdale-Hollywood"),
    "CLT": (35.2140,-80.9431,"Charlotte Douglas"),
    "BWI": (39.1754,-76.6682,"Baltimore/Washington"),
    "SLC": (40.7884,-111.9778,"Salt Lake City"),
    "DCA": (38.8512,-77.0402,"Ronald Reagan Washington"),
    "IAD": (38.9531,-77.4565,"Washington Dulles"),
    "MDW": (41.7868,-87.7522,"Chicago Midway"),
    "HNL": (21.3187,-157.9225,"Daniel K. Inouye"),
    "SAN": (32.7336,-117.1897,"San Diego"),
    "TPA": (27.9755,-82.5332,"Tampa"),
    "PDX": (45.5887,-122.5975,"Portland"),
    "STL": (38.7487,-90.3700,"St. Louis Lambert"),
    "BNA": (36.1245,-86.6782,"Nashville"),
    "AUS": (30.1975,-97.6664,"Austin-Bergstrom"),
    "OAK": (37.7213,-122.2208,"Oakland"),
    "RDU": (35.8776,-78.7875,"Raleigh-Durham"),
    "MCI": (39.2976,-94.7139,"Kansas City"),
    "SJC": (37.3626,-121.9290,"San Jose"),
    "SMF": (38.6954,-121.5908,"Sacramento"),
    "CLE": (41.4117,-81.8498,"Cleveland Hopkins"),
    "PIT": (40.4915,-80.2329,"Pittsburgh"),
    "MKE": (42.9472,-87.8966,"Milwaukee Mitchell"),
    "OMA": (41.3032,-95.8941,"Eppley Airfield"),
    "ABQ": (35.0402,-106.6090,"Albuquerque"),
    "TUS": (32.1161,-110.9410,"Tucson"),
    "ELP": (31.8072,-106.3779,"El Paso"),
    "OGG": (20.8986,-156.4305,"Kahului"),
    "KOA": (19.7388,-156.0456,"Ellison Onizuka Kona"),
    "ITO": (19.7214,-155.0485,"Hilo"),
    "LIH": (21.9760,-159.3388,"Lihue"),
    "ASE": (39.2232,-106.8693,"Aspen/Pitkin County"),
    "SNA": (33.6757,-117.8682,"John Wayne Orange County"),
    "BUR": (34.2007,-118.3585,"Hollywood Burbank"),
    "LGB": (33.8177,-118.1516,"Long Beach"),
    "ONT": (34.0560,-117.6012,"Ontario"),
    "PSP": (33.8297,-116.5067,"Palm Springs"),
}

for code, (lat, lng, name) in HARDCODED.items():
    if code not in coord_lookup:
        coord_lookup[code] = {"lat": lat, "lng": lng, "name": name, "type": "large_airport"}


# ── Step 2b: Per-year delay stats per airport ─────────────
print("\n── Per-year delay rates ──")
YEARS = list(range(2018, 2027))  # 2026 is partial (Jan–Apr)
per_year = {}  # code → {year: {pct_delayed, mean_delay, flights}}

for yr in YEARS:
    yr_df = con.execute(f"""
        SELECT origin AS code,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
                     / COUNT(*), 1) AS pct_delayed,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               COUNT(*) AS flights
        FROM {GLOB}
        WHERE depdelay IS NOT NULL AND year = {yr}
        GROUP BY origin
        HAVING COUNT(*) >= 500
    """).df()
    for _, r in yr_df.iterrows():
        code = str(r["code"])
        if code not in per_year:
            per_year[code] = {}
        per_year[code][yr] = {
            "pct_delayed": float(r["pct_delayed"]),
            "mean_delay":  float(r["mean_delay"]),
            "flights":     int(r["flights"]),
        }
    print(f"  {yr}: {len(yr_df)} airports")


# ── Step 3: Build airports GeoJSON ────────────────────────
print("\n── Building airports.geojson ──")

features = []
matched = 0
skipped = 0

for _, row in airport_stats.iterrows():
    code = row["code"]
    if code not in coord_lookup:
        skipped += 1
        continue
    c = coord_lookup[code]
    matched += 1

    # Delay severity bucket for map styling
    pct = row["pct_delayed"]
    if pct < 15:
        severity = "low"
    elif pct < 22:
        severity = "medium"
    else:
        severity = "high"

    # Per-year pct_delayed and flights fields
    yr_props = {}
    for yr in YEARS:
        yd = per_year.get(code, {}).get(yr, {})
        yr_props[f"pct_{yr}"] = yd.get("pct_delayed")
        yr_props[f"flt_{yr}"] = yd.get("flights")

    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [c["lng"], c["lat"]]
        },
        "properties": {
            "code":        code,
            "name":        c["name"],
            "city":        row["city"],
            "state":       row["state"],
            "flights":     int(row["flights"]),
            "mean_delay":  float(row["mean_delay"]),
            "pct_delayed": float(row["pct_delayed"]),
            "cancel_pct":  float(row["cancel_pct"]),
            "severity":    severity,
            **yr_props,
        }
    })

airports_geojson = {"type": "FeatureCollection", "features": features}

path = f"{OUTDIR}/airports.geojson"
with open(path, "w") as f:
    json.dump(airports_geojson, f)
print(f"  ✓ {path}  ({matched} airports, {skipped} skipped — no coordinates)")


# ── Step 4: Build routes GeoJSON (top 300 routes) ────────
print("\n── Building routes.geojson ──")

routes_stats = con.execute(f"""
    SELECT
        origin, dest,
        origincityname  AS origin_city,
        destcityname    AS dest_city,
        COUNT(*)        AS flights,
        ROUND(AVG(depdelay), 1)  AS mean_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)     AS pct_delayed,
        ROUND(STDDEV(depdelay), 1) AS std_delay,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY origin, dest, origincityname, destcityname
    ORDER BY flights DESC
""").df()

# Per-year stats for each route
print("  computing per-year route stats …")
route_per_year = {}  # (orig, dest) → {year: {flights, mean_delay, pct_delayed}}
for yr in YEARS:
    yr_stats = con.execute(f"""
        SELECT origin, dest,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB}
        WHERE depdelay IS NOT NULL AND year = {yr}
        GROUP BY origin, dest
    """).df()
    for _, r in yr_stats.iterrows():
        key = (r["origin"], r["dest"])
        if key not in route_per_year:
            route_per_year[key] = {}
        route_per_year[key][yr] = {
            "flights":     int(r["flights"]),
            "mean_delay":  float(r["mean_delay"]),
            "pct_delayed": float(r["pct_delayed"]),
        }

route_features = []
route_skipped = 0

for _, row in routes_stats.iterrows():
    orig, dest = row["origin"], row["dest"]
    if orig not in coord_lookup or dest not in coord_lookup:
        route_skipped += 1
        continue

    oc = coord_lookup[orig]
    dc = coord_lookup[dest]

    pct = row["pct_delayed"]
    if pct < 15:
        severity = "low"
    elif pct < 22:
        severity = "medium"
    else:
        severity = "high"

    # Route personality
    mean_d = row["mean_delay"]
    std_d  = row["std_delay"]
    if mean_d <= 11 and std_d <= 30:
        personality = "reliably_good"
    elif mean_d <= 11 and std_d > 30:
        personality = "unpredictably_good"
    elif mean_d > 11 and std_d <= 30:
        personality = "reliably_bad"
    else:
        personality = "unpredictably_bad"

    route_features.append({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [oc["lng"], oc["lat"]],
                [dc["lng"], dc["lat"]]
            ]
        },
        "properties": {
            "origin":       orig,
            "dest":         dest,
            "origin_city":  row["origin_city"],
            "dest_city":    row["dest_city"],
            "flights":      int(row["flights"]),
            "mean_delay":   float(row["mean_delay"]),
            "pct_delayed":  float(row["pct_delayed"]),
            "std_delay":    float(row["std_delay"]),
            "cancel_pct":   float(row["cancel_pct"]),
            "severity":     severity,
            "personality":  personality,
            **{f"flt_{yr}":  route_per_year.get((orig, dest), {}).get(yr, {}).get("flights") for yr in YEARS},
            **{f"pct_{yr}":  route_per_year.get((orig, dest), {}).get(yr, {}).get("pct_delayed") for yr in YEARS},
            **{f"mean_{yr}": route_per_year.get((orig, dest), {}).get(yr, {}).get("mean_delay") for yr in YEARS},
        }
    })

routes_geojson = {"type": "FeatureCollection", "features": route_features}

import math

def sanitize(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj

path = f"{OUTDIR}/routes.geojson"
with open(path, "w") as f:
    json.dump(sanitize(routes_geojson), f)
print(f"  ✓ {path}  ({len(route_features)} routes, {route_skipped} skipped)")


# ── Step 5: State-level aggregation for choropleth ───────
print("\n── Building states.json ──")

state_stats = con.execute(f"""
    SELECT
        originstate             AS state,
        COUNT(*)                AS flights,
        ROUND(AVG(depdelay), 1) AS mean_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)    AS pct_delayed,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND originstate IS NOT NULL
      AND LENGTH(originstate) = 2
    GROUP BY originstate
    ORDER BY pct_delayed DESC
""").df()

path = f"{OUTDIR}/states.json"
with open(path, "w") as f:
    json.dump(json.loads(state_stats.to_json(orient="records")), f, indent=2)
print(f"  ✓ {path}  ({len(state_stats)} states)")


# ── Data cutoff metadata ──────────────────────────────────
MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]
cutoff = con.execute(f"SELECT MAX(year) AS yr, MAX(month) AS mo FROM {GLOB} WHERE year=(SELECT MAX(year) FROM {GLOB})").fetchone()
cutoff_year, cutoff_month = int(cutoff[0]), int(cutoff[1])
start = con.execute(f"SELECT MIN(year) AS yr, MIN(month) AS mo FROM {GLOB} WHERE year=(SELECT MIN(year) FROM {GLOB})").fetchone()
start_year, start_month = int(start[0]), int(start[1])
meta = {
    "year_min": start_year,
    "year_max": cutoff_year,
    "year_min_month": start_month,
    "year_min_month_name": MONTH_NAMES[start_month - 1],
    "partial_year": cutoff_year,
    "partial_month": cutoff_month,
    "partial_month_name": MONTH_NAMES[cutoff_month - 1],
}
path = f"{OUTDIR}/meta.json"
with open(path, "w") as f:
    json.dump(meta, f)
print(f"  ✓ {path}  (data through {meta['partial_month_name']} {cutoff_year})")

print(f"\n✅ Map data built → {OUTDIR}/")
print("   airports.geojson  — airport points (size=volume, color=delay rate)")
print("   routes.geojson    — route lines (color=delay rate, personality)")
print("   states.json       — state-level aggregation for choropleth")
print("   meta.json         — data cutoff metadata")