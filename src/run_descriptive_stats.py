"""
run_descriptive_stats.py -- Step 2 of the build order (Phase 2 of the
roadmap).

Reads data/processed/analysis_table.csv (already extracted via SQL) and
computes every descriptive statistic the roadmap asks for: distributions by
phase/status/sponsor type, enrollment distribution (mean/median/IQR/
skewness), registrations-per-year trend, sponsor-type mix over time, and
top conditions studied. Everything is written to results/descriptive/ as
CSV so the Streamlit dashboard can read pre-computed numbers instead of
recomputing them live (per the build order's explicit instruction).
"""

import os
import json

import pandas as pd

from src.stats_utils import describe_numeric, frequency_table

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PATH = os.path.join(HERE, "data", "processed", "analysis_table.csv")
OUT_DIR = os.path.join(HERE, "results", "descriptive")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(IN_PATH, parse_dates=["start_date", "completion_date"])

    # --- Frequency distributions --------------------------------------------
    frequency_table(df["phase"]).to_csv(os.path.join(OUT_DIR, "by_phase.csv"), index=False)
    frequency_table(df["overall_status"]).to_csv(os.path.join(OUT_DIR, "by_status.csv"), index=False)
    frequency_table(df["sponsor_type"]).to_csv(os.path.join(OUT_DIR, "by_sponsor_type.csv"), index=False)

    # --- Enrollment distribution --------------------------------------------
    enrollment_stats = describe_numeric(df["enrollment"])
    with open(os.path.join(OUT_DIR, "enrollment_stats.json"), "w") as f:
        json.dump(enrollment_stats, f, indent=2)

    # --- Duration distribution (documented exclusion of ongoing trials) ----
    duration_stats = describe_numeric(df["duration_days"])
    n_missing_duration = int(df["duration_days"].isna().sum())
    duration_stats["n_excluded_ongoing"] = n_missing_duration
    with open(os.path.join(OUT_DIR, "duration_stats.json"), "w") as f:
        json.dump(duration_stats, f, indent=2)

    # --- Trend over time: registrations per year ----------------------------
    df["start_year"] = df["start_date"].dt.year
    by_year = df.groupby("start_year").size().rename("n_trials").reset_index()
    by_year.to_csv(os.path.join(OUT_DIR, "trials_per_year.csv"), index=False)

    # --- Trend: sponsor-type mix by year (are trends shifting?) ------------
    sponsor_by_year = (
        df.groupby(["start_year", "sponsor_type"]).size().rename("n").reset_index()
    )
    sponsor_by_year.to_csv(os.path.join(OUT_DIR, "sponsor_type_by_year.csv"), index=False)

    # --- Trend: phase mix by year --------------------------------------------
    phase_by_year = df.groupby(["start_year", "phase"]).size().rename("n").reset_index()
    phase_by_year.to_csv(os.path.join(OUT_DIR, "phase_by_year.csv"), index=False)

    # --- Top conditions studied ----------------------------------------------
    top_conditions = (
        df["primary_condition"].value_counts().head(15).rename_axis("condition")
        .reset_index(name="n_trials")
    )
    top_conditions.to_csv(os.path.join(OUT_DIR, "top_conditions.csv"), index=False)

    # --- Top-line summary metrics used by the dashboard header --------------
    n_total = len(df)
    n_completed = int((df["overall_status"] == "Completed").sum())
    summary = {
        "n_total_trials": n_total,
        "date_range": f"{df['start_date'].min().date()} to {df['start_date'].max().date()}",
        "completion_rate": n_completed / n_total,
        "n_completed": n_completed,
    }
    with open(os.path.join(OUT_DIR, "summary_metrics.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("Descriptive statistics written to results/descriptive/")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
