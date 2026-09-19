# TrialScope

**A no-nonsense look at 9,000 clinical trials: which ones finish, which ones
stop early, and what actually explains the difference.**

🔗 **Live app:** [trialscope-bmdqtoqvdfsjcs469nc9zh.streamlit.app](https://trialscope-bmdqtoqvdfsjcs469nc9zh.streamlit.app/)

---

## What is TrialScope, in plain English?

Every clinical trial that runs anywhere in the world gets registered on
[ClinicalTrials.gov](https://clinicaltrials.gov), a public database. That
registry records things like: what phase the trial is in, who's paying for
it, how many patients it enrolled, and whether it finished, is still
running, or was stopped early.

**TrialScope takes that raw registry data and asks three honest,
answerable questions about it:**

1. Does a trial's **phase** (1 through 4) have anything to do with whether
   it **completes, gets terminated, or gets withdrawn**?
2. Do **industry-funded**, **government (NIH)-funded**, and
   **other-funded** trials tend to **enroll different numbers of
   patients**?
3. Do trials that **finish** as planned run for a **different length of
   time** than trials that get **stopped early**?

Each question is answered with a standard, well-known statistical test —
not a guess, not a machine-learning model, not an AI's opinion. Every
result comes with the actual numbers (test statistic, p-value, effect
size) and a plain-language sentence explaining what it means, so you don't
need a statistics degree to read the conclusion — but the real math is
always there if you want to check it yourself.

You can explore all of this interactively in the **[live Streamlit
app](https://trialscope-bmdqtoqvdfsjcs469nc9zh.streamlit.app/)**, or run
the whole pipeline yourself locally (instructions below).

### What TrialScope deliberately is *not*

To keep every result fully explainable, this project does **not** use:

- ❌ Machine learning or predictive modeling of any kind
- ❌ AI agents, LLMs, chatbots, or generative text
- ❌ An ORM — every database query is a hand-written SQL file you can read
  top to bottom
- ❌ Any statistical method beyond a handful of textbook tests

If a number appears in this app, you can trace it back to one SQL query
and one SciPy function call. Nothing is a black box.

---

## How the project fits together

```
   PostgreSQL database          Hand-written SQL          Python
  (clinical trial records)  →   (sql/*.sql files)    →   (pandas, SciPy)
                                                              │
                                                              ▼
                                              Descriptive statistics
                                              + 3 hypothesis tests
                                                              │
                                                              ▼
                                                 Streamlit dashboard
                                            (reads saved results only)
```

The dashboard **never talks to the database directly and never runs a
statistical test itself** — it only displays results that were already
computed and saved to disk by the pipeline. This keeps the dashboard fast
and keeps every number reproducible: run the pipeline once, and the
dashboard will show exactly the same figures every time until you re-run
it.

---

## Exploring the app

The live app is organized into four pages, accessible from the sidebar:

| Page | What you'll find there |
|---|---|
| 🏠 **Home** | Headline numbers (total trials, completion rate, typical enrollment/duration) and quick-glance charts, so you can get the gist in ten seconds. |
| 📊 **Descriptive Statistics** | How trials break down by phase, status, sponsor type, and condition; registration trends over time; the shape of the enrollment-size data (and why the "average" trial size can be misleading). |
| 🧮 **Group Comparisons** | The three hypothesis tests described above — each with its hypothesis, the test actually used (and why), the result, and what it means in plain language. |
| 🔎 **Trial Explorer** | Search and filter all 9,000 trials yourself — by phase, status, sponsor, condition, enrollment size, or date — and export whatever you filter down to as a CSV. |

Every chart is a bar, line, or box plot — deliberately simple, readable
chart types, with nothing 3D or animated to distract from the numbers.

---

## Where the data comes from

TrialScope is built on the schema used by **AACT** (*Aggregate Analysis of
ClinicalTrials.gov*) — a free, public, relational database maintained by
the Clinical Trials Transformation Initiative (CTTI) at Duke University
(<https://aact.ctti-clinicaltrials.org/>). AACT mirrors every study
registered on ClinicalTrials.gov and requires no special access or
credentialing.

**This build ships with a realistic synthetic stand-in for AACT**, so
anyone can run it without downloading a multi-gigabyte external database.
`src/generate_sample_aact.py` creates a local Postgres schema — using
AACT's own schema and table names (`ctgov.studies`, `ctgov.sponsors`,
`ctgov.conditions`) — filled with generated data whose statistical
properties mirror the real registry: right-skewed enrollment sizes,
realistic phase/status/sponsor mixes, and modest, realistic relationships
between phase, sponsor type, and outcomes.

Because every SQL file is written against AACT's real column names,
**pointing this project at an actual AACT database instead only requires
changing the connection settings** — no query needs to be rewritten. See
[Using a real AACT database](#using-a-real-aact-database-instead-of-the-synthetic-one)
below. The full reasoning behind every data-scoping decision is documented
in [`docs/methodology.md`](docs/methodology.md).

---

## Repository structure

```
TrialScope/
├── README.md
├── requirements.txt
│
├── sql/                          # Hand-written SQL — no ORM, no query builder
│   ├── extract_studies.sql
│   ├── extract_sponsors.sql
│   └── extract_conditions.sql
│
├── src/                          # The pipeline: SQL → stats → saved results
│   ├── db.py                     #   raw psycopg2 connection + .sql file runner
│   ├── generate_sample_aact.py   #   builds the local synthetic database
│   ├── run_extraction.py         #   Step 1: runs sql/*.sql, joins, computes duration
│   ├── run_descriptive_stats.py  #   Step 2: descriptive stats → results/descriptive/
│   ├── run_hypothesis_tests.py   #   Step 3: the 3 hypothesis tests → results/
│   └── stats_utils.py            #   every statistical function, fully documented
│
├── data/processed/               # Extracted + joined CSVs (built by the pipeline)
├── results/                      # Saved numbers the dashboard reads
│   └── descriptive/
│
├── app/                          # The Streamlit dashboard
│   ├── streamlit_app.py          #   Home page
│   ├── pages/
│   │   ├── 1_Descriptive_Statistics.py
│   │   ├── 2_Group_Comparisons.py
│   │   └── 3_Trial_Explorer.py
│   └── components/               #   shared styling + cached data-loading helpers
│       ├── ui.py
│       └── data_access.py
│
├── notebooks/                    # The same 3 pipeline steps, walked through interactively
│   ├── 01_data_extraction.ipynb
│   ├── 02_descriptive_statistics.ipynb
│   └── 03_group_comparisons.ipynb
│
└── docs/
    └── methodology.md            # Every scope, filtering, and join decision, and why
```

---

## Running it yourself

**Requirements:** Python 3.10+ and a local PostgreSQL 14+ server.

```bash
pip install -r requirements.txt

# 1. Create a database + role (one-time setup; matches src/db.py defaults)
sudo -u postgres psql -c "CREATE USER trialscope WITH PASSWORD 'trialscope';"
sudo -u postgres psql -c "CREATE DATABASE aact OWNER trialscope;"

# 2. Build the local synthetic ctgov schema
#    (skip this step if you're using a real AACT restore instead — see below)
python -m src.generate_sample_aact

# 3. Run the pipeline: SQL extraction → descriptive stats → hypothesis tests
python -m src.run_extraction
python -m src.run_descriptive_stats
python -m src.run_hypothesis_tests

# 4. Launch the dashboard
streamlit run app/streamlit_app.py
```

Prefer to read through the analysis step by step instead? Open the
notebooks in `notebooks/` — they're already executed, with output saved,
so you can follow along without running anything.

### Using a real AACT database instead of the synthetic one

1. Download a monthly AACT PostgreSQL dump from
   <https://aact.ctti-clinicaltrials.org/> (or use CTTI's hosted read-only
   instance — check their site for the current access method) and restore
   it locally. Real AACT uses the schema name `ctgov`, exactly like this
   project's synthetic stand-in.
2. Skip `python -m src.generate_sample_aact` — a real restore already has
   the `ctgov.studies`, `ctgov.sponsors`, and `ctgov.conditions` tables
   (with many more columns than this project needs; the SQL files simply
   select the ones they use).
3. Point `src/db.py` at your real database using environment variables —
   `TRIALSCOPE_DB_HOST`, `TRIALSCOPE_DB_PORT`, `TRIALSCOPE_DB_NAME`,
   `TRIALSCOPE_DB_USER`, `TRIALSCOPE_DB_PASSWORD` — instead of editing any
   code.
4. Run steps 3–4 from above, unchanged.

---

## The three hypothesis tests, explained

> Numbers below are from this build's synthetic dataset (9,000
> interventional trials, 2011–2025). They'll shift slightly if you
> regenerate the data with a different random seed, or point the project
> at a real AACT restore — that's expected. What stays constant is *how*
> each test was chosen and *why*.

**1. Does trial phase relate to completion status?**
*Test used: Chi-square test of independence.*
Result: statistically significant (p < 0.0001), but the real-world
relationship is weak (Cramér's V = 0.10) — phase nudges the mix of
outcomes somewhat, but doesn't come close to determining it.

**2. Does sponsor type relate to enrollment size?**
*Test used: Kruskal-Wallis test* (enrollment data failed a normality
check in every group — expected, since it's right-skewed — so the
non-parametric alternative to ANOVA was used instead).
Result: statistically significant (p < 0.0001), small effect
(epsilon-squared = 0.042). Median enrollment: Industry 88, NIH 63,
Other 52 — industry-sponsored trials tend to enroll somewhat more
patients.

**3. Do completed trials run longer than trials stopped early?**
*Test used: Mann-Whitney U test* (again, non-parametric, because duration
also failed the normality check).
Result: statistically significant (p < 0.0001), and this time the effect
is large (rank-biserial correlation = -0.83) — completed trials run
substantially longer than terminated or withdrawn ones, which makes
intuitive sense: a trial that gets stopped early is, by definition, cut
short.

For each test's exact hypotheses (H0/H1), the assumption check that
determined which test to use, and the full interpretation, see the
**Group Comparisons** page in the app or `results/hypothesis_tests.csv`.

### A 30-second guide to reading these results

- **The p-value** answers *"could this pattern just be random chance?"*
  It is **not** the probability that the null hypothesis is true, and it
  says nothing about how big or important the effect is. With thousands of
  trials, even a tiny, practically meaningless difference can produce a
  very small p-value.
- **The effect size** (Cramér's V, epsilon-squared, or rank-biserial
  correlation, depending on the test) answers *"okay, but how big is the
  difference, really?"* — on a scale that doesn't grow just because the
  sample is large.

You need both numbers to tell the full story: the p-value tells you
whether a difference is probably real, and the effect size tells you
whether it's big enough to matter.

---

## Design principles (why some things are intentionally left out)

- **No machine learning, anywhere** — including as an "optional" addition.
  Every number in this project comes from a single, explainable, textbook
  statistical test.
- **No agentic AI, LLM calls, RAG, or chatbot interface.**
- **No ORM.** `src/db.py` is a thin `psycopg2` connection helper, and every
  query is a `.sql` file you can open and read directly.
- **No statistics beyond what's in scope** — no multivariate regression,
  survival analysis, Bayesian methods, or ML-based imputation.
- **Only bar, line, and box charts** — chosen for clarity over novelty.

---

## Technical stack

| Layer | Tools |
|---|---|
| Database | PostgreSQL (AACT schema; synthetic local stand-in included) |
| Query layer | Raw SQL via `psycopg2` — no ORM |
| Statistics | SciPy |
| Data handling | pandas |
| Visualization | Plotly (bar, line, and box plots only) |
| Application | Streamlit |
| Language | Python, SQL |