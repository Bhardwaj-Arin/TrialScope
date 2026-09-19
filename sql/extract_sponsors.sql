-- extract_sponsors.sql
--
-- Joins each study to its LEAD sponsor only.
--
-- WHY lead-sponsor-only (documented again in docs/methodology.md): a study
-- in AACT's sponsors table can have many rows -- one lead sponsor plus any
-- number of collaborators. If we joined in every sponsor row, a study with
-- 5 collaborators would be counted 5 times in every downstream GROUP BY,
-- silently inflating trial counts and biasing the sponsor-type vs.
-- enrollment comparison toward whichever sponsor type tends to collaborate
-- more. Filtering to lead_or_collaborator = 'lead' guarantees exactly one
-- sponsor row per nct_id, so the join cannot duplicate studies.
--
-- WHY INNER JOIN: a study with no sponsor row at all would be unusable for
-- the sponsor-type comparison anyway, so an inner join (rather than LEFT
-- JOIN) is both correct and self-documenting -- it makes "studies without a
-- usable lead sponsor are excluded from this extraction" explicit in the
-- query itself instead of a downstream dropna() with no explanation.

SELECT
    s.nct_id,
    sp.agency_class AS sponsor_type,
    sp.name         AS sponsor_name
FROM ctgov.studies s
INNER JOIN ctgov.sponsors sp
    ON s.nct_id = sp.nct_id
   AND sp.lead_or_collaborator = 'lead'
WHERE s.study_type = 'Interventional'
  AND s.phase IN ('Phase 1', 'Phase 2', 'Phase 3', 'Phase 4')
  AND s.start_date BETWEEN DATE '2011-01-01' AND DATE '2025-12-31'
ORDER BY s.nct_id;
