"""
run_extraction.py -- Step 1 of the build order.

Runs the three standalone .sql files in sql/ against the database (via
db.run_sql_file, a thin psycopg2 + pandas.read_sql_query wrapper -- no ORM),
joins the three results in pandas, computes duration_days, and writes the
resulting analysis table to data/processed/. Every later step (descriptive
stats, hypothesis tests, dashboard) reads only from data/processed/ -- none
of them re-query the database -- so the SQL extraction step is the single
place the raw data enters the pipeline.
"""

import os

import pandas as pd

from src.db import run_sql_file

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(HERE, "sql")
OUT_DIR = os.path.join(HERE, "data", "processed")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    studies = run_sql_file(os.path.join(SQL_DIR, "extract_studies.sql"))
    sponsors = run_sql_file(os.path.join(SQL_DIR, "extract_sponsors.sql"))
    conditions = run_sql_file(os.path.join(SQL_DIR, "extract_conditions.sql"))

    studies.to_csv(os.path.join(OUT_DIR, "extracted_studies.csv"), index=False)
    sponsors.to_csv(os.path.join(OUT_DIR, "extracted_sponsors.csv"), index=False)
    conditions.to_csv(os.path.join(OUT_DIR, "extracted_conditions.csv"), index=False)

    # --- Join into one analysis table -------------------------------------
    # Left join sponsors/conditions onto studies (not inner) so that a study
    # missing a lead sponsor or a condition row is still visible in the
    # merged table with NaNs rather than silently vanishing a second time --
    # the SQL files already did the exclusion filtering; this join should
    # not exclude anything further.
    df = studies.merge(sponsors, on="nct_id", how="left")
    df = df.merge(conditions, on="nct_id", how="left")

    df["start_date"] = pd.to_datetime(df["start_date"])
    df["completion_date"] = pd.to_datetime(df["completion_date"])

    # --- duration_days + documented handling of ongoing trials -------------
    # A trial that is still Recruiting / Active / Unknown status has no
    # completion_date yet -- that's not missing data, it's a trial that
    # hasn't finished. We do NOT drop these rows from the dataset (they are
    # still valid observations for phase/status/enrollment descriptive
    # stats and for the chi-square test). We only exclude them from anything
    # that needs duration_days, and we report exactly how many rows that is.
    has_both_dates = df["start_date"].notna() & df["completion_date"].notna()
    df["duration_days"] = pd.NA
    df.loc[has_both_dates, "duration_days"] = (
        df.loc[has_both_dates, "completion_date"] - df.loc[has_both_dates, "start_date"]
    ).dt.days

    n_missing_duration = int((~has_both_dates).sum())
    n_total = len(df)
    print(
        f"{n_missing_duration} of {n_total} studies ({n_missing_duration / n_total:.1%}) "
        "have no completion_date (still Recruiting / Active / Unknown status) and are "
        "excluded from duration_days-based analyses only -- they are kept for every "
        "other analysis. See docs/methodology.md."
    )

    df.to_csv(os.path.join(OUT_DIR, "analysis_table.csv"), index=False)

    with open(os.path.join(OUT_DIR, "extraction_log.txt"), "w") as f:
        f.write(
            f"Total studies extracted: {n_total}\n"
            f"Studies missing completion_date (excluded from duration analyses only): "
            f"{n_missing_duration} ({n_missing_duration / n_total:.1%})\n"
        )

    print(f"Wrote {n_total} rows to data/processed/analysis_table.csv")


if __name__ == "__main__":
    main()
