"""
stats_utils.py -- descriptive-statistics and hypothesis-testing helpers.

Every function here does exactly one textbook computation and returns plain
numbers/dicts. Nothing in this file is a machine-learning model, and none of
these functions fit or tune anything -- they run a single fixed statistical
test and hand back its result, per the project's "no ML" constraint.
"""

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats


# --------------------------------------------------------------------------
# Descriptive statistics
# --------------------------------------------------------------------------

def describe_numeric(series: pd.Series) -> dict:
    """
    Mean, median, std, IQR, and skewness for a numeric series.

    WHY report median + IQR alongside the mean: enrollment (and, to a lesser
    extent, duration) in real trial registries is heavily right-skewed --
    most trials are small, a handful are huge multi-site trials with
    thousands of participants. The mean gets pulled upward by that long
    tail, so on its own it overstates the "typical" trial size. The median
    describes the typical trial regardless of that tail, and skewness is
    reported explicitly so the write-up doesn't just assert skew, it shows
    the number that demonstrates it (skewness > 1 is conventionally
    considered highly skewed).
    """
    clean = series.dropna().astype(float)
    if len(clean) == 0:
        return {"n": 0}
    q1, q3 = np.percentile(clean, [25, 75])
    return {
        "n": int(len(clean)),
        "mean": float(clean.mean()),
        "median": float(clean.median()),
        "std": float(clean.std(ddof=1)) if len(clean) > 1 else float("nan"),
        "iqr": float(q3 - q1),
        "q1": float(q1),
        "q3": float(q3),
        "skewness": float(stats.skew(clean)),
        "min": float(clean.min()),
        "max": float(clean.max()),
    }


def frequency_table(series: pd.Series) -> pd.DataFrame:
    """Counts + proportions for a categorical series (e.g. phase, status)."""
    counts = series.value_counts(dropna=False)
    props = series.value_counts(normalize=True, dropna=False)
    out = pd.DataFrame({"count": counts, "proportion": props})
    out.index.name = series.name
    return out.reset_index()


# --------------------------------------------------------------------------
# Hypothesis test #1 -- chi-square test of independence
# Phase vs. completion status
# --------------------------------------------------------------------------

@dataclass
class TestResult:
    test_name: str
    h0: str
    h1: str
    statistic: float
    p_value: float
    effect_size_name: str
    effect_size: float
    n: int
    interpretation: str
    assumption_note: str

    def to_dict(self):
        return asdict(self)


def cramers_v(chi2_stat: float, n: int, table_shape: tuple[int, int]) -> float:
    """
    Cramer's V effect size for a chi-square test of independence.
    Formula: sqrt((chi2 / n) / min(rows-1, cols-1)).
    WHY report it: the chi-square p-value only tells us whether phase and
    completion status are related at all; with 9,000 studies even a tiny,
    practically meaningless association can be "statistically significant."
    Cramer's V (0 = no association, larger = stronger) tells us how strongly
    they're related, which is the number that actually matters for the
    plain-language interpretation.
    """
    r, c = table_shape
    denom = min(r - 1, c - 1)
    if denom <= 0:
        return float("nan")
    return float(np.sqrt((chi2_stat / n) / denom))


def test_phase_vs_completion(df: pd.DataFrame) -> tuple[TestResult, pd.DataFrame]:
    """
    Chi-square test of independence: is `phase` independent of
    `overall_status`?

    H0: trial phase and overall status are independent (the distribution of
        completion/termination/etc. is the same across phases).
    H1: they are not independent (completion-status mix differs by phase).

    Assumption check: chi-square requires expected cell counts of at least
    5 in (ideally) every cell of the contingency table. We check this and
    fall back to noting it explicitly rather than silently trusting the
    result if it's violated -- with 9,000 studies across 4 phases and 6
    statuses this comfortably passes, but the check is still run and
    reported so the choice is justified rather than assumed.
    """
    table = pd.crosstab(df["phase"], df["overall_status"])
    chi2, p, dof, expected = stats.chi2_contingency(table)
    min_expected = expected.min()
    assumption_note = (
        f"All expected cell counts >= 5 (minimum observed: {min_expected:.1f}), "
        "so the chi-square approximation is appropriate."
        if min_expected >= 5
        else
        f"WARNING: minimum expected cell count is {min_expected:.1f} (< 5); "
        "chi-square's approximation may be unreliable for this table and a "
        "Fisher's exact test would be preferred for the affected cells."
    )
    v = cramers_v(chi2, table.values.sum(), table.shape)

    strength = (
        "negligible" if v < 0.1 else
        "weak" if v < 0.2 else
        "moderate" if v < 0.3 else
        "strong"
    )
    interpretation = (
        f"Phase and completion status are {'statistically dependent' if p < 0.05 else 'not statistically distinguishable from independent'} "
        f"(chi2={chi2:.1f}, p={p:.4g}); the association is {strength} in practical "
        f"terms (Cramer's V={v:.3f}), meaning phase shifts the completion-status mix "
        f"somewhat but does not determine it."
    )

    result = TestResult(
        test_name="Chi-square test of independence: phase vs. overall_status",
        h0="Trial phase and overall completion status are statistically independent.",
        h1="Trial phase and overall completion status are associated.",
        statistic=float(chi2),
        p_value=float(p),
        effect_size_name="Cramer's V",
        effect_size=float(v),
        n=int(table.values.sum()),
        interpretation=interpretation,
        assumption_note=assumption_note,
    )
    return result, table


# --------------------------------------------------------------------------
# Hypothesis test #2 -- ANOVA / Kruskal-Wallis
# Sponsor type vs. enrollment size
# --------------------------------------------------------------------------

def eta_squared_from_kruskal(h_stat: float, n: int, k_groups: int) -> float:
    """
    Epsilon-squared (a small-sample-corrected rank-based effect size for
    Kruskal-Wallis, reported here under the "eta-squared or rank-based
    effect size" umbrella the roadmap asks for).
    Formula: (H - k + 1) / (n - k).
    """
    if n - k_groups <= 0:
        return float("nan")
    return float((h_stat - k_groups + 1) / (n - k_groups))


def one_way_anova_eta_squared(groups: list[np.ndarray], f_stat: float) -> float:
    """Classic eta-squared for one-way ANOVA: SS_between / SS_total."""
    all_vals = np.concatenate(groups)
    grand_mean = all_vals.mean()
    ss_total = np.sum((all_vals - grand_mean) ** 2)
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
    if ss_total == 0:
        return float("nan")
    return float(ss_between / ss_total)


def test_sponsor_vs_enrollment(df: pd.DataFrame) -> tuple[TestResult, pd.DataFrame]:
    """
    One-way comparison of enrollment across sponsor_type (Industry / NIH /
    Other).

    H0: mean (or, if non-parametric, mean rank of) enrollment is equal
        across all sponsor types.
    H1: at least one sponsor type differs.

    Assumption check: enrollment is expected to be right-skewed (see
    describe_numeric). We test each group for normality with Shapiro-Wilk
    (on a capped sample, since Shapiro-Wilk is sensitive/slow on very large
    n) -- if any group fails normality, we use Kruskal-Wallis (rank-based,
    no normality assumption) instead of ANOVA, and report which test was
    actually used and why.
    """
    clean = df.dropna(subset=["enrollment", "sponsor_type"])
    groups_dict = {
        name: g["enrollment"].astype(float).values
        for name, g in clean.groupby("sponsor_type")
        if len(g) >= 3
    }
    group_names = list(groups_dict.keys())
    groups = [groups_dict[name] for name in group_names]

    normal_flags = []
    for g in groups:
        sample = g if len(g) <= 5000 else np.random.default_rng(0).choice(g, 5000, replace=False)
        _, p_norm = stats.shapiro(sample)
        normal_flags.append(p_norm >= 0.05)
    all_normal = all(normal_flags)

    n_total = sum(len(g) for g in groups)

    if all_normal:
        stat, p = stats.f_oneway(*groups)
        test_used = "One-way ANOVA"
        effect_name = "eta-squared"
        effect = one_way_anova_eta_squared(groups, stat)
        assumption_note = (
            "Shapiro-Wilk did not reject normality for any sponsor-type group "
            "(p >= 0.05 in every group), so the ANOVA normality assumption is "
            "reasonably satisfied and ANOVA was used."
        )
    else:
        stat, p = stats.kruskal(*groups)
        test_used = "Kruskal-Wallis H-test"
        effect_name = "epsilon-squared (rank-based)"
        effect = eta_squared_from_kruskal(stat, n_total, len(groups))
        failed = [name for name, ok in zip(group_names, normal_flags) if not ok]
        assumption_note = (
            f"Shapiro-Wilk rejected normality (p < 0.05) for: {', '.join(failed)} -- "
            "expected, since enrollment is right-skewed (see descriptive stats). "
            "ANOVA's normality assumption is not met, so the non-parametric "
            "Kruskal-Wallis test was used instead."
        )

    strength = (
        "negligible" if abs(effect) < 0.01 else
        "small" if abs(effect) < 0.06 else
        "medium" if abs(effect) < 0.14 else
        "large"
    )
    medians = clean.groupby("sponsor_type")["enrollment"].median().to_dict()
    interpretation = (
        f"{test_used} finds enrollment size {'differs' if p < 0.05 else 'does not detectably differ'} "
        f"across sponsor types (statistic={stat:.2f}, p={p:.4g}); the effect size is "
        f"{strength} ({effect_name}={effect:.3f}). Median enrollment by sponsor type: "
        + ", ".join(f"{k}={v:.0f}" for k, v in medians.items()) + "."
    )

    result = TestResult(
        test_name=f"{test_used}: sponsor_type vs. enrollment",
        h0="Mean/central enrollment is equal across Industry, NIH, and Other-sponsored trials.",
        h1="Enrollment differs across at least one sponsor type.",
        statistic=float(stat),
        p_value=float(p),
        effect_size_name=effect_name,
        effect_size=float(effect),
        n=int(n_total),
        interpretation=interpretation,
        assumption_note=assumption_note,
    )
    group_summary = clean.groupby("sponsor_type")["enrollment"].agg(
        ["count", "mean", "median", "std"]
    ).reset_index()
    return result, group_summary


# --------------------------------------------------------------------------
# Hypothesis test #3 -- t-test / Mann-Whitney U
# Duration: completed vs. terminated/withdrawn
# --------------------------------------------------------------------------

def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d using pooled standard deviation."""
    na, nb = len(a), len(b)
    pooled_std = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    if pooled_std == 0:
        return float("nan")
    return float((a.mean() - b.mean()) / pooled_std)


def rank_biserial_from_mannwhitney(u_stat: float, n1: int, n2: int) -> float:
    """
    Rank-biserial correlation derived from the Mann-Whitney U statistic:
    r = 1 - (2U) / (n1 * n2). Ranges -1..1; sign indicates which group has
    the larger typical value.
    """
    return float(1 - (2 * u_stat) / (n1 * n2))


def test_duration_completed_vs_terminated(df: pd.DataFrame) -> tuple[TestResult, pd.DataFrame]:
    """
    Compares duration_days between Completed trials and
    Terminated/Withdrawn trials.

    H0: mean/typical duration is equal between Completed and
        Terminated-or-Withdrawn trials.
    H1: duration differs between the two groups.

    Rows with no duration_days (ongoing trials) are excluded here --
    exactly the exclusion documented and counted in run_extraction.py -- and
    nowhere else in the pipeline.

    Assumption check: Shapiro-Wilk on each group; if either group departs
    from normality, Mann-Whitney U (rank-based) is used instead of an
    independent t-test.
    """
    clean = df.dropna(subset=["duration_days"]).copy()
    clean = clean[clean["overall_status"].isin(["Completed", "Terminated", "Withdrawn"])]
    clean["group"] = np.where(clean["overall_status"] == "Completed", "Completed", "Terminated/Withdrawn")

    a = clean.loc[clean["group"] == "Completed", "duration_days"].astype(float).values
    b = clean.loc[clean["group"] == "Terminated/Withdrawn", "duration_days"].astype(float).values

    sample_a = a if len(a) <= 5000 else np.random.default_rng(0).choice(a, 5000, replace=False)
    sample_b = b if len(b) <= 5000 else np.random.default_rng(0).choice(b, 5000, replace=False)
    _, p_norm_a = stats.shapiro(sample_a)
    _, p_norm_b = stats.shapiro(sample_b)
    both_normal = (p_norm_a >= 0.05) and (p_norm_b >= 0.05)

    if both_normal:
        stat, p = stats.ttest_ind(a, b, equal_var=False)  # Welch's t-test: no equal-variance assumption needed
        test_used = "Independent t-test (Welch)"
        effect_name = "Cohen's d"
        effect = cohens_d(a, b)
        assumption_note = (
            "Shapiro-Wilk did not reject normality for either group (p >= 0.05), so "
            "an independent t-test was used; Welch's variant was used regardless so "
            "no equal-variance assumption is required either."
        )
    else:
        stat, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        test_used = "Mann-Whitney U test"
        effect_name = "rank-biserial correlation"
        effect = rank_biserial_from_mannwhitney(stat, len(a), len(b))
        assumption_note = (
            f"Shapiro-Wilk rejected normality for at least one group "
            f"(Completed p={p_norm_a:.3g}, Terminated/Withdrawn p={p_norm_b:.3g}), so the "
            "non-parametric Mann-Whitney U test was used instead of a t-test."
        )

    direction = "longer" if a.mean() > b.mean() else "shorter"
    interpretation = (
        f"{test_used} finds duration {'differs significantly' if p < 0.05 else 'does not differ significantly'} "
        f"between Completed and Terminated/Withdrawn trials (statistic={stat:.2f}, p={p:.4g}); "
        f"Completed trials run {direction} on average ({a.mean():.0f} vs {b.mean():.0f} median-adjacent days), "
        f"{effect_name}={effect:.3f}."
    )

    result = TestResult(
        test_name=f"{test_used}: duration_days, Completed vs. Terminated/Withdrawn",
        h0="Trial duration is equal between Completed and Terminated/Withdrawn trials.",
        h1="Trial duration differs between Completed and Terminated/Withdrawn trials.",
        statistic=float(stat),
        p_value=float(p),
        effect_size_name=effect_name,
        effect_size=float(effect),
        n=int(len(a) + len(b)),
        interpretation=interpretation,
        assumption_note=assumption_note,
    )
    group_summary = clean.groupby("group")["duration_days"].agg(
        ["count", "mean", "median", "std"]
    ).reset_index()
    return result, group_summary
