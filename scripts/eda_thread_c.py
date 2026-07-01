"""
EDA Thread C — Trends Over Time (2018–2025)
============================================
Run from your project root:
    python scripts/eda_thread_c.py

Outputs saved to: docs/eda_thread_c/
  - c1_annual_trend.png
  - c2_covid_story.png
  - c3_carrier_trajectories.png
  - c4_airport_trends.png
  - c5_cause_mix_shift.png
  - findings.md
"""

import os
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Setup ─────────────────────────────────────────────────────────────────────
LAKE   = "./data/lake"
OUTDIR = "./docs/eda_thread_c"
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
GREEN  = "#639922"

# Helper: shade COVID period on any axis
def shade_covid(ax):
    ax.axvspan(2020 + 2/12, 2021 + 6/12, color=AMBER, alpha=0.10, zorder=0)
    ax.text(2020.3, ax.get_ylim()[1] * 0.95, "COVID", fontsize=7,
            color=AMBER, va="top", style="italic")

# Time index helper: year + month as decimal
def ym_to_float(year, month):
    return year + (month - 1) / 12

print("\n" + "═"*60)
print("  EDA Thread C — Trends Over Time (2018–2025)")
print("═"*60)


# ════════════════════════════════════════════════════════════
# C1 — Annual trend: has delay improved or worsened?
# ════════════════════════════════════════════════════════════
print("\n── C1: Annual trend ──")

annual = con.execute(f"""
    SELECT
        year,
        COUNT(*)                                                              AS flights,
        ROUND(AVG(depdelay), 2)                                               AS mean_dep_delay,
        ROUND(AVG(arrdelay), 2)                                               AS mean_arr_delay,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY depdelay), 1)      AS median_dep,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                                   AS pct_delayed_15,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2)                           AS cancel_pct,
        ROUND(100.0 * SUM(diverted)  / COUNT(*), 2)                           AS divert_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY year
    ORDER BY year
""").df()

print(annual.to_string(index=False))

pre_covid  = annual[annual["year"] < 2020]["mean_dep_delay"].mean()
covid_yr   = annual[annual["year"] == 2020]["mean_dep_delay"].values
post_covid = annual[annual["year"] > 2021]["mean_dep_delay"].mean()

note(f"Pre-COVID avg departure delay (2018–2019): {pre_covid:.1f} min")
if len(covid_yr): note(f"COVID year 2020 avg departure delay: {covid_yr[0]:.1f} min")
note(f"Post-COVID avg departure delay (2022–2025): {post_covid:.1f} min")
note(f"Best year: {annual.loc[annual['mean_dep_delay'].idxmin(), 'year']} ({annual['mean_dep_delay'].min():.1f} min avg)")
note(f"Worst year: {annual.loc[annual['mean_dep_delay'].idxmax(), 'year']} ({annual['mean_dep_delay'].max():.1f} min avg)")

fig, axes = plt.subplots(2, 2, figsize=(14, 9))
fig.suptitle("C1 — Annual flight delay trends (2018–2025)", y=1.01)

# Mean delay
axes[0,0].plot(annual["year"], annual["mean_dep_delay"],
               color=BLUE, lw=2, marker="o", ms=6, label="Departure")
axes[0,0].plot(annual["year"], annual["mean_arr_delay"],
               color=CORAL, lw=2, marker="s", ms=5, ls="--", label="Arrival")
axes[0,0].set_ylabel("Mean delay (min)")
axes[0,0].set_title("Mean departure & arrival delay")
axes[0,0].legend()
axes[0,0].set_xticks(annual["year"])

# % delayed
axes[0,1].bar(annual["year"], annual["pct_delayed_15"],
              color=[CORAL if y >= 2022 else BLUE for y in annual["year"]], alpha=0.8)
axes[0,1].set_ylabel("% flights delayed >15 min")
axes[0,1].set_title("% flights delayed >15 min")
axes[0,1].set_xticks(annual["year"])

# Flight volume
axes[1,0].bar(annual["year"], annual["flights"] / 1_000_000,
              color=TEAL, alpha=0.8)
axes[1,0].set_ylabel("Flights (millions)")
axes[1,0].set_title("Total flights per year")
axes[1,0].set_xticks(annual["year"])

# Cancellation rate
axes[1,1].plot(annual["year"], annual["cancel_pct"],
               color=PURPLE, lw=2, marker="o", ms=5, label="Cancellation %")
axes[1,1].plot(annual["year"], annual["divert_pct"],
               color=AMBER, lw=1.5, marker="s", ms=4, ls="--", label="Diversion %")
axes[1,1].set_ylabel("Rate (%)")
axes[1,1].set_title("Cancellation & diversion rates")
axes[1,1].legend()
axes[1,1].set_xticks(annual["year"])

for ax in axes.flatten():
    ax.axvspan(2019.5, 2021.5, color=AMBER, alpha=0.10, zorder=0)

plt.tight_layout()
save(fig, "c1_annual_trend.png")


# ════════════════════════════════════════════════════════════
# C2 — COVID story: the collapse and recovery
# ════════════════════════════════════════════════════════════
print("\n── C2: COVID story ──")

monthly = con.execute(f"""
    SELECT
        year,
        month,
        COUNT(*)                                                              AS flights,
        ROUND(AVG(depdelay), 2)                                               AS mean_dep_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)                                                   AS pct_delayed,
        ROUND(100.0 * SUM(cancelled) / COUNT(*), 2)                           AS cancel_pct
    FROM {GLOB}
    WHERE depdelay IS NOT NULL
    GROUP BY year, month
    ORDER BY year, month
""").df()

monthly["time"] = monthly.apply(lambda r: ym_to_float(r["year"], r["month"]), axis=1)

# Key events for annotation
events = [
    (2020 + 2/12,  "WHO\npandemic"),
    (2020 + 3/12,  "Travel\nbans"),
    (2021 + 5/12,  "Vaccines\nroll out"),
    (2021 + 11/12, "Revenge\ntravel surge"),
    (2022 + 5/12,  "Southwest\nmeltdown"),
]

fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
fig.suptitle("C2 — The COVID collapse and recovery (monthly, 2018–2025)", y=1.01)

# Flight volume
axes[0].fill_between(monthly["time"], monthly["flights"] / 1000,
                     alpha=0.4, color=TEAL)
axes[0].plot(monthly["time"], monthly["flights"] / 1000, color=TEAL, lw=1.2)
axes[0].set_ylabel("Flights (thousands)")
axes[0].set_title("Flight volume")

# Mean delay
axes[1].fill_between(monthly["time"], monthly["mean_dep_delay"],
                     alpha=0.3, color=BLUE)
axes[1].plot(monthly["time"], monthly["mean_dep_delay"], color=BLUE, lw=1.2)
axes[1].axhline(monthly[monthly["year"] < 2020]["mean_dep_delay"].mean(),
                color=GRAY, lw=0.8, ls="--", label="Pre-COVID avg")
axes[1].set_ylabel("Mean dep delay (min)")
axes[1].set_title("Mean departure delay")
axes[1].legend(fontsize=9)

# Cancellation rate
axes[2].fill_between(monthly["time"], monthly["cancel_pct"],
                     alpha=0.3, color=CORAL)
axes[2].plot(monthly["time"], monthly["cancel_pct"], color=CORAL, lw=1.2)
axes[2].set_ylabel("Cancellation rate (%)")
axes[2].set_title("Cancellation rate")
axes[2].set_xlabel("Year")

# Shade COVID + annotate events on all axes
for ax in axes:
    ax.axvspan(2020 + 2/12, 2021 + 6/12, color=AMBER, alpha=0.10, zorder=0)
    ylim = ax.get_ylim()
    for x, label in events:
        ax.axvline(x, color=GRAY, lw=0.6, ls=":", alpha=0.7)

# Add event labels only to top axis
ylim = axes[0].get_ylim()
for x, label in events:
    axes[0].text(x + 0.03, ylim[1] * 0.92, label,
                 fontsize=6.5, color=GRAY, va="top", ha="left")

# X-axis: year ticks
year_ticks = [ym_to_float(y, 1) for y in range(2018, 2026)]
axes[2].set_xticks(year_ticks)
axes[2].set_xticklabels([str(y) for y in range(2018, 2026)])

plt.tight_layout()
save(fig, "c2_covid_story.png")

covid_min_flights = monthly.loc[monthly["flights"].idxmin()]
note(f"Lowest flight volume month: {int(covid_min_flights['year'])}-{int(covid_min_flights['month']):02d} ({int(covid_min_flights['flights']):,} flights)")
note(f"COVID period: delays paradoxically {'lower' if monthly[monthly['year']==2020]['mean_dep_delay'].mean() < pre_covid else 'higher'} than pre-COVID despite chaos")


# ════════════════════════════════════════════════════════════
# C3 — Carrier trajectories: who improved, who declined?
# ════════════════════════════════════════════════════════════
print("\n── C3: Carrier trajectories ──")

carrier_annual = con.execute(f"""
    SELECT
        iata_code_marketing_airline AS carrier,
        year,
        COUNT(*)                    AS flights,
        ROUND(AVG(depdelay), 2)     AS mean_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)        AS pct_delayed
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY iata_code_marketing_airline, year
    HAVING COUNT(*) > 10000
    ORDER BY iata_code_marketing_airline, year
""").df()

# Index to 2018 baseline (or first available year)
carriers = carrier_annual["carrier"].unique()
baseline = carrier_annual[carrier_annual["year"] == carrier_annual["year"].min()]
baseline_dict = baseline.set_index("carrier")["mean_delay"].to_dict()

carrier_annual["indexed"] = carrier_annual.apply(
    lambda r: r["mean_delay"] - baseline_dict.get(r["carrier"], r["mean_delay"]), axis=1
)

# Keep only carriers with enough years of data
carrier_coverage = carrier_annual.groupby("carrier")["year"].count()
major_carriers = carrier_coverage[carrier_coverage >= 5].index.tolist()
ca_filtered = carrier_annual[carrier_annual["carrier"].isin(major_carriers)]

palette = [BLUE, CORAL, TEAL, PURPLE, AMBER, GREEN, GRAY,
           "#D85A30", "#1D9E75", "#7F77DD", "#BA7517", "#639922"]

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("C3 — Carrier delay trajectories (2018–2025)", y=1.01)

# Absolute delay trend
for i, carrier in enumerate(major_carriers):
    cd = ca_filtered[ca_filtered["carrier"] == carrier]
    color = palette[i % len(palette)]
    axes[0].plot(cd["year"], cd["mean_delay"],
                 lw=1.8, marker="o", ms=4, color=color, label=carrier, alpha=0.85)

axes[0].axvspan(2019.5, 2021.5, color=AMBER, alpha=0.08, zorder=0)
axes[0].set_ylabel("Mean departure delay (min)")
axes[0].set_title("Absolute mean delay by carrier")
axes[0].legend(fontsize=8, ncol=2)
axes[0].set_xticks(range(2018, 2026))

# Indexed to baseline (change from first year)
for i, carrier in enumerate(major_carriers):
    cd = ca_filtered[ca_filtered["carrier"] == carrier]
    color = palette[i % len(palette)]
    axes[1].plot(cd["year"], cd["indexed"],
                 lw=1.8, marker="o", ms=4, color=color, label=carrier, alpha=0.85)

axes[1].axhline(0, color=GRAY, lw=0.8, ls="--", label="No change from baseline")
axes[1].axvspan(2019.5, 2021.5, color=AMBER, alpha=0.08, zorder=0)
axes[1].set_ylabel("Change in mean delay vs first year (min)")
axes[1].set_title("Delay change indexed to first available year\n(negative = improved)")
axes[1].legend(fontsize=8, ncol=2)
axes[1].set_xticks(range(2018, 2026))

plt.tight_layout()
save(fig, "c3_carrier_trajectories.png")

# Who improved most / declined most by 2024-2025?
latest = ca_filtered[ca_filtered["year"] >= 2024].groupby("carrier")["indexed"].mean()
if len(latest) > 0:
    improver = latest.idxmin()
    decliner = latest.idxmax()
    note(f"Most improved carrier vs baseline: {improver} ({latest[improver]:+.1f} min)")
    note(f"Most declined carrier vs baseline: {decliner} ({latest[decliner]:+.1f} min)")


# ════════════════════════════════════════════════════════════
# C4 — Airport trends: structural improvement or decline?
# ════════════════════════════════════════════════════════════
print("\n── C4: Airport trends ──")

airport_annual = con.execute(f"""
    SELECT
        origin                  AS airport,
        origincityname          AS city,
        year,
        COUNT(*)                AS flights,
        ROUND(AVG(depdelay), 2) AS mean_delay,
        ROUND(100.0 * SUM(CASE WHEN depdelay > 15 THEN 1 ELSE 0 END)
              / COUNT(*), 1)    AS pct_delayed
    FROM {GLOB}
    WHERE depdelay IS NOT NULL AND cancelled = 0
    GROUP BY origin, origincityname, year
    HAVING COUNT(*) > 20000
    ORDER BY origin, year
""").df()

# Top 20 busiest airports
top_airports = airport_annual.groupby("airport")["flights"].sum().nlargest(20).index.tolist()
aa_top = airport_annual[airport_annual["airport"].isin(top_airports)]

# Compute first→latest year change
first_yr = aa_top.sort_values("year").groupby("airport").first().reset_index()
last_yr  = aa_top.sort_values("year").groupby("airport").last().reset_index()

change = first_yr[["airport","city","mean_delay"]].merge(
    last_yr[["airport","mean_delay"]], on="airport", suffixes=("_first","_last")
)
change["delta"] = change["mean_delay_last"] - change["mean_delay_first"]
change = change.sort_values("delta")

note(f"Airport with biggest improvement: {change.iloc[0]['airport']} ({change.iloc[0]['delta']:+.1f} min)")
note(f"Airport with biggest deterioration: {change.iloc[-1]['airport']} ({change.iloc[-1]['delta']:+.1f} min)")

fig, axes = plt.subplots(1, 2, figsize=(16, 7))
fig.suptitle("C4 — Airport delay trends (top 20 busiest, 2018–2025)", y=1.01)

# Change bar chart
colors_change = [TEAL if v < 0 else CORAL for v in change["delta"]]
axes[0].barh(change["airport"], change["delta"], color=colors_change, alpha=0.85)
axes[0].axvline(0, color=GRAY, lw=0.8)
axes[0].set_xlabel("Change in mean departure delay (min)\nfirst available year → most recent year")
axes[0].set_title("Airport delay improvement / deterioration")

# Trend lines for most changed airports
top_changed = pd.concat([change.head(5), change.tail(5)])["airport"].tolist()
for i, airport in enumerate(top_changed):
    ad = aa_top[aa_top["airport"] == airport]
    color = TEAL if change[change["airport"]==airport]["delta"].values[0] < 0 else CORAL
    axes[1].plot(ad["year"], ad["mean_delay"],
                 lw=1.5, marker="o", ms=4, color=color,
                 alpha=0.85, label=airport)

axes[1].axvspan(2019.5, 2021.5, color=AMBER, alpha=0.08, zorder=0)
axes[1].set_ylabel("Mean departure delay (min)")
axes[1].set_title("Delay trend for most-changed airports\n(teal = improved, coral = worsened)")
axes[1].legend(fontsize=8, ncol=2)
axes[1].set_xticks(range(2018, 2026))

plt.tight_layout()
save(fig, "c4_airport_trends.png")


# ════════════════════════════════════════════════════════════
# C5 — Has the delay cause mix shifted over time?
# ════════════════════════════════════════════════════════════
print("\n── C5: Cause mix shift ──")

cause_annual = con.execute(f"""
    SELECT
        year,
        ROUND(AVG(carrierdelay),      2) AS carrier,
        ROUND(AVG(weatherdelay),      2) AS weather,
        ROUND(AVG(nasdelay),          2) AS nas,
        ROUND(AVG(securitydelay),     2) AS security,
        ROUND(AVG(lateaircraftdelay), 2) AS late_aircraft,
        COUNT(*) AS delayed_flights
    FROM {GLOB}
    WHERE depdelay > 15
    GROUP BY year
    ORDER BY year
""").df()

# Normalize to % of total cause minutes per year
cause_cols = ["carrier", "weather", "nas", "security", "late_aircraft"]
cause_annual["total"] = cause_annual[cause_cols].sum(axis=1)
for col in cause_cols:
    cause_annual[f"{col}_pct"] = cause_annual[col] / cause_annual["total"] * 100

print(cause_annual[["year"] + cause_cols].to_string(index=False))

# Which cause grew most?
for col in cause_cols:
    first_val = cause_annual[cause_annual["year"] == cause_annual["year"].min()][col].values[0]
    last_val  = cause_annual[cause_annual["year"] == cause_annual["year"].max()][col].values[0]
    note(f"{col.replace('_',' ').title()} delay: {first_val:.1f} → {last_val:.1f} min avg ({last_val-first_val:+.1f} min)")

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("C5 — Has the mix of delay causes shifted over time?", y=1.01)

cause_colors = [CORAL, BLUE, TEAL, GRAY, AMBER]
cause_labels = ["Carrier", "Weather", "NAS", "Security", "Late aircraft"]

# Stacked area: absolute minutes
bottom = np.zeros(len(cause_annual))
for col, color, label in zip(cause_cols, cause_colors, cause_labels):
    axes[0].fill_between(cause_annual["year"],
                         bottom,
                         bottom + cause_annual[col].fillna(0),
                         color=color, alpha=0.75, label=label)
    bottom += cause_annual[col].fillna(0).values

axes[0].axvspan(2019.5, 2021.5, color="white", alpha=0.15, zorder=5)
axes[0].set_ylabel("Avg delay minutes (delayed flights only)")
axes[0].set_title("Absolute delay cause breakdown per year")
axes[0].legend(fontsize=9)
axes[0].set_xticks(cause_annual["year"])

# Stacked area: % share
pct_cols = [f"{c}_pct" for c in cause_cols]
bottom = np.zeros(len(cause_annual))
for col, color, label in zip(pct_cols, cause_colors, cause_labels):
    axes[1].fill_between(cause_annual["year"],
                         bottom,
                         bottom + cause_annual[col].fillna(0),
                         color=color, alpha=0.75, label=label)
    bottom += cause_annual[col].fillna(0).values

axes[1].axvspan(2019.5, 2021.5, color="white", alpha=0.15, zorder=5)
axes[1].set_ylabel("% share of total cause minutes")
axes[1].set_title("Relative cause mix shift over time")
axes[1].legend(fontsize=9)
axes[1].set_xticks(cause_annual["year"])
axes[1].set_ylim(0, 100)

plt.tight_layout()
save(fig, "c5_cause_mix_shift.png")


# ════════════════════════════════════════════════════════════
# Save findings.md
# ════════════════════════════════════════════════════════════
findings_path = os.path.join(OUTDIR, "findings.md")
with open(findings_path, "w") as f:
    f.write("# EDA Thread C — Key findings\n\n")
    f.write("## Core research question\n")
    f.write("How have flight delays changed from 2018 to 2025? What did COVID reveal?\n\n")
    f.write("## Findings\n\n")
    for i, finding in enumerate(findings, 1):
        f.write(f"{i}. {finding}\n")
    f.write("\n## Story angles to develop\n")
    f.write("- The COVID natural experiment: fewer flights = lower delays. What does that tell us?\n")
    f.write("- The revenge travel surge: 2022–2023 spike and whether it normalized\n")
    f.write("- Carrier winners and losers: who came out of COVID in better shape?\n")
    f.write("- Cause mix shift: is the system getting structurally better or worse?\n")
    f.write("\n---\n*Auto-generated by eda_thread_c.py — annotate and expand into your story brief.*\n")

print(f"\n✅ Thread C complete.")
print(f"   Charts: {OUTDIR}/")
print(f"   Findings: {findings_path}")