"""
EDA Thread B — Predictability of a Specific Flight
====================================================
Run from your project root:
    python scripts/eda_thread_b.py

Outputs saved to: docs/eda_thread_b/
  - b1_route_consistency.png
  - b2_historical_predictability.png
  - b3_aircraft_cascade.png
  - b4_route_dow_heatmap.png
  - b5_safe_booking_window.png
  - findings.md
"""

import os
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Setup ─────────────────────────────────────────────────────────────────────
LAKE   = "./data/lake"
OUTDIR = "./docs/eda_thread_b"
GLOB   = f"'{LAKE}/**/*.parquet'"

os.makedirs(OUTDIR, exist_ok=True)
con = duckdb.connect()

findings = []

def save(fig, name):
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ saved {name}")

def note(text):
    print(f"  📝 {text}")
    findings.append(text)

plt.rcParams.update({
    "figure.facecolor":  "#FAFAFA",
    "axes.facecolor":    "#FAFAFA",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "font.family":       "sans-serif",
    "axes.labelsize":    11,
    "axes.titlesize":    13,
    "axes.titleweight":  "bold",
})

BLUE   = "#378ADD"
AMBER  = "#BA7517"
CORAL  = "#D85A30"
TEAL   = "#1D9E75"
PURPLE = "#7F77DD"
GRAY   = "#888780"

# Top routes to analyze throughout this thread
TOP_ROUTES_QUERY = f"""
    SELECT origin || '-' || dest AS route, origin, dest, COUNT(*) AS flights
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY origin, dest
    HAVING COUNT(*) > 50000
    ORDER BY flights DESC
    LIMIT 12
"""

print("\n" + "═"*60)
print("  EDA Thread B — Predictability of a Specific Flight")
print("═"*60)

top_routes = con.execute(TOP_ROUTES_QUERY).df()
print(f"\n  Analyzing top {len(top_routes)} routes by volume:")
print(top_routes[["route","flights"]].to_string(index=False))


# ════════════════════════════════════════════════════════════
# B1 — Route consistency: how variable is delay on a given route?
# ════════════════════════════════════════════════════════════
print("\n── B1: Route consistency ──")

route_stats = con.execute(f"""
    SELECT
        origin || '-' || dest                                               AS route,
        COUNT(*)                                                             AS flights,
        ROUND(AVG(depdelay), 2)                                              AS mean_delay,
        ROUND(STDDEV(depdelay), 2)                                           AS std_delay,
        ROUND(PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY depdelay), 1)    AS p10,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY depdelay), 1)    AS p25,
        ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY depdelay), 1)    AS median,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY depdelay), 1)    AS p75,
        ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY depdelay), 1)    AS p90,
        ROUND(STDDEV(depdelay) / NULLIF(AVG(depdelay) + 15, 0), 3)         AS coeff_variation
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY origin, dest
    HAVING COUNT(*) > 50000
    ORDER BY std_delay DESC
""").df()

most_variable   = route_stats.iloc[0]
least_variable  = route_stats.loc[route_stats["std_delay"].idxmin()]
note(f"Most variable route: {most_variable['route']} (std={most_variable['std_delay']:.1f} min, mean={most_variable['mean_delay']:.1f} min)")
note(f"Most consistent route: {least_variable['route']} (std={least_variable['std_delay']:.1f} min, mean={least_variable['mean_delay']:.1f} min)")

# Box plot of delay distribution for top routes
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("B1 — Route delay consistency", y=1.01)

# Fetch raw delay samples for top routes for boxplot
route_delays = {}
for _, row in top_routes.iterrows():
    data = con.execute(f"""
        SELECT depdelay FROM {GLOB}
        WHERE origin='{row['origin']}' AND dest='{row['dest']}'
          AND depdelay IS NOT NULL AND cancelled=0
          AND depdelay BETWEEN -30 AND 300
        USING SAMPLE 20000
    """).df()
    route_delays[row["route"]] = data["depdelay"].tolist()

bp = axes[0].boxplot(
    [route_delays[r] for r in top_routes["route"]],
    labels=top_routes["route"],
    patch_artist=True,
    medianprops=dict(color=CORAL, lw=2),
    boxprops=dict(facecolor=BLUE, alpha=0.4),
    flierprops=dict(marker=".", ms=1, alpha=0.2),
    whis=[10, 90]
)
axes[0].set_xticklabels(top_routes["route"], rotation=45, ha="right", fontsize=8)
axes[0].axhline(0, color=GRAY, lw=0.8, ls="--")
axes[0].set_ylabel("Departure delay (min, clipped at 300)")
axes[0].set_title("Delay spread per route (whiskers = p10/p90)")

# Scatter: mean vs std — predictability quadrant
axes[1].scatter(route_stats["mean_delay"], route_stats["std_delay"],
                alpha=0.4, color=PURPLE, s=15, edgecolors="none")
# Highlight top routes
for _, row in top_routes.iterrows():
    match = route_stats[route_stats["route"] == row["route"]]
    if not match.empty:
        r = match.iloc[0]
        axes[1].scatter(r["mean_delay"], r["std_delay"], color=CORAL, s=60, zorder=5)
        axes[1].annotate(r["route"], (r["mean_delay"], r["std_delay"]),
                         fontsize=7, ha="left", va="bottom")

med_mean = route_stats["mean_delay"].median()
med_std  = route_stats["std_delay"].median()
axes[1].axvline(med_mean, color=GRAY, lw=0.8, ls="--", alpha=0.6)
axes[1].axhline(med_std,  color=GRAY, lw=0.8, ls="--", alpha=0.6)
axes[1].set_xlabel("Mean delay (min)")
axes[1].set_ylabel("Std deviation (min)")
axes[1].set_title("Predictability quadrant\n(lower-left = low delay + consistent)")

# Annotate quadrants
axes[1].text(med_mean*0.1, med_std*1.05, "Low delay\nHigh variance", fontsize=7, color=GRAY)
axes[1].text(med_mean*1.1, med_std*1.05, "High delay\nHigh variance", fontsize=7, color=CORAL)
axes[1].text(med_mean*0.1, med_std*0.1,  "Low delay\nConsistent ✓", fontsize=7, color=TEAL)
axes[1].text(med_mean*1.1, med_std*0.1,  "High delay\nConsistent", fontsize=7, color=AMBER)

plt.tight_layout()
save(fig, "b1_route_consistency.png")


# ════════════════════════════════════════════════════════════
# B2 — Does historical delay predict future delay?
# ════════════════════════════════════════════════════════════
print("\n── B2: Historical predictability ──")

# For each top route: monthly avg delay — does it correlate month-to-month?
monthly_route = con.execute(f"""
    SELECT
        origin || '-' || dest AS route,
        year,
        month,
        ROUND(AVG(depdelay), 2) AS avg_delay,
        COUNT(*) AS flights
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY origin, dest, year, month
    ORDER BY origin, dest, year, month
""").df()

fig, axes = plt.subplots(3, 4, figsize=(18, 12), sharex=False)
fig.suptitle("B2 — Monthly delay trend per route (2018–2025)\nConsistency = predictability", y=1.01)
axes_flat = axes.flatten()

correlations = []
for idx, (_, row) in enumerate(top_routes.iterrows()):
    if idx >= 12:
        break
    ax = axes_flat[idx]
    route_data = monthly_route[monthly_route["route"] == row["route"]].copy()
    route_data["time_idx"] = route_data["year"] * 12 + route_data["month"]
    route_data = route_data.sort_values("time_idx")

    # Lag-1 autocorrelation (does last month predict this month?)
    if len(route_data) > 2:
        ac = route_data["avg_delay"].autocorr(lag=1)
        correlations.append({"route": row["route"], "lag1_autocorr": round(ac, 3)})
    else:
        ac = float("nan")

    ax.plot(route_data["time_idx"], route_data["avg_delay"],
            color=BLUE, lw=1.2, alpha=0.8)
    ax.fill_between(route_data["time_idx"], route_data["avg_delay"],
                    alpha=0.15, color=BLUE)
    ax.axhline(route_data["avg_delay"].mean(), color=CORAL, lw=0.8, ls="--")

    # Mark COVID period
    covid_start = 2020 * 12 + 3
    covid_end   = 2021 * 12 + 6
    ax.axvspan(covid_start, covid_end, color=AMBER, alpha=0.12, label="COVID")

    ax.set_title(f"{row['route']}  (r={ac:.2f})", fontsize=9)
    ax.set_ylabel("Avg dep delay", fontsize=8)
    ax.tick_params(labelsize=7)

    # X-axis: year labels
    year_ticks = [y * 12 + 1 for y in range(2018, 2026)]
    ax.set_xticks(year_ticks)
    ax.set_xticklabels([str(y) for y in range(2018, 2026)], rotation=45, fontsize=6)

plt.tight_layout()
save(fig, "b2_historical_predictability.png")

if correlations:
    corr_df = pd.DataFrame(correlations)
    best  = corr_df.loc[corr_df["lag1_autocorr"].idxmax()]
    worst = corr_df.loc[corr_df["lag1_autocorr"].idxmin()]
    note(f"Highest month-to-month autocorrelation: {best['route']} (r={best['lag1_autocorr']:.3f}) — most predictable from history")
    note(f"Lowest autocorrelation: {worst['route']} (r={worst['lag1_autocorr']:.3f}) — least predictable")
    note(f"Mean lag-1 autocorrelation across top routes: {corr_df['lag1_autocorr'].mean():.3f}")


# ════════════════════════════════════════════════════════════
# B3 — Do delays cascade within a day? (aircraft propagation)
# ════════════════════════════════════════════════════════════
print("\n── B3: Aircraft delay cascade ──")

# Late aircraft delay as % of total delay, by departure hour
cascade = con.execute(f"""
    SELECT
        FLOOR(crsdeptime / 100) AS dep_hour,
        COUNT(*)                AS flights,
        ROUND(AVG(depdelay), 2) AS avg_total_delay,
        ROUND(AVG(lateaircraftdelay), 2) AS avg_late_aircraft,
        ROUND(100.0 * AVG(lateaircraftdelay) / NULLIF(AVG(depdelay), 0), 1) AS late_ac_pct_of_total
    FROM {GLOB}
    WHERE depdelay > 15
      AND lateaircraftdelay IS NOT NULL
      AND crsdeptime IS NOT NULL
      AND crsdeptime BETWEEN 0 AND 2359
    GROUP BY dep_hour
    ORDER BY dep_hour
""").df()

# Correlation between earlier and later flights on same tail number (sampled)
tail_cascade = con.execute(f"""
    WITH ordered AS (
        SELECT
            tail_number,
            flightdate,
            crsdeptime,
            depdelay,
            lateaircraftdelay,
            ROW_NUMBER() OVER (PARTITION BY tail_number, flightdate ORDER BY crsdeptime) AS leg
        FROM {GLOB}
        WHERE depdelay IS NOT NULL
          AND tail_number IS NOT NULL
          AND cancelled = 0
        USING SAMPLE 5%
    )
    SELECT
        a.depdelay AS leg1_delay,
        b.depdelay AS leg2_delay,
        b.lateaircraftdelay AS leg2_late_aircraft
    FROM ordered a
    JOIN ordered b
      ON a.tail_number = b.tail_number
      AND a.flightdate = b.flightdate
      AND b.leg = a.leg + 1
    WHERE a.depdelay IS NOT NULL AND b.depdelay IS NOT NULL
""").df()

if len(tail_cascade) > 0:
    corr = tail_cascade["leg1_delay"].corr(tail_cascade["leg2_delay"])
    note(f"Leg-to-leg delay correlation (same tail number, same day): r={corr:.3f}")
    note(f"When leg 1 delayed >30 min, leg 2 avg delay: {tail_cascade[tail_cascade['leg1_delay']>30]['leg2_delay'].mean():.1f} min")
    note(f"When leg 1 on time (<5 min), leg 2 avg delay: {tail_cascade[tail_cascade['leg1_delay']<5]['leg2_delay'].mean():.1f} min")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("B3 — Delay cascade: does a delayed aircraft propagate delays?", y=1.01)

axes[0].bar(cascade["dep_hour"], cascade["avg_total_delay"],
            color=BLUE, alpha=0.6, label="Total delay")
axes[0].bar(cascade["dep_hour"], cascade["avg_late_aircraft"],
            color=CORAL, alpha=0.8, label="Late aircraft portion")
axes[0].set_xlabel("Departure hour")
axes[0].set_ylabel("Avg delay (min, delayed flights only)")
axes[0].set_title("Late aircraft delay grows through the day")
axes[0].legend()

if len(tail_cascade) > 100:
    sample = tail_cascade.sample(min(5000, len(tail_cascade)))
    axes[1].hexbin(sample["leg1_delay"].clip(-30, 200),
                   sample["leg2_delay"].clip(-30, 200),
                   gridsize=40, cmap="Blues", mincnt=1)
    axes[1].axhline(0, color=GRAY, lw=0.8, ls="--")
    axes[1].axvline(0, color=GRAY, lw=0.8, ls="--")
    axes[1].set_xlabel("Leg 1 departure delay (min)")
    axes[1].set_ylabel("Leg 2 departure delay (min)")
    axes[1].set_title(f"Same aircraft: leg 1 → leg 2 delay\n(r={corr:.3f})")

plt.tight_layout()
save(fig, "b3_aircraft_cascade.png")


# ════════════════════════════════════════════════════════════
# B4 — Route × day-of-week heatmap
# ════════════════════════════════════════════════════════════
print("\n── B4: Route × day-of-week ──")

route_dow = con.execute(f"""
    SELECT
        origin || '-' || dest AS route,
        dayofweek,
        ROUND(AVG(depdelay), 2) AS avg_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
      AND origin || '-' || dest IN ({', '.join([f"'{r}'" for r in top_routes['route']])})
    GROUP BY origin, dest, dayofweek
    ORDER BY origin, dest, dayofweek
""").df()

pivot = route_dow.pivot(index="route", columns="dayofweek", values="avg_delay")
pivot_pct = route_dow.pivot(index="route", columns="dayofweek", values="pct_delayed")
dow_labels = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("B4 — Delay by route × day of week", y=1.01)

im1 = axes[0].imshow(pivot.values, aspect="auto", cmap="RdYlGn_r")
axes[0].set_xticks(range(7))
axes[0].set_xticklabels(dow_labels)
axes[0].set_yticks(range(len(pivot.index)))
axes[0].set_yticklabels(pivot.index, fontsize=8)
axes[0].set_title("Mean departure delay (min)")
plt.colorbar(im1, ax=axes[0], shrink=0.8)

for i in range(pivot.values.shape[0]):
    for j in range(pivot.values.shape[1]):
        val = pivot.values[i, j]
        if not np.isnan(val):
            axes[0].text(j, i, f"{val:.0f}", ha="center", va="center",
                         fontsize=7, color="black")

im2 = axes[1].imshow(pivot_pct.values, aspect="auto", cmap="RdYlGn_r")
axes[1].set_xticks(range(7))
axes[1].set_xticklabels(dow_labels)
axes[1].set_yticks(range(len(pivot_pct.index)))
axes[1].set_yticklabels(pivot_pct.index, fontsize=8)
axes[1].set_title("% flights delayed >15 min")
plt.colorbar(im2, ax=axes[1], shrink=0.8)

for i in range(pivot_pct.values.shape[0]):
    for j in range(pivot_pct.values.shape[1]):
        val = pivot_pct.values[i, j]
        if not np.isnan(val):
            axes[1].text(j, i, f"{val:.0f}%", ha="center", va="center",
                         fontsize=7, color="black")

plt.tight_layout()
save(fig, "b4_route_dow_heatmap.png")

# Which route has the most day-of-week variation?
route_dow_var = route_dow.groupby("route")["avg_delay"].std().sort_values(ascending=False)
note(f"Route most sensitive to day of week: {route_dow_var.index[0]} (std across days = {route_dow_var.iloc[0]:.1f} min)")
note(f"Route least sensitive to day of week: {route_dow_var.index[-1]} (std = {route_dow_var.iloc[-1]:.1f} min)")


# ════════════════════════════════════════════════════════════
# B5 — Safe booking window: risk by departure hour
# ════════════════════════════════════════════════════════════
print("\n── B5: Safe booking window ──")

booking = con.execute(f"""
    SELECT
        FLOOR(crsdeptime / 100)                                              AS dep_hour,
        COUNT(*)                                                              AS flights,
        ROUND(AVG(depdelay), 2)                                              AS mean_delay,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY depdelay), 1)    AS p25,
        ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY depdelay), 1)    AS median,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY depdelay), 1)    AS p75,
        ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY depdelay), 1)    AS p90,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15  THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_15,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 30  THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_30,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 60  THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_60,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 120 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_120
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
      AND crsdeptime IS NOT NULL
      AND crsdeptime BETWEEN 0 AND 2359
      AND cancelled = 0
    GROUP BY dep_hour
    ORDER BY dep_hour
""").df()

safest_hour = booking.loc[booking["pct_15"].idxmin()]
riskiest    = booking.loc[booking["pct_15"].idxmax()]
note(f"Safest departure hour: {int(safest_hour['dep_hour']):02d}:00 — {safest_hour['pct_15']:.1f}% flights delayed >15 min")
note(f"Riskiest departure hour: {int(riskiest['dep_hour']):02d}:00 — {riskiest['pct_15']:.1f}% flights delayed >15 min")

fig, axes = plt.subplots(2, 1, figsize=(13, 9))
fig.suptitle("B5 — Risk by departure hour: the 'safe booking window'", y=1.01)

# Top: mean + IQR band
axes[0].fill_between(booking["dep_hour"], booking["p25"], booking["p75"],
                     alpha=0.2, color=BLUE, label="IQR (p25–p75)")
axes[0].fill_between(booking["dep_hour"], booking["p25"], booking["p90"],
                     alpha=0.1, color=CORAL, label="p75–p90 range")
axes[0].plot(booking["dep_hour"], booking["median"],
             color=BLUE, lw=2, label="Median delay")
axes[0].plot(booking["dep_hour"], booking["mean_delay"],
             color=CORAL, lw=1.5, ls="--", label="Mean delay")
axes[0].axhline(0, color=GRAY, lw=0.8, ls=":")
axes[0].set_ylabel("Departure delay (min)")
axes[0].set_title("Delay distribution by hour (median + IQR bands)")
axes[0].legend(fontsize=9)
axes[0].set_xticks(range(0, 24))
axes[0].set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45, ha="right", fontsize=8)

# Bottom: % delayed at different thresholds
axes[1].plot(booking["dep_hour"], booking["pct_15"],
             color=AMBER,  lw=2,   marker="o", ms=4, label=">15 min")
axes[1].plot(booking["dep_hour"], booking["pct_30"],
             color=CORAL,  lw=1.8, marker="o", ms=3, label=">30 min")
axes[1].plot(booking["dep_hour"], booking["pct_60"],
             color=PURPLE, lw=1.5, marker="o", ms=3, label=">60 min")
axes[1].plot(booking["dep_hour"], booking["pct_120"],
             color=GRAY,   lw=1.2, marker="o", ms=2, label=">2 hours", ls="--")

# Shade the "safe window" (hours with <15% of flights delayed >15 min)
safe_hours = booking[booking["pct_15"] < 15]["dep_hour"]
if len(safe_hours) > 0:
    axes[1].axvspan(safe_hours.min(), safe_hours.max(),
                    alpha=0.08, color=TEAL, label=f"Safe window (<15% delayed)")

axes[1].set_xlabel("Scheduled departure hour")
axes[1].set_ylabel("% of flights delayed")
axes[1].set_title("Delay risk at different thresholds by hour")
axes[1].legend(fontsize=9)
axes[1].set_xticks(range(0, 24))
axes[1].set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45, ha="right", fontsize=8)

plt.tight_layout()
save(fig, "b5_safe_booking_window.png")


# ════════════════════════════════════════════════════════════
# Save findings.md
# ════════════════════════════════════════════════════════════
findings_path = os.path.join(OUTDIR, "findings.md")
with open(findings_path, "w") as f:
    f.write("# EDA Thread B — Key findings\n\n")
    f.write("## Core research question\n")
    f.write("Can the delay history of a specific route predict future delay?\n\n")
    f.write("## Findings\n\n")
    for i, finding in enumerate(findings, 1):
        f.write(f"{i}. {finding}\n")
    f.write("\n## Story angles to develop\n")
    f.write("- The cascade effect: one late plane ripples through the whole day\n")
    f.write("- The safe booking window: what time should you fly?\n")
    f.write("- Route personality: some routes are reliably bad, others unpredictably bad\n")
    f.write("\n---\n*Auto-generated by eda_thread_b.py — annotate and expand into your story brief.*\n")

print(f"\n✅ Thread B complete.")
print(f"   Charts: {OUTDIR}/")
print(f"   Findings: {findings_path}")