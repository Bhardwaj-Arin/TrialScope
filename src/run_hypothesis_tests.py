"""
run_hypothesis_tests.py -- Step 3 of the build order (Phase 3 of the
roadmap).

Runs exactly the three required hypothesis tests (no more -- the fourth,
"optional stretch" item in the roadmap, logistic regression, is a modeling
step and is explicitly excluded by the build prompt's "no ML of any kind"
constraint, so it is not implemented anywhere in this project) against
data/processed/analysis_table.csv, and writes:
  - results/hypothesis_tests.csv / .json -- the results table the dashboard
    shows (test name, H0/H1, statistic, p-value, effect size, assumption
    note, plain-language interpretation).
  - results/phase_vs_status_table.csv -- the underlying contingency table.
  - results/sponsor_vs_enrollment_groups.csv -- group summary stats.
  - results/duration_groups.csv -- group summary stats.
These are the "saved artifacts" the Streamlit dashboard reads; it does not
recompute any test live.
"""

import os
import json

import pandas as pd

from src.stats_utils import (
    test_phase_vs_completion,
    test_sponsor_vs_enrollment,
    test_duration_completed_vs_terminated,
)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PATH = os.path.join(HERE, "data", "processed", "analysis_table.csv")
OUT_DIR = os.path.join(HERE, "results")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(IN_PATH, parse_dates=["start_date", "completion_date"])

    result1, contingency = test_phase_vs_completion(df)
    result2, sponsor_groups = test_sponsor_vs_enrollment(df)
    result3, duration_groups = test_duration_completed_vs_terminated(df)

    results = [result1.to_dict(), result2.to_dict(), result3.to_dict()]

    results_df = pd.DataFrame(results)
    results_df.to_csv(os.path.join(OUT_DIR, "hypothesis_tests.csv"), index=False)
    with open(os.path.join(OUT_DIR, "hypothesis_tests.json"), "w") as f:
        json.dump(results, f, indent=2)

    contingency.to_csv(os.path.join(OUT_DIR, "phase_vs_status_table.csv"))
    sponsor_groups.to_csv(os.path.join(OUT_DIR, "sponsor_vs_enrollment_groups.csv"), index=False)
    duration_groups.to_csv(os.path.join(OUT_DIR, "duration_groups.csv"), index=False)

    # --- Raw per-group values for the dashboard's box plots -----------------
    # (a saved extract, not a live recomputation -- the dashboard just plots
    # these two columns as-is).
    enrollment_box = df.dropna(subset=["enrollment", "sponsor_type"])[["sponsor_type", "enrollment"]]
    enrollment_box.to_csv(os.path.join(OUT_DIR, "boxplot_enrollment_by_sponsor.csv"), index=False)

    dur = df.dropna(subset=["duration_days"]).copy()
    dur = dur[dur["overall_status"].isin(["Completed", "Terminated", "Withdrawn"])]
    dur["group"] = dur["overall_status"].apply(
        lambda s: "Completed" if s == "Completed" else "Terminated/Withdrawn"
    )
    dur[["group", "duration_days"]].to_csv(
        os.path.join(OUT_DIR, "boxplot_duration_by_outcome.csv"), index=False
    )

    print("Hypothesis test results written to results/hypothesis_tests.csv")
    for r in results:
        print(f"\n{r['test_name']}")
        print(f"  statistic={r['statistic']:.3f}  p={r['p_value']:.4g}  "
              f"{r['effect_size_name']}={r['effect_size']:.3f}")
        print(f"  {r['interpretation']}")


if __name__ == "__main__":
    main()
