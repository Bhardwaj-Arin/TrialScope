# TrialScope — Methodology

This document records every scope, filtering, and join decision made in the
pipeline, and why, so the project can be defended from first principles
rather than treated as a black box. Each decision is also commented at the
point it's made in the code (`sql/*.sql`, `src/run_extraction.py`,
`src/stats_utils.py`) — this file collects them in one place.

## 1. Data source

The project is built to run against **AACT** (Aggregate Analysis of
ClinicalTrials.gov), a public, freely downloadable PostgreSQL database
maintained by CTTI at Duke University, containing structured data from
every study registered on ClinicalTrials.gov. No credentialing is required.

**Offline-build substitution.** Restoring a real AACT dump requires
downloading a multi-gigabyte monthly snapshot from
`https://aact.ctti-clinicaltrials.org/`, an external step this build
environment cannot perform. So that the rest of the project — SQL
extraction, descriptive statistics, hypothesis tests, and the dashboard —
is still fully runnable end-to-end, `src/generate_sample_aact.py` creates a
local Postgres schema named `ctgov` (the same schema name AACT itself uses)
containing a **subset of three real AACT tables** (`studies`, `sponsors`,
`conditions`) with the same table and column names, and fills them with
**synthetically generated data** whose distributions are deliberately built
to resemble the real registry:

- Enrollment is log-normal (heavily right-skewed), with a modestly larger
  scale for industry-sponsored trials.
- Phase mix, sponsor-type mix, and status mix roughly match real-world
  ClinicalTrials.gov proportions.
- Completion likelihood is nudged upward for later phases and
  industry sponsors; trial duration is modeled as generally longer for
  Completed trials than for Terminated/Withdrawn trials.

These relationships are intentionally modest, not planted to guarantee a
"clean" result — the point is a realistic, defensible dataset, not a rigged
one. **Every `.sql` query in `sql/` is written against real AACT column
names**, so pointing the project at a real AACT restore instead requires
changing only the connection settings in `src/db.py` — see the README
section "Switching to the real AACT database." No statistical or SQL logic
in this project depends on the synthetic generator.

## 2. Scope filter: interventional studies, 2011–2025

Every extraction query filters to `study_type = 'Interventional'` and
`start_date` between 2011-01-01 and 2025-12-31.

- **Interventional only**: observational studies aren't designed or phased
  the same way as interventional trials, so mixing them in would make every
  phase-based comparison meaningless.
- **A fixed 15-year window**: keeps the dataset a manageable, explicitly
  stated size, and avoids diluting the "current landscape" trend charts
  with very old trials that used different registration practices.
- **`phase IN ('Phase 1','Phase 2','Phase 3','Phase 4')`**: studies with no
  FDA phase (e.g. many device or behavioral trials, coded "Not Applicable"
  or NULL in real AACT) are dropped, because they can't be placed on the
  phase axis every phase-based comparison in this project uses.

## 3. Sponsor join: lead sponsor only

A study in AACT's `sponsors` table can have many rows: one lead sponsor
plus any number of collaborators. `extract_sponsors.sql` filters to
`lead_or_collaborator = 'lead'`, guaranteeing exactly one sponsor row per
study.

**Why this matters:** joining in every sponsor row (lead + collaborators)
would let a study with, say, 5 collaborators be counted 5 times in every
downstream `GROUP BY` — silently inflating trial counts and biasing the
sponsor-type-vs-enrollment comparison toward whichever sponsor type tends
to collaborate more often. Lead-sponsor-only avoids that duplication.
The join is an `INNER JOIN`, which makes "a study with no usable lead
sponsor row is excluded from this extraction" explicit in the query itself,
rather than an unexplained `dropna()` downstream.

## 4. Condition join: primary condition only, not exploded

A study can list several conditions. `extract_conditions.sql` keeps exactly
**one condition per study** — the first one AACT lists (`condition_order =
0`), found via `MIN(condition_order)` per study rather than a window
function, to stay within this project's stated SQL scope (`SELECT`, `JOIN`,
`WHERE`, `GROUP BY`, basic aggregates only).

**Why not explode to one row per condition:** doing so would let a single
study count toward multiple rows in the "top conditions studied" chart, and
would duplicate that study's enrollment/phase/status in any `GROUP BY` that
joins conditions in — the same double-counting risk avoided in the sponsor
join. Keeping one condition per study trades a small amount of information
(a study's secondary conditions aren't reflected anywhere) for a dataset
where "number of trials" always means what it says.

## 5. Duration and ongoing trials

`duration_days = completion_date - start_date`, computed in pandas (not
SQL) so the handling of missing dates is visible in code rather than buried
in a `CASE` expression.

A trial still `Recruiting` / `Active, not recruiting` / `Unknown status`
has no `completion_date` yet — that is not missing data, it is a trial that
has not finished. These rows are **kept** in the dataset for every other
analysis (phase mix, status mix, enrollment distribution, the chi-square
test) and are excluded **only** from `duration_days`-based statistics (the
duration descriptive stats and the third hypothesis test). The extraction
step reports exactly how many rows this affects (roughly 30% of the
dataset in this synthetic build, since about 30% of trials in any live
registry snapshot are still ongoing) — see `data/processed/extraction_log.txt`
after running the pipeline.

## 6. Statistical test selection

For each comparison, an assumption check decides which test is used, and
the choice is recorded in the result's `assumption_note` field (shown in
the dashboard):

1. **Phase vs. completion status** — categorical × categorical → chi-square
   test of independence. Assumption: every expected cell count should be
   ≥ 5. Checked directly against the contingency table's expected-count
   matrix; if violated, the note recommends Fisher's exact test instead
   (not implemented here, since our sample size comfortably satisfies the
   assumption).
2. **Sponsor type vs. enrollment** — continuous outcome across 3 groups →
   ANOVA if each group passes a Shapiro-Wilk normality check, Kruskal-Wallis
   otherwise. Enrollment is right-skewed by construction, so Kruskal-Wallis
   is expected to be selected — and it was, on this run.
3. **Duration, Completed vs. Terminated/Withdrawn** — continuous outcome
   across 2 groups → independent (Welch) t-test if both groups pass
   Shapiro-Wilk, Mann-Whitney U otherwise. Duration is modeled as skewed
   (gamma-distributed), so Mann-Whitney U is expected to be selected — and
   it was, on this run.

No test's assumption check is skipped or assumed to pass "because the
sample is large" — each one is actually computed and reported.

## 7. What is intentionally NOT in this project

Per the build prompt's hard constraints, and re-stated here for clarity:

- **No machine learning of any kind** — no logistic regression, no
  classification, no model-fitting step of any kind, even though the
  roadmap PDF lists a logistic-regression odds-ratio model as an *optional
  stretch goal*. The build prompt's constraints take priority over the
  roadmap and explicitly rule this out.
- **No agentic AI, no LLM calls, no RAG, no chatbot interface.**
- **No statistical techniques beyond what's listed as in-scope** — no
  multivariate regression, no survival analysis, no Bayesian methods, no
  ML-based imputation.
- **No ORM** — `src/db.py` uses raw `psycopg2` plus `pandas.read_sql_query`
  against hand-written `.sql` files; nothing builds a query
  programmatically.

## 8. Data-quality caveats

- The synthetic dataset (see §1) is a stand-in for a real AACT restore. Its
  relationships are realistic in direction but were not fit to match any
  specific published statistic about ClinicalTrials.gov as a whole — treat
  the specific numbers as illustrative of the method, not as a claim about
  the real registry.
- Sponsor type is simplified to three categories (Industry / NIH / Other);
  real AACT's `agency_class` has more granular values (e.g. "U.S. Fed",
  "Other Gov", "Network").
- A study's secondary conditions are not reflected anywhere in this
  analysis (see §4).
