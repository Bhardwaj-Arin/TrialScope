"""
generate_sample_aact.py
------------------------
TrialScope is designed to run against the real AACT (Aggregate Analysis of
ClinicalTrials.gov) PostgreSQL database. AACT is distributed as a large
monthly database dump that must be downloaded from https://aact.ctti-clinicaltrials.org/
and restored locally, or reached through CTTI's hosted read-only Postgres
instance -- both require an external download/registration step that an
offline build environment cannot perform.

To keep the rest of the project (SQL extraction -> descriptive stats ->
hypothesis tests -> dashboard) fully runnable end-to-end without that
external dependency, this script creates a local Postgres schema named
`ctgov` -- the same schema name AACT itself uses -- containing a *subset* of
three real AACT tables (studies, sponsors, conditions) with the same table
and column names the real database uses. It then fills those tables with
synthetically generated data whose distributions are deliberately built to
resemble the real registry (right-skewed enrollment, realistic phase/status
mixes, and modest, realistic relationships between phase/sponsor type and
outcomes).

WHY THIS MATTERS FOR THE INTERVIEW DEFENSE: every SQL query in sql/*.sql is
written against the real AACT column names, so pointing this project at a
real AACT restore instead requires changing nothing but the connection
string in src/db.py (see README "Switching to the real AACT database").
None of the statistics or SQL logic depends on this file -- it only exists
to make the project runnable without a multi-GB external download.

Run directly: `python -m src.generate_sample_aact`
"""

import datetime as dt
import random

import numpy as np
import psycopg2
import psycopg2.extras

from src.db import get_connection

RNG_SEED = 42
N_STUDIES = 9000

# Scope decision (documented again in docs/methodology.md): we only ever
# generate/keep interventional studies starting in the last 15 years, which
# mirrors the scope filter the extraction SQL applies.
START_DATE_FLOOR = dt.date(2011, 1, 1)
START_DATE_CEIL = dt.date(2025, 12, 31)

PHASES = ["Phase 1", "Phase 2", "Phase 3", "Phase 4"]
# Base phase mix roughly reflects ClinicalTrials.gov reality: most
# interventional trials are early/mid phase, Phase 4 is the smallest slice.
PHASE_WEIGHTS = [0.28, 0.34, 0.24, 0.14]

SPONSOR_TYPES = ["Industry", "NIH", "Other"]
SPONSOR_WEIGHTS = [0.55, 0.07, 0.38]

STATUSES = [
    "Completed",
    "Terminated",
    "Withdrawn",
    "Recruiting",
    "Active, not recruiting",
    "Unknown status",
]

CONDITIONS = [
    "Breast Cancer", "Type 2 Diabetes Mellitus", "Hypertension",
    "Major Depressive Disorder", "Rheumatoid Arthritis", "Asthma",
    "Chronic Obstructive Pulmonary Disease", "Alzheimer's Disease",
    "Non-Small Cell Lung Cancer", "Coronary Artery Disease",
    "Multiple Sclerosis", "Psoriasis", "Chronic Kidney Disease",
    "Obesity", "HIV Infections", "Parkinson's Disease",
    "Ulcerative Colitis", "Migraine", "Osteoarthritis", "Schizophrenia",
]


def _status_probs(phase: str, sponsor: str) -> list[float]:
    """
    Documented modeling choice: completion likelihood is nudged up for
    later phases and for industry-sponsored trials, and down for Phase 1 /
    NIH-sponsored trials -- consistent with the *direction* of real-world
    AACT patterns (later-phase and industry trials are somewhat more likely
    to reach "Completed" and less likely to be "Terminated"/"Withdrawn").
    Magnitudes are chosen to produce a realistic, moderate effect, not an
    artificially huge one, so the chi-square result reads like a real
    finding rather than a planted one.
    """
    base = {
        "Completed": 0.52, "Terminated": 0.11, "Withdrawn": 0.05,
        "Recruiting": 0.14, "Active, not recruiting": 0.10, "Unknown status": 0.08,
    }
    phase_bump = {"Phase 1": -0.10, "Phase 2": -0.03, "Phase 3": 0.05, "Phase 4": 0.09}[phase]
    sponsor_bump = {"Industry": 0.05, "NIH": -0.03, "Other": -0.02}[sponsor]
    completed = max(0.05, base["Completed"] + phase_bump + sponsor_bump)
    terminated = max(0.02, base["Terminated"] - phase_bump * 0.6 - sponsor_bump * 0.6)
    remainder_keys = ["Withdrawn", "Recruiting", "Active, not recruiting", "Unknown status"]
    used = completed + terminated
    remainder_total = max(0.05, 1 - used)
    remainder_weights = np.array([base[k] for k in remainder_keys])
    remainder_weights = remainder_weights / remainder_weights.sum() * remainder_total
    probs = [completed, terminated] + list(remainder_weights)
    probs = np.array(probs)
    probs = probs / probs.sum()
    return list(probs)


def _enrollment_for(sponsor: str, rng: np.random.Generator) -> int:
    """
    Enrollment is modeled as log-normal (documented in methodology.md as the
    reason median/IQR are reported alongside the mean -- the distribution is
    heavily right-skewed). Industry-sponsored trials get a modestly larger
    scale parameter than NIH/Other, which is the relationship the sponsor
    type vs. enrollment hypothesis test is checking for.
    """
    mu, sigma = {
        "Industry": (4.5, 1.15),
        "NIH": (4.1, 1.35),
        "Other": (4.0, 1.25),
    }[sponsor]
    val = rng.lognormal(mean=mu, sigma=sigma)
    return int(np.clip(val, 5, 20000))


def _duration_days_for(status: str, phase: str, rng: np.random.Generator) -> int:
    """
    Completed trials run a realistic full course; terminated/withdrawn
    trials are modeled as generally shorter (stopped early), which is the
    relationship the duration hypothesis test is checking for. Duration is
    also nudged upward for later phases (larger, longer trials), mirroring
    real-world patterns.
    """
    phase_shift = {"Phase 1": 0, "Phase 2": 60, "Phase 3": 150, "Phase 4": 90}[phase]
    if status == "Completed":
        base = rng.gamma(shape=4.0, scale=140) + 250 + phase_shift
    else:  # Terminated / Withdrawn
        base = rng.gamma(shape=2.2, scale=110) + 90 + phase_shift * 0.5
    return int(np.clip(base, 10, 3650))


def generate_rows(seed: int = RNG_SEED, n: int = N_STUDIES):
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)

    studies, sponsors, conditions = [], [], []
    span_days = (START_DATE_CEIL - START_DATE_FLOOR).days

    for i in range(n):
        nct_id = f"NCT{100000000 + i}"
        phase = py_rng.choices(PHASES, weights=PHASE_WEIGHTS, k=1)[0]
        sponsor_type = py_rng.choices(SPONSOR_TYPES, weights=SPONSOR_WEIGHTS, k=1)[0]

        status_probs = _status_probs(phase, sponsor_type)
        status = py_rng.choices(STATUSES, weights=status_probs, k=1)[0]

        start_offset = int(rng.uniform(0, span_days))
        start_date = START_DATE_FLOOR + dt.timedelta(days=start_offset)

        enrollment = _enrollment_for(sponsor_type, rng)

        completion_date = None
        if status in ("Completed", "Terminated", "Withdrawn"):
            dur = _duration_days_for(status, phase, rng)
            completion_date = start_date + dt.timedelta(days=dur)
            if completion_date > START_DATE_CEIL + dt.timedelta(days=365):
                completion_date = min(completion_date, START_DATE_CEIL)
        # Recruiting / Active / Unknown status trials are genuinely ongoing
        # in this synthetic snapshot -> completion_date stays NULL, exactly
        # as it would for a live AACT snapshot. These rows are intentionally
        # kept (not dropped) so downstream code must explicitly decide how
        # to handle them, per the roadmap's requirement to document this.

        studies.append((
            nct_id, "Interventional", phase, status, enrollment,
            start_date, completion_date,
        ))

        sponsor_name = f"{sponsor_type} Sponsor #{py_rng.randint(1, 400)}"
        sponsors.append((nct_id, sponsor_type, "lead", sponsor_name))

        n_conditions = py_rng.choices([1, 2, 3], weights=[0.6, 0.3, 0.1], k=1)[0]
        chosen = py_rng.sample(CONDITIONS, k=n_conditions)
        for order, cond_name in enumerate(chosen):
            conditions.append((nct_id, cond_name, order))

    return studies, sponsors, conditions


DDL = """
CREATE SCHEMA IF NOT EXISTS ctgov;

DROP TABLE IF EXISTS ctgov.conditions;
DROP TABLE IF EXISTS ctgov.sponsors;
DROP TABLE IF EXISTS ctgov.studies;

-- Subset of the real AACT `studies` table (same table/column names).
CREATE TABLE ctgov.studies (
    nct_id           TEXT PRIMARY KEY,
    study_type       TEXT,
    phase            TEXT,
    overall_status   TEXT,
    enrollment       INTEGER,
    start_date       DATE,
    completion_date  DATE
);

-- Subset of the real AACT `sponsors` table.
CREATE TABLE ctgov.sponsors (
    nct_id              TEXT REFERENCES ctgov.studies(nct_id),
    agency_class        TEXT,
    lead_or_collaborator TEXT,
    name                TEXT
);

-- Subset of the real AACT `conditions` table (one-to-many per study).
CREATE TABLE ctgov.conditions (
    nct_id       TEXT REFERENCES ctgov.studies(nct_id),
    name         TEXT,
    condition_order INTEGER
);

CREATE INDEX idx_sponsors_nct ON ctgov.sponsors(nct_id);
CREATE INDEX idx_conditions_nct ON ctgov.conditions(nct_id);
"""


def main():
    studies, sponsors, conditions = generate_rows()

    conn = get_connection()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO ctgov.studies (nct_id, study_type, phase, overall_status, "
                "enrollment, start_date, completion_date) VALUES %s",
                studies,
            )
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO ctgov.sponsors (nct_id, agency_class, lead_or_collaborator, name) "
                "VALUES %s",
                sponsors,
            )
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO ctgov.conditions (nct_id, name, condition_order) VALUES %s",
                conditions,
            )
        conn.commit()
        print(f"Loaded {len(studies)} studies, {len(sponsors)} sponsor rows, "
              f"{len(conditions)} condition rows into ctgov schema.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
