"""
streamlit_app.py -- TrialScope dashboard.

Design constraint honored here: this app ONLY reads pre-computed artifacts
from results/ (written by src/run_descriptive_stats.py and
src/run_hypothesis_tests.py). It does not connect to the database and does
not run any statistical test itself -- if you want fresh numbers, re-run
`python -m src.run_extraction && python -m src.run_descriptive_stats && \
python -m src.run_hypothesis_tests` and then reload this page.

Chart types used are limited to bar, line, and box plots per the project's
"in-scope" visualization constraint (no 3D or animated charts).
"""

import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(HERE, "results")
DESC_DIR = os.path.join(RESULTS_DIR, "descriptive")

st.set_page_config(page_title="TrialScope", layout="wide")


@st.cache_data
def load_json(path):
    with open(path) as f:
        return json.load(f)


@st.cache_data
def load_csv(path, **kwargs):
    return pd.read_csv(path, **kwargs)


# ---------------------------------------------------------------------------
# Guard: tell the user clearly if the pipeline hasn't been run yet, instead
# of a confusing stack trace.
# ---------------------------------------------------------------------------
required = [
    os.path.join(DESC_DIR, "summary_metrics.json"),
    os.path.join(RESULTS_DIR, "hypothesis_tests.csv"),
]
missing = [p for p in required if not os.path.exists(p)]
if missing:
    st.error(
        "Pre-computed results are missing. Run these once from the project root "
        "before starting the dashboard:\n\n"
        "```\npython -m src.generate_sample_aact\npython -m src.run_extraction\n"
        "python -m src.run_descriptive_stats\npython -m src.run_hypothesis_tests\n```"
    )
    st.stop()

summary = load_json(os.path.join(DESC_DIR, "summary_metrics.json"))
enrollment_stats = load_json(os.path.join(DESC_DIR, "enrollment_stats.json"))
duration_stats = load_json(os.path.join(DESC_DIR, "duration_stats.json"))

st.title("TrialScope")
st.caption(
    "SQL-first descriptive statistics and group comparisons on clinical trial "
    "registry data (AACT schema). Every number below was computed once by the "
    "src/ pipeline and saved to results/ -- this page only displays it."
)

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total trials analyzed", f"{summary['n_total_trials']:,}")
c2.metric("Date range (start_date)", summary["date_range"])
c3.metric("Completion rate", f"{summary['completion_rate']:.1%}")
c4.metric("Trials excluded from duration analysis", f"{duration_stats['n_excluded_ongoing']:,}",
          help="Still Recruiting / Active / Unknown status -- no completion_date yet. "
               "Kept in every other analysis, excluded only from duration_days.")

st.divider()

tab1, tab2, tab3 = st.tabs(["Descriptive Statistics", "Group Comparisons", "How to Read This"])

# ---------------------------------------------------------------------------
# TAB 1 -- Descriptive statistics
# ---------------------------------------------------------------------------
with tab1:
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Trials by phase")
        by_phase = load_csv(os.path.join(DESC_DIR, "by_phase.csv"))
        fig = px.bar(by_phase, x="phase", y="count", text="count")
        st.plotly_chart(fig, width='stretch')

        st.subheader("Trials by sponsor type")
        by_sponsor = load_csv(os.path.join(DESC_DIR, "by_sponsor_type.csv"))
        fig = px.bar(by_sponsor, x="sponsor_type", y="count", text="count")
        st.plotly_chart(fig, width='stretch')

    with col_b:
        st.subheader("Trials by overall status")
        by_status = load_csv(os.path.join(DESC_DIR, "by_status.csv"))
        fig = px.bar(by_status.sort_values("count", ascending=True), x="count", y="overall_status", orientation="h")
        st.plotly_chart(fig, width='stretch')

        st.subheader("Top conditions studied")
        top_cond = load_csv(os.path.join(DESC_DIR, "top_conditions.csv"))
        fig = px.bar(top_cond.sort_values("n_trials"), x="n_trials", y="condition", orientation="h")
        st.plotly_chart(fig, width='stretch')

    st.subheader("New trial registrations per year")
    by_year = load_csv(os.path.join(DESC_DIR, "trials_per_year.csv"))
    fig = px.line(by_year, x="start_year", y="n_trials", markers=True)
    st.plotly_chart(fig, width='stretch')

    st.subheader("Sponsor-type mix over time")
    sponsor_year = load_csv(os.path.join(DESC_DIR, "sponsor_type_by_year.csv"))
    fig = px.bar(sponsor_year, x="start_year", y="n", color="sponsor_type", barmode="stack")
    st.plotly_chart(fig, width='stretch')

    st.subheader("Enrollment size distribution")
    st.markdown(
        f"**Mean:** {enrollment_stats['mean']:.1f} &nbsp;&nbsp; "
        f"**Median:** {enrollment_stats['median']:.1f} &nbsp;&nbsp; "
        f"**IQR:** {enrollment_stats['iqr']:.1f} (Q1={enrollment_stats['q1']:.1f}, "
        f"Q3={enrollment_stats['q3']:.1f}) &nbsp;&nbsp; "
        f"**Skewness:** {enrollment_stats['skewness']:.2f}"
    )
    if enrollment_stats["skewness"] > 1:
        st.info(
            "Skewness > 1 confirms enrollment is heavily right-skewed (a long tail of "
            "large trials pulls the mean above the median) -- this is why median and "
            "IQR, not just the mean, are reported here."
        )

# ---------------------------------------------------------------------------
# TAB 2 -- Group comparisons (the four hypothesis tests)
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Hypothesis test results")
    results_df = load_csv(os.path.join(RESULTS_DIR, "hypothesis_tests.csv"))

    display_df = results_df.copy()
    display_df["p_value"] = display_df["p_value"].apply(
        lambda p: "< 0.0001" if p < 0.0001 else f"{p:.4g}"
    )
    display_df["statistic"] = display_df["statistic"].apply(lambda s: f"{s:,.2f}")
    display_df["effect_size"] = display_df["effect_size"].apply(lambda e: f"{e:.3f}")
    st.dataframe(
        display_df[["test_name", "statistic", "p_value", "effect_size_name", "effect_size", "n"]],
        width='stretch',
        hide_index=True,
    )

    for _, row in results_df.iterrows():
        with st.expander(row["test_name"]):
            st.markdown(f"**H0:** {row['h0']}")
            st.markdown(f"**H1:** {row['h1']}")
            st.markdown(f"**Assumption check:** {row['assumption_note']}")
            st.markdown(f"**Plain-language interpretation:** {row['interpretation']}")

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Phase vs. completion status")
        contingency = load_csv(os.path.join(RESULTS_DIR, "phase_vs_status_table.csv"), index_col=0)
        contingency_long = contingency.reset_index().melt(
            id_vars=contingency.index.name or "index", var_name="overall_status", value_name="count"
        )
        contingency_long.columns = ["phase", "overall_status", "count"]
        fig = px.bar(contingency_long, x="phase", y="count", color="overall_status", barmode="stack")
        st.plotly_chart(fig, width='stretch')

    with col_b:
        st.subheader("Enrollment by sponsor type")
        box_enroll = load_csv(os.path.join(RESULTS_DIR, "boxplot_enrollment_by_sponsor.csv"))
        fig = px.box(box_enroll, x="sponsor_type", y="enrollment", points=False)
        fig.update_yaxes(range=[0, box_enroll["enrollment"].quantile(0.98)])
        st.plotly_chart(fig, width='stretch')

    st.subheader("Duration: Completed vs. Terminated/Withdrawn")
    box_dur = load_csv(os.path.join(RESULTS_DIR, "boxplot_duration_by_outcome.csv"))
    fig = px.box(box_dur, x="group", y="duration_days", points=False)
    st.plotly_chart(fig, width='stretch')

# ---------------------------------------------------------------------------
# TAB 3 -- how to read a p-value / effect size
# ---------------------------------------------------------------------------
with tab3:
    st.markdown(
        """
### How to read a p-value

A p-value is the probability of seeing a difference at least this large *if
the null hypothesis (H0) were actually true* -- it is **not** the
probability that H0 is true, and it is **not** a measure of how big or
important the effect is. A very small p-value (e.g. p < 0.0001) with 9,000
trials just means the observed pattern is very unlikely to be pure chance
-- it says nothing about whether the pattern is large enough to matter in
practice. Conventionally, p < 0.05 is treated as "statistically
significant," meaning we reject H0.

### How to read an effect size

An effect size measures *how large* a relationship or difference is, on a
scale that doesn't depend on sample size the way a p-value does:

- **Cramer's V** (chi-square test): 0 = no association, roughly
  0.1 = weak, 0.3 = moderate, 0.5+ = strong.
- **Eta-squared / epsilon-squared** (ANOVA / Kruskal-Wallis): proportion of
  variance explained by group membership; roughly 0.01 = small,
  0.06 = medium, 0.14 = large.
- **Cohen's d** (t-test): standardized mean difference; roughly
  0.2 = small, 0.5 = medium, 0.8 = large.
- **Rank-biserial correlation** (Mann-Whitney U): -1 to 1; magnitude
  interpreted similarly to a correlation coefficient.

**Why report both, always:** with a large enough sample, almost any real
difference becomes "statistically significant" (tiny p-value), even if it's
too small to matter. The p-value answers "is there probably a real
difference?" and the effect size answers "how big is it?" -- you need both
to tell a complete, honest story about a result.
"""
    )
