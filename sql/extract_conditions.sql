-- extract_conditions.sql
--
-- Joins each study to a single PRIMARY condition only.
--
-- WHY primary-condition-only, not exploded to multiple rows (documented
-- again in docs/methodology.md): a study can list several conditions (e.g.
-- "Type 2 Diabetes Mellitus" and "Obesity" on the same trial). Exploding to
-- one row per condition would let that single study count toward multiple
-- rows in the "top conditions studied" chart and would duplicate its
-- enrollment/phase/status in any GROUP BY that joins conditions in --
-- again risking silent double-counting, the same failure mode avoided in
-- extract_sponsors.sql. Keeping one condition per study (the first one
-- AACT lists, which is conventionally the primary condition) trades a
-- small amount of information loss for a dataset where "number of trials"
-- always means what it says.
--
-- HOW "first condition" is picked with only GROUP BY + aggregates (no
-- window functions, per this project's SQL scope): condition_order records
-- the order conditions were listed for a study (0 = first/primary), so the
-- inner query just finds MIN(condition_order) per study, and the outer
-- query joins back on that minimum to fetch the matching row.

SELECT
    s.nct_id,
    c.name AS primary_condition
FROM ctgov.studies s
INNER JOIN (
    SELECT nct_id, MIN(condition_order) AS min_order
    FROM ctgov.conditions
    GROUP BY nct_id
) first_cond
    ON s.nct_id = first_cond.nct_id
INNER JOIN ctgov.conditions c
    ON c.nct_id = first_cond.nct_id
   AND c.condition_order = first_cond.min_order
WHERE s.study_type = 'Interventional'
  AND s.phase IN ('Phase 1', 'Phase 2', 'Phase 3', 'Phase 4')
  AND s.start_date BETWEEN DATE '2011-01-01' AND DATE '2025-12-31'
ORDER BY s.nct_id;
