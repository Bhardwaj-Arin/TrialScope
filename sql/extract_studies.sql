-- extract_studies.sql
--
-- Pulls one row per study with the fields needed for every downstream
-- analysis: phase, status, enrollment, and the two dates used to compute
-- trial duration.
--
-- WHY the WHERE filters (documented again in docs/methodology.md):
--   * study_type = 'Interventional' -- observational studies aren't
--     designed/phased the same way, so mixing them in would make the
--     phase-based comparisons meaningless. This keeps the analysis focused
--     on trials that actually test an intervention.
--   * start_date between 2011-01-01 and 2025-12-31 -- a fixed, clearly
--     stated 15-year window keeps the dataset a manageable size and avoids
--     diluting the "current landscape" trend charts with very old trials
--     that used different registration practices.
--   * phase IN (...) -- we keep exactly the four phases the roadmap asks
--     us to compare (Phase 1-4) and drop "Not Applicable"/NULL phase
--     studies (e.g. device or behavioral trials without an FDA phase),
--     because they can't be placed on the phase axis this analysis compares.
--
-- duration_days is intentionally NOT computed here in SQL (it depends on a
-- policy decision -- what to do when completion_date is NULL for an
-- ongoing trial -- that we want visible and explained in Python, not
-- silently buried in a CASE expression). See src/run_descriptive_stats.py.

SELECT
    nct_id,
    study_type,
    phase,
    overall_status,
    enrollment,
    start_date,
    completion_date
FROM ctgov.studies
WHERE study_type = 'Interventional'
  AND phase IN ('Phase 1', 'Phase 2', 'Phase 3', 'Phase 4')
  AND start_date BETWEEN DATE '2011-01-01' AND DATE '2025-12-31'
ORDER BY nct_id;
