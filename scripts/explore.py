"""
Flight Delay Explorer — CLI
============================
Query your BTS parquet lake from the terminal.

Usage:
    # Airport view — overview + top routes + carriers
    python scripts/explore.py --airport SFO

    # Route view — all flights on this route compared side by side
    python scripts/explore.py --origin SFO --dest JFK

    # Multiple routes compared
    python scripts/explore.py --origin SFO --dest JFK LAX ORD

    # Flight number view — deep dive + comparison against all flights on same route
    python scripts/explore.py --carrier UA --flight 1

    # Add year filter to any mode
    python scripts/explore.py --origin SFO --dest JFK --year 2022 2025
    python scripts/explore.py --carrier UA --flight 1 --year 2023

    # Custom output folder
    python scripts/explore.py --airport SFO --out docs/sfo
"""

import argparse
import os
import sys
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor":  "#FAFAFA",
    "axes.facecolor":    "#FAFAFA",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "font.family":       "sans-serif",
    "axes.labelsize":    11,
    "axes.titlesize":    12,
    "axes.titleweight":  "bold",
})

BLUE   = "#378ADD"
AMBER  = "#BA7517"
CORAL  = "#D85A30"
TEAL   = "#1D9E75"
PURPLE = "#7F77DD"
GRAY   = "#888780"
GREEN  = "#639922"
PALETTE = [BLUE, CORAL, TEAL, PURPLE, AMBER, GREEN, GRAY,
           "#C05080", "#50A0C0", "#A0C050"]

LAKE = "./data/lake"
GLOB = f"'{LAKE}/**/*.parquet'"
DOW_LABELS   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def connect():
    return duckdb.connect()

def save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {path}")

def year_filter(years, prefix="AND"):
    if not years:
        return ""
    if len(years) == 1:
        return f"{prefix} year = {years[0]}"
    return f"{prefix} year BETWEEN {min(years)} AND {max(years)}"

def shade_covid(ax):
    ax.axvspan(2020 + 2/12, 2021 + 6/12, color=AMBER, alpha=0.10, zorder=0)

def to_time(year, month):
    return year + (month - 1) / 12

def print_section(title):
    print(f"\n── {title} ──")


# ══════════════════════════════════════════════════════════════════════════════
# MODE 1 — Airport
# ══════════════════════════════════════════════════════════════════════════════
def mode_airport(con, airport, years, outdir):
    yf    = year_filter(years)
    code  = airport.upper()
    yspan = f"{'–'.join(str(y) for y in ([min(years), max(years)] if years else []))  or '2018–2025'}"

    print(f"\n{'═'*55}\n  Airport: {code}  {yspan}\n{'═'*55}")

    summary = con.execute(f"""
        SELECT COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1)  AS mean_dep,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_dep,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_15,
               ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
        FROM {GLOB} WHERE origin='{code}' AND depdelay IS NOT NULL {yf}
    """).df()
    print_section("Summary")
    print(summary.T.to_string(header=False))

    top_routes = con.execute(f"""
        SELECT dest, destcityname AS city, COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(STDDEV(depdelay), 1) AS std_delay
        FROM {GLOB} WHERE origin='{code}' AND depdelay IS NOT NULL {yf}
        GROUP BY dest, destcityname HAVING COUNT(*) > 200
        ORDER BY flights DESC LIMIT 25
    """).df()

    by_carrier = con.execute(f"""
        SELECT iata_code_marketing_airline AS carrier,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
        FROM {GLOB} WHERE origin='{code}' AND depdelay IS NOT NULL {yf}
        GROUP BY carrier HAVING COUNT(*) > 500
        ORDER BY mean_delay DESC
    """).df()

    by_hour = con.execute(f"""
        SELECT FLOOR(crsdeptime / 100) AS dep_hour,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB} WHERE origin='{code}' AND depdelay IS NOT NULL
          AND crsdeptime BETWEEN 0 AND 2359 AND cancelled=0 {yf}
        GROUP BY dep_hour ORDER BY dep_hour
    """).df()

    by_year = con.execute(f"""
        SELECT year, COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
        FROM {GLOB} WHERE origin='{code}' AND depdelay IS NOT NULL {yf}
        GROUP BY year ORDER BY year
    """).df()

    by_month = con.execute(f"""
        SELECT month,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB} WHERE origin='{code}' AND depdelay IS NOT NULL AND cancelled=0 {yf}
        GROUP BY month ORDER BY month
    """).df()

    causes = con.execute(f"""
        SELECT ROUND(AVG(carrierdelay), 1) AS carrier,
               ROUND(AVG(weatherdelay), 1) AS weather,
               ROUND(AVG(nasdelay), 1) AS nas,
               ROUND(AVG(lateaircraftdelay), 1) AS late_aircraft
        FROM {GLOB} WHERE origin='{code}' AND depdelay > 15 {yf}
    """).df()

    fig = plt.figure(figsize=(20, 13))
    fig.suptitle(f"{code} Airport — Delay Overview  {yspan}", fontsize=15, fontweight="bold", y=1.01)
    gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35)

    # Top routes by volume
    ax = fig.add_subplot(gs[0, :2])
    top15v = top_routes.head(15)
    ax.barh(top15v["dest"][::-1], top15v["flights"][::-1] / 1000, color=BLUE, alpha=0.8)
    ax.set_xlabel("Flights (thousands)")
    ax.set_title("Top 15 destinations — volume")

    # Top routes by delay
    ax = fig.add_subplot(gs[0, 2:])
    top15d = top_routes.sort_values("mean_delay", ascending=False).head(15)
    colors_d = [CORAL if v > top_routes["mean_delay"].median() else TEAL for v in top15d["mean_delay"]]
    ax.barh(top15d["dest"][::-1], top15d["mean_delay"][::-1], color=colors_d[::-1], alpha=0.85)
    ax.set_xlabel("Mean departure delay (min)")
    ax.set_title("Top 15 destinations — delay")

    # By carrier
    ax = fig.add_subplot(gs[1, :2])
    cs = by_carrier.sort_values("mean_delay")
    colors_c = [CORAL if v > by_carrier["mean_delay"].median() else TEAL for v in cs["mean_delay"]]
    ax.barh(cs["carrier"], cs["mean_delay"], color=colors_c, alpha=0.85)
    ax.set_xlabel("Mean departure delay (min)")
    ax.set_title("Delay by carrier")

    # By hour
    ax = fig.add_subplot(gs[1, 2:])
    colors_h = [CORAL if v > 10 else BLUE for v in by_hour["mean_delay"]]
    ax.bar(by_hour["dep_hour"], by_hour["mean_delay"], color=colors_h, alpha=0.85)
    ax2 = ax.twinx()
    ax2.plot(by_hour["dep_hour"], by_hour["pct_delayed"], color=AMBER, lw=1.5, marker="o", ms=3)
    ax2.set_ylabel("% delayed >15 min", color=AMBER, fontsize=9)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(True)
    ax.set_xlabel("Departure hour"); ax.set_ylabel("Mean delay (min)")
    ax.set_title("Delay by hour of day"); ax.set_xticks(range(0, 24, 2))

    # Annual trend
    ax = fig.add_subplot(gs[2, :2])
    ax.plot(by_year["year"], by_year["mean_delay"], color=BLUE, lw=2, marker="o", ms=5)
    ax.fill_between(by_year["year"], by_year["mean_delay"], alpha=0.15, color=BLUE)
    shade_covid(ax)
    ax.set_ylabel("Mean delay (min)"); ax.set_title("Delay trend by year")
    ax.set_xticks(by_year["year"]); ax.tick_params(axis="x", rotation=45)

    # By month
    ax = fig.add_subplot(gs[2, 2:])
    ax.bar(by_month["month"], by_month["mean_delay"], color=PURPLE, alpha=0.8)
    ax.set_xticks(range(1, 13)); ax.set_xticklabels(MONTH_LABELS, fontsize=8)
    ax.set_ylabel("Mean delay (min)"); ax.set_title("Delay by month")

    save(fig, outdir, f"airport_{code}.png")

    print_section("Top 10 routes by delay")
    print(top_routes.sort_values("mean_delay", ascending=False).head(10)[
        ["dest","city","flights","mean_delay","pct_delayed","std_delay"]].to_string(index=False))
    print_section("Carriers")
    print(by_carrier.to_string(index=False))


# ══════════════════════════════════════════════════════════════════════════════
# MODE 2 — Route: all flights on this route compared
# ══════════════════════════════════════════════════════════════════════════════
def mode_route(con, origin, dests, years, outdir):
    yf   = year_filter(years)
    orig = origin.upper()
    dests = [d.upper() for d in dests]
    yspan = f"{'–'.join(str(y) for y in ([min(years), max(years)] if years else []))  or '2018–2025'}"

    for dest in dests:
        print(f"\n{'═'*55}\n  Route: {orig}→{dest}  {yspan}\n{'═'*55}")

        # ── All specific flights on this route ──────────────────────────────
        flights_on_route = con.execute(f"""
            SELECT
                iata_code_marketing_airline AS carrier,
                flight_number_marketing_airline AS flight_num,
                carrier || CAST(flight_number_marketing_airline AS VARCHAR) AS flight_label,
                COUNT(*) AS operated,
                ROUND(AVG(depdelay), 1) AS mean_delay,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_delay,
                ROUND(STDDEV(depdelay), 1) AS std_delay,
                ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
                ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY depdelay), 1) AS p90,
                ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct,
                ROUND(AVG(FLOOR(crsdeptime / 100)), 0) AS avg_dep_hour
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND depdelay IS NOT NULL {yf}
            GROUP BY carrier, flight_number_marketing_airline
            HAVING COUNT(*) > 100
            ORDER BY mean_delay DESC
        """).df()

        if flights_on_route.empty:
            print(f"  ✗ No data for {orig}→{dest}")
            continue

        print_section(f"All flights on {orig}→{dest} ranked by delay")
        print(flights_on_route.to_string(index=False))

        # Route-level summary
        route_summary = con.execute(f"""
            SELECT COUNT(*) AS total_flights,
                   ROUND(AVG(depdelay), 1) AS mean_delay,
                   ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
                   ROUND(100.0 * SUM(cancelled) / COUNT(*), 2) AS cancel_pct
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}' AND depdelay IS NOT NULL {yf}
        """).df()

        # Monthly trend for whole route
        route_monthly = con.execute(f"""
            SELECT year, month,
                   ROUND(AVG(depdelay), 1) AS mean_delay,
                   COUNT(*) AS flights
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND depdelay IS NOT NULL AND cancelled=0 {yf}
            GROUP BY year, month ORDER BY year, month
        """).df()
        route_monthly["time"] = route_monthly.apply(lambda r: to_time(r["year"], r["month"]), axis=1)

        # Delay distribution per flight (for violin/box)
        top_flights = flights_on_route.head(12)  # show top 12 by volume for readability
        flight_samples = {}
        for _, row in top_flights.iterrows():
            data = con.execute(f"""
                SELECT depdelay FROM {GLOB}
                WHERE origin='{orig}' AND dest='{dest}'
                  AND iata_code_marketing_airline='{row["carrier"]}'
                  AND flight_number_marketing_airline={int(row["flight_num"])}
                  AND depdelay IS NOT NULL AND cancelled=0 {yf}
                  AND depdelay BETWEEN -60 AND 300
            """).df()
            flight_samples[row["flight_label"]] = data["depdelay"].tolist()

        # Day of week for whole route
        route_dow = con.execute(f"""
            SELECT dayofweek,
                   ROUND(AVG(depdelay), 1) AS mean_delay,
                   ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND depdelay IS NOT NULL AND cancelled=0 {yf}
            GROUP BY dayofweek ORDER BY dayofweek
        """).df()

        # Hour of day for whole route
        route_hour = con.execute(f"""
            SELECT FLOOR(crsdeptime / 100) AS dep_hour,
                   ROUND(AVG(depdelay), 1) AS mean_delay,
                   ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
                   COUNT(*) AS flights
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND depdelay IS NOT NULL AND cancelled=0
              AND crsdeptime BETWEEN 0 AND 2359 {yf}
            GROUP BY dep_hour ORDER BY dep_hour
        """).df()

        # Per-flight delay by day of week
        flight_dow = con.execute(f"""
            SELECT iata_code_marketing_airline || CAST(flight_number_marketing_airline AS VARCHAR) AS flight_label,
                   dayofweek,
                   ROUND(AVG(depdelay), 1) AS mean_delay
            FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND depdelay IS NOT NULL AND cancelled=0 {yf}
              AND iata_code_marketing_airline || CAST(flight_number_marketing_airline AS VARCHAR)
                  IN ({', '.join([f"'{f}'" for f in top_flights['flight_label']])})
            GROUP BY flight_label, dayofweek
            ORDER BY flight_label, dayofweek
        """).df()

        # ── Plot ──────────────────────────────────────────────────────────
        fig = plt.figure(figsize=(20, 16))
        fig.suptitle(f"Route: {orig}→{dest}  {yspan}", fontsize=15, fontweight="bold", y=1.01)
        gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.50, wspace=0.35)

        # Flight ranking — mean delay
        ax = fig.add_subplot(gs[0, 0])
        fr = flights_on_route.sort_values("mean_delay", ascending=True).head(20)
        colors_f = [CORAL if v > flights_on_route["mean_delay"].median() else TEAL
                    for v in fr["mean_delay"]]
        ax.barh(fr["flight_label"], fr["mean_delay"], color=colors_f, alpha=0.85)
        ax.axvline(route_summary["mean_delay"].iloc[0], color=GRAY, lw=1, ls="--",
                   label=f"Route avg ({route_summary['mean_delay'].iloc[0]:.0f} min)")
        ax.set_xlabel("Mean dep delay (min)")
        ax.set_title("Flights ranked by mean delay")
        ax.legend(fontsize=8)

        # Flight ranking — % delayed
        ax = fig.add_subplot(gs[0, 1])
        fr2 = flights_on_route.sort_values("pct_delayed", ascending=True).head(20)
        ax.barh(fr2["flight_label"], fr2["pct_delayed"], color=PURPLE, alpha=0.8)
        ax.axvline(route_summary["pct_delayed"].iloc[0], color=GRAY, lw=1, ls="--",
                   label=f"Route avg ({route_summary['pct_delayed'].iloc[0]:.0f}%)")
        ax.set_xlabel("% flights delayed >15 min")
        ax.set_title("Flights ranked by % delayed")
        ax.legend(fontsize=8)

        # Flight ranking — std (consistency)
        ax = fig.add_subplot(gs[0, 2])
        fr3 = flights_on_route.sort_values("std_delay", ascending=True).head(20)
        ax.barh(fr3["flight_label"], fr3["std_delay"], color=AMBER, alpha=0.8)
        ax.set_xlabel("Std deviation of delay (min)")
        ax.set_title("Flights ranked by consistency\n(lower = more predictable)")

        # Box plot — delay distribution per flight
        ax = fig.add_subplot(gs[1, :2])
        labels  = list(flight_samples.keys())
        samples = [flight_samples[l] for l in labels]
        bp = ax.boxplot(samples, labels=labels, patch_artist=True,
                        medianprops=dict(color=CORAL, lw=2),
                        boxprops=dict(facecolor=BLUE, alpha=0.35),
                        flierprops=dict(marker=".", ms=1, alpha=0.15),
                        whis=[10, 90])
        ax.axhline(0, color=GRAY, lw=0.8, ls="--")
        ax.axhline(15, color=AMBER, lw=0.8, ls="--", alpha=0.6)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Departure delay (min)")
        ax.set_title("Delay distribution per flight (whiskers=p10/p90)")

        # Day of week heatmap per flight
        ax = fig.add_subplot(gs[1, 2])
        if not flight_dow.empty:
            try:
                dow_pivot = flight_dow.pivot(index="flight_label", columns="dayofweek", values="mean_delay")
                im = ax.imshow(dow_pivot.values, aspect="auto", cmap="RdYlGn_r")
                ax.set_xticks(range(7)); ax.set_xticklabels(DOW_LABELS, fontsize=8)
                ax.set_yticks(range(len(dow_pivot.index)))
                ax.set_yticklabels(dow_pivot.index, fontsize=7)
                ax.set_title("Mean delay: flight × day of week")
                plt.colorbar(im, ax=ax, shrink=0.8)
                for i in range(dow_pivot.values.shape[0]):
                    for j in range(dow_pivot.values.shape[1]):
                        val = dow_pivot.values[i, j]
                        if not np.isnan(val):
                            ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=6)
            except Exception:
                ax.set_visible(False)

        # Monthly trend (route-level)
        ax = fig.add_subplot(gs[2, :2])
        ax.plot(route_monthly["time"], route_monthly["mean_delay"],
                color=BLUE, lw=2, label="Route monthly avg")
        ax.fill_between(route_monthly["time"], route_monthly["mean_delay"], alpha=0.15, color=BLUE)
        shade_covid(ax)
        ax.set_ylabel("Mean dep delay (min)")
        ax.set_title(f"{orig}→{dest} — monthly delay trend")
        ax.legend(fontsize=9)
        ax.set_xticks(range(int(route_monthly["year"].min()), int(route_monthly["year"].max()) + 1))
        ax.set_xticklabels(range(int(route_monthly["year"].min()), int(route_monthly["year"].max()) + 1),
                            rotation=45, fontsize=8)

        # Hour of day for route
        ax = fig.add_subplot(gs[2, 2])
        colors_h = [CORAL if v > 10 else BLUE for v in route_hour["mean_delay"]]
        ax.bar(route_hour["dep_hour"], route_hour["mean_delay"], color=colors_h, alpha=0.85)
        ax.set_xlabel("Departure hour"); ax.set_ylabel("Mean delay (min)")
        ax.set_title("Delay by hour of day"); ax.set_xticks(range(0, 24, 3))

        save(fig, outdir, f"route_{orig}_{dest}.png")


# ══════════════════════════════════════════════════════════════════════════════
# MODE 3 — Flight number: deep dive + comparison against same route
# ══════════════════════════════════════════════════════════════════════════════
def mode_flight(con, carrier, flight_num, years, outdir):
    yf      = year_filter(years)
    carrier = carrier.upper()
    yspan   = f"{'–'.join(str(y) for y in ([min(years), max(years)] if years else []))  or '2018–2025'}"

    print(f"\n{'═'*55}\n  Flight: {carrier}{flight_num}  {yspan}\n{'═'*55}")

    # All route variants for this flight number
    variants = con.execute(f"""
        SELECT origin, dest, destcityname AS city,
               COUNT(*) AS flights,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
        FROM {GLOB}
        WHERE iata_code_marketing_airline='{carrier}'
          AND flight_number_marketing_airline={flight_num}
          AND depdelay IS NOT NULL {yf}
        GROUP BY origin, dest, destcityname HAVING COUNT(*) > 50
        ORDER BY flights DESC
    """).df()

    if variants.empty:
        print(f"  ✗ No data for {carrier}{flight_num}.")
        return

    print_section("Route variants for this flight number")
    print(variants.to_string(index=False))

    # Deep dive on primary (highest-volume) variant
    target = variants.iloc[0]
    orig, dest = target["origin"], target["dest"]
    flight_label = f"{carrier}{flight_num}"
    print(f"\n  Deep dive: {flight_label}  {orig}→{dest}  ({int(target['flights']):,} flights)")

    # This specific flight's history
    history = con.execute(f"""
        SELECT year, month, dayofmonth, dayofweek, flightdate,
               crsdeptime, depdelay, arrdelay,
               carrierdelay, weatherdelay, nasdelay, lateaircraftdelay,
               tail_number
        FROM {GLOB}
        WHERE iata_code_marketing_airline='{carrier}'
          AND flight_number_marketing_airline={flight_num}
          AND origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL {yf}
        ORDER BY year, month, dayofmonth
    """).df()
    history["time"] = history.apply(lambda r: to_time(r["year"], r["month"]), axis=1)

    # ALL other flights on the same route (for comparison)
    all_on_route = con.execute(f"""
        SELECT iata_code_marketing_airline AS carrier,
               flight_number_marketing_airline AS flight_num,
               iata_code_marketing_airline || CAST(flight_number_marketing_airline AS VARCHAR) AS flight_label,
               COUNT(*) AS operated,
               ROUND(AVG(depdelay), 1) AS mean_delay,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_delay,
               ROUND(STDDEV(depdelay), 1) AS std_delay,
               ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed,
               ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY depdelay), 1) AS p90,
               ROUND(AVG(FLOOR(crsdeptime / 100)), 0) AS avg_dep_hour
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL {yf}
        GROUP BY carrier, flight_number_marketing_airline
        HAVING COUNT(*) > 100
        ORDER BY mean_delay ASC
    """).df()

    # Mark which row is our target flight
    all_on_route["is_target"] = (
        (all_on_route["carrier"] == carrier) &
        (all_on_route["flight_num"] == flight_num)
    )

    print_section(f"All flights on {orig}→{dest} — where does {flight_label} rank?")
    print(all_on_route.to_string(index=False))

    target_rank = all_on_route[all_on_route["is_target"]].index
    if not target_rank.empty:
        rank_pos = all_on_route.index.get_loc(target_rank[0]) + 1
        print(f"\n  {flight_label} ranks #{rank_pos} of {len(all_on_route)} flights on this route (by mean delay)")

    # Monthly avg for this flight
    monthly = history.groupby(["year","month"]).agg(
        mean_delay=("depdelay","mean"),
        flights=("depdelay","count"),
        pct_delayed=("depdelay", lambda x: (x > 15).mean() * 100)
    ).reset_index()
    monthly["time"] = monthly.apply(lambda r: to_time(r["year"], r["month"]), axis=1)

    # Route-level monthly (for comparison overlay)
    route_monthly = con.execute(f"""
        SELECT year, month, ROUND(AVG(depdelay), 1) AS mean_delay
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}'
          AND depdelay IS NOT NULL AND cancelled=0 {yf}
        GROUP BY year, month ORDER BY year, month
    """).df()
    route_monthly["time"] = route_monthly.apply(lambda r: to_time(r["year"], r["month"]), axis=1)

    # Day of week
    dow = history.groupby("dayofweek").agg(
        mean_delay=("depdelay","mean"),
        pct_delayed=("depdelay", lambda x: (x > 15).mean() * 100)
    ).reset_index()

    # Causes
    cause_cols = ["carrierdelay","weatherdelay","nasdelay","lateaircraftdelay"]
    this_causes  = history[history["depdelay"] > 15][cause_cols].mean()
    route_causes = con.execute(f"""
        SELECT ROUND(AVG(carrierdelay), 1) AS carrierdelay,
               ROUND(AVG(weatherdelay), 1) AS weatherdelay,
               ROUND(AVG(nasdelay), 1) AS nasdelay,
               ROUND(AVG(lateaircraftdelay), 1) AS lateaircraftdelay
        FROM {GLOB}
        WHERE origin='{orig}' AND dest='{dest}' AND depdelay > 15 {yf}
    """).df().iloc[0]

    # Delay samples for this flight vs best/worst on route
    best_flight  = all_on_route[~all_on_route["is_target"]].iloc[-1]  # lowest mean delay
    worst_flight = all_on_route[~all_on_route["is_target"]].iloc[0]   # highest mean delay

    comparison_flights = {
        f"Best: {best_flight['flight_label']}":   (best_flight["carrier"],  int(best_flight["flight_num"])),
        f"{flight_label} (this)":                 (carrier, flight_num),
        f"Worst: {worst_flight['flight_label']}": (worst_flight["carrier"], int(worst_flight["flight_num"])),
    }
    comparison_samples = {}
    for label, (c, fn) in comparison_flights.items():
        data = con.execute(f"""
            SELECT depdelay FROM {GLOB}
            WHERE origin='{orig}' AND dest='{dest}'
              AND iata_code_marketing_airline='{c}'
              AND flight_number_marketing_airline={fn}
              AND depdelay IS NOT NULL AND cancelled=0 {yf}
              AND depdelay BETWEEN -60 AND 300
        """).df()
        comparison_samples[label] = data["depdelay"].tolist()

    # ── Plot ──────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 17))
    fig.suptitle(f"{flight_label}: {orig}→{dest}  {yspan}\nvs all {len(all_on_route)} flights on same route",
                 fontsize=14, fontweight="bold", y=1.01)
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.50, wspace=0.38)

    # Route ranking — highlight target flight
    ax = fig.add_subplot(gs[0, :2])
    all_sorted = all_on_route.sort_values("mean_delay", ascending=True)
    bar_colors = [CORAL if row["is_target"] else
                  (TEAL if row["mean_delay"] < all_on_route["mean_delay"].median() else BLUE)
                  for _, row in all_sorted.iterrows()]
    bars = ax.barh(all_sorted["flight_label"], all_sorted["mean_delay"],
                   color=bar_colors, alpha=0.85)
    ax.set_xlabel("Mean dep delay (min)")
    ax.set_title(f"All flights on {orig}→{dest} — {flight_label} highlighted in red")
    # Add arrow to target
    if not all_on_route[all_on_route["is_target"]].empty:
        target_val = all_on_route[all_on_route["is_target"]]["mean_delay"].iloc[0]
        target_lbl = flight_label
        ax.annotate(f"← {flight_label}",
                    xy=(target_val, list(all_sorted["flight_label"]).index(target_lbl)),
                    fontsize=8, color=CORAL, va="center")

    # % delayed ranking
    ax = fig.add_subplot(gs[0, 2])
    all_sorted2 = all_on_route.sort_values("pct_delayed", ascending=True)
    bar_colors2 = [CORAL if row["is_target"] else PURPLE for _, row in all_sorted2.iterrows()]
    ax.barh(all_sorted2["flight_label"], all_sorted2["pct_delayed"],
            color=bar_colors2, alpha=0.8)
    ax.set_xlabel("% flights delayed >15 min")
    ax.set_title("% delayed ranking")

    # Distribution comparison: this flight vs best vs worst
    ax = fig.add_subplot(gs[1, :2])
    labels  = list(comparison_samples.keys())
    samples = [comparison_samples[l] for l in labels]
    bp = ax.boxplot(samples, labels=labels, patch_artist=True,
                    medianprops=dict(color="white", lw=2),
                    whis=[10, 90])
    box_colors = [TEAL, CORAL, BLUE]
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color); patch.set_alpha(0.5)
    ax.axhline(0,  color=GRAY, lw=0.8, ls="--")
    ax.axhline(15, color=AMBER, lw=0.8, ls="--", alpha=0.7, label="+15 min")
    ax.set_ylabel("Departure delay (min)")
    ax.set_title(f"Delay distribution: {flight_label} vs best & worst on route (whiskers=p10/p90)")
    ax.legend(fontsize=8)

    # Day of week
    ax = fig.add_subplot(gs[1, 2])
    colors_dow = [CORAL if v > dow["mean_delay"].median() else TEAL for v in dow["mean_delay"]]
    tick_lbl = [DOW_LABELS[int(d)-1] for d in dow["dayofweek"]]
    ax.bar(range(len(dow)), dow["mean_delay"], color=colors_dow, alpha=0.85)
    ax.set_xticks(range(len(dow))); ax.set_xticklabels(tick_lbl)
    ax.set_ylabel("Mean dep delay (min)")
    ax.set_title(f"Delay by day of week")

    # Monthly trend: this flight vs route avg
    ax = fig.add_subplot(gs[2, :2])
    ax.fill_between(route_monthly["time"], route_monthly["mean_delay"],
                    alpha=0.12, color=GRAY, label="Route avg")
    ax.plot(route_monthly["time"], route_monthly["mean_delay"],
            color=GRAY, lw=1, ls="--")
    ax.plot(monthly["time"], monthly["mean_delay"],
            color=CORAL, lw=2, marker="o", ms=3, label=f"{flight_label} monthly avg")
    shade_covid(ax)
    ax.set_ylabel("Mean dep delay (min)")
    ax.set_title(f"{flight_label} vs route average — monthly trend")
    ax.legend(fontsize=9)
    ax.set_xticks(range(int(monthly["year"].min()), int(monthly["year"].max()) + 1))
    ax.set_xticklabels(range(int(monthly["year"].min()), int(monthly["year"].max()) + 1),
                        rotation=45, fontsize=8)

    # Cause comparison: this flight vs route
    ax = fig.add_subplot(gs[2, 2])
    cause_labels = ["Carrier","Weather","NAS","Late A/C"]
    x = np.arange(len(cause_labels)); w = 0.35
    ax.bar(x - w/2, this_causes.fillna(0).values,  width=w, color=CORAL, alpha=0.85, label=flight_label)
    ax.bar(x + w/2, route_causes.fillna(0).values, width=w, color=BLUE,  alpha=0.65, label="Route avg")
    ax.set_xticks(x); ax.set_xticklabels(cause_labels, fontsize=9)
    ax.set_ylabel("Avg min (delayed flights only)")
    ax.set_title("Delay causes: this flight vs route avg")
    ax.legend(fontsize=9)

    save(fig, outdir, f"flight_{carrier}{flight_num}.png")

    # Print full delay scatter
    print_section("Distribution summary")
    q = history["depdelay"]
    print(f"  mean={q.mean():.1f}  median={q.median():.0f}  "
          f"p90={q.quantile(0.9):.0f}  p99={q.quantile(0.99):.0f}  "
          f"std={q.std():.1f}  "
          f"% >15min={(q > 15).mean()*100:.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(
        description="Flight delay explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/explore.py --airport SFO
  python scripts/explore.py --airport ORD --year 2022 2023
  python scripts/explore.py --origin SFO --dest JFK
  python scripts/explore.py --origin SFO --dest JFK LAX ORD
  python scripts/explore.py --origin SFO --dest JFK --year 2019 2025
  python scripts/explore.py --carrier UA --flight 1
  python scripts/explore.py --carrier DL --flight 400 --year 2023
        """
    )
    p.add_argument("--airport",  type=str,           help="Airport code (e.g. SFO)")
    p.add_argument("--origin",   type=str,           help="Origin airport for route mode")
    p.add_argument("--dest",     type=str, nargs="+",help="Destination(s) for route mode")
    p.add_argument("--carrier",  type=str,           help="Carrier IATA code (e.g. UA, DL)")
    p.add_argument("--flight",   type=int,           help="Flight number (e.g. 1, 400)")
    p.add_argument("--year",     type=int, nargs="+",help="Year(s): one value or two for range")
    p.add_argument("--out",      type=str,           default="./docs/explore",
                                                      help="Output folder for charts")
    return p.parse_args()

def main():
    args = parse_args()
    con  = connect()

    if not os.path.exists(LAKE):
        print(f"✗ Lake not found at {LAKE}. Run scripts/download_bts.py first.")
        sys.exit(1)

    if args.origin and args.dest:
        mode_route(con, args.origin, args.dest, args.year or [], args.out)
    elif args.airport:
        mode_airport(con, args.airport, args.year or [], args.out)
    elif args.carrier and args.flight is not None:
        mode_flight(con, args.carrier, args.flight, args.year or [], args.out)
    else:
        print("✗ Provide one of:\n"
              "  --airport CODE\n"
              "  --origin CODE --dest CODE [CODE ...]\n"
              "  --carrier CODE --flight NUMBER")
        sys.exit(1)

    print(f"\n  Charts saved to: {args.out}/")

if __name__ == "__main__":
    main()