# TrialScope

**TrialScope** is a small, SQL-first data analytics project on public
clinical trial registry data. It answers a handful of concrete questions —
how trial phase, sponsor type, and enrollment size relate to completion
outcomes — using raw SQL extraction, descriptive statistics, and three
hypothesis tests, presented in a small Streamlit dashboard. It deliberately
contains **no machine learning, no agentic AI, and no ORM** — every query is
hand-written SQL, and every statistical result is a single, explainable
test, by design (see "Hard constraints" below).

## What this project does

1. Extracts clinical trial data (studies, lead sponsors, primary conditions)
   from an AACT-schema PostgreSQL database using three hand-written SQL
   files (`sql/*.sql`) — no ORM, no query built programmatically.
2. Computes descriptive statistics: distributions by phase / status /
   sponsor type, the enrollment-size distribution (mean, median, IQR,
   skewness), registration trends over time, and top conditions studied.
3. Runs exactly three hypothesis tests to answer specific questions about
   how phase, sponsor type, and enrollment relate to completion outcomes —
   each with H0/H1, an assumption check that determines which test is
   actually used, the test statistic, p-value, an effect size, and a
   plain-language interpretation.
4. Displays all of the above in a two-tab Streamlit dashboard that reads
   only pre-computed, saved results (it does not recompute anything live).

## Data source

**AACT** (Aggregate Analysis of ClinicalTrials.gov) — a public, freely
downloadable relational database maintained by the Clinical Trials
Transformation Initiative (CTTI) at Duke University
(`https://aact.ctti-clinicaltrials.org/`), containing structured data from
every study registered on ClinicalTrials.gov. No credentialing is required.

**This build ships with a synthetic, local stand-in for AACT** so the
project runs without a multi-gigabyte external download: `src/generate_sample_aact.py`
creates a local Postgres schema literally named `ctgov` (AACT's own schema
name) with a subset of the real `studies`, `sponsors`, and `conditions`
tables — same table and column names — filled with synthetically generated
data whose distributions resemble the real registry (right-skewed
enrollment, realistic phase/status/sponsor mixes, modest and realistic
relationships between phase/sponsor type and outcomes). Every `.sql` file in
`sql/` is written against the real AACT column names, so **pointing this
project at a real AACT restore instead requires changing only the
connection settings in `src/db.py`** — see "Switching to the real AACT
database" below. Full reasoning in `docs/methodology.md`.

## Repository structure

```
TrialScope/
├── README.md
├── requirements.txt
├── sql/
│   ├── extract_studies.sql
│   ├── extract_sponsors.sql
│   └── extract_conditions.sql
├── notebooks/
│   ├── 01_data_extraction.ipynb
│   ├── 02_descriptive_statistics.ipynb
│   └── 03_group_comparisons.ipynb
├── src/
│   ├── db.py                    # raw psycopg2 connection + .sql file runner (no ORM)
│   ├── generate_sample_aact.py  # builds the local synthetic ctgov schema
│   ├── run_extraction.py        # Step 1: runs sql/*.sql, joins, computes duration_days
│   ├── run_descriptive_stats.py # Step 2: descriptive stats -> results/descriptive/
│   ├── run_hypothesis_tests.py  # Step 3: hypothesis tests -> results/
│   └── stats_utils.py           # descriptive-stat and hypothesis-test functions
├── data/
│   └── processed/               # extracted + joined CSVs (created by running the pipeline)
├── results/                     # saved artifacts the dashboard reads (created by the pipeline)
├── app/
│   └── streamlit_app.py         # the dashboard
└── docs/
    └── methodology.md           # every scope/filtering/join decision, and why
```

## How to run

Requires Python 3.10+ and a local PostgreSQL 14+ server.

```bash
pip install -r requirements.txt

# 1. Create a database + role (only needed once; matches src/db.py defaults)
sudo -u postgres psql -c "CREATE USER trialscope WITH PASSWORD 'trialscope';"
sudo -u postgres psql -c "CREATE DATABASE aact OWNER trialscope;"

# 2. Build the local synthetic ctgov schema (skip this step entirely if you
#    are pointing at a real AACT restore instead -- see below)
python -m src.generate_sample_aact

# 3. Run the pipeline: SQL extraction -> descriptive stats -> hypothesis tests
python -m src.run_extraction
python -m src.run_descriptive_stats
python -m src.run_hypothesis_tests

# 4. Launch the dashboard
streamlit run app/streamlit_app.py
```

Or open the notebooks in `notebooks/` (already executed, with output saved)
to walk through the same three steps interactively.

### Switching to the real AACT database

1. Download a monthly AACT PostgreSQL dump from
   `https://aact.ctti-clinicaltrials.org/` (or use CTTI's hosted read-only
   instance — confirm the current access method on their site) and restore
   it locally. Real AACT uses the schema name `ctgov`, exactly like this
   build's synthetic stand-in.
2. Skip `python -m src.generate_sample_aact` — the real restore already has
   the `ctgov.studies`, `ctgov.sponsors`, and `ctgov.conditions` tables (with
   many more columns than this project uses; the SQL below only selects the
   ones it needs).
3. Point `src/db.py` at the real database by setting environment variables
   (`TRIALSCOPE_DB_HOST`, `TRIALSCOPE_DB_PORT`, `TRIALSCOPE_DB_NAME`,
   `TRIALSCOPE_DB_USER`, `TRIALSCOPE_DB_PASSWORD`) instead of editing code.
4. Run steps 3–4 above unchanged.

## Hard constraints (by design, not by omission)

- **No machine learning of any kind.** The roadmap PDF lists a logistic
  regression on completion status as an *optional stretch goal*; it is
  intentionally **not implemented** here, because the build prompt's hard
  constraints ("no ML of any kind... even as an optional bonus") take
  priority over the roadmap.
- **No agentic AI, no LLM calls, no RAG, no chatbot interface.**
- **No ORM.** `src/db.py` is a thin `psycopg2` connection helper; every
  query is a hand-written `.sql` file.
- **No statistics beyond what's listed in scope** — no multivariate
  regression, survival analysis, Bayesian methods, or ML-based imputation.

## The three hypothesis tests, and their results on this build's dataset

Numbers below are from this build's synthetic dataset (9,000 interventional
trials, 2011–2025) and will differ slightly if you regenerate it with a
different seed, or replace it with a real AACT restore — that's expected;
what should stay constant is the reasoning behind each test choice.

**1. Chi-square test of independence — trial phase vs. completion status**
H0: phase and completion status are independent. Result: chi2 = 270.3,
p < 0.0001, Cramér's V = 0.10 (a *statistically* significant but
*practically weak* association — phase shifts the completion-status mix
somewhat, but far from determines it).

**2. Kruskal-Wallis test — sponsor type vs. enrollment size**
H0: central enrollment is equal across Industry / NIH / Other sponsors.
Enrollment failed a Shapiro-Wilk normality check in every group (expected —
it's right-skewed), so Kruskal-Wallis was used instead of one-way ANOVA.
Result: H = 381.3, p < 0.0001, epsilon-squared = 0.042 (small effect).
Median enrollment: Industry 88, NIH 63, Other 52 — industry-sponsored
trials tend to enroll somewhat more participants.

**3. Mann-Whitney U test — trial duration, Completed vs. Terminated/Withdrawn**
H0: duration is equal between the two groups. Duration failed Shapiro-Wilk
in both groups (expected — it's modeled as right-skewed), so Mann-Whitney U
was used instead of a t-test. Result: p < 0.0001, rank-biserial correlation
= -0.83 (a large effect) — Completed trials run substantially longer on
average than Terminated/Withdrawn trials, which is intuitive: a trial that
gets stopped early is, definitionally, cut short.

For every test's exact H0/H1 wording, assumption-check note, and full
interpretation sentence, see the "Group Comparisons" tab of the dashboard
or `results/hypothesis_tests.csv`.

## How to read a p-value / effect size

A p-value is the probability of seeing a difference at least this large *if
the null hypothesis were true* — it is not the probability H0 is true, and
it says nothing about how large or important the effect is. An effect size
(Cramér's V, eta-/epsilon-squared, Cohen's d, or rank-biserial correlation,
depending on the test) measures how large the relationship actually is,
independent of sample size. With thousands of trials, almost any real
difference becomes "statistically significant" — the effect size is what
tells you whether it's also big enough to matter. This note also appears in
the dashboard's "How to Read This" tab.

## Technical stack

| Layer | Tools |
|---|---|
| Database | PostgreSQL (AACT schema; synthetic local stand-in included) |
| Query layer | Raw SQL via `psycopg2` (no ORM) |
| Statistics | SciPy |
| Visualization | Plotly (bar, line, box plots only) |
| Application | Streamlit |
| Language | Python, SQL |
