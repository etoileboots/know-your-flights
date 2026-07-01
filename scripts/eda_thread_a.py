"""
EDA Thread A — Structural Patterns in Flight Delay
====================================================

Outputs saved to: docs/eda_thread_a/
  - a1_delay_distribution.png
  - a2_carrier_ranking.png
  - a3_airport_hotspots.png
  - a4_hour_of_day.png
  - a5_seasonal_heatmap.png
  - a6_delay_causes.png
  - findings.md  ← human-readable story notes, auto-populated

Each section prints key statistics and saves a chart.
"""

import os
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Setup ─────────────────────────────────────────────────────────────────────
LAKE    = "./data/lake"
OUTDIR  = "./docs/eda_thread_a"
GLOB    = f"'{LAKE}/**/*.parquet'"

os.makedirs(OUTDIR, exist_ok=True)
con = duckdb.connect()

findings = []  # collects auto-written story notes

def save(fig, name):
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ saved {name}")

def note(text):
    print(f"  📝 {text}")
    findings.append(text)

# ── Shared style ──────────────────────────────────────────────────────────────
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

print("\n" + "═"*60)
print("  EDA Thread A — Structural Patterns in Flight Delay")
print("═"*60)


# ════════════════════════════════════════════════════════════
# A1 — Delay distribution
# ════════════════════════════════════════════════════════════
print("\n── A1: Delay distribution ──")

dist = con.execute(f"""
    SELECT depdelay
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
      AND cancelled = 0
    USING SAMPLE 5%
""").df()

stats = dist["depdelay"].describe(percentiles=[.25,.5,.75,.90,.95,.99])
note(f"Departure delay: median={stats['50%']:.1f} min, mean={stats['mean']:.1f} min, p95={stats['95%']:.1f} min, p99={stats['99%']:.1f} min")
note(f"Distribution shape: min={stats['min']:.0f} min (early), max={stats['max']:.0f} min")

delayed_pct = con.execute(f"""
    SELECT ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
""").fetchone()[0]
note(f"{delayed_pct}% of flights depart more than 15 minutes late")

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
fig.suptitle("A1 — Departure delay distribution", y=1.01)

# Left: full distribution
clipped = dist["depdelay"].clip(-60, 300)
axes[0].hist(clipped, bins=80, color=BLUE, alpha=0.8, edgecolor="none")
axes[0].axvline(0,  color=GRAY,   lw=1, ls="--", label="On time")
axes[0].axvline(15, color=AMBER,  lw=1, ls="--", label="+15 min threshold")
axes[0].axvline(stats["50%"], color=CORAL, lw=1.5, ls="-", label=f"Median ({stats['50%']:.0f} min)")
axes[0].set_xlabel("Departure delay (min, clipped at ±300)")
axes[0].set_ylabel("Flights (5% sample)")
axes[0].legend(fontsize=9)
axes[0].set_title("Full distribution")

# Right: log scale to show the tail
pos = dist["depdelay"][dist["depdelay"] > 0]
axes[1].hist(pos, bins=80, color=CORAL, alpha=0.8, edgecolor="none")
axes[1].set_yscale("log")
axes[1].set_xlabel("Departure delay (min, positive only)")
axes[1].set_ylabel("Flights (log scale)")
axes[1].set_title("Delay tail (log scale)")

plt.tight_layout()
save(fig, "a1_delay_distribution.png")


# ════════════════════════════════════════════════════════════
# A2 — Carrier ranking
# ════════════════════════════════════════════════════════════
print("\n── A2: Carrier ranking ──")

carriers = con.execute(f"""
    SELECT
        iata_code_marketing_airline AS carrier,
        COUNT(*)                                                           AS flights,
        ROUND(AVG(depdelay), 2)                                            AS avg_dep_delay,
        ROUND(AVG(arrdelay), 2)                                            AS avg_arr_delay,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1)   AS median_dep,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                               AS pct_delayed_15,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2)                        AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY iata_code_marketing_airline
    HAVING COUNT(*) > 10000
    ORDER BY avg_dep_delay DESC
""").df()

print(carriers.to_string(index=False))
note(f"Most delayed carrier (mean): {carriers.iloc[0]['carrier']} ({carriers.iloc[0]['avg_dep_delay']:.1f} min avg)")
note(f"Best carrier (mean): {carriers.iloc[-1]['carrier']} ({carriers.iloc[-1]['avg_dep_delay']:.1f} min avg)")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("A2 — Carrier delay performance", y=1.01)

colors_bar = [CORAL if v > carriers["avg_dep_delay"].median() else BLUE for v in carriers["avg_dep_delay"]]

axes[0].barh(carriers["carrier"][::-1], carriers["avg_dep_delay"][::-1], color=colors_bar[::-1])
axes[0].axvline(0, color=GRAY, lw=0.8)
axes[0].set_xlabel("Mean departure delay (min)")
axes[0].set_title("Mean departure delay by carrier")

axes[1].scatter(carriers["pct_delayed_15"], carriers["avg_dep_delay"],
                s=carriers["flights"]/carriers["flights"].max()*400,
                color=PURPLE, alpha=0.7, edgecolors="white", lw=0.5)
for _, row in carriers.iterrows():
    axes[1].annotate(row["carrier"],
                     (row["pct_delayed_15"], row["avg_dep_delay"]),
                     fontsize=8, ha="left", va="bottom")
axes[1].set_xlabel("% flights delayed >15 min")
axes[1].set_ylabel("Mean delay (min)")
axes[1].set_title("Delay rate vs mean delay\n(bubble = flight volume)")

plt.tight_layout()
save(fig, "a2_carrier_ranking.png")


# ════════════════════════════════════════════════════════════
# A3 — Airport hotspots
# ════════════════════════════════════════════════════════════
print("\n── A3: Airport hotspots ──")

airports = con.execute(f"""
    SELECT
        origin                                                             AS airport,
        origincityname                                                     AS city,
        COUNT(*)                                                           AS flights,
        ROUND(AVG(depdelay), 2)                                            AS avg_dep_delay,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1)   AS median_dep,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                               AS pct_delayed,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2)                        AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY origin, origincityname
    HAVING COUNT(*) > 50000
    ORDER BY avg_dep_delay DESC
""").df()

top20 = airports.head(20)
bot10 = airports.tail(10)

note(f"Worst airport (mean dep delay): {top20.iloc[0]['airport']} – {top20.iloc[0]['city']} ({top20.iloc[0]['avg_dep_delay']:.1f} min)")
note(f"Best airport (mean dep delay): {bot10.iloc[-1]['airport']} – {bot10.iloc[-1]['city']} ({bot10.iloc[-1]['avg_dep_delay']:.1f} min)")

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("A3 — Airport delay hotspots (airports with >50k flights)", y=1.01)

colors_ap = [CORAL if v > airports["avg_dep_delay"].median() else TEAL for v in top20["avg_dep_delay"]]
axes[0].barh(top20["airport"][::-1], top20["avg_dep_delay"][::-1], color=colors_ap[::-1])
axes[0].set_xlabel("Mean departure delay (min)")
axes[0].set_title("Top 20 worst origin airports")

axes[1].scatter(airports["pct_delayed"], airports["avg_dep_delay"],
                s=airports["flights"]/airports["flights"].max()*300,
                color=TEAL, alpha=0.6, edgecolors="white", lw=0.5)
for _, row in airports[airports["flights"] > airports["flights"].quantile(0.85)].iterrows():
    axes[1].annotate(row["airport"], (row["pct_delayed"], row["avg_dep_delay"]),
                     fontsize=7, ha="left", va="bottom")
axes[1].set_xlabel("% flights delayed >15 min")
axes[1].set_ylabel("Mean delay (min)")
axes[1].set_title("Delay rate vs mean delay\n(bubble = flight volume, labeled = busiest airports)")

plt.tight_layout()
save(fig, "a3_airport_hotspots.png")


# ════════════════════════════════════════════════════════════
# A4 — Hour of day
# ════════════════════════════════════════════════════════════
print("\n── A4: Hour of day ──")

hour_data = con.execute(f"""
    SELECT
        FLOOR(crsdeptime / 100) AS dep_hour,
        COUNT(*)                AS flights,
        ROUND(AVG(depdelay), 2) AS avg_delay,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1) AS median_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
      AND crsdeptime IS NOT NULL
      AND crsdeptime BETWEEN 0 AND 2359
      AND cancelled = 0
    GROUP BY dep_hour
    ORDER BY dep_hour
""").df()

worst_hour = hour_data.loc[hour_data["avg_delay"].idxmax()]
best_hour  = hour_data.loc[hour_data["avg_delay"].idxmin()]
note(f"Worst departure hour: {int(worst_hour['dep_hour']):02d}:00 ({worst_hour['avg_delay']:.1f} min avg)")
note(f"Best departure hour:  {int(best_hour['dep_hour']):02d}:00 ({best_hour['avg_delay']:.1f} min avg)")

fig, ax1 = plt.subplots(figsize=(12, 5))
fig.suptitle("A4 — Delay by departure hour", y=1.01)

color_bars = [CORAL if v > 10 else BLUE for v in hour_data["avg_delay"]]
bars = ax1.bar(hour_data["dep_hour"], hour_data["avg_delay"], color=color_bars, alpha=0.85)
ax1.set_xlabel("Scheduled departure hour")
ax1.set_ylabel("Mean departure delay (min)", color=BLUE)
ax1.set_xticks(range(0, 24))
ax1.set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45, ha="right", fontsize=8)

ax2 = ax1.twinx()
ax2.plot(hour_data["dep_hour"], hour_data["pct_delayed"], color=AMBER, lw=2, marker="o", ms=4)
ax2.set_ylabel("% flights delayed >15 min", color=AMBER)
ax2.spines["right"].set_visible(True)
ax2.spines["top"].set_visible(False)

plt.tight_layout()
save(fig, "a4_hour_of_day.png")


# ════════════════════════════════════════════════════════════
# A5 — Seasonal heatmap (month × day-of-week)
# ════════════════════════════════════════════════════════════
print("\n── A5: Seasonal heatmap ──")

seasonal = con.execute(f"""
    SELECT
        month,
        dayofweek,
        ROUND(AVG(depdelay), 2) AS avg_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_delayed
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY month, dayofweek
    ORDER BY month, dayofweek
""").df()

pivot_avg  = seasonal.pivot(index="dayofweek", columns="month", values="avg_delay")
pivot_pct  = seasonal.pivot(index="dayofweek", columns="month", values="pct_delayed")

month_labels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
dow_labels   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

fig, axes = plt.subplots(1, 2, figsize=(16, 5))
fig.suptitle("A5 — Seasonal delay patterns (month × day of week)", y=1.01)

im1 = axes[0].imshow(pivot_avg.values, aspect="auto", cmap="RdYlGn_r")
axes[0].set_xticks(range(12)); axes[0].set_xticklabels(month_labels)
axes[0].set_yticks(range(7));  axes[0].set_yticklabels(dow_labels)
axes[0].set_title("Mean departure delay (min)")
plt.colorbar(im1, ax=axes[0], shrink=0.8)

im2 = axes[1].imshow(pivot_pct.values, aspect="auto", cmap="RdYlGn_r")
axes[1].set_xticks(range(12)); axes[1].set_xticklabels(month_labels)
axes[1].set_yticks(range(7));  axes[1].set_yticklabels(dow_labels)
axes[1].set_title("% flights delayed >15 min")
plt.colorbar(im2, ax=axes[1], shrink=0.8)

plt.tight_layout()
save(fig, "a5_seasonal_heatmap.png")

worst_cell = seasonal.loc[seasonal["avg_delay"].idxmax()]
note(f"Worst month+day combo: month={int(worst_cell['month'])} ({month_labels[int(worst_cell['month'])-1]}), day={int(worst_cell['dayofweek'])} ({dow_labels[int(worst_cell['dayofweek'])-1]}) — {worst_cell['avg_delay']:.1f} min avg")


# ════════════════════════════════════════════════════════════
# A6 — Delay causes
# ════════════════════════════════════════════════════════════
print("\n── A6: Delay causes ──")

# Overall cause breakdown
causes_overall = con.execute(f"""
    SELECT
        ROUND(AVG(carrierdelay),      1) AS carrier,
        ROUND(AVG(weatherdelay),      1) AS weather,
        ROUND(AVG(nasdelay),          1) AS nas,
        ROUND(AVG(securitydelay),     1) AS security,
        ROUND(AVG(lateaircraftdelay), 1) AS late_aircraft
    FROM {GLOB}
    WHERE depdelay > 15
""").df()

note(f"Cause breakdown (delayed flights only): {causes_overall.to_dict(orient='records')[0]}")

# Cause by carrier
causes_carrier = con.execute(f"""
    SELECT
        iata_code_marketing_airline AS carrier,
        ROUND(AVG(carrierdelay),      1) AS carrier_delay,
        ROUND(AVG(weatherdelay),      1) AS weather,
        ROUND(AVG(nasdelay),          1) AS nas,
        ROUND(AVG(lateaircraftdelay), 1) AS late_aircraft
    FROM {GLOB}
    WHERE depdelay > 15
    GROUP BY iata_code_marketing_airline
    HAVING COUNT(*) > 5000
    ORDER BY (AVG(carrierdelay) + AVG(lateaircraftdelay)) DESC
""").df()

# Cause by month
causes_month = con.execute(f"""
    SELECT
        month,
        ROUND(AVG(carrierdelay),      1) AS carrier_delay,
        ROUND(AVG(weatherdelay),      1) AS weather,
        ROUND(AVG(nasdelay),          1) AS nas,
        ROUND(AVG(lateaircraftdelay), 1) AS late_aircraft
    FROM {GLOB}
    WHERE depdelay > 15
    GROUP BY month
    ORDER BY month
""").df()

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("A6 — Delay causes", y=1.01)

cause_cols  = ["carrier_delay", "weather", "nas", "late_aircraft"]
cause_colors = [CORAL, BLUE, TEAL, AMBER]
cause_labels = ["Carrier", "Weather", "NAS", "Late aircraft"]

# By carrier — stacked bar
bottom = np.zeros(len(causes_carrier))
for col, color, label in zip(cause_cols, cause_colors, cause_labels):
    vals = causes_carrier[col].fillna(0).values
    axes[0].barh(causes_carrier["carrier"], vals, left=bottom, color=color, label=label, alpha=0.85)
    bottom += vals
axes[0].set_xlabel("Avg delay minutes (delayed flights only)")
axes[0].set_title("Delay cause by carrier")
axes[0].legend(fontsize=9)

# By month — stacked bar
bottom = np.zeros(len(causes_month))
for col, color, label in zip(cause_cols, cause_colors, cause_labels):
    vals = causes_month[col].fillna(0).values
    axes[1].bar(causes_month["month"], vals, bottom=bottom, color=color, label=label, alpha=0.85)
    bottom += vals
axes[1].set_xticks(range(1, 13))
axes[1].set_xticklabels(month_labels)
axes[1].set_ylabel("Avg delay minutes (delayed flights only)")
axes[1].set_title("Delay cause by month")
axes[1].legend(fontsize=9)

plt.tight_layout()
save(fig, "a6_delay_causes.png")


# ════════════════════════════════════════════════════════════
# Save findings.md
# ════════════════════════════════════════════════════════════
findings_path = os.path.join(OUTDIR, "findings.md")
with open(findings_path, "w") as f:
    f.write("# EDA Thread A — Key findings\n\n")
    for i, finding in enumerate(findings, 1):
        f.write(f"{i}. {finding}\n")
    f.write("\n---\n*Auto-generated by eda_thread_a.py — annotate and expand these into your story brief.*\n")

print(f"\n✅ Thread A complete.")
print(f"   Charts saved to: {OUTDIR}/")
print(f"   Findings saved to: {findings_path}")
print(f"\n   Open docs/eda_thread_a/ in Finder to review charts.")